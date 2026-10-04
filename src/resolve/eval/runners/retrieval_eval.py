"""Retrieval ablation runner (PLAN §8.7).

Runs the retrieval golden through a grid of configurations and writes
``docs/retrieval_ablation.md`` with recall@k / MRR / nDCG@10 and query latency, plus
a per-stratum breakdown for the best configuration.

Dense/hybrid arms need Gemini embeddings; on the free tier the embedding quota is
too small to vector the ~5.9k-chunk corpus (ADR-002), so the default run uses the
sparse BM25 arm. Pass ``--with-dense`` once embedding quota is available to include
the dense and hybrid arms (the code paths already exist).
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from qdrant_client import QdrantClient

from resolve.config import Settings, get_settings
from resolve.eval.golden.retrieval_gen import RETRIEVAL_PATH
from resolve.eval.metrics import mrr, ndcg_at_k, recall_at_k
from resolve.eval.schemas import RetrievalQuery, read_jsonl
from resolve.logging import configure_logging, get_logger
from resolve.retrieval.embeddings import BM25SparseEncoder, GeminiDenseEmbedder
from resolve.retrieval.rerank import RerankMode, rerank
from resolve.retrieval.rewrite import heuristic_rewrite, query_text
from resolve.retrieval.search import SearchMode, search

__all__ = ["AblationConfig", "RunResult", "evaluate", "main", "run_ablation"]

log = get_logger(__name__)

_DOC_PATH = Path(__file__).resolve().parents[4] / "docs" / "retrieval_ablation.md"
_K_VALUES = (1, 3, 5, 10)


@dataclass(frozen=True)
class AblationConfig:
    """One point in the ablation grid."""

    mode: SearchMode
    rewrite: bool
    pit: bool
    rerank_mode: RerankMode

    @property
    def label(self) -> str:
        """Human-readable one-line description of this configuration."""
        return (
            f"{self.mode.value} | rewrite={'on' if self.rewrite else 'off'} "
            f"| pit={'on' if self.pit else 'off'} | rerank={self.rerank_mode.value}"
        )


@dataclass
class RunResult:
    """Aggregated metrics for one config over a set of queries."""

    config: AblationConfig
    recall: dict[int, float]
    mrr: float
    ndcg10: float
    latency_ms: float
    n: int


def _ranked_sections(results: list[str]) -> list[str]:
    """Deduplicate a section list, preserving first-seen order."""
    return list(dict.fromkeys(results))


def _mean(values: list[float]) -> float:
    """Arithmetic mean, or 0.0 for an empty list."""
    return sum(values) / len(values) if values else 0.0


def _query_once(
    client: QdrantClient,
    collection: str,
    query: RetrievalQuery,
    config: AblationConfig,
    *,
    sparse_enc: BM25SparseEncoder,
    dense_embedder: GeminiDenseEmbedder | None,
) -> tuple[list[str], float]:
    """Run one query under one config; return (ranked sections, latency ms)."""
    if config.rewrite:
        intent = heuristic_rewrite(query.query)
        text = query_text(intent, for_sparse=config.mode is not SearchMode.DENSE)
    else:
        text = query.query

    as_of = query.as_of if config.pit else None
    start = time.perf_counter()
    sparse = sparse_enc.encode_query(text)
    dense = (
        dense_embedder.embed_query(text)
        if dense_embedder and config.mode is not SearchMode.SPARSE
        else None
    )
    results = search(
        client, collection, mode=config.mode, dense=dense, sparse=sparse, as_of=as_of, k=20
    )
    reranked = rerank(config.rerank_mode, text, results, k=20)
    latency_ms = (time.perf_counter() - start) * 1000
    return _ranked_sections([r.section for r in reranked]), latency_ms


def evaluate(
    client: QdrantClient,
    collection: str,
    queries: list[RetrievalQuery],
    config: AblationConfig,
    *,
    sparse_enc: BM25SparseEncoder,
    dense_embedder: GeminiDenseEmbedder | None = None,
) -> RunResult:
    """Score one configuration over all queries."""
    recalls: dict[int, list[float]] = {k: [] for k in _K_VALUES}
    rrs: list[float] = []
    ndcgs: list[float] = []
    latencies: list[float] = []
    for query in queries:
        ranked, latency = _query_once(
            client, collection, query, config, sparse_enc=sparse_enc, dense_embedder=dense_embedder
        )
        expected = set(query.expected_sections)
        for k in _K_VALUES:
            recalls[k].append(recall_at_k(expected, ranked, k))
        rrs.append(mrr(expected, ranked))
        ndcgs.append(ndcg_at_k(expected, ranked, 10))
        latencies.append(latency)
    return RunResult(
        config=config,
        recall={k: _mean(recalls[k]) for k in _K_VALUES},
        mrr=_mean(rrs),
        ndcg10=_mean(ndcgs),
        latency_ms=_mean(latencies),
        n=len(queries),
    )


def _configs(modes: list[SearchMode]) -> list[AblationConfig]:
    out: list[AblationConfig] = []
    for mode in modes:
        for rw in (False, True):
            for pit in (False, True):
                for rr in (RerankMode.NONE, RerankMode.LEXICAL):
                    out.append(AblationConfig(mode=mode, rewrite=rw, pit=pit, rerank_mode=rr))
    return out


def run_ablation(settings: Settings | None = None, *, with_dense: bool = False) -> list[RunResult]:
    """Run the full ablation grid; returns one :class:`RunResult` per config."""
    settings = settings or get_settings()
    client = QdrantClient(url=settings.qdrant_url)
    collection = settings.qdrant_collection_regulations
    queries = read_jsonl(RETRIEVAL_PATH, RetrievalQuery)
    sparse_enc = BM25SparseEncoder()
    dense_embedder = GeminiDenseEmbedder(settings) if with_dense else None

    modes = [SearchMode.SPARSE]
    if with_dense:
        modes = [SearchMode.SPARSE, SearchMode.DENSE, SearchMode.HYBRID]

    results: list[RunResult] = []
    for config in _configs(modes):
        result = evaluate(
            client,
            collection,
            queries,
            config,
            sparse_enc=sparse_enc,
            dense_embedder=dense_embedder,
        )
        log.info("ablation_config", config=config.label, recall5=round(result.recall[5], 3))
        results.append(result)
    return results


def _per_stratum(
    settings: Settings, config: AblationConfig, *, with_dense: bool
) -> tuple[list[RunResult], list[str]]:
    """Score the given config split by stratum; returns (results, strata)."""
    client = QdrantClient(url=settings.qdrant_url)
    collection = settings.qdrant_collection_regulations
    sparse_enc = BM25SparseEncoder()
    dense_embedder = GeminiDenseEmbedder(settings) if with_dense else None
    queries = read_jsonl(RETRIEVAL_PATH, RetrievalQuery)
    strata = sorted({q.stratum for q in queries})
    out: list[RunResult] = []
    for stratum in strata:
        subset = [q for q in queries if q.stratum == stratum]
        result = evaluate(
            client, collection, subset, config, sparse_enc=sparse_enc, dense_embedder=dense_embedder
        )
        out.append(result)
    return out, strata


def _render_report(
    results: list[RunResult],
    best: RunResult,
    per_stratum: list[RunResult],
    strata: list[str],
    *,
    with_dense: bool,
) -> str:
    lines = [
        "# RESOLVE — Retrieval ablation",
        "",
        f"Point-in-time hybrid retrieval over the eCFR corpus, scored on "
        f"`eval/golden/retrieval_golden.jsonl` ({best.n} queries). Metrics are means "
        "across queries; latency is per query (ms).",
        "",
        "> **Scope note (ADR-002).** `fastembed`/`onnxruntime` segfault on this Python "
        "3.13 Windows environment, so dense vectors use the Gemini embeddings API. The "
        "free-tier embedding quota is too small to vector the ~5.9k-chunk corpus, so the "
        "committed run uses the **sparse BM25** arm. The dense and hybrid code paths exist; "
        "`make retrieval-eval-dense` includes them once embedding quota is available.",
        "",
        "## Configurations",
        "",
        "| Config | recall@1 | recall@3 | recall@5 | recall@10 | MRR | nDCG@10 | latency (ms) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r.config.label} | {r.recall[1]:.2f} | {r.recall[3]:.2f} | {r.recall[5]:.2f} "
            f"| {r.recall[10]:.2f} | {r.mrr:.2f} | {r.ndcg10:.2f} | {r.latency_ms:.1f} |"
        )
    lines += [
        "",
        f"**Best configuration (by recall@5, then MRR):** `{best.config.label}` "
        f"— recall@5 {best.recall[5]:.2f}, MRR {best.mrr:.2f}, nDCG@10 {best.ndcg10:.2f}.",
        "",
        "## Best configuration, per stratum",
        "",
        "| Stratum | recall@5 | MRR | nDCG@10 | n |",
        "| --- | --- | --- | --- | --- |",
    ]
    for stratum, r in zip(strata, per_stratum, strict=True):
        lines.append(f"| {stratum} | {r.recall[5]:.2f} | {r.mrr:.2f} | {r.ndcg10:.2f} | {r.n} |")
    lines += [
        "",
        "See ADR-003 (hybrid + RRF) and ADR-009 (reranking) for the rationale behind the "
        "chosen configuration.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m resolve.eval.runners.retrieval_eval``."""
    parser = argparse.ArgumentParser(description="Run the retrieval ablation.")
    parser.add_argument(
        "--with-dense", action="store_true", help="Include dense + hybrid arms (needs embed quota)."
    )
    args = parser.parse_args(argv)
    configure_logging()
    settings = get_settings()

    results = run_ablation(settings, with_dense=args.with_dense)
    best = max(results, key=lambda r: (r.recall[5], r.mrr))
    per_stratum, strata = _per_stratum(settings, best.config, with_dense=args.with_dense)
    report = _render_report(results, best, per_stratum, strata, with_dense=args.with_dense)
    _DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DOC_PATH.write_text(report, encoding="utf-8")
    log.info(
        "retrieval_ablation_written",
        path=str(_DOC_PATH),
        configs=len(results),
        best=best.config.label,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
