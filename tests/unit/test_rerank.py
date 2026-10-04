"""Unit tests for :mod:`resolve.retrieval.rerank` (PLAN §8.6)."""

from __future__ import annotations

from datetime import date

from resolve.retrieval.chunking import Chunk
from resolve.retrieval.rerank import (
    ChunkLibrary,
    RerankMode,
    expand_parents_children,
    lexical_rerank,
    rerank,
)
from resolve.retrieval.search import SearchResult


def _result(
    chunk_id: str, *, section: str, text: str, score: float, para: str = ""
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        citation_id=chunk_id,
        section=section,
        regulation="Reg E",
        paragraph=para,
        is_interpretation=False,
        interprets=None,
        heading_path=f"Reg E > §{section}",
        text=text,
        score=score,
    )


def test_rerank_none_keeps_order_and_truncates() -> None:
    results = [_result(f"c{i}", section="1005.11", text="x", score=1.0 - i / 10) for i in range(8)]
    out = rerank(RerankMode.NONE, "anything", results, k=5)
    assert [r.chunk_id for r in out] == ["c0", "c1", "c2", "c3", "c4"]


def test_lexical_rerank_promotes_term_overlap() -> None:
    results = [
        _result("off", section="1005.7", text="unrelated disclosures", score=0.9),
        _result(
            "on", section="1005.11", text="provisional credit time limit investigation", score=0.5
        ),
    ]
    out = lexical_rerank("provisional credit time limit", results, k=2)
    assert out[0].chunk_id == "on"  # better lexical coverage wins despite lower score


def test_lexical_rerank_stable_on_zero_overlap() -> None:
    results = [
        _result("a", section="x", text="foo", score=0.9),
        _result("b", section="y", text="bar", score=0.8),
    ]
    out = lexical_rerank("zzz qqq", results, k=2)
    assert [r.chunk_id for r in out] == ["a", "b"]  # falls back to incoming order


def _chunk(
    cid: str, *, section: str, para: str, interp: bool = False, interprets: str | None = None
) -> Chunk:
    return Chunk(
        chunk_id=cid,
        regulation="Reg E",
        part="1005",
        section=section,
        paragraph=para,
        heading="Procedures",
        is_interpretation=interp,
        interprets=interprets,
        valid_from=date(2023, 1, 1),
        valid_to=date(2024, 1, 1),
        text="body",
        heading_path=f"Reg E > §{section}",
    )


def test_expand_attaches_interpretations_and_intro() -> None:
    chunks = [
        _chunk("1005.11(c)(1)@2023-01-01", section="1005.11", para="(c)(1)"),
        _chunk("1005.11@2023-01-01", section="1005.11", para=""),  # section intro
        _chunk(
            "int-1@2023-01-01",
            section="1005.11",
            para="",
            interp=True,
            interprets="1005.11(c)(1)@2023-01-01",
        ),
    ]
    library = ChunkLibrary(chunks)
    results = [
        _result("1005.11(c)(1)@2023-01-01", section="1005.11", text="t", score=0.7, para="(c)(1)")
    ]
    expanded = expand_parents_children(results, library)
    ids = [r.chunk_id for r in expanded]
    assert ids[0] == "1005.11(c)(1)@2023-01-01"  # original first
    assert "int-1@2023-01-01" in ids  # interpretation attached
    assert "1005.11@2023-01-01" in ids  # section intro attached


def test_expand_dedups() -> None:
    chunks = [_chunk("a@2023-01-01", section="1005.11", para="(a)")]
    library = ChunkLibrary(chunks)
    results = [
        _result("a@2023-01-01", section="1005.11", text="t", score=0.9, para="(a)"),
        _result("a@2023-01-01", section="1005.11", text="t", score=0.8, para="(a)"),
    ]
    expanded = expand_parents_children(results, library)
    assert len(expanded) == 1  # duplicate chunk id collapsed
