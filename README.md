# Draft-and-Review Member Support Agent

A two-agent LangGraph loop for financial-services member support. A **Drafter** writes a
reply from the member message and case notes; a **Reviewer** scores it against a compliance
checklist and returns `pass` or `revise`. The system loops up to 3 rounds, then ends in a
distinct outcome — **never auto-send**:

- `pending_human_review` — passed; awaits a human before sending.
- `escalated` — failed 3 rounds, a prompt-injection input was detected, or the model
  pipeline failed (fail-closed) → human intervention.

## Model-agnostic

Models, providers, prompts, and temperatures are set per agent in `config.yaml` and resolved
through LangChain's `init_chat_model`. Swapping a model, provider, or prompt for either agent
is a config edit only — no code change. The Drafter and Reviewer can run different models.

## Setup

    python -m pip install -r requirements.txt
    cp .env.example .env   # then fill in your provider key(s)

## Use as a library

    from src.service import DraftReviewService

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
`/docs`. Empty/missing fields return `422`. A model/runtime failure **fails closed**: the
response is a normal `200` with `status: "escalated"` and a `model_failure` entry in
`review.failed_rules` — read `status`, not the HTTP code; `5xx` is reserved for broken
deployments. A passing draft is returned as `pending_human_review` — the caller still puts
it in front of a human; the API never sends.

## Run with Docker

The service is containerized (slim image, non-root user, `/health` healthcheck).

    docker build -t draft-review-agent:latest .
    docker run --rm -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... draft-review-agent:latest

Or with Compose (reads your key from `.env`, which is git/docker-ignored):

    cp .env.example .env   # fill in ANTHROPIC_API_KEY
    docker compose up --build

The API is then at `http://127.0.0.1:8000` (docs at `/docs`). The key is supplied at
runtime only — it is never copied into the image. Without a key the app still boots and
`/health` is green; `/draft` fails closed (returns `escalated` with a `model_failure`
rule) until a key is provided.

## Test

Tests need the dev dependencies (runtime deps plus pytest + httpx):

    python -m pip install -r requirements-dev.txt
    python -m pytest -v --ignore=tests/test_acceptance.py   # deterministic suite (no API key)
    ANTHROPIC_API_KEY=... python -m pytest tests/test_acceptance.py -v   # live acceptance test

Or run the suite in a container (no local Python needed; the repo is bind-mounted, so
code changes don't require a rebuild):

    docker build -f Dockerfile.test -t draft-review-agent-test .
    docker run --rm -v "$(pwd):/app" draft-review-agent-test

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

On exhaustion the run fails closed: the service returns an `escalated` `RunResult` with a
`model_failure` feedback entry, which the API relays as a normal `200` response.
See `config.yaml` for commented examples.
