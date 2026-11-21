"""SQLite storage and the explicit pilot seed data."""

import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parents[1] / "data"
SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (kind, id)
);
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY, position INTEGER NOT NULL, payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting', thread_id TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS decisions (
    claim_id TEXT PRIMARY KEY REFERENCES claims(claim_id),
    outcome TEXT NOT NULL, amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
    calculation TEXT NOT NULL, explanation TEXT NOT NULL, policy_section TEXT NOT NULL,
    handler_id TEXT, signed_at TEXT, paid_cents INTEGER, paid_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    thread_id TEXT NOT NULL, type TEXT NOT NULL, content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""


def dollars(cents: int) -> str:
    """Format integer cents without floating point arithmetic."""
    return str((Decimal(cents) / 100).quantize(Decimal("0.01")))


class Store:
    """Keep each operation in a short-lived SQLite transaction."""

    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        """Import only the files approved for the pilot, once per database."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM claims LIMIT 1").fetchone():
                return
            for kind in ("customers", "policies", "handlers"):
                records = self.read_json(f"{kind}.json")
                key = {
                    "customers": "customer_id",
                    "policies": "policy_id",
                    "handlers": "handler_id",
                }[kind]
                for record in records:
                    self.insert_record(db, kind, record[key], record)
            plans = self.read_json("plans.json")
            self.insert_record(db, "settings", "plans", plans)
            company = self.read_json("company.json")
            self.insert_record(
                db,
                "settings",
                "company",
                {
                    "payout_approval_limit_cents": int(
                        Decimal(str(company["payout_approval_limit"])) * 100
                    ),
                    "policy_wording_version": company["policy_wording_version"],
                },
            )
            self.insert_record(
                db,
                "settings",
                "wording",
                {
                    "text": (DATA / "policy_wording.md").read_text(encoding="utf-8"),
                    "version": company["policy_wording_version"],
                },
            )
            for position, claim in enumerate(self.read_json("claims.json")):
                claim["status"] = "waiting"
                db.execute(
                    "INSERT INTO claims (claim_id, position, payload) VALUES (?, ?, ?)",
                    (claim["claim_id"], position, json.dumps(claim)),
                )
            db.commit()

    @staticmethod
    def read_json(name: str) -> Any:
        return json.loads((DATA / name).read_text(encoding="utf-8"), parse_float=str)

    @staticmethod
    def insert_record(db: sqlite3.Connection, kind: str, key: str, payload: Any):
        db.execute(
            "INSERT INTO records VALUES (?, ?, ?)", (kind, key, json.dumps(payload))
        )

    @staticmethod
    def record(db: sqlite3.Connection, kind: str, key: str) -> Any:
        row = db.execute(
            "SELECT payload FROM records WHERE kind = ? AND id = ?", (kind, key)
        ).fetchone()
        if row is None:
            raise KeyError(key)
        return json.loads(row["payload"])

    @staticmethod
    def claim(db: sqlite3.Connection, claim_id: str) -> dict[str, Any]:
        row = db.execute(
            "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        if row is None:
            raise KeyError(claim_id)
        result = json.loads(row["payload"])
        result.update(status=row["status"], thread_id=row["thread_id"], decision=None)
        decision = db.execute(
            "SELECT * FROM decisions WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        if decision:
            result["decision"] = dict(decision)
            result["decision"]["amount"] = dollars(decision["amount_cents"])
            result["decision"]["paid_amount"] = (
                dollars(decision["paid_cents"])
                if decision["paid_cents"] is not None
                else None
            )
        return result

    def claims(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            ids = db.execute("SELECT claim_id FROM claims ORDER BY position").fetchall()
            result = [self.claim(db, row["claim_id"]) for row in ids]
            for claim in result:
                claim["customer_name"] = self.record(
                    db, "customers", claim["customer_id"]
                )["name"]
            return result

    def context(self, claim_id: str) -> dict[str, Any]:
        with self.connect() as db:
            claim = self.claim(db, claim_id)
            policy = self.record(db, "policies", claim["policy_id"])
            plans = self.record(db, "settings", "plans")
            return {
                "customer": self.record(db, "customers", claim["customer_id"]),
                "policy": policy,
                "plan": next(p for p in plans["plans"] if p["plan"] == policy["plan"]),
                "add_ons": [
                    a for a in plans["add_ons"] if a["add_on"] in policy["add_ons"]
                ],
                "deductible_applies_to": plans["deductible_applies_to"],
            }
