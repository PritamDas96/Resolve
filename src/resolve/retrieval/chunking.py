"""Structure-aware chunking of the eCFR corpus (PLAN §8.2).

The eCFR ingest already emits one record per paragraph per validity range, so
chunking here is a *transform*: prepend the heading path so embeddings and BM25 see
the hierarchy, keep interpretation comments as their own chunks (linked by
``interprets``), and merge very short sibling paragraphs (recording the merged ids).

Invariants (enforced by tests): no chunk crosses a section, and every chunk has a
resolvable citation id.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from resolve.config import Settings, get_settings

__all__ = [
    "MIN_CHARS",
    "Chunk",
    "build_heading_path",
    "chunk_records",
    "load_chunks",
    "merge_short_siblings",
    "read_regulations",
]

# Paragraphs shorter than this are merged into their previous sibling (PLAN §8.2).
MIN_CHARS = 120

# Far-future sentinel ordinal for "current" text whose valid_to is open-ended.
_SENTINEL_VALID_TO = date(9999, 12, 31)


class Chunk(BaseModel):
    """One indexable regulation chunk with its hierarchy and validity range."""

    chunk_id: str
    regulation: str
    part: str
    section: str
    paragraph: str
    heading: str
    is_interpretation: bool
    interprets: str | None
    valid_from: date
    valid_to: date
    text: str
    heading_path: str
    merged_ids: list[str] = []

    @property
    def embed_text(self) -> str:
        """Text sent to the embedder / BM25: heading path prepended to the body."""
        return f"{self.heading_path}\n{self.text}"

    @property
    def citation_id(self) -> str:
        """Stable citation reference, e.g. ``1005.11(c)(1)@2023-01-01``."""
        return self.chunk_id


def build_heading_path(regulation: str, section: str, heading: str, paragraph: str) -> str:
    """Build the ``Reg E > §1005.11 Heading > (c)(1)`` breadcrumb (PLAN §8.2)."""
    parts = [regulation]
    if section:
        parts.append(f"§{section}" + (f" {heading}" if heading else ""))
    elif heading:
        parts.append(heading)
    if paragraph:
        parts.append(paragraph)
    return " > ".join(parts)


def read_regulations(path: Path | str) -> list[dict[str, object]]:
    """Load the raw eCFR records from ``regulations.jsonl``."""
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _to_date(value: object) -> date:
    """Parse an ISO date string; treat missing/open-ended as the sentinel."""
    if not value:
        return _SENTINEL_VALID_TO
    return date.fromisoformat(str(value))


def _record_to_chunk(record: dict[str, object]) -> Chunk:
    regulation = str(record.get("regulation", ""))
    section = str(record.get("section", ""))
    heading = str(record.get("heading", ""))
    paragraph = str(record.get("paragraph", ""))
    interprets = record.get("interprets")
    return Chunk(
        chunk_id=str(record["chunk_id"]),
        regulation=regulation,
        part=str(record.get("part", "")),
        section=section,
        paragraph=paragraph,
        heading=heading,
        is_interpretation=bool(record.get("is_interpretation", False)),
        interprets=str(interprets) if interprets else None,
        valid_from=_to_date(record.get("valid_from")),
        valid_to=_to_date(record.get("valid_to")),
        text=str(record.get("text", "")),
        heading_path=build_heading_path(regulation, section, heading, paragraph),
    )


def merge_short_siblings(chunks: list[Chunk], *, min_chars: int = MIN_CHARS) -> list[Chunk]:
    """Merge a too-short chunk into the previous one in the same section + validity.

    A chunk whose body is shorter than ``min_chars`` is appended to the previous
    chunk when they share ``(regulation, section, valid_from, valid_to,
    is_interpretation)``; the merged chunk records both ids in ``merged_ids``. A
    short chunk with no mergeable predecessor is kept as-is (never dropped).
    """
    out: list[Chunk] = []
    for chunk in chunks:
        if (
            len(chunk.text) < min_chars
            and out
            and out[-1].regulation == chunk.regulation
            and out[-1].section == chunk.section
            and out[-1].valid_from == chunk.valid_from
            and out[-1].valid_to == chunk.valid_to
            and out[-1].is_interpretation == chunk.is_interpretation
        ):
            prev = out[-1]
            merged_ids = (prev.merged_ids or [prev.chunk_id]) + [chunk.chunk_id]
            out[-1] = prev.model_copy(
                update={
                    "text": f"{prev.text}\n{chunk.text}",
                    "merged_ids": merged_ids,
                }
            )
        else:
            out.append(chunk)
    return out


def chunk_records(
    records: list[dict[str, object]], *, merge: bool = True, min_chars: int = MIN_CHARS
) -> list[Chunk]:
    """Transform raw eCFR records into indexable :class:`Chunk` objects."""
    chunks = [_record_to_chunk(r) for r in records]
    if merge:
        chunks = merge_short_siblings(chunks, min_chars=min_chars)
    return chunks


def load_chunks(settings: Settings | None = None, *, merge: bool = True) -> list[Chunk]:
    """Load and chunk the committed regulations corpus."""
    settings = settings or get_settings()
    path = Path(settings.data_dir) / "processed" / "regulations.jsonl"
    return chunk_records(read_regulations(path), merge=merge)
