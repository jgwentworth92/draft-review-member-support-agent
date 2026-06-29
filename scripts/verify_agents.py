#!/usr/bin/env python3
"""Local pre-deploy verification: run all four scenario agents against REAL models
and print their structured results.

This exercises each pipeline end-to-end (config -> models -> graph -> structured
output) WITHOUT needing the deployed endpoints — useful before the new routes are
live. Requires ANTHROPIC_API_KEY (loaded from the repo-root .env, or the env).

For testing the LIVE deployed endpoints after a deploy, use scripts/call_scenario.py.

Run from the repo root:
    python scripts/verify_agents.py
Exit code 0 if all four agents produced a valid result, 1 otherwise.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# Ensure the repo root (which contains the `src` package) is importable when this
# script is run directly from anywhere.
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=value, # comments ignored). Does not overwrite
    vars already present in the real environment."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    load_dotenv(_ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set (.env or environment).", file=sys.stderr)
        return 2

    # Imported here so the module loads even without a key (e.g. for --help).
    from src.scenarios.content.service import ContentService
    from src.scenarios.onboarding.service import OnboardingService
    from src.scenarios.policy.service import PolicyService
    from src.scenarios.quality.service import QualityService

    cases = [
        ("content", lambda: ContentService.from_config_path().run(
            "NorthBay 12-Cup Pour-Over Carafe",
            "Borosilicate glass, 1.5L capacity, dishwasher safe, cork lid, "
            "heat-resistant to 150C, BPA-free, 8.2 x 8.2 x 22 cm, 480g, $34.99",
        )),
        ("quality", lambda: QualityService.from_config_path().run(
            "I see a $58 charge from 'SQ *BREW HOUSE' I don't recognize and I'm really upset. Fix this now.",
            "Dispute can be filed; provisional credit in 10 business days; "
            "member must confirm last 4 digits of card.",
        )),
        ("onboarding", lambda: OnboardingService.from_config_path().run(
            "Onboard 2 new forklift-certified associates starting Monday on the evening shift.",
            "warehouse associate",
        )),
        ("policy", lambda: PolicyService.from_config_path().run(
            "How many PTO days do I get per year?",
            "Section 4.2 PTO Accrual. Full-time employees accrue 1.5 PTO days per month "
            "(18 days/year). Accrual begins on the first of the month following hire date. "
            "Unused PTO above 10 days does not roll over past Dec 31.",
        )),
    ]

    results: dict[str, str] = {}
    for name, run in cases:
        print(f"\n===== {name} =====")
        try:
            result = run()
            body = json.dumps(result.model_dump(), indent=2, default=str)
            print(body[:1800] + ("\n... (truncated)" if len(body) > 1800 else ""))
            results[name] = "OK"
        except Exception as exc:  # noqa: BLE001 - report any failure per scenario
            print(f"FAILED: {exc}")
            results[name] = f"FAIL: {exc}"

    print("\n===== SUMMARY =====")
    for name, status in results.items():
        print(f"  {name:<11} {status}")
    return 0 if all(v == "OK" for v in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
