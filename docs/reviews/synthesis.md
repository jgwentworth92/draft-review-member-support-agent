# Synthesis — Draft-and-Review Agent, Passes 1–3

**Date:** 2026-07-02
**Sources:** `docs/reviews/2026-07-02-invariant-audit.md` (P1), `docs/reviews/2026-07-02-failure-mode-review.md` (P2), `docs/reviews/2026-07-02-maintainability-review.md` (P3)
**Ordering:** invariant violations → failure modes → maintainability. ⚡ = quick win (small, self-contained diff).

---

## Root-cause dedup

Six clusters absorb most of the 25 raw findings:

| Root cause | Absorbed findings | Net severity |
|---|---|---|
| **RC-A — No fail-closed boundary for degraded model output.** Exceptions and `None`/empty/list-shaped model responses escape the graph instead of converting to `escalated`. | P1 1.1, P2 F1, P2 F2 | **High** |
| **RC-B — Config is neither validated nor loaded at startup.** Lazy first-request construction + `extra="ignore"` + no field bounds + uncompiled regexes. | P2 F6, P2 F7, P2 F9, P1 1.2 ≡ P2 F5 (same finding, verbatim), P1 3.1, P3 §4 import-time-logging item | **High** |
| **RC-C — Retry layers stack with no deadline.** SDK retries × fallback × node RetryPolicy × rounds, no timeout anywhere. | P2 F3, P2 F4, P2 F10, P2 §3 caveat (fallback doesn't inherit timeout) | **High** |
| **RC-D — Error responses echo internals.** Raw exception text to clients; hand-built unescaped JSON in the Functions path. | P2 F8 | Medium |
| **RC-E — Credential/injection regexes are document-scoped literals with no request-context.** One exploitable false negative, one systematic false positive, plus expected screen gaps. | P1 5.3, P1 5.4, P1 5.1/5.2 | Medium |
| **RC-F — `ReviewVerdict` is flattened into untyped dicts in graph state.** Three definitions of the same shape; string-key access; `RunResult.status` a bare `str`. | P3 §5 DRY, P3 §6 typing, P1 6.2 | Medium (maintainability) |

Standalone (no shared root cause): P1 6.1 (multi-writer channels), P1 6.3 (revise-with-empty-feedback), P3 §1 (policy in closure), P3 §2 (README credential claim), P3 §4 (tests coupled to prod config), P3 §4 (fallback stubbing).

---

## Pass-3 refactors changed or invalidated by P1/P2 findings

1. **P3 §1 `apply_review_policy` extraction — contract changed by RC-A.** The extracted pure function must accept `verdict_obj=None` (reviewer no-tool-call, P2 F1) or the `None`-raise must live in the chain wrapper *before* `with_fallbacks` composition — otherwise the extraction re-buries the exact bug P2 found. Extraction must also keep the guard override on the path that runs every round (P1 invariant 4).
2. **P3 §4 lifespan refactor — superseded/merged, priority upgraded.** P3 filed "move `configure_logging()` and `_service` global into lifespan" as **Low**. P2 F6/F7/F9 make the same change the fix for two **High** findings. Do it once, at the higher priority; don't schedule it twice.
3. **P3 §2 option (a) (config-extensible `credential_patterns` as `dict[label, regex]`) — constrained by three findings.** If chosen, the new mechanism must: compile regexes in a validator (P2 F6), reject/warn on empty lists (P1 3.1), and bake in the per-sentence "last 4" scoping and request-shaped context (P1 5.3/5.4) rather than porting the current document-wide suppression. Option (b) (README correction) is unaffected and stays a quick win.
4. **P3 §5/§6 un-flatten `ReviewVerdict` in state — sequencing changed by RC-A and P1 6.3.** Adding the `model_validator` ("revise ⇒ non-empty failed_rules") turns today's silent bad rounds into `ValidationError`s, which are **not** node-retried and currently 503. Land the RC-A fail-closed boundary *first*, then the validator, then the un-flattening. Also fold in P1 6.1: while touching state shape, decide reducer vs. last-writer-wins explicitly.
5. **P3 §4 test decoupling — minor update.** The `tests/config.yaml` fixture must be authored against the *stricter* schema from RC-B (`extra="forbid"`, `ge` bounds), and P3's "one test that the production file parses" becomes load-bearing once startup validation exists.
6. **P3 §4 fallback stubbing params — small scope addition.** While adding `drafter_fallback`/`reviewer_fallback` injection, also default the fallback's `timeout` from the primary (P2 §3 caveat), since it's the same constructor path.

No P3 refactor is outright invalidated; #2 is absorbed, #1/#3/#4 need redesign before execution.

---

## Ranked list

### Tier 1 — invariant violations

| Rank | Finding | Sev | Location | Fix |
|---|---|---|---|---|
| 1 | **RC-A: fail-closed exception boundary** (P1 1.1 + P2 F1 + P2 F2) | High | `src/service.py:34-37`, `src/graph.py:75-108` (line 77 `None` crash), `src/agents.py:54,61` | Catch exceptions in `DraftReviewService.run` and return `escalated` `RunResult` with a `model_failure` feedback entry. In `agents.py`: raise a typed error on parser `None` *inside* the chain wrapper (before `with_fallbacks`) so the fallback fires; normalize `message.content` when it is a block list; treat empty/whitespace drafts as raised failures. Reserve 5xx for broken deployments. |
| 2 | ⚡ **`max_rounds` unvalidated** (P1 1.2 ≡ P2 F5 — deduped) | Med | `src/config.py:51-53`, `src/service.py:36` | `max_rounds: int = Field(default=3, ge=1, le=8)` **and** pass `config={"recursion_limit": 3*max_rounds + 4}` to `invoke`. |
| 3 | ⚡ **"last 4" suppression false negative** (P1 5.3) | Med | `src/guards.py:59,65` | Apply suppression per-sentence / within a character window; add `(full|complete|entire|whole)` to the strong-match alternation. |

### Tier 2 — failure modes

| Rank | Finding | Sev | Location | Fix |
|---|---|---|---|---|
| 4 | **RC-B: startup config validation + lifespan build** (P2 F6 + F7 + F9 + P1 3.1; absorbs P3 lifespan item) | High | `src/config.py:72-75`, `src/api.py:22,31,34-40,49`, `function_app.py:34-43` | Build service in a FastAPI lifespan handler (kills bad config at deploy, fixes the 500-vs-503 `Depends` leak and the init race); `ConfigDict(extra="forbid")` on all config models; `Field(ge=...)` bounds; compile guard regexes in a validator; `min_length=1` (or loud warning) on empty pattern lists; move `configure_logging()` into lifespan. |
| 5 | **RC-C: no timeout + retry stacking** (P2 F3 + F4 + F10 + fallback-timeout caveat) | High | `config.yaml:59`, `src/graph.py:20`, `src/config.py:12-24`, `src/api.py:44` | Set `timeout` for both agents *and* fallbacks in shipped config (default/inherit at `AppConfig` level); enforce an overall run deadline around `self._app.invoke`; custom `retry_on` in `RetryPolicy` excluding 4xx `anthropic.APIStatusError`; make `/health` `async def`. |
| 6 | ⚡ **RC-D: error detail echoes internals; broken JSON** (P2 F8) | Med | `src/api.py:54`, `function_app.py:71,83` | Return generic `"Agent run failed"`; keep `logger.exception` server-side; use `json.dumps` in `function_app.py`. |
| 7 | **Mention-vs-request credential false positive** (P1 5.4) | Med | `src/guards.py:28-34` | Request-shaped context, e.g. `(share|provide|send|confirm|reply with|enter)[^.]{0,40}\bpin\b`, or allowlist negated phrasings; LLM rule stays as semantic backstop. |
| 8 | **Injection/credential pattern gaps** (P1 5.1/5.2 — accepted screen quality) | Med (info) | `src/guards.py:3-14,28-68` | `\s+` instead of literal spaces; add `the|your` to ignore-alternation; `cvv2?|cvc`, `passcode`, `personal identification number`; spaced/dashed card-number forms. Batch with #3/#7. |
| 9 | **Revise-with-empty-feedback burns rounds** (P1 6.3) | Low | `src/graph.py:78`, `src/agents.py:23-28`, `src/schemas.py:13-24` | `model_validator` on `ReviewVerdict` ("revise ⇒ failed_rules non-empty; pass ⇒ empty"). **Sequencing: only after #1**, else validator failures 503. |

### Tier 3 — maintainability

| Rank | Finding | Sev | Location | Fix |
|---|---|---|---|---|
| 10 | ⚡ **README overpromises `credential_patterns` config** (P3 §2) | Med | `README.md:103`, `src/guards.py:42-68` | Option (b) now: correct README to "built-in checks; config can only disable." Option (a) (true config extensibility) → backlog with RC-E constraints (see flag #3 above). |
| 11 | **Compliance policy buried in `reviewer_node` closure** (P3 §1 + §4-closures) | Med | `src/graph.py:75-108` | Extract pure `apply_review_policy(verdict_obj, draft, cred_patterns)` into `guards.py`/`policy.py`; must handle `verdict_obj=None` per flag #1. Lift `route_after_review` to module level taking `max_rounds`. Unit-test directly. |
| 12 | **Tests coupled to production `config.yaml`** (P3 §4) | Med | `tests/test_loop.py:6-7` | Pinned `AppConfig` fixture / `tests/config.yaml` (authored against the post-RC-B strict schema); keep one test asserting the production file parses. |
| 13 | **RC-F: un-flatten `ReviewVerdict`; typed state** (P3 §5+§6 + P1 6.2 + P1 6.1) | Med | `src/graph.py:72,77,96-102,111,113`, `src/schemas.py:30,36-48,56-61`, `src/agents.py:24` | Keep `ReviewVerdict`/`list[FailedRule]` in graph state; one typed helper for history records; `RunResult.status: Literal["pending_human_review", "escalated"]` (turns invariant 1 into an enforced contract); decide reducers vs. last-writer-wins for `status`/`verdict`/`feedback`/`history` while touching state. **After #1 and #9.** |
| 14 | ⚡ **Fallback models can't be stubbed** (P3 §4) | Low | `src/service.py:17-28` | Optional `drafter_fallback`/`reviewer_fallback` params; default fallback `timeout` from primary while there. |
| 15 | ⚡ **Trivia** (P3 §6) | Triv | `src/guards.py:26`, `src/graph.py:38-44` | Move `import re` to top; annotate model params as `BaseChatModel`/`Protocol`; `initial_state` → `GraphState`. |

---

## Act now

Highest-severity items plus quick wins whose diff is small enough to land immediately.

1. **Fail-closed exception boundary** — `src/service.py:34-37`, `src/graph.py:77`, `src/agents.py:54,61`. Catch in `DraftReviewService.run` → `escalated` + `model_failure` feedback; typed raise on parser `None` before `with_fallbacks`; normalize block-list content; empty draft = failure. *(Rank 1 — restores invariants 1 & 5; single highest-leverage fix, converts the whole crash class into the promised state.)*
2. ⚡ **Validate `max_rounds` + recursion limit** — `src/config.py:51-53`, `src/service.py:36`. `Field(ge=1, le=8)` + `recursion_limit = 3*max_rounds + 4`. *(Rank 2)*
3. ⚡ **Fix "last 4" suppression** — `src/guards.py:59,65`. Per-sentence/window suppression; add `(full|complete|entire|whole)` to strong match. *(Rank 3 — the one exploitable guard false negative.)*
4. **Startup validation + lifespan build** — `src/config.py:72-75`, `src/api.py:22,31,34-40,49`, `function_app.py:34-43`. Lifespan-built service; `extra="forbid"`; field bounds; compile regexes; guard empty pattern lists; logging into lifespan. *(Rank 4 — one change closes P2 F6, F7, F9, P1 3.1 and the P3 lifespan item.)*
5. **Timeouts + retry discipline** — `config.yaml:59`, `src/graph.py:20`, `src/config.py:12-24`, `src/api.py:44`. Ship timeouts (fallbacks inherit); run-level deadline; `retry_on` excluding 4xx; `/health` async. *(Rank 5 — ends the 108-attempt / threadpool-starvation / restart-loop chain.)*
6. ⚡ **Sanitize error responses** — `src/api.py:54`, `function_app.py:71,83`. Generic detail; `json.dumps`. *(Rank 6 — the one live internal-detail leak vector.)*
7. ⚡ **Correct README on `credential_patterns`** — `README.md:103`. State that credential checks are built-in and config only disables them. *(Rank 10, option (b) — five-minute doc fix for the only doc/code contract break.)*

## Backlog

Ordered; sequencing notes are binding.

1. **Request-shaped credential context** (Rank 7) — `src/guards.py:28-34`. Fixes the "never share your PIN" → forced-escalation pipeline. Batch with item 2 below.
2. **Regex screen-quality batch** (Rank 8) — `src/guards.py:3-14,28-68`. `\s+`, `the|your` alternation, `cvv2?|cvc`, `passcode`, spaced card numbers. Accepted-screen posture; do in one pass with backlog item 1.
3. **`ReviewVerdict` consistency validator** (Rank 9) — `src/schemas.py:13-24`. Revise ⇒ non-empty `failed_rules`. **Requires Act-now #1 first** (validator failures must escalate, not 503).
4. **Extract `apply_review_policy`** (Rank 11) — `src/graph.py:75-108` → `guards.py`/`policy.py`. Contract must handle `verdict_obj=None` (see flag #1); lift `route_after_review` to module level; add direct unit tests.
5. **Decouple tests from prod config** (Rank 12) — `tests/test_loop.py:6-7`. Pinned fixture against the strict post-RC-B schema + one prod-file-parses test.
6. **Un-flatten state / typed plumbing / `Literal` status** (Rank 13) — `src/graph.py`, `src/schemas.py`, `src/agents.py:24`. Keep Pydantic objects in state; typed history helper; `RunResult.status` as `Literal`; decide reducer policy (P1 6.1). **After Act-now #1 and backlog #3.**
7. **Config-extensible credential patterns, option (a)** (Rank 10a) — `src/guards.py:42-68`, `src/config.py:56-62`. Only if the checklist is expected to grow; must satisfy RC-E constraints (compiled-at-load, empty-list guard, windowed suppression, request-shaped context).
8. ⚡ **Fallback injection params + timeout inheritance** (Rank 14) — `src/service.py:17-28`.
9. ⚡ **Trivia** (Rank 15) — `src/guards.py:26` import placement; `BaseChatModel`/`Protocol` annotations; `initial_state` return type.
