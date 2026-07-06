#!/usr/bin/env python3
"""Live integration test for the DEPLOYED draft-and-review member-support agent.

This is the project's live integration test: it runs every case from
`scripts/test_cases.yaml` against the real deployed Azure Function
`POST /api/draft` endpoint and checks each response against the structural
expectations declared alongside the message. Real model calls happen
server-side; nothing here talks to the model directly.

This script contains NO secrets. The deployed endpoint URL and function key are
read from the environment (or a local, un-committed .env file):

    FUNCTION_URL=https://<app>.azurewebsites.net/api/draft
    FUNCTION_KEY=<the function key>

Test messages live in `scripts/test_cases.yaml` — add or edit cases there; no
code change required.

Usage (from the repo root):
    python scripts/integration_test.py                        # run every case
    python scripts/integration_test.py --health               # just hit /api/health
    python scripts/integration_test.py --case prompt_injection  # run one case by name
    python scripts/integration_test.py --cases path.yaml --env-file path/.env

On completion a machine-readable report is written to
`test-artifacts/integration_test.json` (override with $INTEGRATION_ARTIFACT).
Exit code is 0 only if every case and its assertions pass.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = REPO_ROOT / "scripts" / "test_cases.yaml"
ARTIFACT_PATH = Path(
    os.environ.get(
        "INTEGRATION_ARTIFACT", str(REPO_ROOT / "test-artifacts" / "integration_test.json")
    )
)

# Full card number (13-19 digits, optional separators) or an explicit CVV/PIN
# disclosure — the fallback "bad output" definition used only when the server's
# own guard can't be imported (e.g. running the script outside the repo).
_CREDENTIAL_LEAK = re.compile(
    r"\b(?:\d[ -]?){13,19}\b|\bcvv\d?\b\s*[:=]?\s*\d{3,4}|\bpin\b\s*[:=]?\s*\d{3,6}",
    re.IGNORECASE,
)

VALID_STATUSES = {"pending_human_review", "escalated"}

# Output-safety oracle. We re-run the SERVER'S OWN credential guard on every
# returned draft: if a draft that came back APPROVED trips it, the deployed
# output guard failed to fire — the exact defect this test exists to flag. Using
# the real guard (not a reimplementation) means the oracle can't silently drift
# from what the server enforces. Falls back to the regex above if the repo isn't
# importable (src.guards only imports `re`, so this is cheap and dependency-free).
try:
    sys.path.insert(0, str(REPO_ROOT))
    from src.guards import scan_output as _scan_output

    ORACLE = "src.guards.scan_output"

    def output_violations(draft: str) -> list[str]:
        return _scan_output(draft)

except Exception:  # pragma: no cover - only when run detached from the repo
    ORACLE = "builtin-regex-fallback"

    def output_violations(draft: str) -> list[str]:
        m = _CREDENTIAL_LEAK.search(draft or "")
        return [m.group(0)] if m else []


# --- env / .env --------------------------------------------------------------


def load_env_file(path: Path) -> int:
    """Minimal .env loader (no third-party dependency).

    Parses `KEY=value` lines, ignoring blanks and `#` comments, and sets any key
    not already present in the environment. Real shell env vars win, so
    `FUNCTION_KEY=... python ...` still overrides the file.
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


# --- HTTP --------------------------------------------------------------------


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


# --- assertions --------------------------------------------------------------


def evaluate(body: dict, expect: dict) -> list[dict]:
    """Return one {assertion, ok, detail} record per checked expectation.

    Always validates the response shape; then applies whatever keys the case's
    `expect` block declares. Unknown expect keys fail loudly so typos in the
    YAML can't silently pass.
    """
    checks: list[dict] = []

    def record(assertion: str, ok: bool, detail: str = "") -> None:
        checks.append({"assertion": assertion, "ok": bool(ok), "detail": detail})

    review = body.get("review") or {}
    failed = review.get("failed_rules") or []
    failed_names = [fr.get("rule") for fr in failed]
    status = body.get("status")

    # Always-on shape validation.
    record("response shape valid", status in VALID_STATUSES, f"status={status!r}")
    record(
        "review verdict present",
        review.get("verdict") in {"pass", "revise"},
        f"verdict={review.get('verdict')!r}",
    )

    # Always-on OUTPUT-GUARD cross-check ("flag bad output"): re-run the server's
    # own credential guard on the returned draft. An APPROVED
    # (pending_human_review) draft that trips it means the deployed output guard
    # failed to fire — a real defect, so FAIL. An escalated draft that trips it
    # is the guard doing its job (caught the issue, routed to a human): recorded
    # but not failed. A clean draft passes either way.
    draft = body.get("draft") or ""
    violations = output_violations(draft) if draft else []
    approved_leak = status == "pending_human_review" and bool(violations)
    record(
        "output guard: approved draft carries no prohibited info",
        not approved_leak,
        f"oracle={ORACLE} status={status} violations={violations}"
        + ("  <- ESCALATED (guard caught it)" if violations and status == "escalated" else ""),
    )

    handlers = {
        "status": lambda v: (body.get("status") == v, f"want {v!r}, got {body.get('status')!r}"),
        "draft_present": lambda v: (
            bool(body.get("draft")) == bool(v),
            f"draft {'present' if body.get('draft') else 'absent'}",
        ),
        "rounds": lambda v: (body.get("rounds") == v, f"want {v}, got {body.get('rounds')}"),
        "rounds_max": lambda v: (
            isinstance(body.get("rounds"), int) and body.get("rounds") <= v,
            f"rounds={body.get('rounds')} <= {v}",
        ),
        "failed_rule": lambda v: (v in failed_names, f"want {v!r} in {failed_names}"),
    }

    for key, want in (expect or {}).items():
        handler = handlers.get(key)
        if handler is None:
            record(f"expect.{key}", False, "unknown expect key (check test_cases.yaml)")
            continue
        ok, detail = handler(want)
        record(f"expect.{key} == {want!r}", ok, detail)

    return checks


# --- reporting ---------------------------------------------------------------


def print_case(name: str, http_status: int, checks: list[dict], body: dict | None) -> None:
    passed = all(c["ok"] for c in checks)
    print(f"\n[{'PASS' if passed else 'FAIL'}] {name}  (HTTP {http_status})")
    if body is not None:
        review = body.get("review") or {}
        print(
            f"       status={body.get('status')} rounds={body.get('rounds')} "
            f"verdict={review.get('verdict')} failed={[fr.get('rule') for fr in review.get('failed_rules') or []]}"
        )
        draft = body.get("draft")
        if draft:
            preview = draft.replace("\n", " ")
            print(f"       draft: {preview[:100]}{'...' if len(preview) > 100 else ''}")
    for c in checks:
        mark = "ok " if c["ok"] else "XX "
        print(f"         {mark}{c['assertion']}" + (f"  ({c['detail']})" if c["detail"] else ""))


def write_artifact(report: dict) -> None:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nWrote JSON report -> {ARTIFACT_PATH}")


# --- main --------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", help="Path to the test-cases YAML.", default=str(DEFAULT_CASES))
    parser.add_argument("--case", help="Run only the case with this name.")
    parser.add_argument("--health", action="store_true", help="Call /api/health and exit.")
    parser.add_argument("--env-file", help="Path to the .env file with FUNCTION_URL/FUNCTION_KEY.")
    args = parser.parse_args()

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
        return 2

    # Health check (also the --health-only path).
    try:
        status, body = _get(_health_url(url), key)
        health_ok = status == 200
        print(f"GET /health -> {status}: {body}")
    except urllib.error.URLError as exc:
        print(f"ERROR: could not reach the deployed function: {exc.reason}", file=sys.stderr)
        return 2
    if args.health:
        return 0 if health_ok else 1

    cases_path = Path(args.cases).expanduser()
    if not cases_path.exists():
        print(f"ERROR: test-cases file not found: {cases_path}", file=sys.stderr)
        return 2
    doc = yaml.safe_load(cases_path.read_text(encoding="utf-8")) or {}
    cases = doc.get("cases") or []
    if args.case:
        cases = [c for c in cases if c.get("name") == args.case]
        if not cases:
            print(f"ERROR: no case named {args.case!r} in {cases_path}", file=sys.stderr)
            return 2

    print(f"\nRunning {len(cases)} case(s) against {url}\n" + "=" * 70)

    results: list[dict] = []
    for case in cases:
        name = case.get("name", "<unnamed>")
        payload = {
            "member_message": case.get("member_message", ""),
            "case_notes": case.get("case_notes", ""),
        }
        try:
            http_status, raw = _post_json(url, key, payload)
            body = json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            checks = [{"assertion": "HTTP 200", "ok": False, "detail": f"HTTP {exc.code}: {detail[:200]}"}]
            print_case(name, exc.code, checks, None)
            results.append({"name": name, "http_status": exc.code, "ok": False, "checks": checks, "response": None})
            continue
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            checks = [{"assertion": "request succeeds", "ok": False, "detail": str(exc)}]
            print_case(name, 0, checks, None)
            results.append({"name": name, "http_status": 0, "ok": False, "checks": checks, "response": None})
            continue

        checks = [{"assertion": "HTTP 200", "ok": http_status == 200, "detail": f"got {http_status}"}]
        checks += evaluate(body, case.get("expect") or {})
        case_ok = all(c["ok"] for c in checks)
        print_case(name, http_status, checks, body)
        results.append(
            {"name": name, "http_status": http_status, "ok": case_ok, "checks": checks, "response": body}
        )

    passed = [r for r in results if r["ok"]]
    failed = [r["name"] for r in results if not r["ok"]]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": url,
        "health_ok": health_ok,
        "passed": not failed and health_ok,
        "total": len(results),
        "passed_count": len(passed),
        "failed_count": len(failed),
        "failures": failed,
        "cases": results,
    }
    write_artifact(report)

    print("\n" + "=" * 70)
    if failed or not health_ok:
        why = failed if failed else ["health check"]
        print(f"INTEGRATION TEST FAILED: {why}")
        return 1
    print(f"All {len(results)} integration case(s) passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
