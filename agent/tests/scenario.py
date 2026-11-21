"""Scripted claim agent for browser tests; never contacts a model provider."""

import argparse
import sys
from decimal import Decimal
from uuid import uuid4

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent.main import run


class ScenarioModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def replies(outcome: str, amount: str, pause: bool):
    for index, name in enumerate(("read_claim", "read_context", "read_policy_wording")):
        yield AIMessage(
            content="",
            tool_calls=[
                {
                    "name": name,
                    "args": {},
                    "id": str(index),
                }
            ],
        )
        if index == 0 and pause:
            print("READY", flush=True)
            if sys.stdin.readline().strip() != "continue":
                raise RuntimeError("Browser test did not release the scripted model.")
    explanation = {
        "approve": (
            "The evidence establishes a covered incident. The expenses are eligible."
        ),
        "decline": "The loss is excluded under the policy. No payment is due.",
        "refer": "A required document is missing. A handler must obtain more evidence.",
    }[outcome]
    section = {
        "approve": "3. Trip Delay",
        "decline": "9. General exclusions",
        "refer": "11. How to claim",
    }[outcome]
    yield AIMessage(
        content="",
        tool_calls=[
            {
                "name": "record_decision",
                "id": "decision",
                "args": {
                    "outcome": outcome,
                    "amount": amount,
                    "calculation": f"Synthetic test eligible amount: ${amount}.",
                    "explanation": explanation,
                    "policy_section": section,
                },
            }
        ],
    )
    if outcome == "approve" and Decimal(amount) <= 1000:
        yield AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "pay_claim",
                    "id": "payment",
                    "args": {"amount": amount},
                }
            ],
        )
    yield AIMessage(content="Scripted claim review complete.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("claim_id")
    parser.add_argument("outcome", choices=["approve", "decline", "refer"])
    parser.add_argument("amount")
    parser.add_argument("--pause", action="store_true")
    args = parser.parse_args()
    model = ScenarioModel(messages=iter(replies(args.outcome, args.amount, args.pause)))
    print(run(args.claim_id, str(uuid4()), model), flush=True)


if __name__ == "__main__":
    main()
