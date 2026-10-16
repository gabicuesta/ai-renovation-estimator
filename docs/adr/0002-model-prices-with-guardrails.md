# ADR 0002: Unit prices from the model, with guardrails and evals

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

A real estimating tool would anchor prices in a price database. But the good Spanish ones (CYPE, BEDEC and others) are licensed and can't be published in an open repository, and a home-made catalogue would be small and go stale quickly.

## Decision

- Unit-price ranges come from the model, conditioned on the province and the quality level.
- Ranges are required: there are no point prices, so uncertainty is visible.
- Guardrails (see ADR 0001) catch the failures that cost the most, such as unit mistakes and absurd quantities.
- An eval set with reference ranges measures how far each model's price knowledge goes, and lets us notice when it drifts.

## Consequences

- The project is fully open and runs with nothing but an API key.
- Accuracy is bounded by what each model knows about the Spanish market, which is exactly what the evals are for.
- The roadmap keeps an optional price catalogue, updated with INE construction cost indices, as the next step.
