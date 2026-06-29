"""Azure Functions entry point (native HTTP trigger) for the draft-and-review agent.

This is the serverless counterpart to src/api.py (FastAPI). It exposes the same
DraftReviewService over HTTP, but using Azure's native programming model instead
of FastAPI — no ASGI server, one less layer.

Routes (Azure prepends the configurable `/api` route prefix from host.json):
- POST /api/draft   — run the Drafter->Reviewer loop on member message + case notes.
- GET  /api/health  — liveness probe.

The service (models + compiled graph) is built ONCE on first request and reused
across invocations on a warm worker. Cold starts rebuild it.
"""

from __future__ import annotations

import logging

import azure.functions as func
from pydantic import ValidationError

from src.core.runtime import configure_logging
from src.scenarios.quality.schemas import RunInput
from src.scenarios.quality.service import DraftReviewService

configure_logging()
logger = logging.getLogger(__name__)

# auth_level=FUNCTION: callers must pass a function key (?code=... or the
# x-functions-key header). Switch to func.AuthLevel.ANONYMOUS for a fully public
# endpoint, or front it with API Management / Entra ID for real auth.
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

_service: DraftReviewService | None = None


def get_service() -> DraftReviewService:
    """Lazily build the service once and reuse it. Built on first request so
    importing the app needs no API key; warm invocations reuse the compiled graph."""
    global _service
    if _service is None:
        _service = DraftReviewService.from_config_path()
    return _service


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        body='{"status": "ok"}',
        mimetype="application/json",
        status_code=200,
    )


@app.route(route="draft", methods=["POST"])
def draft(req: func.HttpRequest) -> func.HttpResponse:
    # 1. Parse + validate the request body (mirrors FastAPI's automatic validation).
    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse(
            body='{"detail": "Request body must be valid JSON."}',
            mimetype="application/json",
            status_code=400,
        )

    try:
        request = RunInput(**payload)
    except (ValidationError, TypeError) as exc:
        return func.HttpResponse(
            body=f'{{"detail": "Invalid input: {exc}"}}',
            mimetype="application/json",
            status_code=422,
        )

    # 2. Run the agent. A failure here is a config/model/runtime problem
    #    (e.g. missing API key) -> 503, same as the FastAPI layer.
    try:
        result = get_service().run(request.member_message, request.case_notes)
    except Exception as exc:
        logger.exception("Agent run failed")
        return func.HttpResponse(
            body=f'{{"detail": "Agent run failed: {exc}"}}',
            mimetype="application/json",
            status_code=503,
        )

    # 3. Log the outcome only — not the member message or draft body (may contain PII).
    logger.info("/draft -> status=%s rounds=%d", result.status, result.rounds)
    return func.HttpResponse(
        body=result.model_dump_json(),
        mimetype="application/json",
        status_code=200,
    )
