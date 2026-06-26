from __future__ import annotations

import argparse
import sys

from src.config import load_config
from src.graph import build_app, initial_state
from src.models import build_model
from src.schemas import RunInput


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
    app = build_app(config, drafter_model, reviewer_model)
    return app.invoke(initial_state(inp.member_message, inp.case_notes))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draft-and-review member support agent")
    parser.add_argument("--member-message", required=True)
    parser.add_argument("--case-notes", required=True)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)

    final = run(args.member_message, args.case_notes, config_path=args.config)

    print(f"STATUS: {final.get('status')}")
    print(f"ROUNDS: {len(final.get('history', []))}")
    print("DRAFT:")
    print(final.get("draft") or "(no draft — escalated before drafting)")
    if final.get("status") == "escalated":
        print("\nESCALATION REASONS (last review):")
        for fi in (final.get("feedback") or []):
            print(f"  - {fi['item']}: {fi['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
