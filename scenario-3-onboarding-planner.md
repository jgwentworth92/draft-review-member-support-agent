# Scenario 3: Warehouse Onboarding Planner

**Pattern:** Planner → Executor (decomposition + step execution)
**Industry:** Logistics / Supply Chain
**Difficulty:** Intermediate

---

## Business Context

**Dematic Regional DC** (a distribution center) hires seasonal warehouse associates
in waves before peak season. Each new hire needs a first-week onboarding plan:
safety induction, equipment certification, system logins, shift assignment, and a
buddy pairing. Today a shift supervisor builds this by hand in a spreadsheet, and
the steps get missed when several people start the same week.

The Ops team wants a two-agent assistant: one agent breaks a high-level onboarding
request into an ordered task list, and a second agent produces the concrete
artifact for each task (a checklist item, a draft message, a form to fill).

## The Problem

Turn a one-line request into a structured plan, then generate the actual outputs
for each step — keeping the *planning* and the *doing* in separate agents.

## Agents

| Agent | Role | Input | Output |
|-------|------|-------|--------|
| **A — Planner** | Decompose request into ordered steps | Onboarding request + role | Numbered task list with dependencies |
| **B — Executor** | Produce the artifact for each task | One task at a time | Concrete output (checklist, draft, form) |

## Flow

```
Request ──> [Planner] ──> task list ──> loop over tasks ──> [Executor] ──> artifacts
```

The Planner runs once. The Executor runs once per task. Keep them decoupled — the
Executor never re-plans, it just executes the task it's handed.

## Sample Input

> **Request:** "Onboard 2 new forklift-certified associates starting Monday on the
> evening shift."

A reasonable Planner output might be:

1. Verify forklift certification on file *(blocks step 4)*
2. Create WMS system logins
3. Schedule safety induction (Mon 3pm)
4. Assign to evening shift roster
5. Pair each with a buddy from current evening crew
6. Send day-one welcome message

## Success Criteria

- Planner output is ordered and notes obvious dependencies.
- Executor produces a usable artifact per task (not just a restatement).
- No step is silently dropped between plan and execution.

## Stretch Goal

Let the Planner mark steps as `auto` (Executor handles) vs `human` (needs a
person), so the Executor only acts on `auto` steps and lists the rest for the
supervisor.
