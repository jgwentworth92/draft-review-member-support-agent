"""Thin FastAPI layer over the draft-and-review agent.

Exposes:
- POST /draft  — run the Drafter→Reviewer loop on a member message + case notes.
- GET  /health — liveness probe.

The endpoint delegates to `src.run.run`, which validates input, builds the
configured (provider-agnostic) models, runs the LangGraph loop, and returns the
final state. Models are supplied via the `get_models` dependency so tests can
inject deterministic stubs; in production it returns (None, None), letting
`run()` build the real models from config.yaml (requires the relevant provider
key, e.g. ANTHROPIC_API_KEY).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.logging_config import configure_logging
from src.run import run
from src.schemas import ReviewVerdict, RunInput

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Draft-and-Review Member Support Agent",
    version="1.0.0",
    summary="Generate a compliance-reviewed member-support reply (human-in-the-loop).",
)


class DraftResponse(BaseModel):
    """Result of one draft-and-review run."""

    status: str = Field(description="'pending_human_review' (approved) or 'escalated'.")
    draft: Optional[str] = Field(
        default=None, description="Final email body, or null if escalated before drafting."
    )
    rounds: int = Field(description="Number of review rounds executed.")
    review: ReviewVerdict = Field(
        description="Structured verdict from the latest review: {verdict, failed_rules, notes}."
    )
    history: list[dict] = Field(
        default_factory=list,
        description="Per-round records: {round, draft, verdict, failed_rules, notes}.",
    )


def get_models():
    """Model provider for the /draft endpoint.

    Returns (drafter_model, reviewer_model). In production both are None, so
    `run()` builds them from config.yaml. Tests override this dependency to
    inject stub models (no API key, deterministic).
    """
    return (None, None)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/draft", response_model=DraftResponse)
def draft(request: RunInput, models=Depends(get_models)) -> DraftResponse:
    drafter_model, reviewer_model = models
    try:
        final = run(
            request.member_message,
            request.case_notes,
            drafter_model=drafter_model,
            reviewer_model=reviewer_model,
        )
    except Exception as exc:  # config/model/runtime failure (e.g. missing API key)
        logger.exception("Agent run failed")
        raise HTTPException(status_code=503, detail=f"Agent run failed: {exc}") from exc

    # Log the outcome only — not the member message or draft body (may contain PII).
    logger.info(
        "/draft -> status=%s rounds=%d", final.get("status"), len(final.get("history", []))
    )
    review = ReviewVerdict(
        verdict=final.get("verdict") or "revise",
        failed_rules=final.get("feedback") or [],
        notes=final.get("notes") or "",
    )
    return DraftResponse(
        status=final["status"],
        draft=final.get("draft"),
        rounds=len(final.get("history", [])),
        review=review,
        history=final.get("history", []),
    )
