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
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request

from src.logging_config import configure_logging
from src.schemas import RunInput, RunResult
from src.service import DraftReviewService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the service at STARTUP: a bad config kills the deploy visibly
    # instead of 500ing the first customer request, and there is no lazy-init
    # race. Model clients construct without an API key and without network.
    configure_logging()
    app.state.service = DraftReviewService.from_config_path()
    yield


app = FastAPI(
    title="Draft-and-Review Member Support Agent",
    version="1.0.0",
    summary="Generate a compliance-reviewed member-support reply (human-in-the-loop).",
    lifespan=lifespan,
)


def get_service(request: Request) -> DraftReviewService:
    """Return the service built in the lifespan handler. Tests override this
    dependency to inject stub-model services."""
    service = getattr(request.app.state, "service", None)
    if service is None:
        raise RuntimeError("service not initialized - app was started without its lifespan")
    return service


@app.get("/health")
async def health() -> dict:
    # async so liveness never waits on the threadpool that runs /draft.
    return {"status": "ok"}


@app.post("/draft", response_model=RunResult)
def draft(request: RunInput, service: DraftReviewService = Depends(get_service)) -> RunResult:
    try:
        result = service.run(request.member_message, request.case_notes)
    except Exception as exc:  # last-resort belt: the service itself fails closed
        # Generic detail only - exception text can carry provider bodies,
        # request IDs, and config internals. The real error is in the log line.
        logger.exception("Agent run failed")
        raise HTTPException(status_code=503, detail="Agent run failed") from exc

    # Log the outcome only — not the member message or draft body (may contain PII).
    logger.info("/draft -> status=%s rounds=%d", result.status, result.rounds)
    return result
