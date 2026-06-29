# Scenario 1: Product Launch Content Pipeline

**Pattern:** Sequential handoff (Agent A → Agent B, single pass)
**Industry:** Consumer Packaged Goods (CPG) / E-commerce
**Difficulty:** Beginner

---

## Business Context

**NorthBay Goods** is a mid-sized CPG company that sells household and kitchen
products through its own Shopify store and on Amazon. The marketing team launches
roughly 30–40 new SKUs per quarter. For each launch, a copywriter has to research
the product (materials, dimensions, competitor positioning) and then write a
storefront description.

Today this takes a copywriter about 45 minutes per product, and the research and
writing are done by the same person — so launches bottleneck whenever the team is
short-staffed. Marketing Ops wants to pilot a two-agent assistant that splits the
job: one agent assembles the facts, a second turns them into on-brand copy.

## The Problem

Separate **research** from **writing** so the two steps can run independently and
the output is consistent across SKUs.

## Agents

| Agent | Role | Input | Output |
|-------|------|-------|--------|
| **A — Researcher** | Pull key product facts and 2–3 differentiators | Product name + raw spec sheet | Structured bullet notes |
| **B — Writer** | Turn notes into storefront copy | Researcher's notes | ~200-word description + 5 bullet highlights |

## Flow

```
Spec sheet ──> [Researcher] ──> notes ──> [Writer] ──> final copy
```

One pass, no looping. The Writer only uses what the Researcher provides.

## Sample Input

> **Product:** NorthBay 12-Cup Pour-Over Carafe
> **Specs:** Borosilicate glass, 1.5L capacity, dishwasher safe, cork lid,
> heat-resistant to 150°C, BPA-free, 8.2 x 8.2 x 22 cm, 480g, $34.99

## Success Criteria

- Researcher output is purely factual (no marketing language).
- Writer copy stays under 220 words and references only the researched facts.
- Brand tone: warm, practical, no superlatives like "best ever."
- No hallucinated specs (e.g., don't invent a warranty that wasn't provided).

## Stretch Goal

Add a simple rule: if the spec sheet is missing capacity or material, the
Researcher flags it as `MISSING` instead of guessing.
