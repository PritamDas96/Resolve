"""Agent tools as plain Python functions (PLAN §9, Phase 4).

Phase 4 keeps tools as ordinary callables (no MCP yet). The retrieval tool is the one
the drafter needs; deadline computation delegates to the deterministic calculator.
Account lookup is provided for the account-join stratum but is best-effort and not
required to draft a letter.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from qdrant_client import QdrantClient

from resolve.config import Settings, get_settings
from resolve.retrieval.embeddings import BM25SparseEncoder
from resolve.retrieval.search import SearchMode, SearchResult, search

__all__ = ["Retriever", "make_retriever"]

# A retrieval tool: (query, as_of, regulation, k) -> results.
Retriever = Callable[..., list[SearchResult]]


def make_retriever(
    settings: Settings | None = None, *, client: QdrantClient | None = None
) -> Retriever:
    """Build a sparse point-in-time retrieval tool over the regulations collection.

    Sparse BM25 is the committed arm (ADR-002); the returned callable signature is
    arm-agnostic, so swapping to hybrid later needs no call-site change.
    """
    settings = settings or get_settings()
    client = client or QdrantClient(url=settings.qdrant_url)
    collection = settings.qdrant_collection_regulations
    encoder = BM25SparseEncoder()

    def retrieve(
        query: str, *, as_of: date | None = None, regulation: str | None = None, k: int = 8
    ) -> list[SearchResult]:
        return search(
            client,
            collection,
            mode=SearchMode.SPARSE,
            sparse=encoder.encode_query(query),
            as_of=as_of,
            regulation=regulation,
            k=k,
        )

    return retrieve
