"""Point-in-time hybrid search over the regulations collection (PLAN §8.4).

Exposes dense-only, sparse-only and hybrid (RRF-fused) search behind one
:func:`search` entry point so the ablation can switch arms, plus an optional
point-in-time filter that restricts results to the regulation text in force on the
``as_of`` date — the core "answer a 2019 complaint with 2019 law" property.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel
from qdrant_client import QdrantClient, models

from resolve.retrieval.embeddings import SparseVector
from resolve.retrieval.index import DENSE, SPARSE

__all__ = ["SearchMode", "SearchResult", "hybrid_search", "pit_filter", "search"]


class SearchMode(StrEnum):
    """Which retrieval arm to use."""

    DENSE = "dense"
    SPARSE = "sparse"
    HYBRID = "hybrid"


class SearchResult(BaseModel):
    """One retrieved chunk with its score and the payload fields callers need."""

    chunk_id: str
    citation_id: str
    section: str
    regulation: str
    paragraph: str
    is_interpretation: bool
    interprets: str | None
    heading_path: str
    text: str
    score: float


def pit_filter(as_of: date | None, regulation: str | None = None) -> models.Filter | None:
    """Build the point-in-time (+ optional regulation) filter, or None when as_of is None."""
    must: list[models.FieldCondition] = []
    if as_of is not None:
        ordinal = as_of.toordinal()
        must.append(models.FieldCondition(key="valid_from_ord", range=models.Range(lte=ordinal)))
        must.append(models.FieldCondition(key="valid_to_ord", range=models.Range(gt=ordinal)))
    if regulation:
        must.append(
            models.FieldCondition(key="regulation", match=models.MatchValue(value=regulation))
        )
    return models.Filter(must=must) if must else None


def _to_results(points: list[models.ScoredPoint]) -> list[SearchResult]:
    out: list[SearchResult] = []
    for point in points:
        payload = point.payload or {}
        out.append(
            SearchResult(
                chunk_id=str(payload.get("chunk_id", "")),
                citation_id=str(payload.get("citation_id", "")),
                section=str(payload.get("section", "")),
                regulation=str(payload.get("regulation", "")),
                paragraph=str(payload.get("paragraph", "")),
                is_interpretation=bool(payload.get("is_interpretation", False)),
                interprets=payload.get("interprets"),
                heading_path=str(payload.get("heading_path", "")),
                text=str(payload.get("text", "")),
                score=float(point.score),
            )
        )
    return out


def hybrid_search(
    client: QdrantClient,
    collection: str,
    *,
    dense: list[float],
    sparse: SparseVector,
    flt: models.Filter | None,
    k: int = 20,
    prefetch_limit: int = 50,
) -> list[SearchResult]:
    """Dense + sparse prefetch fused with Reciprocal Rank Fusion (PLAN §8.4)."""
    indices, values = sparse
    response = client.query_points(
        collection_name=collection,
        prefetch=[
            models.Prefetch(query=dense, using=DENSE, limit=prefetch_limit, filter=flt),
            models.Prefetch(
                query=models.SparseVector(indices=indices, values=values),
                using=SPARSE,
                limit=prefetch_limit,
                filter=flt,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=k,
    )
    return _to_results(response.points)


def search(
    client: QdrantClient,
    collection: str,
    *,
    mode: SearchMode,
    dense: list[float] | None = None,
    sparse: SparseVector | None = None,
    as_of: date | None = None,
    regulation: str | None = None,
    k: int = 20,
) -> list[SearchResult]:
    """Run the chosen retrieval arm with an optional point-in-time filter."""
    flt = pit_filter(as_of, regulation)
    if mode is SearchMode.HYBRID:
        if dense is None or sparse is None:
            raise ValueError("hybrid search needs both dense and sparse query vectors")
        return hybrid_search(client, collection, dense=dense, sparse=sparse, flt=flt, k=k)
    if mode is SearchMode.DENSE:
        if dense is None:
            raise ValueError("dense search needs a dense query vector")
        response = client.query_points(
            collection_name=collection, query=dense, using=DENSE, limit=k, query_filter=flt
        )
        return _to_results(response.points)
    if sparse is None:
        raise ValueError("sparse search needs a sparse query vector")
    indices, values = sparse
    response = client.query_points(
        collection_name=collection,
        query=models.SparseVector(indices=indices, values=values),
        using=SPARSE,
        limit=k,
        query_filter=flt,
    )
    return _to_results(response.points)
