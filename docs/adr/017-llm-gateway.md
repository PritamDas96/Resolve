# ADR-017: Hand-rolled LLM gateway instead of LiteLLM

- **Status:** accepted
- **Date:** 2026-10-04
- **Deciders:** Pritam Das

## Context

The agent needs a provider-agnostic way to call the drafter/router (Gemini) and the
judge (Groq), with structured JSON output, token/cost capture, and a deterministic
fake for tests and CI. The plan suggested LiteLLM. This environment has already shown
that heavy native/transitive dependencies are risky here (onnxruntime segfaults,
ADR-002), and CI must run the agent path without network or API quota.

## Options considered

1. **LiteLLM** — broad provider coverage and built-in fallbacks/cost, but a large
   transitive dependency surface and another moving part to pin; the fake/record path
   is less direct.
2. **Thin hand-rolled gateway over httpx** — Gemini + Groq by model prefix, structured
   output with one repair retry, token capture, and a trivially deterministic
   `FakeGateway`. More code we own; fewer dependencies.

## Decision

Build a thin `llm/gateway.py` over `httpx` (already a dependency) with a `Gateway`
protocol, `HttpGateway` (Gemini + Groq), and `FakeGateway` for offline tests. The API
key is sent via headers (never the URL) and transient 5xx/429 are retried with backoff
(see FAILURES F-002/F-003).

## Consequences

- Positive: no new heavy deps; CI runs the full agent + API path with the fake (no
  quota); structured-output + repair logic is in one place; key never leaks into URLs.
- Negative / trade-offs: we maintain the provider request/response mapping ourselves,
  and lack LiteLLM's breadth of providers and routing features.
- Follow-ups: add provider fallbacks and a per-model price table if cost reporting
  needs to be exact; revisit LiteLLM if provider count grows.
