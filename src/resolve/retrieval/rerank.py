"""Reranking and parent-child expansion (PLAN §8.6).

After hybrid search returns a candidate set, an optional reranker reorders it and
parent-child expansion attaches each kept paragraph's Supplement I interpretation
comments (by ``interprets``) and its section-heading context, deduplicated.

The plan's cross-encoder rerankers depend on ``onnxruntime``/``torch``, which do not
run in this environment (ADR-002), so the two available arms are ``none`` (keep the
fusion order) and a deterministic ``lexical`` reranker (query-term coverage over the
heading path + text). An LLM reranker is deferred to Phase 4.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from enum import StrEnum

from resolve.retrieval.chunking import Chunk
from resolve.retrieval.embeddings import tokenize
from resolve.retrieval.search import SearchResult

__all__ = [
    "ChunkLibrary",
    "RerankMode",
    "expand_parents_children",
    "lexical_rerank",
    "rerank",
]


class RerankMode(StrEnum):
    """Available rerank arms (cross-encoder/LLM deferred; see module docstring)."""

    NONE = "none"
    LEXICAL = "lexical"


def lexical_rerank(query: str, results: Sequence[SearchResult], k: int) -> list[SearchResult]:
    """Reorder by query-term coverage over heading path + text (deterministic).

    Ties (and zero-overlap results) fall back to the incoming fusion order, so this
    never discards the retriever's signal — it only promotes lexically on-topic hits.
    """
    query_terms = set(tokenize(query))
    if not query_terms:
        return list(results[:k])

    def coverage(result: SearchResult) -> float:
        doc_terms = set(tokenize(f"{result.heading_path} {result.text}"))
        if not doc_terms:
            return 0.0
        return len(query_terms & doc_terms) / len(query_terms)

    ranked = sorted(enumerate(results), key=lambda pair: (-coverage(pair[1]), pair[0]))
    return [result for _, result in ranked][:k]


def rerank(
    mode: RerankMode, query: str, results: Sequence[SearchResult], *, k: int = 5
) -> list[SearchResult]:
    """Apply the chosen rerank arm and truncate to ``k``."""
    if mode is RerankMode.LEXICAL:
        return lexical_rerank(query, results, k)
    return list(results[:k])


class ChunkLibrary:
    """Lookup over the full chunk set for parent-child expansion."""

    def __init__(self, chunks: Sequence[Chunk]) -> None:
        """Index chunks by citation, by what they interpret, and by section intro."""
        self._by_citation: dict[str, Chunk] = {}
        self._interps: dict[str, list[Chunk]] = defaultdict(list)
        self._section_intro: dict[tuple[str, str], Chunk] = {}
        for chunk in chunks:
            self._by_citation[chunk.citation_id] = chunk
            if chunk.interprets:
                self._interps[chunk.interprets].append(chunk)
            if chunk.is_interpretation is False and chunk.paragraph == "" and chunk.section:
                self._section_intro.setdefault((chunk.regulation, chunk.section), chunk)

    def interpretations_for(self, citation_id: str, section: str) -> list[Chunk]:
        """Return interpretation chunks that interpret this paragraph or its section."""
        return self._interps.get(citation_id, []) + [
            c for c in self._interps.get(section, []) if c.citation_id != citation_id
        ]

    def section_intro(self, regulation: str, section: str) -> Chunk | None:
        """Return the section's heading/intro chunk, if one exists."""
        return self._section_intro.get((regulation, section))


def expand_parents_children(
    results: Sequence[SearchResult],
    library: ChunkLibrary,
    *,
    max_expansions_per_result: int = 3,
) -> list[SearchResult]:
    """Attach interpretations + section intros to the kept results, deduplicated.

    Expansions keep the parent result's score (they are context, not independently
    ranked) and are appended after the originals; the first occurrence of each
    chunk id wins.
    """
    seen: set[str] = set()
    out: list[SearchResult] = []

    def _add(result: SearchResult) -> None:
        if result.chunk_id not in seen:
            seen.add(result.chunk_id)
            out.append(result)

    for result in results:
        _add(result)
        extras: list[Chunk] = library.interpretations_for(result.citation_id, result.section)
        intro = library.section_intro(result.regulation, result.section)
        if intro is not None:
            extras = [*extras, intro]
        for chunk in extras[:max_expansions_per_result]:
            _add(_chunk_as_result(chunk, parent_score=result.score))
    return out


def _chunk_as_result(chunk: Chunk, *, parent_score: float) -> SearchResult:
    return SearchResult(
        chunk_id=chunk.chunk_id,
        citation_id=chunk.citation_id,
        section=chunk.section,
        regulation=chunk.regulation,
        paragraph=chunk.paragraph,
        is_interpretation=chunk.is_interpretation,
        interprets=chunk.interprets,
        heading_path=chunk.heading_path,
        text=chunk.text,
        score=parent_score,
    )
