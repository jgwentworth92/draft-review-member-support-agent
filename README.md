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

## Run

    python -m src.run \
      --member-message "I see a \$50 charge I do not recognize and I'm really upset." \
      --case-notes "Disputes can be filed. Provisional credit in 10 business days. Member must confirm last 4 digits of card."

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
      "feedback": null,                     // failed checklist items, if any
      "history": [ { "round": 1, "draft": "…", "verdict": "pass", "failed_items": [] } ]
    }

Endpoints: `POST /draft` (run the loop), `GET /health` (liveness). Interactive docs at
`/docs`. Empty/missing fields return `422`; an agent/model failure returns `503`. A passing
draft is returned as `pending_human_review` — the caller still puts it in front of a human;
the API never sends.

## Test

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
