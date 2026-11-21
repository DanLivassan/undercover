"""Required, validated inputs to the pilot API."""

import re
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Text = Annotated[str, Field(min_length=1)]
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Execution(Input):
    thread_id: Text


class Event(Execution):
    type: Literal["tool_call", "tool_result", "error"]
    content: Text


class Decision(Execution):
    outcome: Literal["approve", "decline", "refer"]
    amount: Money
    calculation: Text
    explanation: Text
    policy_section: Text

    @field_validator("explanation")
    @classmethod
    def sentences(cls, value: str) -> str:
        count = len(re.split(r"(?<=[.!?])\s+(?=[A-Z])", value))
        if count not in (2, 3):
            raise ValueError("Explain the decision in two or three sentences.")
        return value

    @field_validator("policy_section")
    @classmethod
    def section(cls, value: str) -> str:
        if not re.search(r"\b(?:[1-9]|1[0-2])\b", value):
            raise ValueError("Cite a numbered section of the policy wording.")
        return value

    @model_validator(mode="after")
    def outcome_amount(self):
        if self.outcome != "approve" and self.amount != 0:
            raise ValueError("Only an approval can have a payout.")
        return self


class SignOff(Input):
    handler_id: Text


class Payment(Input):
    amount: Money


class Failure(Execution):
    content: Text
