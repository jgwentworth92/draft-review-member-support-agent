"""Azure Functions entry point (native HTTP trigger).

Registers all scenario blueprints (quality, draft, content, policy, onboarding)
plus a GET /api/health liveness probe.

Routes (Azure prepends the configurable `/api` prefix from host.json):
- POST /api/quality
- POST /api/draft      (back-compat alias for /api/quality)
- POST /api/content
- POST /api/policy
- POST /api/onboarding
- GET  /api/health
"""

from __future__ import annotations

import azure.functions as func

from src.core.runtime import configure_logging
from src.api.blueprints import bp

configure_logging()

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
app.register_functions(bp)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse('{"status": "ok"}', mimetype="application/json", status_code=200)
