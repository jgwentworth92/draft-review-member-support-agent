"""Thin FastAPI layer over the multi-scenario agent pipeline.

Exposes:
- POST /draft        — run the Drafter→Reviewer loop (quality scenario, back-compat alias).
- POST /quality      — same as /draft (quality scenario).
- POST /content      — content-pipeline scenario.
- POST /policy       — policy Q&A scenario.
- POST /onboarding   — onboarding planner scenario.
- GET  /health       — liveness probe.

Each service (models + compiled graph) is built ONCE via a lazy dependency and
reused across requests. Tests override `get_service` (quality) to inject a stub.
"""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException

from src.core.runtime import configure_logging
from src.scenarios.quality.schemas import RunInput, RunResult
from src.scenarios.quality.service import DraftReviewService
from src.scenarios.content.schemas import ContentInput, ContentResult
from src.scenarios.content.service import ContentService
from src.scenarios.policy.schemas import PolicyInput, PolicyResult
from src.scenarios.policy.service import PolicyService
from src.scenarios.onboarding.schemas import OnboardingInput, OnboardingResult
from src.scenarios.onboarding.service import OnboardingService

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Draft-and-Review Member Support Agent",
    version="1.0.0",
    summary="Generate a compliance-reviewed member-support reply (human-in-the-loop).",
)

# ---------------------------------------------------------------------------
# Lazy build-once service dependencies (one per scenario)
# ---------------------------------------------------------------------------

_service: DraftReviewService | None = None


def get_service() -> DraftReviewService:
    """Lazily build the quality service once and reuse it. Tests override this dependency."""
    global _service
    if _service is None:
        _service = DraftReviewService.from_config_path()
    return _service


_content_service: ContentService | None = None


def get_content_service() -> ContentService:
    global _content_service
    if _content_service is None:
        _content_service = ContentService.from_config_path()
    return _content_service


_policy_service: PolicyService | None = None


def get_policy_service() -> PolicyService:
    global _policy_service
    if _policy_service is None:
        _policy_service = PolicyService.from_config_path()
    return _policy_service


_onboarding_service: OnboardingService | None = None


def get_onboarding_service() -> OnboardingService:
    global _onboarding_service
    if _onboarding_service is None:
        _onboarding_service = OnboardingService.from_config_path()
    return _onboarding_service


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/draft", response_model=RunResult)
def draft(request: RunInput, service: DraftReviewService = Depends(get_service)) -> RunResult:
    try:
        result = service.run(request.member_message, request.case_notes)
    except Exception as exc:
        logger.exception("Agent run failed")
        raise HTTPException(status_code=503, detail=f"Agent run failed: {exc}") from exc
    logger.info("/draft -> status=%s rounds=%d", result.status, result.rounds)
    return result


@app.post("/quality", response_model=RunResult)
def quality(request: RunInput, service: DraftReviewService = Depends(get_service)) -> RunResult:
    """Quality scenario — same pipeline as /draft."""
    try:
        result = service.run(request.member_message, request.case_notes)
    except Exception as exc:
        logger.exception("Agent run failed")
        raise HTTPException(status_code=503, detail=f"Agent run failed: {exc}") from exc
    logger.info("/quality -> status=%s rounds=%d", result.status, result.rounds)
    return result


@app.post("/content", response_model=ContentResult)
def content(request: ContentInput, service: ContentService = Depends(get_content_service)) -> ContentResult:
    try:
        result = service.run(request.product_name, request.spec_sheet)
    except Exception as exc:
        logger.exception("Agent run failed")
        raise HTTPException(status_code=503, detail=f"Agent run failed: {exc}") from exc
    logger.info("/content ok")
    return result


@app.post("/policy", response_model=PolicyResult)
def policy(request: PolicyInput, service: PolicyService = Depends(get_policy_service)) -> PolicyResult:
    try:
        result = service.run(request.question, request.handbook)
    except Exception as exc:
        logger.exception("Agent run failed")
        raise HTTPException(status_code=503, detail=f"Agent run failed: {exc}") from exc
    logger.info("/policy ok")
    return result


@app.post("/onboarding", response_model=OnboardingResult)
def onboarding(request: OnboardingInput, service: OnboardingService = Depends(get_onboarding_service)) -> OnboardingResult:
    try:
        result = service.run(request.request, request.role)
    except Exception as exc:
        logger.exception("Agent run failed")
        raise HTTPException(status_code=503, detail=f"Agent run failed: {exc}") from exc
    logger.info("/onboarding ok")
    return result
