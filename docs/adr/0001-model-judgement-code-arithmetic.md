# ADR 0001: The model decides *what*, code computes *how much*

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

An estimate mixes two kinds of work:

- **Judgement:** what the job involves, how much of each item and roughly what each unit costs.
- **Arithmetic:** line totals, subtotals, VAT and aggregate confidence.

LLMs are good at the first and unreliable at the second. A single wrong sum makes the whole estimate untrustworthy, and nobody can see it.

## Decision

- The model output schema (`DraftEstimate`) has **no totals at all**. It holds quantities, unit-price ranges, confidence, the basis for each item, assumptions, questions and risks.
- `pricing.py` computes every total and adds **deterministic checks**:
  - Swapped ranges
  - Unit-price outliers, which usually mean a unit mistake
  - Quantities that don't match the declared area
  - Missing companion trades, e.g. demolition without waste removal
  - Very wide ranges
  - Low cost-weighted confidence
- Checks are returned to the user rather than hidden, so a weak estimate looks weak.

## Consequences

- Totals are always internally consistent.
- The model's work can be audited line by line.
- The checks are heuristics: they can raise false alarms and they can't prove an estimate right.
