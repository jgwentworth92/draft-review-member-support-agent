from __future__ import annotations
import logging
from typing import Callable, Type
import azure.functions as func
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


def run_json_route(
    service_getter: Callable[[], object],
    input_model: Type[BaseModel],
    req: func.HttpRequest,
    *,
    map_input: Callable[[BaseModel], dict],
) -> func.HttpResponse:
    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse('{"detail": "Request body must be valid JSON."}',
                                 mimetype="application/json", status_code=400)
    try:
        model = input_model(**payload)
    except (ValidationError, TypeError) as exc:
        return func.HttpResponse(f'{{"detail": "Invalid input: {exc}"}}',
                                 mimetype="application/json", status_code=422)
    try:
        result = service_getter().run(**map_input(model))
    except Exception as exc:
        logger.exception("Pipeline run failed")
        return func.HttpResponse(f'{{"detail": "Agent run failed: {exc}"}}',
                                 mimetype="application/json", status_code=503)

    logger.info("route ok -> %s", type(result).__name__)
    return func.HttpResponse(result.model_dump_json(), mimetype="application/json", status_code=200)
