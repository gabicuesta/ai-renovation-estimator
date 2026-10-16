# ADR 0003: Multi-provider through thin HTTP adapters, without vendor SDKs

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

We want to compare Anthropic, OpenAI and Google on the same task. Each vendor has its own SDK, its own release cadence and its own way of producing structured output:

- **Anthropic:** forced tool calls.
- **OpenAI:** the Responses API with `json_schema`.
- **Gemini:** JSON mode with a schema dialect that supports only part of JSON Schema.

Generic abstraction libraries add another layer that can hide differences that matter, such as token usage, errors and image handling.

## Decision

- One `Provider` protocol with a single method, `generate(system, prompt, images, schema)`.
- Three adapters of about 60 lines each, written directly against the HTTP APIs with `httpx`.
- The schema is sent **self-contained**, with `$ref`s inlined, because that is the most portable form across vendors.
- All validation and the repair retry live in the estimator, so every model is held to the same bar.
- Tests check each adapter's wire format with `httpx.MockTransport`.

## Consequences

- No vendor lock-in, few dependencies, and the comparison is fair.
- Adding a provider means writing one small file.
- We own maintenance when an API changes. The wire-format tests make those breaks loud and local.
