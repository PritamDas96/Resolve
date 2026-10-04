"""Unit tests for the Tier C synthetic scaffold (PLAN §7.9, §7.10)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from resolve.domain import deadlines as dl
from resolve.eval.golden import tier_c_gen as tc
from resolve.eval.schemas import Stratum, TierCItem, read_jsonl


def test_one_item_per_stratum() -> None:
    items = tc.generate_samples()
    assert {it.stratum for it in items} == set(Stratum)
    assert len({it.id for it in items}) == len(items)


def test_every_item_disclaims_accusations() -> None:
    # CLAUDE.md / §7.12: no item may expect an accusation; all forbid the terms.
    for it in tc.generate_samples():
        assert it.expected.must_not_include == tc.ACCUSATION_TERMS, it.id
        for term in tc.ACCUSATION_TERMS:
            assert all(term not in inc for inc in it.expected.must_include), it.id


def test_unanswerable_item_abstains() -> None:
    items = {it.stratum: it for it in tc.generate_samples()}
    assert items[Stratum.UNANSWERABLE].expected.should_abstain is True


def test_deadlines_match_the_calculator() -> None:
    # Sample deadlines must equal what the calculator produces (never hand-typed).
    single = next(it for it in tc.generate_samples() if it.stratum is Stratum.SINGLE_HOP_REGULATION)
    expected = {d.name: d.due.isoformat() for d in dl.reg_e_error_resolution(date(2025, 2, 3))}
    assert (
        single.expected.deadlines["determination_or_provisional_credit"]
        == expected["determination_or_provisional_credit"]
    )


def test_build_round_trips(tmp_path: Path) -> None:
    out = tmp_path / "e2e_tier_c_sample.jsonl"
    assert tc.build(out) == 5
    assert read_jsonl(out, TierCItem) == tc.generate_samples()
