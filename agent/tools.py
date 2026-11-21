"""Claim-scoped HTTP tools, with observable activity recorded by the API."""

import json
from typing import Any, Literal

from langchain_core.tools import tool

from agent.api import request


def claim_tools(claim_id: str, thread_id: str):
    base = f"/api/claims/{claim_id}"

    def record(kind: str, content: str):
        request(
            "POST",
            f"{base}/events",
            {
                "thread_id": thread_id,
                "type": kind,
                "content": content,
            },
        )

    def call(name: str, method: str, path: str, body: dict[str, Any] | None = None):
        record("tool_call", f"{name}: {json.dumps(body or {})}")
        result = request(method, path, body)
        record("tool_result", f"{name} completed successfully.")
        return json.dumps(result)

    @tool
    def read_claim() -> str:
        """Read the assigned claim, including story, items and documents."""
        return call("read_claim", "GET", base)

    @tool
    def read_context() -> str:
        """Read the customer history, policy, plan and purchased add-ons."""
        return call("read_context", "GET", f"{base}/context")

    @tool
    def read_policy_wording() -> str:
        """Read the complete policy wording; use it as the decision authority."""
        return call("read_policy_wording", "GET", "/api/policy-wording")

    @tool
    def record_decision(
        outcome: Literal["approve", "decline", "refer"],
        amount: str,
        calculation: str,
        explanation: str,
        policy_section: str,
    ) -> str:
        """Record one decision with dollar amount, calculation and 2–3 sentences."""
        return call(
            "record_decision",
            "POST",
            f"{base}/decision",
            {
                "thread_id": thread_id,
                "outcome": outcome,
                "amount": amount,
                "calculation": calculation,
                "explanation": explanation,
                "policy_section": policy_section,
            },
        )

    @tool
    def pay_claim(amount: str) -> str:
        """Make a simulated payment equal to the approved dollar amount."""
        return call("pay_claim", "POST", f"{base}/pay", {"amount": amount})

    return [read_claim, read_context, read_policy_wording, record_decision, pay_claim]
