"""Unit tests for :mod:`resolve.data.data_card` (offline — no network, no DB)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from resolve import config
from resolve.data import data_card as dc


def _frame() -> pl.DataFrame:
    """A tiny complaints frame spanning banks, years, splits and one UNMAPPED row."""
    return pl.DataFrame(
        {
            "complaint_id": [1, 2, 3, 4, 5],
            "bank": [
                "JPMorgan Chase",
                "JPMorgan Chase",
                "Citi",
                "Wells Fargo",
                "Citi",
            ],
            "date_received": [
                date(2023, 1, 1),
                date(2024, 6, 1),
                date(2025, 2, 2),
                date(2024, 3, 3),
                date(2023, 7, 7),
            ],
            "product": [
                "Credit card or prepaid card",  # cards
                "Mortgage",  # mortgage
                "Checking or savings account",  # deposits
                "Student loan",  # out of scope -> UNMAPPED
                "Credit card",  # cards
            ],
            "sub_product": [None, None, None, None, None],
            "issue": [
                "Fees or interest",
                "Trouble during payment process",
                "Managing an account",
                "Dealing with lender",
                "Fees or interest",
            ],
            "sub_issue": [None, None, None, None, None],
            "year": [2023, 2024, 2025, 2024, 2023],
            "split": ["train", "val", "test", "val", "train"],
        }
    )


# --- pure counting ----------------------------------------------------------


def test_split_counts() -> None:
    assert dc.split_counts(_frame()) == {"train": 2, "val": 2, "test": 1}


def test_bank_counts() -> None:
    assert dc.bank_counts(_frame()) == {
        "JPMorgan Chase": 2,
        "Citi": 2,
        "Wells Fargo": 1,
    }


def test_family_year_counts_excludes_unmapped() -> None:
    report = dc.family_year_counts(_frame())
    # Student loan (Wells Fargo) is UNMAPPED and must not appear.
    assert "Wells Fargo" not in set(report["bank"].to_list())
    assert set(report["family"].to_list()) == {"cards", "mortgage", "deposits"}
    rows = {(r["bank"], r["year"], r["family"]): r["count"] for r in report.iter_rows(named=True)}
    assert rows[("JPMorgan Chase", 2023, "cards")] == 1
    assert rows[("JPMorgan Chase", 2024, "mortgage")] == 1
    assert rows[("Citi", 2023, "cards")] == 1
    assert rows[("Citi", 2025, "deposits")] == 1
    assert report["count"].sum() == 4  # the UNMAPPED row is excluded


def test_unmapped_count() -> None:
    assert dc.unmapped_count(_frame()) == 1


# --- rendering --------------------------------------------------------------


def _stats() -> dc.DataCardStats:
    return dc.DataCardStats(
        total_complaints=5,
        counts_by_split={"train": 2, "val": 2, "test": 1},
        counts_by_bank={"JPMorgan Chase": 2, "Citi": 2, "Wells Fargo": 1},
        family_year_counts=[
            {"bank": "Citi", "year": 2023, "family": "cards", "count": 1},
            {"bank": "Citi", "year": 2025, "family": "deposits", "count": 1},
            {"bank": "JPMorgan Chase", "year": 2023, "family": "cards", "count": 1},
            {"bank": "JPMorgan Chase", "year": 2024, "family": "mortgage", "count": 1},
        ],
        unmapped_complaints=1,
        cfpb_manifest={"retrieved_at": "2026-10-04T00:00:00+00:00"},
        ecfr_manifest=None,
        bank_docs_manifest=None,
        synthetic={"accounts": 120, "transactions": 900, "disputes": 150},
    )


def test_render_card_is_deterministic() -> None:
    assert dc.render_card(_stats()) == dc.render_card(_stats())


def test_render_card_has_required_sections() -> None:
    card = dc.render_card(_stats())
    for heading in (
        "## Sources",
        "## Filters",
        "## Counts",
        "## Splits",
        "## Taxonomy mapping",
        "## Known biases and limitations",
        "## Licence",
    ):
        assert heading in card, heading
    # counts actually surfaced
    assert "120" in card  # synthetic accounts
    assert "UNMAPPED" in card  # the unmapped count is reported, never silently dropped


def test_render_card_respects_no_accusation_guardrails() -> None:
    card = dc.render_card(_stats()).lower()
    # CLAUDE.md / §7.12: never single out a bank as "worst"; narratives are
    # unverified opinions; the card must explicitly disclaim legal conclusions.
    assert "worst" not in card  # no bank-quality ranking
    assert "company size" in card  # volume-depends-on-size caveat present
    assert "unverified" in card  # narratives-are-opinions caveat present
    assert "representative sample" in card  # consent-only sampling caveat present
    # The one permitted use of "violated" is the explicit no-accusation disclaimer.
    assert "never concludes that a named bank violated a law" in card


# --- orchestration ----------------------------------------------------------


@pytest.fixture
def _settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> config.Settings:
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("GROQ_API_KEY", "test")
    return config.Settings(data_dir=tmp_path / "data")


def test_build_writes_data_card_from_parquet(_settings: config.Settings) -> None:
    processed = Path(_settings.data_dir) / "processed"
    processed.mkdir(parents=True)
    _frame().write_parquet(processed / "complaints.parquet")

    out_path = Path(_settings.data_dir).parent / "data_card.md"
    written = dc.build(_settings, out_path=out_path)

    assert written == out_path
    text = out_path.read_text(encoding="utf-8")
    assert text.startswith("# RESOLVE — Data card")
    assert "Total in-scope complaints" in text
    # 4 mapped complaints across three families; 1 UNMAPPED reported separately.
    assert "cards" in text and "mortgage" in text and "deposits" in text
