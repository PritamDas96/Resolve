# ADR-002: Embedding backend for retrieval

- **Status:** accepted
- **Date:** 2026-10-04
- **Deciders:** Pritam Das

## Context

Phase 3 needs dense + sparse vectors for Qdrant hybrid search. The plan specified
`fastembed` (local `BAAI/bge-small-en-v1.5` dense, `Qdrant/bm25` sparse,
cross-encoder rerankers). On this environment (Python 3.13.14, Windows), **every
`onnxruntime` version segfaults on import** (1.20–1.30), and `fastembed` hard-depends
on it. `torch` is not installed and is unlikely to fare better on 3.13. A working,
reproducible retrieval pipeline is required regardless.

## Options considered

1. **Fix onnxruntime at the OS level** (VC++ redistributable, different Python
   build) — not reliably doable from the agent; blocks progress on the user's env.
2. **Local `fastembed`/`torch`** — blocked (segfault) / heavy and risky on 3.13.
3. **Gemini embeddings API (dense) + pure-Python BM25 (sparse)** — no native deps;
   dense is semantic; BM25 scored by Qdrant's IDF modifier. Costs API calls/quota.
4. **BM25-only** — fully local, zero API, but no semantic/dense arm.

## Decision

Use **Gemini `gemini-embedding-001` (768-dim, L2-normalised, disk-cached)** for dense
vectors and a **pure-Python BM25 encoder** (hashed term ids + Qdrant IDF modifier)
for sparse. Keep `qdrant-client`; drop `fastembed`/`onnxruntime`. Because the
free-tier embedding quota is too small to vector the ~5.9k-chunk corpus, the
committed index and ablation run on the **sparse arm**; the dense/hybrid code paths
exist and run via `--with-dense` / `make index` once embedding quota is available.

## Consequences

- Positive: retrieval works today with no fragile native deps; sparse is fully local
  and reproducible; dense is a drop-in once quota allows.
- Negative / trade-offs: the committed ablation lacks live dense/hybrid numbers;
  dense depends on an external API and quota; 768-dim reduced vectors need manual
  normalisation.
- Follow-ups: embed the corpus densely when a paid/quota-raised key is available and
  re-run `make retrieval-eval-dense`; revisit a local embedder if onnxruntime is fixed.
