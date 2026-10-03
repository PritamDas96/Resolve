"""Retrieval metrics: recall@k, MRR and nDCG@k with binary relevance (PLAN §12.2)."""

from __future__ import annotations

import math
from collections.abc import Collection, Sequence

__all__ = ["mrr", "ndcg_at_k", "recall_at_k"]


def recall_at_k(relevant: Collection[str], ranked: Sequence[str], k: int) -> float:
    """Fraction of relevant items retrieved within the top ``k`` of ``ranked``."""
    if not relevant:
        return 0.0
    top = set(ranked[:k])
    return len(top & set(relevant)) / len(relevant)


def mrr(relevant: Collection[str], ranked: Sequence[str]) -> float:
    """Reciprocal rank of the first relevant item (0.0 if none retrieved)."""
    relevant_set = set(relevant)
    for index, item in enumerate(ranked, start=1):
        if item in relevant_set:
            return 1.0 / index
    return 0.0


def ndcg_at_k(relevant: Collection[str], ranked: Sequence[str], k: int) -> float:
    """Normalised discounted cumulative gain at ``k`` with binary relevance."""
    relevant_set = set(relevant)
    dcg = sum(
        1.0 / math.log2(index + 1)
        for index, item in enumerate(ranked[:k], start=1)
        if item in relevant_set
    )
    ideal_hits = min(len(relevant_set), k)
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0
