# Failure-Mode Review — Draft-and-Review Member Support Agent

**Date:** 2026-07-02
**Scope:** Assume the model provider, the config, and the caller all misbehave. Style ignored.
**Verified against:** installed `langgraph` 0.6.11, `langchain-anthropic` 0.3.22, `langchain-core` 0.3.86 in `.venv` (retry/parser behavior confirmed from package source, not docs).

---

## 1. Structured output failure (reviewer + drafter)

The reviewer chain is `bind_tools([ReviewVerdict], tool_choice=forced) | PydanticToolsParser(first_tool_only=True)` (`src/agents.py:61`). Three distinct failure shapes, three different behaviors:

- **Extra prose:** harmless. Tool choice is forced and the parser reads only tool-call blocks; surrounding text is ignored.
- **Invalid verdict value / missing required field:** `PydanticToolsParser` raises a pydantic `ValidationError` inside the chain. `ValidationError` is a `ValueError` subclass, so LangGraph's `default_retry_on` (verified in `langgraph/_internal/_retry.py`) will **not** node-retry it. If a fallback is configured it **does** fire (`with_fallbacks` handles all `Exception`s). Without a fallback the exception propagates → 503. It never silently passes and never counts as a round (history is appended only on successful node return).
- **No tool call at all** (truncated output, refusal, `max_tokens` stop): the parser returns **`None`**, not an error. Then `src/graph.py:77` does `verdict_obj.failed_rules` → `AttributeError`. `AttributeError` is *not* in the retry exclusion list, so a configured node `RetryPolicy` retries it — but critically the **fallback never fires for this case**: the crash happens in the node, after the fallback-wrapped chain already "succeeded" by returning `None`. The fallback covers malformed output but not absent output. Asymmetric and accidental.

**Finding 1 — High.** `src/graph.py:76-77`. Worst case: a single truncated reviewer response 503s the request with a bare `AttributeError: 'NoneType' object has no attribute 'failed_rules'` even though a healthy fallback model is configured.
**Fix:** after `reviewer(...)`, raise a typed error on `None` inside the chain wrapper in `agents.py` (before `with_fallbacks` composition) so the fallback catches it; or use `with_structured_output(..., include_raw=True)` and handle explicitly.

- **Drafter empty output:** `message.content == ""` flows straight through — the empty draft goes to the reviewer, burns a round, and counts toward `max_rounds`. No crash, no detection; a persistently empty drafter converts into `escalated` after 3 wasted paid review calls. Worse: Anthropic `content` can be a **list of blocks** (multi-block responses); then `src/agents.py:33-41` does `"\n<draft>\n" + draft` → `TypeError` → excluded from node retry → immediate 503.

**Finding 2 — Medium.** `src/agents.py:54`.
**Fix:** normalize `message.content` (join text blocks when it is a list) and treat empty/whitespace-only drafts as a raised failure so retry/fallback machinery applies.

---

## 2. Retry stacking

The layers multiply, they don't coordinate:

| Layer | Scope | Worst-case multiplier |
|---|---|---|
| Provider SDK `max_retries` (default 2) | per HTTP call | 3 HTTP attempts |
| `with_fallbacks` | per chain invoke | ×2 (primary chain exhausts, then fallback chain with *its own* provider retries) |
| Node `RetryPolicy` (`max_attempts` 3) | per node execution | ×3 (each attempt re-runs primary+fallback) |
| Round loop (`max_rounds` 3) | per request | ×6 node visits (3 drafter + 3 reviewer) |

Worst case: **108 HTTP attempts per request**. Bounded in count, but effectively unbounded in time: `config.yaml` leaves `timeout` unset, so the Anthropic SDK default of **600 s per attempt** applies. One node visit can take 3 × (3+3) × 600 s ≈ 3 h; a full request, tens of hours — all while holding a threadpool thread (see §6).

**Finding 3 — High.** `config.yaml:59` (timeout commented out), no run-level deadline anywhere. Worst case: requests that never return within any caller's patience, threadpool exhaustion, healthcheck-driven restart loops.
**Fix:** set `timeout` for both agents (and fallbacks) in the shipped config, and enforce an overall deadline (wrap `self._app.invoke` or pass a graph-level timeout).

**Finding 4 — Medium-high: node retry retries permanent errors.** `default_retry_on` only exempts `httpx.HTTPStatusError`/`requests.HTTPError` 4xx plus a list of builtin exception types. Anthropic SDK errors (`AuthenticationError` 401, `BadRequestError` 400, `PermissionDeniedError` 403) are none of those → **retried** by the node policy, and they also trigger the fallback. A bad API key with node retry + fallback configured costs 3 node attempts × 2 models × per-node backoff at every node, per request.
**Fix:** pass a custom `retry_on` to `RetryPolicy` in `src/graph.py:20` that excludes 4xx `anthropic.APIStatusError`.

**Round counter interaction: clean.** Verified: `round` changes only in the `increment` node (no retry policy attached), and `history` is appended only when `reviewer_node` returns successfully — LangGraph discards state updates from a raising attempt. Node retries neither reset nor double-count rounds.

**Finding 5 — Medium: `max_rounds` vs recursion limit.** Path length is `3·rounds + 1` supersteps; LangGraph's default recursion limit is 25. `max_rounds >= 9` in config makes the graph raise `GraphRecursionError` *before* reaching the escalate node → 503 instead of a clean `escalated` result. `max_rounds: 0` or negative is also accepted (drafts once, then escalates — surprising semantics).
**Fix:** `Field(ge=1)` on `max_rounds` and pass `{"recursion_limit": 3*max_rounds + 4}` to `invoke`.

---

## 3. Fallback correctness — confirmed correct

- **Drafter:** `model.with_fallbacks([fallback_model])` is invoked with the same `[SystemMessage(system_prompt), HumanMessage(...)]` list (`src/agents.py:49-53`) — prompts travel in the messages, not the model, so the fallback sees the identical prompt.
- **Reviewer:** the fallback is composed **after** structured output on both sides — `fallback_model.with_structured_output(ReviewVerdict)` (`src/agents.py:65-67`) — so both endpoints have the same schema binding. No config path runs the fallback without the schema or system prompt.

Two caveats, both low severity:

1. The fallback `ModelConfig` does **not** inherit the primary's `temperature`/`max_retries`/`timeout` — a primary with `timeout: 30` and a bare `fallback:` block silently gives the fallback the 600 s default (`src/config.py:12-24`). Consider requiring/defaulting `timeout` at `AppConfig` level.
2. `with_fallbacks` fires on *every* exception, including auth and validation errors, not just transient ones — acceptable, but the fallback can mask primary misconfiguration.

---

## 4. Config resolution — errors at first request, not startup

`load_config` is `yaml.safe_load` + `AppConfig(**data)` (`src/config.py:72-75`), invoked lazily from `get_service()` on the **first request** in both entrypoints (`src/api.py:34-40`, `function_app.py:37-43`). Behavior by failure:

- Missing `config.yaml` → `FileNotFoundError` at first request. Missing top-level key / wrong type → `ValidationError` at first request. Unknown provider → `ValueError` from `init_chat_model` at first request. Empty YAML file → `AppConfig(**None)` → `TypeError`.
- Missing API key notably does **not** fail at build: `anthropic_api_key` defaults to `""` (verified in langchain-anthropic 0.3.22), the client is a lazy `cached_property`, so it surfaces as a 401 at invoke → 503. The README's "boots without a key, /draft returns 503" claim holds *only* for that case.
- **Typo'd nested keys are silently swallowed:** pydantic's default is `extra="ignore"` at every level, so `loop: {max_round: 10}` silently runs with `max_rounds=3`. Same for `fallbck:`, `injection_pattern:`, etc.
- Guard regexes are never compiled at load; an invalid regex in `guards.injection_patterns` raises `re.error` per request inside the graph (`src/guards.py:39`).

**Finding 6 — High:** everything above is first-request, not startup.
**Finding 7 — High:** in the FastAPI app, `get_service` runs as a `Depends`, **outside** the `try` in the handler (`src/api.py:49-54`) — so every construction-time failure (bad/missing config, unknown provider) returns a **500 Internal Server Error**, not the documented 503. The Azure Functions layer calls `get_service()` inside its `try` (`function_app.py:79`) and correctly returns 503 — the two entrypoints disagree.
**Fix:** build the service in a FastAPI lifespan handler so bad config kills the process at startup (visible in deploy, not on the first customer request); set `model_config = ConfigDict(extra="forbid")` on all config models; add `Field(ge=...)` bounds; compile guard patterns in a validator.
**Minor:** an invalid `LOG_LEVEL` env value makes `configure_logging()` raise at import — the app won't boot, with an unhelpful error (`src/logging_config.py:27`).

---

## 5. API contract

Verified against the README contract:

- **422 on empty/missing fields:** ✅ `RunInput` has `min_length=1`; FastAPI returns 422 (tests cover it). Whitespace-only strings pass validation — minor.
- **503 on agent/model failure:** ✅ for failures inside `service.run`; ❌ for service-construction failures in the FastAPI path (Finding 7 — 500 leak).
- **Response shape:** ✅ both statuses. Guard-escalation path sets no `draft`, so `RunResult.draft` is `null`, `rounds` is 0, and `review` is populated from the guard's verdict/feedback (`src/schemas.py:36-48`) — matches the documented `draft: null` case.

**Finding 8 — Medium: error detail echoes raw exception text to clients.** `src/api.py:54` `detail=f"Agent run failed: {exc}"` and `function_app.py:71,83` forward `str(exc)` verbatim. Anthropic exception strings don't contain the key itself, but they do contain provider error bodies, request IDs, model names, and — for config errors in the Azure path — file paths and pydantic dumps of config internals. Additionally, **function_app.py builds its JSON by f-string interpolation without escaping**: a `ValidationError`'s string contains newlines and quotes, producing a syntactically broken JSON body on the 422 path.
**Fix:** return a generic detail (`"Agent run failed"`), keep `logger.exception` for the real error, and use `json.dumps` in `function_app.py`.

---

## 6. Concurrency

The graph itself is safe under concurrent invokes: compiled once with no checkpointer, per-invoke state, node closures capture only read-only config, and `reviewer_node` builds a new history list rather than mutating (`src/graph.py:107`). `ChatAnthropic`/httpx clients are thread-safe. Two real issues:

**Finding 9 — Low:** `_service` lazy-init race (`src/api.py:37-40`): N concurrent first requests build N services (N sets of models + compiled graphs). Last write wins; all are functional, so it's wasted work, not corruption. A lifespan-startup build (the fix for Finding 6) eliminates it.

**Finding 10 — Medium:** `/draft` and `/health` are both sync `def` → both run on anyio's shared threadpool (default 40 threads). With no timeout configured (Finding 3), 40 slow provider calls pin every thread, `/health` stops answering, and the Docker `HEALTHCHECK` (3 s timeout, 3 retries) marks the container unhealthy → restart loop under an orchestrator, killing in-flight work.
**Fix:** the timeout from Finding 3, plus consider making `/health` `async def` so it never waits on the threadpool.

---

## 7. Secrets hygiene — mostly clean

- **Never logged:** ✅ log statements emit only status, round numbers, verdicts, rule names, and guard-pattern hits; `logger.exception` writes provider error text to server logs only (no key material in Anthropic error strings).
- **Never echoed:** ⚠️ the key itself doesn't appear in error responses, but Finding 8's raw-exception echo is the one live leak vector for provider/internal detail.
- **Not in the image:** ✅ Dockerfile copies only `src/` + `config.yaml`; `.dockerignore` excludes `.env*`; compose injects the key at runtime. `.funcignore` excludes `local.settings.json` from the Functions deploy; `git ls-files` confirms `.env` and `local.settings.json` are untracked (only `.env.example` is committed). Residual risk is procedural only: `local.settings.json` sits in the repo root holding a real key protected solely by `.gitignore` — a `git add -f` or a future `.gitignore` edit exposes it. Consider a pre-commit secret scan.

---

## Summary table

| # | Severity | Location | Issue |
|---|---|---|---|
| 7 | High | `src/api.py:49` | Config/build failures escape `Depends` → 500 instead of 503; contract broken; differs from Azure path |
| 1 | High | `src/graph.py:77` | Reviewer no-tool-call → `None` → `AttributeError`; fallback never fires for this case |
| 3 | High | `config.yaml:59` | No timeout + retry×fallback×node-retry×rounds stacking → up to 108 HTTP attempts, multi-hour requests |
| 6 | High | `src/config.py:72` | All config errors surface at first request, not startup; typo'd keys silently ignored; regexes unvalidated |
| 4 | Med-high | `src/graph.py:20` | Node RetryPolicy retries permanent 401/400 provider errors |
| 8 | Medium | `src/api.py:54`, `function_app.py:71` | Raw exception text echoed to clients; unescaped f-string JSON breaks on ValidationError |
| 5 | Medium | `src/config.py:52` | `max_rounds >= 9` hits recursion limit → 503 instead of escalated; `<= 0` accepted |
| 10 | Medium | `Dockerfile:28`, `src/api.py:44` | Sync endpoints + no timeout can starve `/health` threadpool → healthcheck restart loop |
| 2 | Medium | `src/agents.py:54` | Empty drafter output burns rounds undetected; list-content → `TypeError` → unretried 503 |
| 9 | Low | `src/api.py:37` | Benign lazy-init race builds duplicate services |

Fallback correctness (task 3) and round-counter integrity under node retries (task 2) both check out clean; secrets (task 7) are clean except the error-echo vector.
