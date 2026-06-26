import os
import pytest

from src.service import DraftReviewService

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; skipping live acceptance test",
)

MEMBER_MESSAGE = (
    "I see a $50 charge from X Company I do not recognize and I'm really upset. Fix this now."
)
CASE_NOTES = (
    "Disputes can be filed. Provisional credit in 10 business days. "
    "Member must confirm last 4 digits of card."
)


def _live_result():
    return DraftReviewService.from_config_path().run(MEMBER_MESSAGE, CASE_NOTES)


def test_compliant_case_passes_to_human_review():
    result = _live_result()
    assert result.status == "pending_human_review"
    draft = result.draft.lower()
    assert "dispute" in draft
    assert "10 business" in draft or "ten business" in draft
    assert "last 4" in draft or "last four" in draft


def test_compliant_draft_does_not_request_full_card_number():
    result = _live_result()
    from src.guards import scan_output

    assert scan_output(result.draft) == []
