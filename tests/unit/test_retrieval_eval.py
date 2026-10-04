"""Offline unit tests for the retrieval golden + ablation helpers (no Qdrant)."""

from __future__ import annotations

from resolve.eval.golden import retrieval_gen as rg
from resolve.eval.runners import retrieval_eval as re
from resolve.retrieval.rerank import RerankMode
from resolve.retrieval.search import SearchMode


def test_retrieval_golden_queries() -> None:
    queries = rg.generate_queries()
    assert len(queries) == 20
    assert len({q.id for q in queries}) == 20
    assert {q.stratum for q in queries} == {"single_hop", "multi_hop", "point_in_time"}
    assert all(q.expected_sections for q in queries)
    # multi-hop queries carry two expected sections
    multi = [q for q in queries if q.stratum == "multi_hop"]
    assert all(len(q.expected_sections) == 2 for q in multi)


def test_ablation_config_grid_sparse_only() -> None:
    configs = re._configs([SearchMode.SPARSE])
    assert len(configs) == 8  # 1 mode x rewrite(2) x pit(2) x rerank(2)
    assert all(c.mode is SearchMode.SPARSE for c in configs)


def test_ablation_config_grid_with_dense() -> None:
    configs = re._configs([SearchMode.SPARSE, SearchMode.DENSE, SearchMode.HYBRID])
    assert len(configs) == 24


def test_ablation_config_label() -> None:
    cfg = re.AblationConfig(
        mode=SearchMode.SPARSE, rewrite=True, pit=False, rerank_mode=RerankMode.LEXICAL
    )
    assert cfg.label == "sparse | rewrite=on | pit=off | rerank=lexical"


def test_mean_and_ranked_sections() -> None:
    assert re._mean([1.0, 2.0, 3.0]) == 2.0
    assert re._mean([]) == 0.0
    assert re._ranked_sections(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]
