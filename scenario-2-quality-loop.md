# Scenario 2: Customer Email Quality Loop

**Pattern:** Generator → Reviewer critique loop (with stopping condition)
**Industry:** Financial Services / Retail Banking
**Difficulty:** Beginner–Intermediate

---

## Business Context

**Meridian Credit Union** runs a member-support team that replies to everyday
inquiries — disputed charges, card replacements, statement questions. Because
these are financial communications, replies must be accurate, plain-language, and
compliant: no guarantees about timelines the CU can't honor, no requests for full
card numbers or passwords over email, and a calm, professional tone even when the
member is frustrated.

New support reps often get the facts right but the *tone or compliance* wrong on
the first try. The team lead currently reviews every draft manually. Operations
wants a two-agent helper that drafts the reply and then self-reviews it against a
short checklist before a human sees it.

## The Problem

Build a draft-then-review loop that catches tone and compliance issues
automatically, and knows when to stop.

## Agents

| Agent | Role | Input | Output |
|-------|------|-------|--------|
| **A — Drafter** | Write a reply to the member | Member's message + case notes | Draft email |
| **B — Reviewer** | Score the draft against a checklist | Draft email | `PASS` or `REVISE` + specific reasons |

## Flow

```
Member message ──> [Drafter] ──> draft ──> [Reviewer]
                       ^                        |
                       |                        v
                       └──── REVISE (reasons) ──┘   (max 3 rounds)
                                                └──> PASS ──> human
```

Stop when the Reviewer returns `PASS` **or** after 3 rounds — whichever comes
first. If still failing after 3 rounds, escalate to a human with the reasons.

## Reviewer Checklist

1. Plain language — no unexplained jargon.
2. No promised timelines unless given in case notes.
3. Never asks for full card number, PIN, or password.
4. Empathetic, professional tone.
5. Clear next step for the member.

## Sample Input

> **Member message:** "I see a $58 charge from 'SQ *BREW HOUSE' I don't recognize
> and I'm really upset. Fix this now."
> **Case notes:** Dispute can be filed; provisional credit in 10 business days;
> member must confirm last 4 digits of card.

## Success Criteria

- Loop terminates correctly (PASS or 3-round cap).
- Reviewer reasons are specific and actionable, not vague.
- Final email never violates a checklist rule.

## Stretch Goal

Have the Reviewer return a structured object (`{verdict, failed_rules[], notes}`)
so the loop logic reads the verdict programmatically instead of parsing prose.
