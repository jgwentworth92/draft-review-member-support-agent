from __future__ import annotations

from typing import Literal, Optional, TypedDict

from pydantic import BaseModel, Field


class FailedItem(BaseModel):
    item: str = Field(description="The checklist item that failed.")
    reason: str = Field(description="Specific reason this checklist item failed.")


class ReviewVerdict(BaseModel):
    verdict: Literal["pass", "revise"] = Field(
        description="'pass' only if every checklist item passes, otherwise 'revise'."
    )
    failed_items: list[FailedItem] = Field(
        default_factory=list,
        description="One entry per failed checklist item. Empty when verdict is 'pass'.",
    )


class RunInput(BaseModel):
    member_message: str = Field(min_length=1)
    case_notes: str = Field(min_length=1)


class RoundRecord(TypedDict):
    round: int
    draft: str
    verdict: str
    failed_items: list[dict]


class GraphState(TypedDict, total=False):
    member_message: str
    case_notes: str
    draft: str
    feedback: Optional[list[dict]]
    round: int
    verdict: Optional[str]
    status: Optional[str]
    history: list[RoundRecord]
