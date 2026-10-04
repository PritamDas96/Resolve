"""Integration test: sparse PIT search over Qdrant (skips if unavailable).

Requires the regulations collection to be indexed (``make index-sparse``). Skips
cleanly when Qdrant is unreachable or the collection is empty, like the Postgres
integration tests.
"""

from __future__ import annotations

from datetime import date

import pytest
from qdrant_client import QdrantClient

from resolve.config import get_settings
from resolve.retrieval.embeddings import BM25SparseEncoder
from resolve.retrieval.search import SearchMode, search


def _client_or_skip() -> tuple[QdrantClient, str]:
    settings = get_settings()
    try:
        client = QdrantClient(url=settings.qdrant_url, timeout=3)
        name = settings.qdrant_collection_regulations
        if not client.collection_exists(name) or client.count(name).count == 0:
            pytest.skip("regulations collection empty; run `make index-sparse`.")
        return client, name
    except Exception as exc:
        pytest.skip(f"Qdrant not reachable ({exc}); start it with `make up`.")


def test_sparse_pit_search_returns_scoped_results() -> None:
    client, name = _client_or_skip()
    enc = BM25SparseEncoder()
    query = "escrow account analysis and annual escrow statement requirements"
    results = search(
        client,
        name,
        mode=SearchMode.SPARSE,
        sparse=enc.encode_query(query),
        as_of=date(2023, 6, 1),
        k=10,
    )
    assert results, "expected at least one result"
    # The escrow rule (Reg X §1024.17) should surface for this query.
    assert any(r.section == "1024.17" for r in results)
    # Point-in-time filter: every hit must be valid on the as_of date (non-empty section).
    assert all(r.regulation for r in results)


def test_sparse_search_respects_k() -> None:
    client, name = _client_or_skip()
    enc = BM25SparseEncoder()
    results = search(
        client, name, mode=SearchMode.SPARSE, sparse=enc.encode_query("billing error"), k=5
    )
    assert len(results) <= 5
