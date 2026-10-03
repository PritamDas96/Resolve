"""Unit tests for :mod:`resolve.data.complaints_load` (offline — no database)."""

from __future__ import annotations

from datetime import date

import polars as pl

from resolve.data import complaints_load as cl


def _frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "complaint_id": [1, 2, 3],
            "bank": ["JPMorgan Chase", "Citi", "Wells Fargo"],
            "date_received": [date(2024, 1, 1), date(2023, 6, 1), date(2025, 2, 2)],
            "product": [
                "Credit card or prepaid card",  # cards
                "Student loan",  # out of scope -> dropped
                "Mortgage",  # mortgage
            ],
            "sub_product": ["General-purpose credit card", None, "Conventional home mortgage"],
            "issue": ["Fees or interest", "Dealing with lender", "Trouble during payment process"],
            "sub_issue": [None, None, None],
            "split": ["val", "train", "test"],
        }
    )


def test_prepare_rows_assigns_queue_and_drops_out_of_scope() -> None:
    rows = cl.prepare_rows(_frame())

    assert len(rows) == 2  # Student loan dropped
    ids = {r[0] for r in rows}
    assert ids == {1, 3}
    by_id = {r[0]: r for r in rows}
    assert by_id[1][-2] == "cards"  # queue_id
    assert by_id[3][-2] == "mortgage"
    # queue_id is the second-to-last column; split is last
    assert by_id[1][-1] == "val"
    assert by_id[3][-1] == "test"


def test_prepare_rows_matches_column_contract() -> None:
    rows = cl.prepare_rows(_frame())
    assert len(rows[0]) == len(cl._COLUMNS)
    first = dict(zip(cl._COLUMNS, rows[0], strict=True))
    assert first["complaint_id"] == 1
    assert first["product"] == "Credit card or prepaid card"
    assert first["queue_id"] == "cards"


def test_dropped_unmapped_counts_out_of_scope() -> None:
    assert cl.dropped_unmapped(_frame()) == 1
