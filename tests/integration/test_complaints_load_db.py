"""Integration test: load complaints into Postgres (skips without a database)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pytest

from resolve.config import get_settings
from resolve.data import complaints_load as cl

if TYPE_CHECKING:
    import asyncpg


async def _connect_or_skip() -> asyncpg.Connection:
    import asyncpg

    try:
        return await asyncpg.connect(get_settings().postgres_dsn, timeout=3)
    except Exception as exc:
        pytest.skip(f"Postgres not reachable ({exc}); start it with `make up`.")


async def test_load_complaints_roundtrip(tmp_path: Path) -> None:
    conn = await _connect_or_skip()
    try:
        df = pl.DataFrame(
            {
                "complaint_id": [9001, 9002, 9003],
                "bank": ["JPMorgan Chase", "Citi", "Wells Fargo"],
                "date_received": [date(2024, 1, 1), date(2023, 6, 1), date(2025, 2, 2)],
                "product": ["Credit card", "Student loan", "Mortgage"],
                "sub_product": [None, None, None],
                "issue": ["Fees or interest", "x", "Trouble during payment process"],
                "sub_issue": [None, None, None],
                "split": ["val", "train", "test"],
            }
        )
        parquet = tmp_path / "complaints.parquet"
        df.write_parquet(parquet)

        counts = await cl.load(parquet, dsn=get_settings().postgres_dsn, truncate=True)
        assert counts == {"loaded": 2, "dropped_unmapped": 1}  # Student loan dropped

        total = await conn.fetchval("SELECT count(*) FROM complaints")
        assert total == 2

        # Re-loading without truncate is idempotent (ON CONFLICT DO NOTHING via the
        # staging upsert): no duplicate rows, same count.
        again = await cl.load(parquet, dsn=get_settings().postgres_dsn, truncate=False)
        assert again == {"loaded": 2, "dropped_unmapped": 1}
        assert await conn.fetchval("SELECT count(*) FROM complaints") == 2
        queues = await conn.fetch(
            "SELECT complaint_id, queue_id FROM complaints ORDER BY complaint_id"
        )
        assert {r["complaint_id"]: r["queue_id"] for r in queues} == {
            9001: "cards",
            9003: "mortgage",
        }
        # every complaint's queue is a valid FK (loaded without error) and narrative is null
        null_narratives = await conn.fetchval(
            "SELECT count(*) FROM complaints WHERE narrative_raw IS NOT NULL"
        )
        assert null_narratives == 0
    finally:
        await conn.execute("TRUNCATE complaints CASCADE")
        await conn.close()
