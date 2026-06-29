#!/usr/bin/env python3
"""Call the deployed Azure Function /api/draft endpoint.

Stdlib only — no pip install needed. Reads the endpoint URL and function key
from environment variables, or from a gitignored `scripts/.env` file so you
never have to paste the key on the command line.

Setup:
    cp scripts/.env.example scripts/.env      # then paste your real key into it

Run:
    python scripts/call_draft.py
    python scripts/call_draft.py --message "Where is my card?" --case-notes "Reissued 2026-06-20, ships 5-7 days."

Config (env var OR scripts/.env):
    FUNCTION_URL   default: the draft-review-func-95005 endpoint
    FUNCTION_KEY   required — the function key (sent as the x-functions-key header)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://draft-review-func-95005.azurewebsites.net/api/draft"

DEFAULT_MESSAGE = "I still haven't received my replacement debit card and it's been over a week."
DEFAULT_CASE_NOTES = (
    "Card reissued 2026-06-20 after fraud report. Standard shipping 5-7 business days. "
    "Member verified by last 4 of SSN."
)


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

    parser = argparse.ArgumentParser(description="Call the deployed /api/draft endpoint.")
    parser.add_argument("--message", default=DEFAULT_MESSAGE, help="member_message")
    parser.add_argument("--case-notes", default=DEFAULT_CASE_NOTES, help="case_notes")
    parser.add_argument("--url", default=os.environ.get("FUNCTION_URL", DEFAULT_URL))
    args = parser.parse_args()

    key = os.environ.get("FUNCTION_KEY")
    if not key:
        print(
            "ERROR: FUNCTION_KEY not set. Copy scripts/.env.example to scripts/.env "
            "and paste your key, or set the FUNCTION_KEY environment variable.",
            file=sys.stderr,
        )
        return 2

    payload = json.dumps(
        {"member_message": args.message, "case_notes": args.case_notes}
    ).encode("utf-8")

    request = urllib.request.Request(
        args.url,
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
