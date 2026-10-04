# RESOLVE — Retrieval ablation

Point-in-time hybrid retrieval over the eCFR corpus, scored on `eval/golden/retrieval_golden.jsonl` (20 queries). Metrics are means across queries; latency is per query (ms).

> **Scope note (ADR-002).** `fastembed`/`onnxruntime` segfault on this Python 3.13 Windows environment, so dense vectors use the Gemini embeddings API. The free-tier embedding quota is too small to vector the ~5.9k-chunk corpus, so the committed run uses the **sparse BM25** arm. The dense and hybrid code paths exist; `make retrieval-eval-dense` includes them once embedding quota is available.

## Configurations

| Config | recall@1 | recall@3 | recall@5 | recall@10 | MRR | nDCG@10 | latency (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sparse | rewrite=off | pit=off | rerank=none | 0.42 | 0.47 | 0.72 | 0.75 | 0.54 | 0.57 | 71.0 |
| sparse | rewrite=off | pit=off | rerank=lexical | 0.55 | 0.70 | 0.72 | 0.75 | 0.64 | 0.66 | 24.2 |
| sparse | rewrite=off | pit=on | rerank=none | 0.42 | 0.47 | 0.78 | 0.80 | 0.55 | 0.59 | 21.9 |
| sparse | rewrite=off | pit=on | rerank=lexical | 0.55 | 0.70 | 0.78 | 0.80 | 0.64 | 0.68 | 18.4 |
| sparse | rewrite=on | pit=off | rerank=none | 0.42 | 0.47 | 0.72 | 0.75 | 0.54 | 0.57 | 17.7 |
| sparse | rewrite=on | pit=off | rerank=lexical | 0.55 | 0.70 | 0.72 | 0.75 | 0.64 | 0.66 | 16.8 |
| sparse | rewrite=on | pit=on | rerank=none | 0.42 | 0.47 | 0.78 | 0.80 | 0.55 | 0.59 | 16.2 |
| sparse | rewrite=on | pit=on | rerank=lexical | 0.55 | 0.70 | 0.78 | 0.80 | 0.64 | 0.68 | 18.8 |

**Best configuration (by recall@5, then MRR):** `sparse | rewrite=off | pit=on | rerank=lexical` — recall@5 0.78, MRR 0.64, nDCG@10 0.68.

## Best configuration, per stratum

| Stratum | recall@5 | MRR | nDCG@10 | n |
| --- | --- | --- | --- | --- |
| multi_hop | 0.25 | 0.18 | 0.23 | 2 |
| point_in_time | 0.33 | 0.33 | 0.33 | 3 |
| single_hop | 0.93 | 0.76 | 0.80 | 15 |

See ADR-003 (hybrid + RRF) and ADR-009 (reranking) for the rationale behind the chosen configuration.
