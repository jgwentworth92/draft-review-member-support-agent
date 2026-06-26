"""API-layer tests for the thin FastAPI wrapper.

Uses Starlette's TestClient and overrides the `get_models` dependency to inject
deterministic stub models, so these run with no API key and no network — the same
discipline as the rest of the suite.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api import app, get_models
from src.schemas import FailedItem, ReviewVerdict
from tests.stub_model import ScriptedModel

client = TestClient(app)


def _override_models(drafter, reviewer):
    def _get():
        return (drafter, reviewer)

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
    app.dependency_overrides[get_models] = _override_models(
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


def test_draft_escalates_on_full_card_number():
    app.dependency_overrides[get_models] = _override_models(
        ScriptedModel(draft_responses=["Please reply with your full card number."] * 3),
        ScriptedModel(review_responses=[ReviewVerdict(verdict="pass")] * 3),
    )
    resp = client.post("/draft", json={"member_message": "m", "case_notes": "n"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "escalated"
    assert any(
        fi["item"] == "credential_request" for fi in body["history"][0]["failed_items"]
    )


def test_draft_escalates_after_three_revises():
    revise = ReviewVerdict(verdict="revise", failed_items=[FailedItem(item="tone", reason="curt")])
    app.dependency_overrides[get_models] = _override_models(
        ScriptedModel(draft_responses=["d1", "d2", "d3"]),
        ScriptedModel(review_responses=[revise, revise, revise]),
    )
    resp = client.post("/draft", json={"member_message": "m", "case_notes": "n"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "escalated"
    assert body["rounds"] == 3


def test_draft_rejects_empty_member_message():
    resp = client.post("/draft", json={"member_message": "", "case_notes": "n"})
    assert resp.status_code == 422


def test_draft_rejects_missing_field():
    resp = client.post("/draft", json={"member_message": "only one field"})
    assert resp.status_code == 422
