"""Integration test: load synthetic accounts into Postgres.

Skips automatically when no database is reachable (e.g. local runs without the
Docker stack up). Requires the ``make up`` Postgres container.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

from resolve.config import get_settings
from resolve.data import synth_accounts as sa

if TYPE_CHECKING:
    import asyncpg

AS_OF = date(2026, 1, 1)


async def _connect_or_skip() -> asyncpg.Connection:
    import asyncpg

    dsn = get_settings().postgres_dsn
    try:
        return await asyncpg.connect(dsn, timeout=3)
    except Exception as exc:
        pytest.skip(f"Postgres not reachable ({exc}); start it with `make up`.")


async def test_apply_schema_and_load_roundtrip() -> None:
    conn = await _connect_or_skip()
    try:
        await sa.apply_schema(conn)
        # isolate this test's rows
        await conn.execute("TRUNCATE disputes, transactions, accounts CASCADE")

        data = sa.generate(120, seed=11, as_of=AS_OF)
        counts = await sa.load(data, dsn=get_settings().postgres_dsn, truncate=True)

        assert counts == data.counts()
        db_accounts = await conn.fetchval("SELECT count(*) FROM accounts")
        db_txns = await conn.fetchval("SELECT count(*) FROM transactions")
        db_disputes = await conn.fetchval("SELECT count(*) FROM disputes")
        assert db_accounts == len(data.accounts)
        assert db_txns == len(data.transactions)
        assert db_disputes == len(data.disputes)

        # the four queues were seeded by the schema
        queue_count = await conn.fetchval("SELECT count(*) FROM queues")
        assert queue_count == 4

        # referential integrity holds in the database (every dispute's account exists)
        orphans = await conn.fetchval(
            "SELECT count(*) FROM disputes d "
            "LEFT JOIN accounts a ON d.account_id = a.account_id WHERE a.account_id IS NULL"
        )
        assert orphans == 0
    finally:
        await conn.execute("TRUNCATE disputes, transactions, accounts CASCADE")
        await conn.close()
