# Scenario 4: Policy Q&A Assistant

**Pattern:** Retriever → Responder (grounded answers / basic RAG)
**Industry:** Healthcare / HR Operations
**Difficulty:** Intermediate

---

## Business Context

**Cedar Valley Health System** has ~4,000 employees and an HR shared-services desk
that fields the same benefits and policy questions over and over: PTO accrual,
parental leave, shift-differential pay, the tuition reimbursement cap. The answers
all live in a 60-page Employee Handbook, but staff often answer from memory and
sometimes get it wrong — which, for things like leave eligibility, creates real
compliance risk.

HR wants a two-agent assistant that answers questions **only** from the official
handbook, never from general knowledge, and points back to the section it used.
This is a deliberately simple "RAG without a vector database" — the document is
small enough to pass in directly.

## The Problem

Answer employee questions grounded strictly in a provided document, with the
retrieval step kept separate from the answering step.

## Agents

| Agent | Role | Input | Output |
|-------|------|-------|--------|
| **A — Retriever** | Find the relevant passage(s) | Question + handbook text | 1–3 quoted snippets + section refs |
| **B — Responder** | Answer using only the snippets | Question + retrieved snippets | Plain-language answer + citation |

## Flow

```
Question ──> [Retriever] ──> relevant snippets ──> [Responder] ──> grounded answer
```

The Responder is forbidden from using anything outside the snippets. If the
snippets don't contain the answer, it must say so rather than guess.

## Sample Document (excerpt)

> **§4.2 PTO Accrual.** Full-time employees accrue 1.5 PTO days per month
> (18 days/year). Accrual begins on the first of the month following hire date.
> Unused PTO above 10 days does not roll over past Dec 31.
>
> **§6.1 Tuition Reimbursement.** Eligible after 12 months of service. Reimburses
> 80% of tuition up to $5,250 per calendar year for approved programs.

## Sample Questions

- "How many PTO days do I get per year?"
- "Can I get tuition help in my first month?" *(answer: no — 12-month rule)*
- "What's the parental leave policy?" *(if not in excerpt → "not found in handbook")*

## Success Criteria

- Responder answers only from retrieved snippets — no outside knowledge.
- Every answer includes the section reference (e.g., §4.2).
- "Not in the document" is an acceptable and expected answer.

## Stretch Goal

Have the Retriever return a confidence flag. If confidence is low, the Responder
hedges ("the handbook doesn't directly address this, but §X mentions...") instead
of answering firmly.
