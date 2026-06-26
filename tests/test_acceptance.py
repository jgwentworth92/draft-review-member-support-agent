import os
import pytest

from src.run import run

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

def test_compliant_case_passes_to_human_review():
    final = run(MEMBER_MESSAGE, CASE_NOTES)
    assert final["status"] == "pending_human_review"
    draft = final["draft"].lower()
    assert "dispute" in draft
    assert "10 business" in draft or "ten business" in draft
    assert "last 4" in draft or "last four" in draft

def test_compliant_draft_does_not_request_full_card_number():
    final = run(MEMBER_MESSAGE, CASE_NOTES)
    from src.guards import scan_output
    assert scan_output(final["draft"]) == []
