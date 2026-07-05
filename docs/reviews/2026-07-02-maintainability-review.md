# Maintainability Review — Draft-and-Review Agent

**Repo:** `agenter_review_06_26_2026` · **Branch:** `master` · **Date:** 2026-07-02
**Scope:** Single Responsibility, Open/Closed (config-only claims), dependency direction, testability, DRY, typing & dead code. Safety and failure modes were reviewed separately and are excluded. The bar is "easy to change, easy to test," not "maximally abstracted."

---

## Verdict

The architecture is genuinely clean for its size — dependency direction is correct, `DraftReviewService` is a proper composition root, and guards are pure functions with standalone tests. The findings below are mostly medium/low. The one thing worth fixing soon is the **credential-guard config claim**: the README promises config-only extensibility the code doesn't deliver.

### Findings at a glance

| # | Severity | Area | Finding |
|---|----------|------|---------|
| 1 | **Medium** | Open/Closed | `guards.credential_patterns` is not config-extensible; README implies it is |
| 2 | **Medium** | SRP | Compliance business rules live inside `reviewer_node` closure in the graph module |
| 3 | **Medium** | Testability | Deterministic test suite is coupled to production `config.yaml` |
| 4 | **Medium** | DRY | Review/round shape is defined ~three times (`ReviewVerdict` → flattened state → `from_state` rehydration) |
| 5 | Low/Med | Testability | Node functions and routers are closures — untestable in isolation |
| 6 | Low | Testability | `configure_logging()` at import time; module-level `_service` global |
| 7 | Low | Testability | Fallback models cannot be stubbed through the service |
| 8 | Low | Typing | Untyped dict plumbing where `FailedRule` / `RoundRecord` models exist |
| 9 | Low | Typing | Untyped model params on `build_app` / `build_drafter` |
| 10 | Trivial | Style | Mid-file `import re`; `initial_state` returns `dict` not `GraphState` |

---

## 1. Single Responsibility

**Medium — compliance business rules live inside the graph module's node closures.**
`reviewer_node` (`src/graph.py:75–108`) does two jobs: graph orchestration *and* the two most important business rules in the system —

- "pass is enforced in code, not trusted from the LLM" (line 78)
- "output guard overrides an LLM pass" (lines 81–87)

These policies are buried in an inline closure inside `build_app`, so the graph module owns compliance logic that belongs beside the guards.

> **Refactor:** extract a pure function, e.g. `apply_review_policy(verdict_obj, draft, cred_patterns) -> tuple[str, list[dict]]`, into `src/guards.py` or a small `policy.py`; `reviewer_node` calls it and updates state. This also fixes the biggest testability gap (§4).

**No finding on the API layer.** The `/draft` handler (`src/api.py:48–58`) is genuinely thin: validate (delegated to Pydantic), call the service, map failure to 503, log outcome. No business logic. Same for `function_app.py`. The config / guards / models / service / api split is otherwise correct.

---

## 2. Open/Closed — verifying the README's config-only claims

**Verified true ✅**

- Swapping model, provider, temperature, or prompt for either agent is config-only (`src/models.py:9–25` passes `ModelConfig` straight to `init_chat_model`).
- `max_rounds`, node retry (`loop.retry`), and fallback models — all config-only as claimed.
- `guards.injection_patterns` are real regexes read from config (`src/guards.py:37–39`), so **adding** an injection pattern is config-only.

**Medium — `guards.credential_patterns` is not config-extensible, but the README implies it is.**
`README.md:103` says config can "override the defaults" for `credential_patterns`, symmetric with `injection_patterns`. But `scan_output` (`src/guards.py:42–68`) treats the config values as an **allowlist of fixed label names** — the detection regexes are hardcoded in `_CREDENTIAL_RULES`, plus special-case blocks for card/account numbers. Via config you can only *disable* built-in checks; adding a new credential pattern (say, "date of birth") silently does nothing without editing `guards.py`. The `scan_output` docstring admits this; the README doesn't.

> **Refactor (pick one):**
> **(a)** Make `credential_patterns` a `dict[label, regex]` in `GuardConfig` so new checks really are config-only, keeping the last-4 exemption logic for the two special labels.
> **(b)** Cheaper — correct the README to say credential checks are built-in and config can only turn them off.
>
> Given "easy to change" as the bar, (b) is defensible; (a) is a small change if the checklist is expected to grow.

---

## 3. Dependency direction

**Clean — no findings.** Verified via imports:

- `src/service.py` imports only `config`, `graph`, `models`, `schemas` — **no FastAPI anywhere below the API layer**.
- `graph` does not import `service`. `api → service` is one-way. `schemas` is a dependency leaf. No cycles.
- The library path (`DraftReviewService`) transitively pulls only langchain / langgraph / pydantic / yaml, so it works with FastAPI uninstalled — the README's "Use as a library" claim holds.

One trivial oddity: `src/config.py:9` imports `guards` just to seed defaults. Acceptable (it's data, not behavior) — not worth changing.

---

## 4. Testability

**Fundamentals are right:** models are injected into `DraftReviewService` and `build_app` (never constructed inside nodes); guards are pure and tested standalone (`tests/test_guards.py`); the `ScriptedModel` stub proves the no-API-key suite works.

**Medium — the deterministic suite is coupled to production `config.yaml`.**
`tests/test_loop.py:6–7` loads the real `config.yaml`, and `test_escalate_after_three_revises` hardcodes three scripted revisions. If someone legitimately changes `loop.max_rounds` in production config, unit tests break — or worse, `ScriptedModel` raises "ran out of responses" mid-graph.

> **Refactor:** build an `AppConfig` fixture in test code (or a `tests/config.yaml`) with pinned `max_rounds`; keep one separate test asserting the production file parses.

**Low/Medium — node functions and routers are untestable in isolation.**
Everything in `build_app` is a closure, so the only way to test `route_after_review` or the verdict-override rule is to run the whole compiled graph with scripted models (`tests/test_loop.py` does exactly this). Fine for most nodes at this size, but the policy logic flagged in §1 deserves direct unit tests.

> **Refactor:** the §1 extraction solves it; also consider lifting `route_after_review` to a module-level function taking `max_rounds` as a parameter.

**Low — import-time side effect in the API module.**
`src/api.py:22` calls `configure_logging()` at import, mutating global logging state for any test that imports the app. Related: the module-level `_service` global (`src/api.py:31`, mirrored in `function_app.py:34`) is cross-test shared state; tests currently dodge it via dependency override.

> **Refactor:** move `configure_logging()` into a FastAPI lifespan handler; hold the service on `app.state` instead of a module global.

**Low — fallback models can't be stubbed through the service.**
`DraftReviewService.__init__` (`src/service.py:17–28`) accepts injected primaries but always calls `build_model()` for configured fallbacks, so any test config with a `fallback:` block forces real client construction.

> **Refactor:** add optional `drafter_fallback` / `reviewer_fallback` params mirroring the primaries.

---

## 5. DRY

**Good news first:** there is exactly one response model — `RunResult` is returned by the service, used as FastAPI's `response_model`, and serialized by the Azure function. No duplicated API schema. ✅

**Medium — the review/round shape is defined ~three times.**

1. `ReviewVerdict` (Pydantic) is flattened into `GraphState` as separate `verdict` / `feedback` / `notes` keys, with `FailedRule` dumped to raw dicts (`src/graph.py:77`).
2. The history record dict is hand-built in `reviewer_node` (`src/graph.py:96–102`), duplicating the keys `RoundRecord` (`src/schemas.py:56–61`) already declares.
3. `RunResult.from_state` (`src/schemas.py:37–48`) re-hydrates a `ReviewVerdict` from the flattened keys.

Adding one field to `ReviewVerdict` means touching three files.

> **Refactor:** keep the `ReviewVerdict` object (or at least `list[FailedRule]`) in graph state instead of flattening to dicts — LangGraph state handles Pydantic values fine — and build history records through one typed helper. That collapses the round-trip in `from_state` to attribute access.

**Low (optional) —** the `/draft` handlers in `src/api.py` and `function_app.py` duplicate the run → 503 → PII-safe-log sequence. Two deployment targets justify it at this size; only extract if a third frontend appears.

*Per review scope: drafter/reviewer prompt and config repetition is deliberate and fine — no finding.*

---

## 6. Typing and dead code

- **Low — untyped dict plumbing where models exist** (same root as §5): `feedback: Optional[list[dict]]` in `GraphState`, `history: list[dict]` in `RunResult`, and `f['rule']` / `f['reason']` string-key access in `src/agents.py:24`. `FailedRule` and `RoundRecord` already exist — use them in the annotations and the key-typo class of bug becomes a type error.
- **Low — untyped model parameters:** `build_app(config, drafter_model, reviewer_model, …)` (`src/graph.py:38–44`) and `build_drafter(model, …)` take bare untyped params; annotate as `BaseChatModel` (already imported in `src/models.py`). Duck-typing keeps the stub working — `ScriptedModel` doesn't subclass it, so either use a `Protocol` or accept the annotation as documentation.
- **Trivial —** `import re` sits mid-file at `src/guards.py:26` after the constant blocks; move to the top. `initial_state` returns `dict` where `GraphState` would do.
- **No dead code found.** Every config option (`timeout`, `max_retries`, `RetryConfig`, `fallback`) is consumed; `RoundRecord` is annotation-only but legitimately used in `GraphState`; `scripts/try_agent.py` is a live smoke test; `conftest.py`'s warning shim is documented and self-expiring.

---

## Priority order

1. **Fix the README / `credential_patterns` mismatch (§2)** — the only place the docs promise something the code doesn't deliver.
2. **Extract the review policy from `reviewer_node` (§1)** — one small pure function fixes the SRP smell and makes the highest-value logic directly testable.
3. **Decouple tests from production `config.yaml` (§4).**
4. **Un-flatten `ReviewVerdict` in graph state (§5/§6)** — do opportunistically; it touches the most files for the least urgent payoff.
