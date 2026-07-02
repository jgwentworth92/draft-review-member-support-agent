#!/usr/bin/env python3
"""Smoke test for the DEPLOYED draft-and-review member-support agent.

Reads the deployed Azure Function endpoint and key from a local .env file
(never committed), then calls the live `POST /api/draft` route with a member
message + case notes and prints the agent's structured result.

This script contains NO secrets: FUNCTION_URL and FUNCTION_KEY are read from
the .env file at runtime. Expected keys (see .env for your values):

    FUNCTION_URL=https://<app>.azurewebsites.net/api/draft
    FUNCTION_KEY=<the function key>

Only the Python standard library is used (urllib) — no extra dependencies.

Usage (from the repo root):
    python scripts/try_agent.py                       # run the built-in sample
    python scripts/try_agent.py --message "..." --notes "..."   # custom case
    python scripts/try_agent.py --health              # just hit /api/health
    python scripts/try_agent.py --env-file path/.env  # custom env file
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> int:
    """Minimal .env loader (no third-party dependency).

    Parses `KEY=value` lines, ignoring blanks and `#` comments, and sets any
    key not already present in the environment. Returns the number of keys set.
    Real shell env vars win, so `FUNCTION_KEY=... python ...` still works.
    """
    if not path.exists():
        return 0
    count = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            count += 1
    return count


def find_env_file(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    for candidate in (REPO_ROOT / "scripts" / ".env", REPO_ROOT / ".env"):
        if candidate.exists():
            return candidate
    return REPO_ROOT / ".env"  # reported as "not found" downstream


# A compliant sample: a real dispute the agent should handle within policy.
SAMPLE_MESSAGE = (
    "I see a $50 charge from X Company I do not recognize and I'm really upset. "
    "Fix this now."
)
SAMPLE_NOTES = (
    "Disputes can be filed. Provisional credit in 10 business days. "
    "Member must confirm last 4 digits of card."
)


def _health_url(draft_url: str) -> str:
    """Derive the /health URL from the /draft URL."""
    if draft_url.endswith("/draft"):
        return draft_url[: -len("/draft")] + "/health"
    return draft_url.rsplit("/", 1)[0] + "/health"


def _post_json(url: str, key: str, payload: dict, timeout: float = 120.0):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "x-functions-key": key},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8")


def _get(url: str, key: str, timeout: float = 30.0):
    req = urllib.request.Request(url, method="GET", headers={"x-functions-key": key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8")


def print_result(body: str) -> None:
    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        print(body)
        return
    review = result.get("review") or {}
    print("=" * 70)
    print(f"status : {result.get('status')}")
    print(f"rounds : {result.get('rounds')}")
    print(f"verdict: {review.get('verdict')}")
    for fr in review.get("failed_rules") or []:
        print(f"  - {fr.get('rule')}: {fr.get('reason')}")
    if review.get("notes"):
        print(f"notes  : {review.get('notes')}")
    print("-" * 70)
    print("DRAFT:")
    print(result.get("draft") or "(no draft produced)")
    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message", help="Member message (overrides the built-in sample).")
    parser.add_argument("--notes", help="Case notes (overrides the built-in sample).")
    parser.add_argument("--health", action="store_true", help="Call /api/health and exit.")
    parser.add_argument("--env-file", help="Path to the .env file with FUNCTION_URL/FUNCTION_KEY.")
    args = parser.parse_args()

    if bool(args.message) ^ bool(args.notes):
        parser.error("--message and --notes must be provided together.")

    env_path = find_env_file(args.env_file)
    loaded = load_env_file(env_path)
    if env_path.exists():
        print(f"Loaded {loaded} var(s) from {env_path}")
    else:
        print(f"No .env file found at {env_path} (relying on the shell environment).")

    url = os.getenv("FUNCTION_URL")
    key = os.getenv("FUNCTION_KEY")
    missing = [n for n, v in (("FUNCTION_URL", url), ("FUNCTION_KEY", key)) if not v]
    if missing:
        print(
            f"ERROR: {', '.join(missing)} not set. Add them to your .env file "
            "(FUNCTION_URL=https://<app>.azurewebsites.net/api/draft, FUNCTION_KEY=...).",
            file=sys.stderr,
        )
        return 1

    try:
        if args.health:
            status, body = _get(_health_url(url), key)
            print(f"GET /health -> {status}: {body}")
            return 0 if status == 200 else 1

        payload = {
            "member_message": args.message or SAMPLE_MESSAGE,
            "case_notes": args.notes or SAMPLE_NOTES,
        }
        print(f"POST {url} (live model calls happen server-side)...\n")
        status, body = _post_json(url, key, payload)
        if status != 200:
            print(f"[HTTP {status}] {body}", file=sys.stderr)
            return 1
        print_result(body)
        return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(f"ERROR: HTTP {exc.code} from the function: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"ERROR: could not reach the function: {exc.reason}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
