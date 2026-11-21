import json

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent import api, main
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
    actions = [("read_claim", {}), ("read_context", {}), ("read_policy_wording", {})]
    actions.append(
        (
            "record_decision",
            {
                "outcome": outcome,
                "amount": amount,
                "calculation": "Eligible costs: $420.",
                "explanation": "The policy conditions are met. The costs are covered.",
                "policy_section": "3. Trip Delay",
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
