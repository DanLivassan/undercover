"""Transactional claim transitions and payment controls."""

import sqlite3
from contextlib import contextmanager
from typing import Any

from backend.models import Decision, Event, Execution, Failure, Payment, SignOff
from backend.store import Store


class Conflict(Exception):
    """An operation conflicts with the claim's current state."""


def event(db: sqlite3.Connection, claim: dict[str, Any], kind: str, content: str):
    db.execute(
        "INSERT INTO events (claim_id, thread_id, type, content) VALUES (?, ?, ?, ?)",
        (claim["claim_id"], claim["thread_id"], kind, content),
    )


def active(claim: dict[str, Any], thread_id: str):
    if claim["thread_id"] != thread_id or claim["status"] != "in_progress":
        raise Conflict("This execution does not own an in-progress claim.")


class Claims:
    def __init__(self, store: Store):
        self.store = store

    @contextmanager
    def edit(self, claim_id: str):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            claim = self.store.claim(db, claim_id)
            yield db, claim

    def start(self, claim_id: str, body: Execution):
        with self.edit(claim_id) as (db, claim):
            if claim["status"] != "waiting":
                raise Conflict("Only waiting claims can be started.")
            db.execute(
                "UPDATE claims SET status = 'in_progress', thread_id = ? "
                "WHERE claim_id = ?",
                (body.thread_id, claim_id),
            )
            claim["thread_id"] = body.thread_id
            event(db, claim, "started", "Agent started reviewing the claim.")
        return self.get(claim_id)

    def get(self, claim_id: str) -> dict[str, Any]:
        with self.store.connect() as db:
            return self.store.claim(db, claim_id)

    def events(self, claim_id: str) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            self.store.claim(db, claim_id)
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM events WHERE claim_id = ? ORDER BY id", (claim_id,)
                )
            ]

    def add_event(self, claim_id: str, body: Event):
        with self.edit(claim_id) as (db, claim):
            if claim["thread_id"] != body.thread_id:
                raise Conflict("This execution does not own the claim.")
            event(db, claim, body.type, body.content)
        return {"status": "recorded"}

    def decide(self, claim_id: str, body: Decision):
        with self.edit(claim_id) as (db, claim):
            active(claim, body.thread_id)
            if claim["decision"]:
                raise Conflict("A recorded decision cannot be replaced.")
            cents = int(body.amount * 100)
            limit = self.store.record(db, "settings", "company")[
                "payout_approval_limit_cents"
            ]
            status = "decided"
            if body.outcome == "approve":
                status = "waiting_for_sign_off" if cents > limit else "in_progress"
            db.execute(
                "INSERT INTO decisions (claim_id, outcome, amount_cents, calculation, "
                "explanation, policy_section) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    claim_id,
                    body.outcome,
                    cents,
                    body.calculation,
                    body.explanation,
                    body.policy_section,
                ),
            )
            db.execute(
                "UPDATE claims SET status = ? WHERE claim_id = ?", (status, claim_id)
            )
            event(
                db,
                claim,
                "decision",
                f"{body.outcome}: ${body.amount:.2f}. "
                f"{body.explanation} ({body.policy_section})",
            )
        return self.get(claim_id)

    def sign_off(self, claim_id: str, body: SignOff):
        with self.edit(claim_id) as (db, claim):
            if claim["status"] != "waiting_for_sign_off":
                raise Conflict("This claim is not waiting for sign-off.")
            handler = self.store.record(db, "handlers", body.handler_id)
            if not handler["can_approve_over_limit"]:
                raise Conflict("This handler cannot authorize over-limit payments.")
            if claim["decision"]["handler_id"]:
                raise Conflict("The decision has already been authorized.")
            db.execute(
                "UPDATE decisions SET handler_id = ?, "
                "signed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE claim_id = ?",
                (body.handler_id, claim_id),
            )
            event(db, claim, "sign_off", f"Authorized by {handler['name']}.")
        return self.get(claim_id)

    def pay(self, claim_id: str, body: Payment):
        with self.edit(claim_id) as (db, claim):
            decision = claim["decision"]
            if not decision or decision["outcome"] != "approve":
                raise Conflict("Only an approved claim can be paid.")
            cents = int(body.amount * 100)
            if cents != decision["amount_cents"]:
                raise Conflict("Payment must equal the approved amount.")
            limit = self.store.record(db, "settings", "company")[
                "payout_approval_limit_cents"
            ]
            if cents > limit and not decision["handler_id"]:
                raise Conflict("A payout over $1,000 requires a handler's sign-off.")
            if decision["paid_cents"] is not None:
                return claim
            db.execute(
                "UPDATE decisions SET paid_cents = ?, "
                "paid_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE claim_id = ?",
                (cents, claim_id),
            )
            db.execute(
                "UPDATE claims SET status = 'decided' WHERE claim_id = ?", (claim_id,)
            )
            event(db, claim, "payment", f"Simulated payment of ${body.amount:.2f}.")
        return self.get(claim_id)

    def fail(self, claim_id: str, body: Failure):
        with self.edit(claim_id) as (db, claim):
            if claim["thread_id"] != body.thread_id:
                raise Conflict("This execution does not own the claim.")
            event(db, claim, "error", body.content)
            if not claim["decision"]:
                db.execute(
                    "UPDATE claims SET status = 'waiting', thread_id = '' "
                    "WHERE claim_id = ?",
                    (claim_id,),
                )
        return self.get(claim_id)
