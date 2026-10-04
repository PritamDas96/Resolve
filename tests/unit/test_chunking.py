"""Unit tests for :mod:`resolve.retrieval.chunking` (PLAN §8.2)."""

from __future__ import annotations

from datetime import date

from resolve.retrieval import chunking as ck


def _record(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "chunk_id": "1005.11(c)(1)@2023-01-01",
        "regulation": "Reg E",
        "part": "1005",
        "section": "1005.11",
        "paragraph": "(c)(1)",
        "heading": "Procedures for resolving errors",
        "is_interpretation": False,
        "interprets": None,
        "valid_from": "2023-01-01",
        "valid_to": "2024-03-15",
        "text": "The financial institution shall investigate promptly and determine "
        "whether an error occurred within the prescribed period.",
    }
    base.update(over)
    return base


def test_build_heading_path() -> None:
    path = ck.build_heading_path("Reg E", "1005.11", "Procedures for resolving errors", "(c)(1)")
    assert path == "Reg E > §1005.11 Procedures for resolving errors > (c)(1)"
    # no section -> fall back to heading
    assert ck.build_heading_path("Reg E", "", "Appendix A", "") == "Reg E > Appendix A"


def test_record_to_chunk_fields() -> None:
    (chunk,) = ck.chunk_records([_record()], merge=False)
    assert chunk.citation_id == "1005.11(c)(1)@2023-01-01"
    assert chunk.valid_from == date(2023, 1, 1)
    assert chunk.valid_to == date(2024, 3, 15)
    assert chunk.heading_path.startswith("Reg E")
    assert chunk.embed_text.startswith(chunk.heading_path)
    assert chunk.text in chunk.embed_text


def test_open_ended_valid_to_uses_sentinel() -> None:
    (chunk,) = ck.chunk_records([_record(valid_to=None)], merge=False)
    assert chunk.valid_to == ck._SENTINEL_VALID_TO


def test_no_chunk_crosses_a_section() -> None:
    records = [
        _record(chunk_id="1005.11(a)@2023-01-01", section="1005.11", paragraph="(a)"),
        _record(chunk_id="1005.12(a)@2023-01-01", section="1005.12", paragraph="(a)"),
    ]
    chunks = ck.chunk_records(records)
    sections = {c.section for c in chunks}
    assert sections == {"1005.11", "1005.12"}
    assert all(c.chunk_id for c in chunks)  # every chunk has a resolvable id


def test_merge_short_siblings_merges_within_section() -> None:
    records = [
        _record(chunk_id="1005.11(c)(1)@2023-01-01", paragraph="(c)(1)"),
        _record(chunk_id="1005.11(c)(2)@2023-01-01", paragraph="(c)(2)", text="(short)"),
    ]
    merged = ck.chunk_records(records, merge=True)
    assert len(merged) == 1
    assert merged[0].merged_ids == [
        "1005.11(c)(1)@2023-01-01",
        "1005.11(c)(2)@2023-01-01",
    ]
    assert "(short)" in merged[0].text


def test_merge_does_not_cross_section_or_validity() -> None:
    records = [
        _record(chunk_id="1005.11(a)@2023-01-01", section="1005.11"),
        _record(chunk_id="1005.12(a)@2023-01-01", section="1005.12", text="x"),  # diff section
    ]
    merged = ck.chunk_records(records, merge=True)
    assert len(merged) == 2  # not merged across sections


def test_short_chunk_without_predecessor_is_kept() -> None:
    (chunk,) = ck.chunk_records([_record(text="tiny")], merge=True)
    assert chunk.text == "tiny"
    assert chunk.merged_ids == []
