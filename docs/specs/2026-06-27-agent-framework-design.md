# Design: Multi-Scenario Agent Framework on Azure Functions

**Date:** 2026-06-27
**Status:** Approved (design) — pending implementation plan
**Goal:** Portfolio / demonstration — show four canonical agent patterns deployed
cleanly on the existing serverless architecture, with a thin shared core that
makes the reuse visible without burying the patterns under indirection.

---

## 1. Context

The repo currently implements **Scenario 2 (Customer Email Quality Loop)** as a
flat `src/` package: a LangGraph drafter→reviewer critique loop, exposed via
FastAPI (`src/api.py`) and Azure Functions (`function_app.py`), deployed to a
Flex Consumption Function App (`draft-review-func-95005`).

We are generalizing this into a framework that hosts all four scenarios as
separate HTTP endpoints in the same Function App.

The four scenarios reduce to **three topologies**:

| Scenario | Pattern | Topology | Status |
|----------|---------|----------|--------|
| 1 — Content Pipeline | Research → Write | sequential, single pass | new |
| 2 — Quality Loop | Draft → Review | critique loop w/ stop | built (relocate) |
| 3 — Onboarding Planner | Plan → Execute | planner + per-task fan-out | new |
| 4 — Policy Q&A | Retrieve → Respond | sequential + grounding check | new |

Scenarios 1 and 4 share the sequential topology; their difference is per-scenario
nodes/prompts/hardening, not wiring.

## 2. Decisions (from brainstorming)

- **Abstraction level:** thin shared core + four self-contained, legible scenario
  pipelines. NOT a generic config-driven graph engine.
- **Reuse strategy (Approach A):** the core provides three reusable *topology
  builders*; each scenario supplies its own nodes/state/schemas and calls one
  builder.
- **Hardening:** reusable safety/resilience lives in the core; each scenario
  opts into only what its pattern needs.
- **Endpoints:** one Function App, four HTTP routes, organized with Azure
  Functions Blueprints (one blueprint module per scenario).

## 3. Module Architecture

```
src/
  core/
    config.py        # base ModelConfig / AgentConfig / GuardConfig / RetryConfig / LoopConfig
    models.py        # build_model (unchanged)
    guards.py        # scan_input / scan_output (unchanged, now opt-in per scenario)
    nodes.py         # node factories: text_agent_node, structured_agent_node, guard_node
    topologies.py    # the three builders
    service.py       # PipelineService base: build models + graph once, .run(input) -> result
    runtime.py       # shared helpers: retry-policy mapping, logging config
  scenarios/
    content/         { schemas.py, agents.py, graph.py, config.yaml }   # Scenario 1
    quality/         { schemas.py, agents.py, graph.py, config.yaml }   # Scenario 2 (relocated)
    onboarding/      { schemas.py, agents.py, graph.py, config.yaml }   # Scenario 3
    policy/          { schemas.py, agents.py, graph.py, config.yaml }   # Scenario 4
  api/
    routes.py        # shared route helper: validate input -> service.run -> JSON, PII-safe logging
    blueprints.py    # one func.Blueprint per scenario
function_app.py      # registers the four blueprints + /api/health
```

### Core topology builders

Each builder takes scenario-supplied node callables and returns a compiled
LangGraph. Signatures (illustrative):

```python
def sequential_pipeline(state_type, *, first, second) -> CompiledGraph:
    # START -> first -> second -> END                       (Scenarios 1, 4)

def critique_loop(state_type, *, generator, reviewer, route, max_rounds,
                  guard=None) -> CompiledGraph:
    # [guard?] -> generator -> reviewer -> (pass|revise|escalate); loop to max_rounds   (Scenario 2)

def planner_executor(state_type, *, planner, executor, task_selector) -> CompiledGraph:
    # planner -> fan-out over selected tasks -> executor per task -> collect             (Scenario 3)
```

`guard=` on `critique_loop` (and a grounding check on the sequential path) is how
pattern-appropriate hardening is wired: Scenario 2 passes injection+credential
guards; Scenario 4 passes a grounding check; Scenarios 1/3 pass what they need or
nothing.

### Core node factories

Generalize today's `build_drafter` / `build_reviewer` into reusable factories so
each scenario's `agents.py` stays small:

```python
text_agent_node(model, system_prompt, format_fn, fallback=None)        -> node
structured_agent_node(model, schema, system_prompt, format_fn, fallback=None) -> node
guard_node(patterns, on_hit_status, ...)                               -> node
```

### Core service base

```python
class PipelineService:
    """Build models from config + compile graph ONCE; run many inputs."""
    def __init__(self, config, graph_builder): ...
    @classmethod
    def from_config_path(cls, path): ...
    def run(self, input_model) -> result_model: ...
```

Each scenario provides a thin subclass/factory binding its config schema, graph
builder, and input/result mapping. Tests inject stub models (no API key), exactly
as today.

## 4. Per-Scenario Mapping

### Scenario 1 — Content (`sequential_pipeline`)
- **Input:** `{ product_name, spec_sheet }`
- **Nodes:** Researcher (structured → `{ facts[], differentiators[], missing[] }`),
  Writer (notes → `{ copy, highlights[] }`).
- **Output:** `{ notes, copy, highlights[], missing[] }`
- **Hardening:** optional input (injection) guard. Stretch: Researcher flags
  `missing` when capacity/material absent instead of guessing.
- **Route:** `POST /api/content`

### Scenario 2 — Quality (`critique_loop`) — relocated, behavior preserved
- **Input:** `{ member_message, case_notes }`  → **Output:** today's `RunResult`.
- **Hardening:** full — injection guard, credential guard, node retries, model
  fallbacks, structured verdict, round history.
- **Routes:** `POST /api/quality` (primary) and `POST /api/draft` (alias kept so
  the deployed endpoint and `scripts/call_draft.py` keep working).

### Scenario 3 — Onboarding (`planner_executor`)
- **Input:** `{ request, role }`
- **Nodes:** Planner (→ ordered `tasks[] { step, description, depends_on[], mode:
  auto|human }`), Executor (one task → artifact). Executor acts only on `auto`
  tasks (stretch goal built in); `human` tasks are listed for the supervisor.
- **Output:** `{ tasks[], artifacts[] }`
- **Fan-out:** builder maps the executor over selected tasks and collects
  artifacts; no task silently dropped.
- **Route:** `POST /api/onboarding`

### Scenario 4 — Policy (`sequential_pipeline` + grounding check)
- **Input:** `{ question, handbook }`
- **Nodes:** Retriever (→ `snippets[] { text, section, confidence }`), Responder
  (answer only from snippets; "not found in handbook" is valid).
- **Output:** `{ answer, citations[], found, confidence }`
- **Hardening:** grounding check — answer must cite a retrieved section; low
  retriever confidence makes the Responder hedge (stretch goal).
- **Route:** `POST /api/policy`

## 5. Configuration

One `config.yaml` per scenario under `scenarios/<name>/`, each loaded by that
scenario's service. The existing root `config.yaml` migrates to
`scenarios/quality/config.yaml`. Shared base config types (`ModelConfig`,
`AgentConfig`, `GuardConfig`, `RetryConfig`, `LoopConfig`) live in `core/config.py`;
each scenario defines its own small config schema composed from them (e.g.
`ContentConfig { researcher: AgentConfig, writer: AgentConfig, guards }`).

## 6. Error Handling

- **Transient model errors:** provider SDK retries (existing `max_retries`), plus
  optional LangGraph node `RetryPolicy` (existing `_retry_policy`, moved to
  `core/runtime.py`).
- **Model fallbacks:** existing `with_fallbacks` pattern, available via the node
  factories.
- **Guards:** opt-in nodes; on hit, short-circuit to an escalate/blocked terminal
  state with a structured reason (as Scenario 2 does today).
- **API layer:** a shared `api/routes.py` helper validates the scenario's input
  schema (`422` on failure), runs the service (`503` on run failure), and logs
  outcome only — never input/output bodies (PII-safe), matching today's
  `function_app.py`.

## 7. Testing

- **Core topology builders:** unit tests with trivial fake nodes — sequential
  ordering, loop stop conditions (pass / max-rounds escalate), fan-out covers all
  selected tasks and drops none.
- **Per-scenario:** service tests with injected stub models (no API key), one per
  scenario, asserting the pattern's contract (e.g. Scenario 1 references only
  researched facts; Scenario 4 answers "not found" when snippets lack the answer).
- **Guards:** existing tests retained.
- **Routes:** one test per blueprint exercising the handler with a stub-backed
  service.
- **Regression:** relocated Scenario 2 tests stay green; behavior unchanged.

## 8. Deployment

- `function_app.py` registers four blueprints → `/api/{content,quality,onboarding,
  policy}` plus `/api/health`. Same Flex Consumption app, OIDC CI/CD unchanged.
- All scenarios share the one `ANTHROPIC_API_KEY` app setting (already set).
- `.funcignore` already excludes tests/venv; per-scenario `config.yaml` files ship
  in the package.
- `auth_level=FUNCTION` retained for all routes.

## 9. Migration / Sequencing Notes

Moving `src/*.py` into `src/core` + `src/scenarios/quality` changes imports
(`src.service` → `src.scenarios.quality.service`, etc.). `function_app.py`,
`src/api.py`, and the existing tests must update accordingly. The implementation
must sequence so **Scenario 2 stays green and deployable throughout**:

1. Stand up `core/` (move models/guards/config; add nodes, topologies, service,
   runtime) with unit tests.
2. Relocate Scenario 2 onto `critique_loop`; keep `/api/draft` alias; prove
   regression green.
3. Add Scenarios 1, 4 (sequential), then 3 (planner/executor) as **independent
   subagent tasks** — each is a self-contained package + blueprint + tests.
4. Register all blueprints; update FastAPI app similarly; deploy.

## 10. Out of Scope (YAGNI)

- Generic config-driven graph engine.
- Vector DB / real retrieval for Scenario 4 (handbook passed inline, by design).
- Per-scenario separate Function Apps or infrastructure.
- Auth beyond the existing function key.
