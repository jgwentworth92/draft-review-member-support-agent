"""Thin FastAPI layer over the draft-and-review agent.

Exposes:
- POST /draft  — run the Drafter→Reviewer loop on a member message + case notes.
- GET  /health — liveness probe.

The service (models + compiled graph) is built ONCE via the `get_service`
dependency and reused across requests. Tests override `get_service` to inject a
service built with deterministic stub models (no API key).
"""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException

from src.logging_config import configure_logging
from src.schemas import RunInput, RunResult
from src.service import DraftReviewService

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Draft-and-Review Member Support Agent",
    version="1.0.0",
    summary="Generate a compliance-reviewed member-support reply (human-in-the-loop).",
)

_service: DraftReviewService | None = None


def get_service() -> DraftReviewService:
    """Lazily build the service once and reuse it. Built on first request so
    importing the app needs no API key; tests override this dependency."""
    global _service
    if _service is None:
        _service = DraftReviewService.from_config_path()
    return _service


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/draft", response_model=RunResult)
def draft(request: RunInput, service: DraftReviewService = Depends(get_service)) -> RunResult:
    try:
        result = service.run(request.member_message, request.case_notes)
    except Exception as exc:  # config/model/runtime failure (e.g. missing API key)
        logger.exception("Agent run failed")
        raise HTTPException(status_code=503, detail=f"Agent run failed: {exc}") from exc

    # Log the outcome only — not the member message or draft body (may contain PII).
    logger.info("/draft -> status=%s rounds=%d", result.status, result.rounds)
    return result
