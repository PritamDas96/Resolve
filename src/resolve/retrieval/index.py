"""Qdrant indexing for the regulations corpus (PLAN §8.3).

Builds the ``regulations`` collection with a dense vector (Gemini embeddings, cosine)
and a sparse ``bm25`` vector (IDF modifier). Point IDs are UUIDv5 of the chunk id, so
re-indexing overwrites rather than duplicates (idempotent). Dates are stored as
ordinals for point-in-time range filters.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Iterable, Sequence

from qdrant_client import QdrantClient, models

from resolve.config import Settings, get_settings
from resolve.logging import configure_logging, get_logger
from resolve.retrieval.chunking import Chunk, load_chunks
from resolve.retrieval.embeddings import BM25SparseEncoder, GeminiDenseEmbedder

__all__ = ["DENSE", "SPARSE", "build_regulations_index", "chunk_payload", "main", "point_id"]

log = get_logger(__name__)

DENSE = "dense"
SPARSE = "bm25"

# Stable namespace so UUIDv5(chunk_id) is reproducible across runs/machines.
_NAMESPACE = uuid.UUID("5f2b0e2e-9a1a-4c3a-8b7a-0e5f9d7c1a00")

# Payload fields indexed for filtering (point-in-time + facets).
_PAYLOAD_INDEXES: list[tuple[str, str]] = [
    ("regulation", "keyword"),
    ("part", "keyword"),
    ("section", "keyword"),
    ("is_interpretation", "bool"),
    ("valid_from_ord", "integer"),
    ("valid_to_ord", "integer"),
]


def point_id(chunk_id: str) -> str:
    """Return the deterministic UUIDv5 point id for a chunk id."""
    return str(uuid.uuid5(_NAMESPACE, chunk_id))


def chunk_payload(chunk: Chunk) -> dict[str, object]:
    """Build the Qdrant payload for a chunk (facets + point-in-time ordinals)."""
    return {
        "chunk_id": chunk.chunk_id,
        "citation_id": chunk.citation_id,
        "regulation": chunk.regulation,
        "part": chunk.part,
        "section": chunk.section,
        "paragraph": chunk.paragraph,
        "heading_path": chunk.heading_path,
        "is_interpretation": chunk.is_interpretation,
        "interprets": chunk.interprets,
        "valid_from_ord": chunk.valid_from.toordinal(),
        "valid_to_ord": chunk.valid_to.toordinal(),
        "text": chunk.text,
    }


def _ensure_collection(client: QdrantClient, name: str, dim: int, *, recreate: bool) -> None:
    exists = client.collection_exists(name)
    if exists and recreate:
        client.delete_collection(name)
        exists = False
    if not exists:
        client.create_collection(
            collection_name=name,
            vectors_config={DENSE: models.VectorParams(size=dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        for field, schema in _PAYLOAD_INDEXES:
            client.create_payload_index(name, field_name=field, field_schema=schema)  # type: ignore[arg-type]


def _points(
    chunks: Sequence[Chunk], dense: list[list[float]], sparse_enc: BM25SparseEncoder
) -> Iterable[models.PointStruct]:
    for chunk, dense_vec in zip(chunks, dense, strict=True):
        indices, values = sparse_enc.encode_document(chunk.embed_text)
        yield models.PointStruct(
            id=point_id(chunk.chunk_id),
            vector={
                DENSE: dense_vec,
                SPARSE: models.SparseVector(indices=indices, values=values),
            },
            payload=chunk_payload(chunk),
        )


def build_regulations_index(
    settings: Settings | None = None,
    *,
    client: QdrantClient | None = None,
    recreate: bool = True,
    batch_size: int = 256,
) -> int:
    """Embed and upsert every regulation chunk into Qdrant; returns the point count."""
    settings = settings or get_settings()
    client = client or QdrantClient(url=settings.qdrant_url)
    name = settings.qdrant_collection_regulations

    chunks = load_chunks(settings)
    _ensure_collection(client, name, settings.embedding_dim, recreate=recreate)

    embedder = GeminiDenseEmbedder(settings)
    sparse_enc = BM25SparseEncoder()
    total = 0
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        dense = embedder.embed_documents([c.embed_text for c in batch])
        client.upsert(collection_name=name, points=list(_points(batch, dense, sparse_enc)))
        total += len(batch)
        log.info("regulations_indexed", done=total, total=len(chunks))
    return total


def main() -> int:
    """CLI entry point: ``python -m resolve.retrieval.index``."""
    configure_logging()
    settings = get_settings()
    count = build_regulations_index(settings)
    log.info(
        "regulations_index_complete",
        collection=settings.qdrant_collection_regulations,
        points=count,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
