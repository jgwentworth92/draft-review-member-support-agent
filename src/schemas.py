from __future__ import annotations

from typing import Literal, Optional, TypedDict

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


class RunResult(BaseModel):
    """Typed result of one draft-and-review run."""

    status: str
    draft: Optional[str] = None
    rounds: int
    review: ReviewVerdict
    history: list[dict] = Field(default_factory=list)

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
