# Draft-and-Review Member Support Agent — Design

**Date:** 2026-06-26
**Status:** Approved (design phase)
**Stack:** Python, LangChain, LangGraph, model-agnostic (Claude as configured default)

## Objective

A two-agent generator/reviewer loop for member support replies in a financial-services
context:

- **Drafter** writes a reply email from the member message plus case notes (and reviewer
  feedback when revising).
- **Reviewer** scores the draft against a compliance checklist and returns `pass` or
  `revise` with a specific reason per failed checklist item.
- The system loops Drafter → Reviewer. On `revise`, the reviewer's feedback is fed back to
  the Drafter.
- Stop on `pass` or after **3 review rounds**.
- A human always sees the final draft before it is sent (never auto-send). If the draft
  still fails after 3 rounds, it is marked **escalated** for human intervention rather than
  approved. `escalated` and `pending_human_review` (approved) are distinct outcomes.

## Core constraint: model-agnostic

The system supports N models and providers, not a single hardcoded model. This is the
central design driver. Claude is only the configured default for the acceptance test.

- The model factory uses LangChain's generic `init_chat_model(model, model_provider=...,
  temperature=...)`. No provider-specific client is imported in the logic.
- Swapping a model or provider for any agent is a `config.yaml` edit only — no code change.
- The Drafter and Reviewer can run on different providers/models simultaneously.
- Structured output uses the generic `.with_structured_output(...)`, which LangChain routes
  to whatever the active provider supports (tool-calling, JSON mode, etc.).

## Architecture — LangGraph generator/reviewer loop

```
START → guard_input ─┬─ injection → status=escalated ───────────────────────────────→ END
                     │
                     └─ clean → drafter → reviewer → guard_output → route
                                  ▲                                   │
                                  └──────── revise ───────────────────┤
   pass (and output guard clean) → status=pending_human_review → END  │
   round==3 & revise → status=escalated → END  ───────────────────────┘
   (reviewer feedback fed back to drafter; output guard can force revise/escalate)
```

### State (`GraphState`, carried through the graph)

| Field            | Type                          | Notes                                            |
|------------------|-------------------------------|--------------------------------------------------|
| `member_message` | `str`                         | Input                                            |
| `case_notes`     | `str`                         | Input; given to BOTH agents                      |
| `draft`          | `str`                         | Current email body                               |
| `feedback`       | `list[FailedItem] | None`     | Failed items + reasons from latest review        |
| `round`          | `int`                         | 1..3                                             |
| `verdict`        | `"pass" | "revise" | None`    | Latest reviewer verdict                          |
| `status`         | `"pending_human_review" | "escalated" | None` | Terminal outcome                 |
| `history`        | `list[RoundRecord]`           | `{round, draft, verdict, failed_items}` per round|

### Nodes

- **drafter_node** — builds the Drafter chain from config and produces `draft`. Output is the
  email body only. When `feedback` is present, the prompt instructs the model to address
  every point.
- **reviewer_node** — builds the Reviewer chain from config with `.with_structured_output(
  ReviewVerdict)`. Receives the draft AND the case notes (needed to judge allowed timelines
  and allowed information requests). Appends a record to `history`.

### Routing rule (conditional edge after reviewer)

- `verdict == "pass"` → `status = "pending_human_review"` → END
- `verdict == "revise"` and `round < max_rounds` → `round += 1`, loop back to drafter with
  feedback
- `verdict == "revise"` and `round == max_rounds` → `status = "escalated"` → END

### Pass/fail enforcement

Overall `pass` is **recomputed in code** from `failed_items`: a verdict is only treated as
`pass` when `failed_items` is empty. The model cannot accidentally pass a draft that lists
failures. (Defensive: trust the structure, not the self-reported label.)

## Safeguards (defense-in-depth)

Deterministic guards around the LLM agents, not a replacement for them. Implemented in
`src/guards.py` with config-tunable patterns; documented as heuristic (reasonable coverage,
not a guarantee).

### Input guard — prompt injection (runs before drafting)

A `guard_input` node at the start of the graph scans `member_message` and `case_notes` for
prompt-injection patterns, e.g. "ignore previous/prior instructions", "disregard the above",
"you are now…", "new instructions", "system prompt", "reveal/print your instructions",
role-override and jailbreak phrasings.

- Untrusted input is additionally wrapped in explicit delimiters, and the agent prompts state
  the delimited content is **data, not instructions**.
- **On detection → set `status = escalated` (reason recorded) and route straight to human.**
  Manipulated content is never fed into the autonomous drafting loop. (Default, safest for a
  financial-services context, over sanitize-and-continue.)

### Output guard — credential/PII backstop (runs after review)

A deterministic scan of the outgoing draft for prohibited requests — full card number (vs.
"last 4"), PIN, password, CVV, SSN, full account number.

- A hit **forces `revise`/escalation even if the LLM reviewer returned `pass`.** Checklist
  item #3 is thereby enforced in code, not solely by the model — no single point (the LLM
  reviewer) is the only safeguard against asking a member for their full card number.

### Validation backbone — Pydantic v2

Pydantic models validate every boundary where structured or untrusted data enters:

- `config.yaml` → validated config models (bad config fails at load, not mid-run).
- Run inputs (member message, case notes) → a validated input model.
- Reviewer output → `ReviewVerdict` / `FailedItem` models driving `.with_structured_output(...)`.

## Review checklist

Lives inside the Reviewer's `system_prompt` in `config.yaml` (the prompt is config, so the
checklist is swappable without a code change). The five items:

1. Plain language.
2. No promised timelines unless that timeline appears in the case notes.
3. Never asks for full card number, PIN, or password.
4. Empathetic, professional tone.
5. Clear next step for the member.

Overall verdict is `pass` only if every checklist item passes.

## Components (files)

- `config.yaml` — per-agent `provider / model / temperature / system_prompt`; `loop.max_rounds`.
- `src/config.py` — load + validate YAML into pydantic models.
- `src/models.py` — provider-agnostic model factory wrapping `init_chat_model`.
- `src/guards.py` — deterministic input prompt-injection scan + output credential/PII scan.
- `src/schemas.py` — pydantic `FailedItem`, `ReviewVerdict`, `RoundRecord`, input model;
  `GraphState` (TypedDict).
- `src/agents.py` — Drafter chain (email body only; addresses all feedback) and Reviewer
  chain (`with_structured_output`, pass only if zero failed items).
- `src/graph.py` — builds the StateGraph, nodes, router.
- `src/run.py` — CLI: member message + case notes → run loop → print final draft, status,
  round history.
- `tests/test_loop.py` — stub-model unit tests (pass-round-1, escalate-after-3,
  feedback-propagates). Deterministic, zero API cost.
- `tests/test_guards.py` — input injection detection → escalate, and output
  credential-request → forced revise/escalation backstop. Deterministic.
- `tests/test_acceptance.py` — live acceptance test for the $50-charge sample (requires
  `ANTHROPIC_API_KEY`; skipped if absent).
- `requirements.txt`, `.env.example`, `README.md`.

### Stub model

A small chat-model shim implementing the LangChain interface with scripted responses, used by
unit tests to drive the loop deterministically (e.g. always `revise` to force escalation, or
`pass` on round 1) without calling any provider.

## Configuration shape

```yaml
drafter:
  provider: anthropic                 # swap to openai / google_genai / bedrock / ...
  model: claude-haiku-4-5-20251001    # default; swap model id freely
  temperature: 0.7
  system_prompt: |
    ...
reviewer:
  provider: anthropic
  model: claude-haiku-4-5-20251001    # default; can run a different model than the drafter
  temperature: 0.0
  system_prompt: |
    ... (checklist lives here)
loop:
  max_rounds: 3
```

## Acceptance criteria

Sample input:
- Member message: *"I see a $50 charge from X Company I do not recognize and I'm really upset.
  Fix this now."*
- Case notes: *"Disputes can be filed. Provisional credit in 10 business days. Member must
  confirm last 4 digits of card."*

Expected:
- A compliant draft acknowledges frustration, states a dispute can be filed and provisional
  credit arrives in 10 business days (allowed — timeline is in the notes), asks only for the
  last 4 digits, gives a clear next step in plain language → Reviewer returns `pass` →
  `status = pending_human_review`.
- A draft asking for the full card number, or promising a timeline not in the notes, returns
  `revise`.
- Three consecutive `revise` rounds → `status = escalated`, routed to human intervention.

## Out of scope (YAGNI)

- No real email sending / inbox integration.
- No persistence/database — state lives in the graph run.
- No interactive human-in-the-loop interrupt; the human step is modeled as a terminal status
  the caller consumes.
- No multi-provider credential management beyond standard env vars.
