import json
from pathlib import Path

import pytest

from backend.store import DATA, Store, dollars


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path / "claims.sqlite3")
    result.initialize()
    return result


def test_seed_and_context(store):
    claims = store.claims()
    assert [c["claim_id"] for c in claims] == [
        f"CLM-{number}" for number in range(1001, 1026)
    ]
    assert {c["status"] for c in claims} == {"waiting"}
    source = json.loads(
        (DATA / "claims.json").read_text(encoding="utf-8"), parse_float=str
    )[0]
    for field in ("story", "documents", "items", "amount_claimed"):
        assert claims[0][field] == source[field]
    context = store.context("CLM-1001")
    assert context["customer"]["previous_claims"]
    assert context["policy"]["plan"] == context["plan"]["plan"]
    assert dollars(123456) == "1234.56"


def test_seed_is_explicit_and_not_repeated(tmp_path, monkeypatch):
    paths = []
    original = Path.read_text

    def read(path, *args, **kwargs):
        paths.append(path.name)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    store = Store(tmp_path / "claims.sqlite3")
    store.initialize()
    assert set(paths) == {
        "claims.json",
        "customers.json",
        "policies.json",
        "plans.json",
        "handlers.json",
        "company.json",
        "policy_wording.md",
    }
    with store.connect() as db:
        db.execute(
            "UPDATE claims SET status = 'in_progress' WHERE claim_id = ?", ("CLM-1001",)
        )
        db.commit()
    paths.clear()
    store.initialize()
    assert paths == []
    assert store.claims()[0]["status"] == "in_progress"
    assert len(store.claims()) == 25


def test_missing_record(store):
    with pytest.raises(KeyError):
        store.context("missing")
    with store.connect() as db, pytest.raises(KeyError):
        store.record(db, "customers", "missing")
