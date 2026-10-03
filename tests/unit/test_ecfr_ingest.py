"""Unit tests for :mod:`resolve.data.ecfr_ingest`.

These tests are the specification for the regulation-ingestion module. They run
fully offline against small committed fixtures that mirror the real eCFR part
XML schema (``DIV5``/``DIV8``/``DIV9``, inline ``(a)(1)(i)`` paragraph markers,
and a Supplement I appendix) and a ``versions`` payload. The two network seams —
``fetch_versions`` and ``fetch_part_xml`` — are monkeypatched so no HTTP happens.

The Reg E fixture is captured at two snapshots:

* ``2023-01-01`` and ``2024-10-01`` are identical **except** the text of
  ``1005.11(c)(1)`` (the error-investigation time limit), so collapsing yields
  two records for that paragraph and one record for everything else.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from resolve import config
from resolve.data import ecfr_ingest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
XML_2023 = (FIXTURES / "ecfr_part-1005_2023-01-01.xml").read_bytes()
XML_2024 = (FIXTURES / "ecfr_part-1005_2024-10-01.xml").read_bytes()
VERSIONS = json.loads((FIXTURES / "ecfr_versions_part-1005.json").read_text(encoding="utf-8"))

D2023 = date(2023, 1, 1)
D2024 = date(2024, 10, 1)
URL = "https://example.test/ecfr"


def _sections(xml: bytes, snapshot: date) -> list[ecfr_ingest.RegChunk]:
    return ecfr_ingest.parse_sections(
        xml, part="1005", regulation="Reg E", snapshot=snapshot, source_url=URL
    )


def _supplement(xml: bytes, snapshot: date) -> list[ecfr_ingest.RegChunk]:
    return ecfr_ingest.parse_supplement(
        xml, part="1005", regulation="Reg E", snapshot=snapshot, source_url=URL
    )


# --- paragraph-path reconstruction -----------------------------------------


def test_paragraph_path_reconstructs_nesting_and_pops() -> None:
    chunks = _sections(XML_2023, D2023)

    s11 = [c.paragraph for c in chunks if c.section == "1005.11"]
    # run-in "(a) ...—(1) ..." introduces both a and 1; then roman (i) nests under
    # (a)(1); (2) pops to the arabic level; (b) pops to the alpha level; etc.
    assert s11 == ["(a)(1)", "(a)(1)(i)", "(a)(2)", "(b)", "(c)", "(c)(1)"]


def test_markers_in_order_captures_leading_and_run_in() -> None:
    assert ecfr_ingest.markers_in_order("(a) Definition of error—(1) Types covered. Text") == [
        "a",
        "1",
    ]
    assert ecfr_ingest.markers_in_order("(i) An unauthorized transfer;") == ["i"]
    # a mid-sentence cross-reference like "§ 1005.10(a)" is not a marker
    assert ecfr_ingest.markers_in_order("The institution shall comply with § 1005.10(a).") == []


def test_marker_type_disambiguates_roman_from_alpha() -> None:
    # "i" after an arabic parent is roman; "c" at the top level is alpha.
    assert ecfr_ingest._marker_type("i", parent_type="arabic") == "roman"
    assert ecfr_ingest._marker_type("c", parent_type=None) == "alpha"
    assert ecfr_ingest._marker_type("1", parent_type="alpha") == "arabic"
    assert ecfr_ingest._marker_type("A", parent_type="roman") == "upper"


# --- section parsing --------------------------------------------------------


def test_parse_sections_captures_sections_headings_and_text() -> None:
    chunks = _sections(XML_2023, D2023)
    sections = {c.section for c in chunks}
    assert sections == {"1005.11", "1005.13"}

    s11_c1 = next(c for c in chunks if c.section == "1005.11" and c.paragraph == "(c)(1)")
    assert "10 business days" in s11_c1.text
    assert s11_c1.heading == "§ 1005.11 Procedures for resolving errors."
    assert s11_c1.regulation == "Reg E"
    assert s11_c1.is_interpretation is False
    assert s11_c1.interprets is None
    assert s11_c1.chunk_id == "1005.11(c)(1)@2023-01-01"
    assert s11_c1.sha256 == ecfr_ingest.sha256_text(s11_c1.text)


# --- Supplement I parsing ---------------------------------------------------


def test_parse_supplement_links_interpretations_to_paragraphs() -> None:
    interps = _supplement(XML_2023, D2023)
    assert len(interps) == 2
    assert all(c.is_interpretation for c in interps)

    targets = {c.interprets for c in interps}
    assert targets == {"1005.11(c)", "1005.11(c)(1)"}

    detailed = next(c for c in interps if c.interprets == "1005.11(c)(1)")
    assert detailed.section == "1005.11"
    assert "ninth business day" in detailed.text
    assert detailed.chunk_id.endswith("@2023-01-01")


def test_resolve_interpreted_target_parses_heading_forms() -> None:
    assert ecfr_ingest._resolve_interpreted_target(
        "1005", "Section 1005.11 Procedures", "11(c)"
    ) == (
        "1005.11",
        "1005.11(c)",
    )
    assert ecfr_ingest._resolve_interpreted_target(
        "1005", "Section 1005.2 Definitions", "Paragraph 2(b)(3)(i)"
    ) == ("1005.2", "1005.2(b)(3)(i)")
    # The section number comes from the part + paragraph heading, so it is correct
    # even when the enclosing HD1 is not a parseable "Section ..." heading.
    assert ecfr_ingest._resolve_interpreted_target(
        "1024", "Subpart B—Mortgage Servicing", "17(k)(5)(ii)(A)When inability exists."
    ) == ("1024.17", "1024.17(k)(5)(ii)(A)")
    # Section-level comment (no paragraph heading) interprets the bare section.
    assert ecfr_ingest._resolve_interpreted_target("1005", "Section 1005.11 Procedures", "") == (
        "1005.11",
        "1005.11",
    )


# --- version collapsing -----------------------------------------------------


def test_collapse_unchanged_paragraph_spans_both_snapshots() -> None:
    snaps = [(D2023, _sections(XML_2023, D2023)), (D2024, _sections(XML_2024, D2024))]
    collapsed = ecfr_ingest.collapse_versions(snaps)

    s13a = [c for c in collapsed if c.section == "1005.13" and c.paragraph == "(a)"]
    assert len(s13a) == 1
    assert s13a[0].valid_from == D2023
    assert s13a[0].valid_to is None  # unchanged through the latest snapshot


def test_collapse_changed_paragraph_splits_into_two_ranges() -> None:
    snaps = [(D2023, _sections(XML_2023, D2023)), (D2024, _sections(XML_2024, D2024))]
    collapsed = ecfr_ingest.collapse_versions(snaps)

    c1 = sorted(
        (c for c in collapsed if c.section == "1005.11" and c.paragraph == "(c)(1)"),
        key=lambda c: c.valid_from,
    )
    assert len(c1) == 2
    assert c1[0].valid_from == D2023
    assert c1[0].valid_to == date(2024, 9, 30)  # day before the change
    assert "10 business days" in c1[0].text
    assert c1[1].valid_from == D2024
    assert c1[1].valid_to is None
    assert "ten (10) business days" in c1[1].text


# --- versions-date extraction -----------------------------------------------


def test_parse_versions_filters_by_year_and_dedupes() -> None:
    dates = ecfr_ingest.parse_versions(VERSIONS, since_year=2017)
    assert dates == [D2023, D2024]  # 2015-06-01 dropped; 1005.11 duplicate on 2023 deduped

    with_old = ecfr_ingest.parse_versions(VERSIONS, since_year=2010)
    assert date(2015, 6, 1) in with_old


# --- orchestrator (network seams monkeypatched) -----------------------------


@pytest.fixture
def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> config.Settings:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    return config.Settings(
        data_dir=tmp_path / "data",
        ecfr_since_year=2017,
        ecfr_request_delay_s=0.0,
    )


def _patch_seams(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ecfr_ingest, "fetch_versions", lambda part, **_: VERSIONS)

    def fake_xml(part: str, snapshot: date, **_: object) -> bytes:
        return XML_2024 if snapshot >= D2024 else XML_2023

    monkeypatch.setattr(ecfr_ingest, "fetch_part_xml", fake_xml)


def test_ingest_writes_jsonl_and_manifest(
    monkeypatch: pytest.MonkeyPatch, _settings: config.Settings
) -> None:
    _patch_seams(monkeypatch)

    result = ecfr_ingest.ingest(_settings, refresh=True, regulations={"Reg E": "1005"})

    assert result.output_path.exists()
    assert result.manifest_path.exists()
    assert result.records > 0

    lines = result.output_path.read_text(encoding="utf-8").strip().splitlines()
    records = [json.loads(line) for line in lines]
    assert len(records) == result.records
    # the changed paragraph appears twice (two validity ranges)
    c1 = [r for r in records if r["section"] == "1005.11" and r["paragraph"] == "(c)(1)"]
    assert len(c1) == 2
    assert any(r["is_interpretation"] for r in records)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["processed"]["records"] == result.records
    assert "Reg E" in manifest["snapshots"]


def test_ingest_is_deterministic(
    monkeypatch: pytest.MonkeyPatch, _settings: config.Settings
) -> None:
    _patch_seams(monkeypatch)

    first = ecfr_ingest.ingest(_settings, refresh=True, regulations={"Reg E": "1005"})
    first_text = first.output_path.read_text(encoding="utf-8")

    second = ecfr_ingest.ingest(_settings, refresh=True, regulations={"Reg E": "1005"})
    second_text = second.output_path.read_text(encoding="utf-8")

    assert ecfr_ingest.sha256_text(first_text) == ecfr_ingest.sha256_text(second_text)
