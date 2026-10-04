# ADR-003: Hybrid retrieval with RRF and point-in-time filtering

- **Status:** accepted
- **Date:** 2026-10-04
- **Deciders:** Pritam Das

## Context

Regulatory questions mix precise legal vocabulary (favouring lexical match) with
paraphrased consumer language (favouring semantics). Answers must also respect the
regulation text **in force on the complaint date**. We need a retrieval design that
handles both and supports point-in-time correctness.

## Options considered

1. **Dense only** — strong on paraphrase, weak on exact section/term matches and
   rare tokens (part numbers, "provisional credit").
2. **Sparse/BM25 only** — strong on exact terms, misses paraphrase; what the
   committed run uses today (ADR-002 quota constraint).
3. **Hybrid dense + sparse fused with Reciprocal Rank Fusion (RRF)** — combines both
   signals without score calibration; Qdrant supports it natively via `prefetch` +
   `FusionQuery(RRF)`.

Point-in-time is orthogonal: store `valid_from_ord`/`valid_to_ord` and filter with a
range on the `as_of` ordinal.

## Decision

Adopt **hybrid dense + sparse with RRF** as the target retrieval, with a **range
point-in-time filter** on ordinal validity dates applied to both prefetch arms. All
three arms (dense, sparse, hybrid) are implemented behind one `search()` entry point
so the ablation can compare them. The committed ablation (`docs/retrieval_ablation.md`)
runs the sparse arm (ADR-002); PIT filtering already improves sparse recall@5
(0.72 → 0.78) on the golden set.

## Consequences

- Positive: one code path covers all arms; PIT is a cheap, correct range filter and a
  rare, concrete capability; RRF needs no score normalisation.
- Negative / trade-offs: hybrid's measured advantage is pending dense embeddings
  (quota); the multi-hop and point-in-time strata are weak on sparse alone
  (recall@5 0.25 and 0.33), which is exactly where dense/hybrid is expected to help.
- Follow-ups: re-run with `--with-dense` and record the hybrid vs sparse delta here.
