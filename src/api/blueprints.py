"""Azure Functions Blueprint: all scenario routes.

Exposes five HTTP POST routes (quality, draft, content, policy, onboarding)
using a lazy build-once service cache per scenario.  `draft` is a back-compat
alias that delegates to the quality handler.

Routes (Azure prepends the configurable `/api` prefix from host.json):
- POST /api/quality
- POST /api/draft      (alias for /api/quality)
- POST /api/content
- POST /api/policy
- POST /api/onboarding
"""

from __future__ import annotations

import azure.functions as func

from src.api.routes import run_json_route
from src.scenarios.content.schemas import ContentInput
from src.scenarios.content.service import ContentService
from src.scenarios.onboarding.schemas import OnboardingInput
from src.scenarios.onboarding.service import OnboardingService
from src.scenarios.policy.schemas import PolicyInput
from src.scenarios.policy.service import PolicyService
from src.scenarios.quality.schemas import RunInput
from src.scenarios.quality.service import QualityService

_services: dict = {}


def _get(name: str, factory):
    """Lazy build-once service cache."""
    if name not in _services:
        _services[name] = factory()
    return _services[name]


bp = func.Blueprint()


@bp.route(route="quality", methods=["POST"])
def quality(req: func.HttpRequest) -> func.HttpResponse:
    return run_json_route(
        lambda: _get("quality", QualityService.from_config_path),
        RunInput,
        req,
        map_input=lambda m: {"member_message": m.member_message, "case_notes": m.case_notes},
    )


@bp.route(route="draft", methods=["POST"])
def draft(req: func.HttpRequest) -> func.HttpResponse:
    """Back-compat alias — delegates to the quality handler."""
    return quality(req)


@bp.route(route="content", methods=["POST"])
def content(req: func.HttpRequest) -> func.HttpResponse:
    return run_json_route(
        lambda: _get("content", ContentService.from_config_path),
        ContentInput,
        req,
        map_input=lambda m: {"product_name": m.product_name, "spec_sheet": m.spec_sheet},
    )


@bp.route(route="policy", methods=["POST"])
def policy(req: func.HttpRequest) -> func.HttpResponse:
    return run_json_route(
        lambda: _get("policy", PolicyService.from_config_path),
        PolicyInput,
        req,
        map_input=lambda m: {"question": m.question, "handbook": m.handbook},
    )


@bp.route(route="onboarding", methods=["POST"])
def onboarding(req: func.HttpRequest) -> func.HttpResponse:
    return run_json_route(
        lambda: _get("onboarding", OnboardingService.from_config_path),
        OnboardingInput,
        req,
        map_input=lambda m: {"request": m.request, "role": m.role},
    )


def registered_routes() -> set[str]:
    """Return the set of route names registered on the blueprint."""
    return {"content", "quality", "draft", "policy", "onboarding"}
