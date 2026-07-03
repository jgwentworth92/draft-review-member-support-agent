"""Compliance policy applied to every review round.

The two most important business rules in the system live here, extracted from
the graph module so they are directly unit-testable:

- a "pass" is enforced in code - never trusted from the LLM verdict alone;
- the credential output guard overrides an LLM pass.
"""

from __future__ import annotations

import logging
from typing import Literal

from src import guards
from src.schemas import FailedRule, ReviewVerdict

logger = logging.getLogger(__name__)


def apply_review_policy(
    verdict_obj: ReviewVerdict, draft: str, cred_patterns: list[str]
) -> tuple[Literal["pass", "revise"], list[FailedRule]]:
    """Compute the effective verdict and failed rules for one round.

    `verdict_obj` is non-None by contract: the reviewer chain raises
    ModelOutputError on absent output before this policy ever runs.
    """
    failed = list(verdict_obj.failed_rules)
    verdict: Literal["pass", "revise"] = (
        "pass" if (verdict_obj.verdict == "pass" and not failed) else "revise"
    )

    cred_hits = guards.scan_output(draft, cred_patterns)
    if cred_hits:
        verdict = "revise"
        failed = failed + [
            FailedRule(
                rule="credential_request",
                reason=f"Draft requests prohibited info: {cred_hits}",
            )
        ]
        logger.warning(
            "Output guard forced revise; prohibited info requested: %s", cred_hits
        )

    return verdict, failed
