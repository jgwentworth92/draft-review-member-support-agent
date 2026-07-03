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

import json
import logging

import azure.functions as func
from pydantic import ValidationError

from src.logging_config import configure_logging
from src.schemas import RunInput
from src.service import DraftReviewService

configure_logging()
logger = logging.getLogger(__name__)

# auth_level=FUNCTION: callers must pass a function key (?code=... or the
# x-functions-key header). Switch to func.AuthLevel.ANONYMOUS for a fully public
# endpoint, or front it with API Management / Entra ID for real auth.
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Built at IMPORT (cold start): a bad config fails host indexing at deploy
# time, not the first customer request. Model clients construct without an
# API key and without network; warm invocations reuse the compiled graph.
_service: DraftReviewService = DraftReviewService.from_config_path()


def get_service() -> DraftReviewService:
    return _service


def _json_response(payload: dict, status_code: int) -> func.HttpResponse:
    # json.dumps, never f-string interpolation: exception text contains quotes
    # and newlines that would produce a syntactically broken body.
    return func.HttpResponse(
        body=json.dumps(payload),
        mimetype="application/json",
        status_code=status_code,
    )


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return _json_response({"status": "ok"}, 200)


@app.route(route="draft", methods=["POST"])
def draft(req: func.HttpRequest) -> func.HttpResponse:
    # 1. Parse + validate the request body (mirrors FastAPI's automatic validation).
    try:
        payload = req.get_json()
    except ValueError:
        return _json_response({"detail": "Request body must be valid JSON."}, 400)

    try:
        request = RunInput(**payload)
    except (ValidationError, TypeError) as exc:
        # Validation detail describes the caller's own input (not internals),
        # but it must go through json.dumps to stay a valid body.
        return _json_response({"detail": f"Invalid input: {exc}"}, 422)

    # 2. Run the agent. The service fails closed (escalated result); this is a
    #    last-resort belt. Generic detail only - the real error is in the log.
    try:
        result = get_service().run(request.member_message, request.case_notes)
    except Exception:
        logger.exception("Agent run failed")
        return _json_response({"detail": "Agent run failed"}, 503)

    # 3. Log the outcome only — not the member message or draft body (may contain PII).
    logger.info("/draft -> status=%s rounds=%d", result.status, result.rounds)
    return func.HttpResponse(
        body=result.model_dump_json(),
        mimetype="application/json",
        status_code=200,
    )
