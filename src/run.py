from __future__ import annotations

import argparse
import logging
import sys

from src.config import load_config
from src.graph import build_app, initial_state
from src.logging_config import configure_logging
from src.models import build_model
from src.schemas import RunInput

logger = logging.getLogger(__name__)


def run(
    member_message: str,
    case_notes: str,
    config_path: str = "config.yaml",
    drafter_model=None,
    reviewer_model=None,
) -> dict:
    inp = RunInput(member_message=member_message, case_notes=case_notes)
    config = load_config(config_path)
    drafter_model = drafter_model or build_model(config.drafter)
    reviewer_model = reviewer_model or build_model(config.reviewer)
    drafter_fallback = build_model(config.drafter.fallback) if config.drafter.fallback else None
    reviewer_fallback = build_model(config.reviewer.fallback) if config.reviewer.fallback else None
    app = build_app(config, drafter_model, reviewer_model, drafter_fallback, reviewer_fallback)
    return app.invoke(initial_state(inp.member_message, inp.case_notes))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draft-and-review member support agent")
    parser.add_argument("--member-message", required=True)
    parser.add_argument("--case-notes", required=True)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)

    configure_logging()

    final = run(args.member_message, args.case_notes, config_path=args.config)

    status = final.get("status")
    rounds = len(final.get("history", []))
    logger.info("Status: %s (after %d round(s))", status, rounds)
    logger.info("Draft:\n%s", final.get("draft") or "(no draft — escalated before drafting)")
    if status == "escalated":
        reasons = "; ".join(
            f"{fr['rule']}: {fr['reason']}" for fr in (final.get("feedback") or [])
        )
        logger.warning("Escalation reasons (last review): %s", reasons or "(none recorded)")
    if final.get("notes"):
        logger.info("Reviewer notes: %s", final["notes"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
