from __future__ import annotations

from typing import Literal, Optional, TypedDict

from pydantic import BaseModel, Field


class FailedRule(BaseModel):
    rule: str = Field(description="The checklist rule that failed.")
    reason: str = Field(description="Specific reason this checklist rule failed.")


class ReviewVerdict(BaseModel):
    verdict: Literal["pass", "revise"] = Field(
        description="'pass' only if every checklist rule passes, otherwise 'revise'."
    )
    failed_rules: list[FailedRule] = Field(
        default_factory=list,
        description="One entry per failed checklist rule. Empty when verdict is 'pass'.",
    )
    notes: str = Field(
        default="",
        description="Brief overall assessment of the draft (1-2 sentences).",
    )


class RunInput(BaseModel):
    member_message: str = Field(min_length=1)
    case_notes: str = Field(min_length=1)


class RoundRecord(TypedDict):
    round: int
    draft: str
    verdict: str
    failed_rules: list[dict]
    notes: str


class GraphState(TypedDict, total=False):
    member_message: str
    case_notes: str
    draft: str
    feedback: Optional[list[dict]]
    notes: Optional[str]
    round: int
    verdict: Optional[str]
    status: Optional[str]
    history: list[RoundRecord]
