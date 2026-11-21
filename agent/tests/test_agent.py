import json

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent import api, cli, main
from agent.tools import claim_tools
from backend.main import app


class StubModel(GenericFakeChatModel):
    """Scripted model used instead of an external model provider."""

    def bind_tools(self, tools, **kwargs):
        return self


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERCOVER_DB", str(tmp_path / "agent.sqlite3"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with TestClient(app) as instance:
        with app.state.store.connect() as db:
            claim = app.state.store.claim(db, "CLM-1001")
            claim["story"] = "A synthetic covered delay with documented expenses."
            claim["documents"] = [
                {
                    "name": "Synthetic carrier report",
                    "type": "carrier_report",
                    "content": "A crew problem delayed departure by eight hours.",
                }
            ]
            db.execute(
                "UPDATE claims SET payload = ? WHERE claim_id = ?",
                (json.dumps(claim), "CLM-1001"),
            )
        monkeypatch.setattr(api, "backend", lambda: TestClient(app))
        yield instance


def scripted_model(outcome="approve", amount="420.00", pay=True):
    explanation = "The policy conditions are met. The costs are covered."
    section = "3. Trip Delay"
    if outcome == "refer":
        explanation = "The required receipt is missing. A handler must request it."
        section = "11. How to claim"
    actions = [("read_claim", {}), ("read_context", {}), ("read_policy_wording", {})]
    actions.append(
        (
            "record_decision",
            {
                "outcome": outcome,
                "amount": amount,
                "calculation": "Eligible costs: $420.",
                "explanation": explanation,
                "policy_section": section,
            },
        )
    )
    if pay:
        actions.append(("pay_claim", {"amount": amount}))
    replies = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": name,
                    "args": args,
                    "id": str(index),
                }
            ],
        )
        for index, (name, args) in enumerate(actions)
    ]
    replies.append(AIMessage(content="Review complete."))
    return StubModel(messages=iter(replies))


@pytest.mark.parametrize(
    ("outcome", "amount", "pay", "status"),
    [
        ("approve", "420.00", True, "decided"),
        ("approve", "1000.01", False, "waiting_for_sign_off"),
        ("decline", "0.00", False, "decided"),
        ("refer", "0.00", False, "decided"),
    ],
)
def test_workflows(client, outcome, amount, pay, status):
    assert (
        main.run("CLM-1001", "thread-1", scripted_model(outcome, amount, pay))
        == "Review complete."
    )
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == status
    assert claim["decision"]["outcome"] == outcome
    events = client.get("/api/claims/CLM-1001/events").json()
    assert events[0]["type"] == "started"
    assert any(e["type"] == "tool_result" for e in events)
    assert "sign_off" not in [tool.name for tool in claim_tools("CLM-1001", "thread-1")]


def test_instructions_are_fetched_from_api(client, monkeypatch):
    received = []
    original = main.create_agent

    def create(*args, **kwargs):
        received.append(kwargs["system_prompt"])
        return original(*args, **kwargs)

    monkeypatch.setattr(main, "create_agent", create)
    main.run("CLM-1001", "t1", scripted_model())
    assert received == [client.get("/api/agent/instructions").json()["text"]]


def test_payment_blocked_even_if_model_attempts_it(client):
    with pytest.raises(Exception, match="409 Conflict"):
        main.run("CLM-1001", "t1", scripted_model(amount="1000.01"))
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "waiting_for_sign_off"
    assert claim["decision"]["paid_amount"] is None
    assert client.get("/api/claims/CLM-1001/events").json()[-1]["type"] == "error"


def test_incomplete_model_run_is_released(client):
    replies = iter([AIMessage(content="Done.")])
    with pytest.raises(RuntimeError, match="stopped before completing"):
        main.run("CLM-1001", "t1", StubModel(messages=replies))
    assert client.get("/api/claims/CLM-1001").json()["status"] == "waiting"


def test_model_failure_and_reporting_failure(client, monkeypatch):
    def broken():
        raise RuntimeError("Model unavailable")

    monkeypatch.setattr(main, "model", broken)
    with pytest.raises(RuntimeError, match="Model unavailable"):
        main.run("CLM-1001", "t1")
    assert client.get("/api/claims/CLM-1001").json()["status"] == "waiting"
    original = main.request

    def request(method, path, body=None):
        if path.endswith("/failure"):
            raise httpx.ConnectError("Backend unavailable")
        return original(method, path, body)

    monkeypatch.setattr(main, "request", request)
    with pytest.raises(RuntimeError, match="Model unavailable") as error:
        main.run("CLM-1001", "t2")
    assert "Could not record" in error.value.__notes__[0]


def test_model_configuration(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    default = main.model()
    assert default.model_name == "openai/gpt-6-luna"
    assert default.reasoning_effort == "low"
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    assert main.model().model_name == "openrouter/free"
    assert main.model().reasoning_effort is None


def test_api_client_configuration(monkeypatch):
    monkeypatch.setenv("BACKEND_URL", "http://example.test:8000")
    with api.backend() as client:
        assert str(client.base_url) == "http://example.test:8000"


def test_tools_are_bound_to_one_claim(client):
    client.post("/api/claims/CLM-1001/start", json={"thread_id": "t1"})
    tool = claim_tools("CLM-1001", "t1")[0]
    result = json.loads(tool.invoke({}))
    assert result["claim_id"] == "CLM-1001"


def test_cli_one_claim_and_no_repeat(client, monkeypatch, capsys):
    threads = []

    def run(claim_id, thread_id):
        threads.append(thread_id)
        return main.run(claim_id, thread_id, scripted_model())

    monkeypatch.setattr(cli, "run", run)
    assert cli.main(["CLM-1001"]) == 0
    assert "CLM-1001: approve $420.00 — decided" in capsys.readouterr().out
    assert cli.main(["CLM-1001"]) == 1
    assert "failed" in capsys.readouterr().err
    assert len(set(threads)) == 2
    events = client.get("/api/claims/CLM-1001/events").json()
    assert len([e for e in events if e["type"] == "payment"]) == 1


def test_cli_queue_order_skip_and_continue(client, monkeypatch, capsys):
    ids = []
    threads = []
    client.post("/api/claims/CLM-1002/start", json={"thread_id": "busy"})
    main.run("CLM-1003", "pending", scripted_model("approve", "1000.01", False))
    main.run("CLM-1004", "finished", scripted_model("decline", "0.00", False))
    seen = set()

    def run(claim_id, thread_id):
        ids.append(claim_id)
        threads.append(thread_id)
        if claim_id == "CLM-1001" and claim_id not in seen:
            seen.add(claim_id)
            raise RuntimeError("Temporary failure")
        return main.run(claim_id, thread_id, scripted_model("refer", "0.00", False))

    monkeypatch.setattr(cli, "run", run)
    assert cli.main([]) == 1
    assert ids == ["CLM-1001"] + [f"CLM-{i}" for i in range(1005, 1026)]
    assert len(set(threads)) == len(threads)
    assert "Completed: 21. Failed: 1." in capsys.readouterr().out
    ids.clear()
    assert cli.main([]) == 0
    assert ids == ["CLM-1001"]
    ids.clear()
    assert cli.main([]) == 0
    assert ids == []


@pytest.mark.parametrize("argv", [[], ["missing"]])
def test_cli_backend_unavailable(monkeypatch, capsys, argv):
    def unavailable(*_args):
        raise httpx.ConnectError("Backend unavailable")

    monkeypatch.setattr(cli, "request", unavailable)
    assert cli.main(argv) == 1
    assert "Check BACKEND_URL" in capsys.readouterr().err


def test_cli_missing_claim(monkeypatch, capsys):
    def missing(*_args):
        response = httpx.Response(
            404, request=httpx.Request("GET", "http://test/missing")
        )
        response.raise_for_status()

    monkeypatch.setattr(cli, "request", missing)
    assert cli.main(["missing"]) == 1
    assert "404" in capsys.readouterr().err
