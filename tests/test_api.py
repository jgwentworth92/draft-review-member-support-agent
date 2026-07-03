"""API-layer tests for the thin FastAPI wrapper.

Uses Starlette's TestClient and overrides the `get_service` dependency to inject
a service built with deterministic stub models, so these run with no API key and
no network — the same discipline as the rest of the suite.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api import app, get_service
from src.schemas import FailedRule, ReviewVerdict
from src.service import DraftReviewService
from tests.conftest import make_test_config
from tests.stub_model import ScriptedModel

client = TestClient(app)


def _override_service(drafter, reviewer):
    svc = DraftReviewService(make_test_config(), drafter_model=drafter, reviewer_model=reviewer)

    def _get():
        return svc

    return _get


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_draft_passes_to_human_review():
    app.dependency_overrides[get_service] = _override_service(
        ScriptedModel(draft_responses=["We can file a dispute. Please confirm the last 4 digits."]),
        ScriptedModel(review_responses=[ReviewVerdict(verdict="pass")]),
    )
    resp = client.post(
        "/draft",
        json={
            "member_message": "I see a $50 charge I do not recognize and I'm upset.",
            "case_notes": "Disputes can be filed. Provisional credit in 10 business days. Confirm last 4 digits.",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending_human_review"
    assert body["draft"]
    assert body["rounds"] == 1
    assert len(body["history"]) == 1
    assert body["history"][0]["verdict"] == "pass"
    # structured review object: {verdict, failed_rules, notes}
    assert body["review"]["verdict"] == "pass"
    assert body["review"]["failed_rules"] == []
    assert "notes" in body["review"]


def test_draft_escalates_on_full_card_number():
    app.dependency_overrides[get_service] = _override_service(
        ScriptedModel(draft_responses=["Please reply with your full card number."] * 3),
        ScriptedModel(review_responses=[ReviewVerdict(verdict="pass")] * 3),
    )
    resp = client.post("/draft", json={"member_message": "m", "case_notes": "n"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "escalated"
    assert any(
        fr["rule"] == "credential_request" for fr in body["history"][0]["failed_rules"]
    )


def test_draft_escalates_after_three_revises():
    revise = ReviewVerdict(verdict="revise", failed_rules=[FailedRule(rule="tone", reason="curt")])
    app.dependency_overrides[get_service] = _override_service(
        ScriptedModel(draft_responses=["d1", "d2", "d3"]),
        ScriptedModel(review_responses=[revise, revise, revise]),
    )
    resp = client.post("/draft", json={"member_message": "m", "case_notes": "n"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "escalated"
    assert body["rounds"] == 3


def test_draft_model_failure_returns_escalated_not_503():
    # Fail-closed contract: a model failure is a normal 200 response with
    # status=escalated (a model_failure rule), not a 5xx.
    app.dependency_overrides[get_service] = _override_service(
        ScriptedModel(draft_responses=[]),  # immediately exhausted -> raises
        ScriptedModel(review_responses=[]),
    )
    resp = client.post("/draft", json={"member_message": "m", "case_notes": "n"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "escalated"
    assert body["rounds"] == 0
    assert any(fr["rule"] == "model_failure" for fr in body["review"]["failed_rules"])


def test_draft_rejects_empty_member_message():
    # FastAPI resolves the get_service dependency even on 422 requests, and the
    # module-scope client never runs lifespan - so give it a stub (never run).
    app.dependency_overrides[get_service] = _override_service(ScriptedModel(), ScriptedModel())
    resp = client.post("/draft", json={"member_message": "", "case_notes": "n"})
    assert resp.status_code == 422


def test_draft_rejects_missing_field():
    app.dependency_overrides[get_service] = _override_service(ScriptedModel(), ScriptedModel())
    resp = client.post("/draft", json={"member_message": "only one field"})
    assert resp.status_code == 422


# --- lifespan startup (service is built at boot, not first request) ---------


def test_lifespan_boots_keyless_and_serves_health():
    # Startup builds the real service from production config.yaml with no API
    # key and no network - the README's "boots without a key" claim.
    with TestClient(app) as booted:
        resp = booted.get("/health")
        assert resp.status_code == 200
        assert app.state.service is not None


def test_lifespan_startup_fails_on_bad_config(monkeypatch):
    # A broken config must kill startup (deploy-visible), not 500 on request one.
    def _boom(*args, **kwargs):
        raise RuntimeError("bad config")

    monkeypatch.setattr(DraftReviewService, "from_config_path", _boom)
    with pytest.raises(RuntimeError, match="bad config"):
        with TestClient(app):
            pass


# --- error hygiene: 503 detail must not echo exception text ------------------


def test_unexpected_service_error_returns_generic_503():
    class _BrokenService:
        def run(self, member_message, case_notes):
            raise RuntimeError("secret internals: /etc/config leaked")

    app.dependency_overrides[get_service] = lambda: _BrokenService()
    resp = client.post("/draft", json={"member_message": "m", "case_notes": "n"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Agent run failed"
    assert "secret internals" not in resp.text
