# ADR-013: Free-tier provider stack (Gemini Flash generator + Groq judge)

- **Status:** accepted
- **Date:** 2026-10-02
- **Deciders:** Pritam Das

## Context

The plan was written around Azure OpenAI (generator) and Langfuse
(observability). The goal for this public build is **zero marginal cost** using
only freely available keys. The available keys are: Google AI Studio (Gemini),
Groq, LangSmith and Hugging Face. All provider access is routed through LiteLLM
(ADR-011), so the concrete models are configuration, not code.

Connectivity was verified against the live APIs on 2026-10-02.

## Options considered

1. **Azure OpenAI generator + Langfuse** (plan default) — not free; no Azure key
   available for day-to-day development.
2. **Gemini generator + Groq judge + LangSmith** — all free tiers; satisfies the
   "judge is a different model family from the generator" rule (ADR-010).
3. **Single provider for everything** — fails ADR-010 (judge self-preference
   bias) and concentrates rate-limit risk.

## Decision

- **Router + drafter:** `gemini/gemini-3.8-flash`.
- **Judge:** `groq/openai/gpt-oss-120b` (different family; 120B).
- **Tracing:** LangSmith (this reverses ADR-012's "Langfuse over LangSmith").

## Consequences

- Positive: fully free; LiteLLM keeps providers swappable; ADR-010 preserved.
- Trade-off: **Gemini Pro is `limit: 0` on this free tier** — only Flash-class
  models work for free, so the drafter is Flash rather than a Pro-tier model.
  Gemini `2.x` models are also blocked for new users; the `3.x` line is required.
- Trade-off: the key labelled "Grok/xAI" by the user is in fact a **Groq**
  (`gsk_...`) key; the environment variable is `GROQ_API_KEY`, not `XAI_API_KEY`.
- Revisit if stronger drafts are needed for free: swap the drafter to
  `groq/openai/gpt-oss-120b` and move the judge to `gemini/gemini-3.8-flash`.
