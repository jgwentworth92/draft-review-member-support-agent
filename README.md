# Draft-and-Review Member Support Agent

A two-agent LangGraph loop for financial-services member support. A **Drafter** writes a
reply from the member message and case notes; a **Reviewer** scores it against a compliance
checklist and returns `pass` or `revise`. The system loops up to 3 rounds, then ends in a
distinct outcome — **never auto-send**:

- `pending_human_review` — passed; awaits a human before sending.
- `escalated` — failed 3 rounds (or a prompt-injection input was detected) → human intervention.

## Model-agnostic

Models, providers, prompts, and temperatures are set per agent in `config.yaml` and resolved
through LangChain's `init_chat_model`. Swapping a model, provider, or prompt for either agent
is a config edit only — no code change. The Drafter and Reviewer can run different models.

## Setup

    python -m pip install -r requirements.txt
    cp .env.example .env   # then fill in your provider key(s)

## Use as a library

    from src.scenarios.quality.service import DraftReviewService

    service = DraftReviewService.from_config_path()   # builds models + graph once
    result = service.run(
        member_message="I see a $50 charge I do not recognize and I'm really upset.",
        case_notes="Disputes can be filed. Provisional credit in 10 business days. Confirm last 4 digits.",
    )
    print(result.status, result.review.verdict)        # RunResult (typed)

## Run the API

A thin FastAPI layer wraps the same loop. Start it (needs a provider key, e.g.
`ANTHROPIC_API_KEY`, since `/draft` calls the live model):

    uvicorn src.api:app --reload

Then POST a member message + case notes:

    curl -s http://127.0.0.1:8000/draft \
      -H "Content-Type: application/json" \
      -d '{"member_message": "I see a $50 charge I do not recognize and I am upset.",
           "case_notes": "Disputes can be filed. Provisional credit in 10 business days. Confirm last 4 digits."}'

Response:

    {
      "status": "pending_human_review",   // or "escalated"
      "draft": "…email body…",            // null if escalated before drafting
      "rounds": 1,
      "review": {                           // structured verdict from the latest review
        "verdict": "pass",                  //   "pass" | "revise"
        "failed_rules": [],                 //   [{ "rule": …, "reason": … }]
        "notes": "…overall assessment…"
      },
      "history": [ { "round": 1, "draft": "…", "verdict": "pass", "failed_rules": [], "notes": "…" } ]
    }

Endpoints: `POST /draft` (run the loop), `GET /health` (liveness). Interactive docs at
`/docs`. Empty/missing fields return `422`; an agent/model failure returns `503`. A passing
draft is returned as `pending_human_review` — the caller still puts it in front of a human;
the API never sends.

## Azure Functions — Deployed Endpoints

The service is also deployed as an Azure Functions app (`draft-review-func-95005`).
All endpoints require the `x-functions-key` header (function-level auth).

Base URL: `https://draft-review-func-95005.azurewebsites.net`

| Route | Alias of | Input fields | Purpose |
|-------|----------|--------------|---------|
| `POST /api/content` | — | `product_name`, `spec_sheet` | Product-launch content pipeline (researcher → writer) |
| `POST /api/quality` | — | `member_message`, `case_notes` | Customer-email quality loop (drafter → reviewer) |
| `POST /api/draft` | `/api/quality` | `member_message`, `case_notes` | Back-compat alias — identical behaviour to `/api/quality` |
| `POST /api/onboarding` | — | `request`, `role` | Warehouse onboarding planner (planner → executor) |
| `POST /api/policy` | — | `question`, `handbook` | Policy Q&A assistant (retriever → responder) |
| `GET /api/health` | — | _(none)_ | Liveness probe |

### Auth

Pass the function key in the `x-functions-key` request header:

    curl -s https://draft-review-func-95005.azurewebsites.net/api/health \
      -H "x-functions-key: <YOUR_FUNCTION_KEY>"

### Sample payloads

**`POST /api/content`** — NorthBay pour-over carafe:

    curl -s https://draft-review-func-95005.azurewebsites.net/api/content \
      -H "Content-Type: application/json" \
      -H "x-functions-key: <YOUR_FUNCTION_KEY>" \
      -d '{
        "product_name": "NorthBay 12-Cup Pour-Over Carafe",
        "spec_sheet": "Borosilicate glass, 1.5L capacity, dishwasher safe, cork lid, heat-resistant to 150C, BPA-free, 8.2 x 8.2 x 22 cm, 480g, $34.99"
      }'

**`POST /api/quality`** — disputed-charge member message (also works as `/api/draft`):

    curl -s https://draft-review-func-95005.azurewebsites.net/api/quality \
      -H "Content-Type: application/json" \
      -H "x-functions-key: <YOUR_FUNCTION_KEY>" \
      -d '{
        "member_message": "I see a $58 charge from SQ *BREW HOUSE I do not recognize and I am really upset. Fix this now.",
        "case_notes": "Dispute can be filed; provisional credit in 10 business days; member must confirm last 4 digits of card."
      }'

**`POST /api/onboarding`** — forklift associates, evening shift:

    curl -s https://draft-review-func-95005.azurewebsites.net/api/onboarding \
      -H "Content-Type: application/json" \
      -H "x-functions-key: <YOUR_FUNCTION_KEY>" \
      -d '{
        "request": "Onboard 2 new forklift-certified associates starting Monday on the evening shift.",
        "role": "Warehouse Associate — Forklift Certified"
      }'

**`POST /api/policy`** — PTO question against handbook excerpt:

    curl -s https://draft-review-func-95005.azurewebsites.net/api/policy \
      -H "Content-Type: application/json" \
      -H "x-functions-key: <YOUR_FUNCTION_KEY>" \
      -d '{
        "question": "How many PTO days do I get per year, and when does accrual start?",
        "handbook": "§4.2 PTO Accrual. Full-time employees accrue 1.5 PTO days per month (18 days/year). Accrual begins on the first of the month following hire date. Unused PTO above 10 days does not roll over past Dec 31.\n\n§6.1 Tuition Reimbursement. Eligible after 12 months of service. Reimburses 80% of tuition up to $5,250 per calendar year for approved programs."
      }'

### Generic caller script

`scripts/call_scenario.py` lets you call any of the four endpoints from the command line
without installing extra packages. Store `FUNCTION_URL` and `FUNCTION_KEY` in
`scripts/.env` (git-ignored) — see `scripts/.env.example`.

    python scripts/call_scenario.py --scenario content --body path/to/payload.json
    python scripts/call_scenario.py --scenario quality   # uses built-in sample payload
    python scripts/call_scenario.py --scenario onboarding
    python scripts/call_scenario.py --scenario policy

## Run with Docker

The service is containerized (slim image, non-root user, `/health` healthcheck).

    docker build -t draft-review-agent:latest .
    docker run --rm -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... draft-review-agent:latest

Or with Compose (reads your key from `.env`, which is git/docker-ignored):

    cp .env.example .env   # fill in ANTHROPIC_API_KEY
    docker compose up --build

The API is then at `http://127.0.0.1:8000` (docs at `/docs`). The key is supplied at
runtime only — it is never copied into the image. Without a key the app still boots and
`/health` is green; `/draft` returns `503` until a key is provided.

## Test

Tests need the dev dependencies (runtime deps plus pytest + httpx):

    python -m pip install -r requirements-dev.txt
    python -m pytest -v --ignore=tests/test_acceptance.py   # deterministic suite (no API key)
    ANTHROPIC_API_KEY=... python -m pytest tests/test_acceptance.py -v   # live acceptance test

## Safeguards

- **Input guard:** scans member message and case notes for prompt-injection patterns; on a
  hit the run is escalated before drafting.
- **Output guard:** scans the outgoing draft for prohibited credential requests (full card
  number, PIN, password, CVV, SSN, full account number); a hit forces `revise` even if the
  LLM reviewer passed it.
- **Pass enforced in code:** a verdict is `pass` only when no checklist items failed.

## Configuration

Edit `config.yaml`. Each agent has `provider`, `model`, `temperature`, and `system_prompt`
(the reviewer's checklist lives in its prompt). `loop.max_rounds` controls the round limit.
Optional `guards.injection_patterns` / `guards.credential_patterns` override the defaults.

## Resilience (retries, timeout, fallback)

Built on the framework's own mechanisms — no custom retry code — all config-driven:

- **Provider retries + backoff:** each agent's `max_retries` (default 2) and `timeout` are
  passed to `init_chat_model`; the provider SDK retries transient errors (429 / 5xx /
  overloaded / connection) with **exponential backoff + jitter**.
- **Fallback model:** add a `fallback:` block to an agent (another `{provider, model, …}`)
  and the primary is wrapped with LangChain's `Runnable.with_fallbacks(...)` — if the primary
  fails, the fallback model/provider is tried. Off unless configured. Drafter and reviewer
  can have different fallbacks.
- **Node-level retry:** set `loop.retry` to attach LangGraph's `RetryPolicy` to the drafter
  and reviewer nodes (`max_attempts`, `backoff_factor`, `initial_interval`, `max_interval`,
  `jitter`). Off unless configured.

On exhaustion, the error surfaces cleanly: the API returns `503`; the service raises an exception.
See `config.yaml` for commented examples.
