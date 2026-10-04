# ADR-009: Reranking and parent-child expansion

- **Status:** accepted
- **Date:** 2026-10-04
- **Deciders:** Pritam Das

## Context

Hybrid search returns ~20 candidates; the drafter should see a small, highly relevant
set. The plan called for benchmarking two cross-encoder rerankers vs none and
choosing on recall@5 per millisecond. Cross-encoders run via `fastembed`/`torch`,
which are unavailable here (ADR-002). We still want a rerank arm and the parent-child
expansion that attaches each kept paragraph's interpretations and section context.

## Options considered

1. **No reranker** — keep the fusion order; cheapest, decent recall.
2. **Cross-encoder (fastembed/torch)** — best quality in the plan, but blocked by the
   onnxruntime segfault (ADR-002).
3. **LLM reranker (Gemini)** — strong, but pulls Phase 4 LLM wiring forward and spends
   quota already constrained by embeddings.
4. **Deterministic lexical reranker** — reorder by query-term coverage over heading
   path + text; no deps, no API, reproducible.

## Decision

Ship **`none` and a deterministic `lexical` reranker** as the two arms now, plus
**parent-child expansion** (attach Supplement I interpretations by `interprets` and
the section intro, deduplicated). On the golden set, lexical reranking lifts recall@1
(0.42 → 0.55) and MRR (0.54 → 0.64) over the fusion order at negligible cost, so it is
the chosen arm. Cross-encoder/LLM rerankers are deferred (env/Phase-4).

## Consequences

- Positive: a measurable rerank win with zero new dependencies; expansion gives the
  drafter the interpreting comments alongside each rule.
- Negative / trade-offs: lexical reranking cannot capture semantic relevance a
  cross-encoder would; its gains concentrate at top ranks (recall@5/@10 unchanged).
- Follow-ups: add a cross-encoder or LLM reranker arm when the environment / Phase 4
  allow, and re-benchmark recall@5 per millisecond.
