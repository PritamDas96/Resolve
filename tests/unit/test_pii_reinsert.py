"""Unit tests for :mod:`resolve.data.pii_reinsert` (PLAN §7.7).

The central property is **offset exactness**: every recorded span must slice out
exactly the synthetic value that was inserted. Tests run on synthetic masked
narratives (no real CFPB narrative is used).
"""

from __future__ import annotations

import re
from pathlib import Path

from faker import Faker

from resolve.data import pii_reinsert as pr


def _fake(seed: int = 1) -> Faker:
    fake = Faker()
    fake.seed_instance(seed)
    return fake


def test_mask_matches_runs_and_dates() -> None:
    assert pr.MASK.search("account XXXX here") is not None
    m = pr.MASK.search("on XX/XX/2025 today")
    assert m is not None and m.group("year") == "2025"
    assert pr.MASK.search("on XX/XX/XXXX") is not None


def test_no_mask_leftover_after_reinsertion() -> None:
    text, spans = pr.reinsert("My card ending in XXXX on XX/XX/2025.", _fake())
    assert "XXXX" not in text
    assert "XX/XX/" not in text
    assert spans  # at least the LAST4 and the DATE


def test_offsets_are_exact() -> None:
    # This is the whole point: text[start:end] must be the inserted value, and
    # the regions must be ordered and non-overlapping.
    for template in pr.SAMPLE_TEMPLATES:
        text, spans = pr.reinsert(template, _fake())
        assert pr.offsets_are_consistent(text, spans)
        for span in spans:
            fragment = text[span.start : span.end]
            assert fragment  # non-empty
            assert " X" not in f" {fragment}"  # not a leftover mask run


def test_context_rules_assign_types() -> None:
    text, spans = pr.reinsert("my email is XXXX and card ending in XXXX on XX/XX/2025", _fake())
    by_type = {s.entity_type for s in spans}
    assert "EMAIL_ADDRESS" in by_type
    assert "LAST4" in by_type
    assert "DATE" in by_type
    # the email fragment really looks like an email
    email_span = next(s for s in spans if s.entity_type == "EMAIL_ADDRESS")
    assert "@" in text[email_span.start : email_span.end]


def test_date_year_preserved_when_known() -> None:
    text, spans = pr.reinsert("charged on XX/XX/2024 last year", _fake())
    date_span = next(s for s in spans if s.entity_type == "DATE")
    fragment = text[date_span.start : date_span.end]
    assert re.fullmatch(r"\d{2}/\d{2}/2024", fragment)  # four-digit year kept


def test_reinsert_is_deterministic_given_seed() -> None:
    a = pr.reinsert(pr.SAMPLE_TEMPLATES[0], _fake(7))
    b = pr.reinsert(pr.SAMPLE_TEMPLATES[0], _fake(7))
    assert a == b


def test_offsets_are_consistent_rejects_overlap() -> None:
    from resolve.eval.schemas import PiiSpan

    assert pr.offsets_are_consistent("abcdef", [PiiSpan(start=0, end=3, entity_type="X")])
    # overlapping spans are rejected
    bad = [PiiSpan(start=0, end=4, entity_type="X"), PiiSpan(start=2, end=5, entity_type="Y")]
    assert not pr.offsets_are_consistent("abcdef", bad)


def test_build_writes_sample(tmp_path: Path) -> None:
    out = tmp_path / "pii_spans_sample.jsonl"
    count = pr.build(out)
    assert count == len(pr.SAMPLE_TEMPLATES)
    from resolve.eval.schemas import PiiItem, read_jsonl

    items = read_jsonl(out, PiiItem)
    assert len(items) == count
    for item in items:
        assert pr.offsets_are_consistent(item.text, item.spans)
