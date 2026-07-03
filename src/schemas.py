from __future__ import annotations

import operator
from typing import Annotated, Literal, Optional, TypedDict

from pydantic import BaseModel, Field, model_validator


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

    @model_validator(mode="after")
    def _revise_requires_feedback(self) -> "ReviewVerdict":
        # "revise" with no failed rules gives the drafter zero signal and burns
        # rounds until the cap escalates. Rejecting it at parse time routes the
        # bad output through fallback + the fail-closed service boundary.
        # "pass" WITH failed_rules stays representable on purpose: policy code
        # flips it to revise, which uses the signal instead of discarding it.
        if self.verdict == "revise" and not self.failed_rules:
            raise ValueError("verdict 'revise' requires at least one failed_rule")
        return self


class RoundRecord(BaseModel):
    """One drafter->reviewer round, as recorded in run history."""

    round: int
    draft: str
    verdict: Literal["pass", "revise"]
    failed_rules: list[FailedRule] = Field(default_factory=list)
    notes: str = ""


class RunResult(BaseModel):
    """Typed result of one draft-and-review run."""

    # Literal turns "every run ends in one of two states" into an enforced
    # contract: a third status is a ValidationError, not a silent new value.
    status: Literal["pending_human_review", "escalated"]
    draft: Optional[str] = None
    rounds: int
    review: ReviewVerdict
    history: list[RoundRecord] = Field(default_factory=list)

    @classmethod
    def from_state(cls, final: dict) -> "RunResult":
        return cls(
            status=final["status"],
            draft=final.get("draft"),
            rounds=len(final.get("history", [])),
            review=ReviewVerdict(
                verdict=final.get("verdict") or "revise",
                failed_rules=final.get("feedback") or [],
                notes=final.get("notes") or "",
            ),
            history=final.get("history", []),
        )


class RunInput(BaseModel):
    member_message: str = Field(min_length=1)
    case_notes: str = Field(min_length=1)


class GraphState(TypedDict, total=False):
    member_message: str
    case_notes: str
    draft: str
    feedback: Optional[list[FailedRule]]
    notes: Optional[str]
    round: int
    verdict: Optional[str]
    status: Optional[str]
    # Reducer: nodes return the one new record; LangGraph appends. The other
    # channels stay last-writer-wins deliberately - the graph is strictly
    # sequential (see the note in src/graph.py).
    history: Annotated[list[RoundRecord], operator.add]
