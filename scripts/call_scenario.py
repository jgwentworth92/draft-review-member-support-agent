#!/usr/bin/env python3
"""Call any deployed Azure Function scenario endpoint.

Stdlib only — no pip install needed. Reads the base URL and function key
from environment variables, or from a gitignored `scripts/.env` file so you
never have to paste the key on the command line.

Setup:
    cp scripts/.env.example scripts/.env      # then paste your real key into it

Run:
    python scripts/call_scenario.py --scenario content
    python scripts/call_scenario.py --scenario quality
    python scripts/call_scenario.py --scenario onboarding
    python scripts/call_scenario.py --scenario policy
    python scripts/call_scenario.py --scenario content --body path/to/payload.json

Config (env var OR scripts/.env):
    FUNCTION_URL   base URL, e.g. https://draft-review-func-95005.azurewebsites.net
    FUNCTION_KEY   required — the function key (sent as the x-functions-key header)

The script POSTs to <FUNCTION_URL>/api/<scenario> and prints the HTTP status
plus pretty-printed JSON response.  /api/draft is a back-compat alias for
/api/quality; use --scenario quality to reach the canonical route.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://draft-review-func-95005.azurewebsites.net"

# Built-in sample payloads — used when --body is omitted.
DEFAULT_BODIES: dict[str, dict] = {
    "content": {
        "product_name": "NorthBay 12-Cup Pour-Over Carafe",
        "spec_sheet": (
            "Borosilicate glass, 1.5L capacity, dishwasher safe, cork lid, "
            "heat-resistant to 150C, BPA-free, 8.2 x 8.2 x 22 cm, 480g, $34.99"
        ),
    },
    "quality": {
        "member_message": (
            "I see a $58 charge from SQ *BREW HOUSE I do not recognize "
            "and I am really upset. Fix this now."
        ),
        "case_notes": (
            "Dispute can be filed; provisional credit in 10 business days; "
            "member must confirm last 4 digits of card."
        ),
    },
    "onboarding": {
        "request": (
            "Onboard 2 new forklift-certified associates starting Monday "
            "on the evening shift."
        ),
        "role": "Warehouse Associate — Forklift Certified",
    },
    "policy": {
        "question": (
            "How many PTO days do I get per year, and when does accrual start?"
        ),
        "handbook": (
            "§4.2 PTO Accrual. Full-time employees accrue 1.5 PTO days per month "
            "(18 days/year). Accrual begins on the first of the month following hire date. "
            "Unused PTO above 10 days does not roll over past Dec 31.\n\n"
            "§6.1 Tuition Reimbursement. Eligible after 12 months of service. "
            "Reimburses 80% of tuition up to $5,250 per calendar year for approved programs."
        ),
    },
}

SCENARIOS = list(DEFAULT_BODIES.keys())


def load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=value per line, # comments and blanks ignored.
    Does not overwrite vars already set in the real environment."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def main() -> int:
    load_dotenv(Path(__file__).with_name(".env"))

    parser = argparse.ArgumentParser(
        description="Call a deployed Azure Function scenario endpoint."
    )
    parser.add_argument(
        "--scenario",
        required=True,
        choices=SCENARIOS,
        help="Which scenario endpoint to call: content, quality, onboarding, or policy.",
    )
    parser.add_argument(
        "--body",
        metavar="JSON_FILE",
        default=None,
        help=(
            "Path to a JSON file whose contents are POSTed as the request body. "
            "If omitted, a built-in sample payload for the chosen scenario is used."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("FUNCTION_URL", DEFAULT_BASE_URL),
        help="Base URL of the deployed Function App (overrides FUNCTION_URL env var).",
    )
    args = parser.parse_args()

    key = os.environ.get("FUNCTION_KEY")
    if not key:
        print(
            "ERROR: FUNCTION_KEY not set. Copy scripts/.env.example to scripts/.env "
            "and paste your key, or set the FUNCTION_KEY environment variable.",
            file=sys.stderr,
        )
        return 2

    # Build payload
    if args.body:
        body_path = Path(args.body)
        if not body_path.is_file():
            print(f"ERROR: body file not found: {body_path}", file=sys.stderr)
            return 2
        try:
            payload_dict = json.loads(body_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"ERROR: invalid JSON in {body_path}: {exc}", file=sys.stderr)
            return 2
    else:
        payload_dict = DEFAULT_BODIES[args.scenario]

    payload = json.dumps(payload_dict).encode("utf-8")

    base = args.base_url.rstrip("/")
    url = f"{base}/api/{args.scenario}"

    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "x-functions-key": key},
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # The function returns JSON error bodies (e.g. 422/503) — show them.
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}", file=sys.stderr)
        print(body, file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Request failed: {exc.reason}", file=sys.stderr)
        return 1

    print(f"HTTP {status}")
    try:
        print(json.dumps(json.loads(body), indent=2))
    except json.JSONDecodeError:
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
