import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend.main import app

BASE = "/api/claims/CLM-1001"
EXPLANATION = (
    "The evidence meets the policy conditions. The eligible costs are covered."
)


def decision(client, outcome="approve", amount="420.00"):
    assert client.post(f"{BASE}/start", json={"thread_id": "t1"}).status_code == 200
    return client.post(
        f"{BASE}/decision",
        json={
            "thread_id": "t1",
            "outcome": outcome,
            "amount": amount,
            "calculation": "Eligible costs minus reimbursements, deductible and cap.",
            "explanation": EXPLANATION,
            "policy_section": "3. Trip Delay",
        },
    )


def test_read_contracts(client):
    assert len(client.get("/api/claims").json()) == 25
    for path in (
        BASE,
        f"{BASE}/context",
        f"{BASE}/events",
        "/api/handlers",
        "/api/policy-wording",
        "/api/agent/instructions",
    ):
        assert client.get(path).status_code == 200
    assert "section 10" in client.get("/api/agent/instructions").json()["text"]
    assert "## 12. Definitions" in client.get("/api/policy-wording").json()["text"]
    for suffix in ("", "/context", "/events"):
        assert client.get(f"/api/claims/missing{suffix}").status_code == 404


def test_api_has_required_inputs_and_unique_operations(client):
    schema = client.get("/openapi.json").json()
    ids = []
    for path in schema["paths"].values():
        for operation in path.values():
            ids.append(operation["operationId"])
            assert operation["summary"]
            assert all(p["required"] for p in operation.get("parameters", []))
            if "requestBody" in operation:
                assert operation["requestBody"]["required"]
                reference = operation["requestBody"]["content"]["application/json"][
                    "schema"
                ]["$ref"].split("/")[-1]
                model = schema["components"]["schemas"][reference]
                assert set(model["required"]) == set(model["properties"])
    assert len(set(ids)) == len(ids)


def test_atomic_reservation_and_execution_owner(client):
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda thread: client.post(f"{BASE}/start", json={"thread_id": thread}),
                ["a", "b"],
            )
        )
    assert sorted(r.status_code for r in responses) == [200, 409]
    body = {"thread_id": "wrong", "type": "tool_call", "content": "Read claim"}
    assert client.post(f"{BASE}/events", json=body).status_code == 409
    assert (
        client.post(
            f"{BASE}/failure", json={"thread_id": "wrong", "content": "failure"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{BASE}/decision",
            json={
                "thread_id": "wrong",
                "outcome": "refer",
                "amount": "0.00",
                "calculation": "No payout.",
                "explanation": EXPLANATION,
                "policy_section": "11",
            },
        ).status_code
        == 409
    )


@pytest.mark.parametrize("amount", ["420.00", "1000.00"])
def test_payment_under_or_at_limit(client, amount):
    assert decision(client, amount=amount).json()["status"] == "in_progress"
    assert client.post(f"{BASE}/pay", json={"amount": "0.01"}).status_code == 409
    paid = client.post(f"{BASE}/pay", json={"amount": amount})
    assert paid.status_code == 200
    assert paid.json()["status"] == "decided"
    assert paid.json()["decision"]["paid_amount"] == amount
    assert client.post(f"{BASE}/pay", json={"amount": amount}).status_code == 200
    events = client.get(f"{BASE}/events").json()
    assert [e["type"] for e in events] == ["started", "decision", "payment"]
    assert all(e["created_at"] for e in events)
    assert (
        client.post(f"{BASE}/sign-off", json={"handler_id": "HND-01"}).status_code
        == 409
    )


def test_over_limit_block_and_persistence(client):
    assert decision(client, amount="1000.01").json()["status"] == "waiting_for_sign_off"
    assert client.post(f"{BASE}/pay", json={"amount": "1000.01"}).status_code == 409
    assert client.get(BASE).json()["decision"]["paid_amount"] is None
    assert (
        client.post(f"{BASE}/sign-off", json={"handler_id": "missing"}).status_code
        == 404
    )
    with app.state.store.connect() as db:
        handler = app.state.store.record(db, "handlers", "HND-01")
        handler["can_approve_over_limit"] = False
        db.execute(
            "UPDATE records SET payload = ? WHERE kind = 'handlers' AND id = ?",
            (json.dumps(handler), "HND-01"),
        )
    assert (
        client.post(f"{BASE}/sign-off", json={"handler_id": "HND-01"}).status_code
        == 409
    )
    assert (
        client.post(f"{BASE}/sign-off", json={"handler_id": "HND-02"}).status_code
        == 200
    )
    assert (
        client.post(f"{BASE}/sign-off", json={"handler_id": "HND-02"}).status_code
        == 409
    )
    assert (
        client.post(
            f"{BASE}/decision",
            json={
                "thread_id": "t1",
                "outcome": "approve",
                "amount": "9000.00",
                "calculation": "Changed.",
                "explanation": EXPLANATION,
                "policy_section": "3",
            },
        ).status_code
        == 409
    )
    assert client.post(f"{BASE}/pay", json={"amount": "1000.01"}).status_code == 200
    before = client.get(BASE).json()
    events = client.get(f"{BASE}/events").json()
    with TestClient(app) as restarted:
        assert restarted.get(BASE).json() == before
        assert restarted.get(f"{BASE}/events").json() == events


@pytest.mark.parametrize("outcome", ["decline", "refer"])
def test_non_payment_decisions(client, outcome):
    result = decision(client, outcome, "0.00").json()
    assert result["status"] == "decided"
    assert result["decision"]["outcome"] == outcome
    assert client.post(f"{BASE}/pay", json={"amount": "0.00"}).status_code == 409


@pytest.mark.parametrize("amount", ["-1", "0.001", "NaN", "Infinity"])
def test_invalid_money(client, amount):
    assert client.post(f"{BASE}/pay", json={"amount": amount}).status_code == 422


def test_decision_validation_and_immutability(client):
    assert decision(client).status_code == 200
    response = client.post(
        f"{BASE}/decision",
        json={
            "thread_id": "t1",
            "outcome": "approve",
            "amount": "420.00",
            "calculation": "Test",
            "explanation": EXPLANATION,
            "policy_section": "3",
        },
    )
    assert response.status_code == 409
    payload = response.request.content
    body = json.loads(payload)
    for field, value in (
        ("explanation", "One sentence."),
        ("policy_section", "Unknown"),
        ("outcome", "decline"),
    ):
        invalid = {**body, field: value}
        assert client.post(f"{BASE}/decision", json=invalid).status_code == 422


def test_failure_releases_only_undecided_claims(client):
    assert client.post(f"{BASE}/pay", json={"amount": "1.00"}).status_code == 409
    client.post(f"{BASE}/start", json={"thread_id": "t1"})
    assert (
        client.post(
            f"{BASE}/events",
            json={"thread_id": "t1", "type": "tool_call", "content": "Read evidence"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{BASE}/failure", json={"thread_id": "t1", "content": "Model unavailable"}
        ).json()["status"]
        == "waiting"
    )
    decision(client)
    after = client.post(
        f"{BASE}/failure", json={"thread_id": "t1", "content": "Payment unavailable"}
    ).json()
    assert after["decision"] is not None
    assert after["status"] == "in_progress"
    assert len(client.get(f"{BASE}/events").json()) == 6
