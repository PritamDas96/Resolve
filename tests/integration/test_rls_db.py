"""Integration test: Postgres row-level security isolates queues (skips without a DB).

Proves authorisation is enforced by the database, not the prompt: a deposits analyst
cannot see a cards account, and vice versa, via the real MCP tool + RLS session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from resolve.config import get_settings
from resolve.data.synth_accounts import apply_schema
from resolve.mcp_server import tools
from resolve.security.auth import Principal
from resolve.security.rls import apply_rls

if TYPE_CHECKING:
    import asyncpg


async def _connect_or_skip() -> asyncpg.Connection:
    import asyncpg

    try:
        return await asyncpg.connect(get_settings().postgres_dsn, timeout=3)
    except Exception as exc:
        pytest.skip(f"Postgres not reachable ({exc}); start it with `make up`.")


async def _seed(conn: asyncpg.Connection) -> None:
    await apply_schema(conn)
    await apply_rls(conn)
    # Users + queue assignments.
    await conn.execute(
        "INSERT INTO app_users (user_id, role) VALUES ('u_dep','analyst'),('u_card','analyst') "
        "ON CONFLICT (user_id) DO NOTHING"
    )
    await conn.execute(
        "INSERT INTO user_queues (user_id, queue_id) VALUES ('u_dep','deposits'),"
        "('u_card','cards') ON CONFLICT DO NOTHING"
    )
    # One account per queue (owner insert bypasses RLS).
    await conn.execute(
        "INSERT INTO accounts (account_id, queue_id, bank, product_type, opened_on, "
        "holder_name, holder_email, status) VALUES "
        "('ACC-DEP','deposits','Citi','checking','2024-01-01','A','a@x.test','open'),"
        "('ACC-CARD','cards','Citi','credit_card','2024-01-01','B','b@x.test','open') "
        "ON CONFLICT (account_id) DO NOTHING"
    )


async def test_rls_isolates_queues() -> None:
    conn = await _connect_or_skip()
    try:
        await _seed(conn)
        dep = Principal(
            user_id="u_dep", role="analyst", queues=["deposits"], scopes=["accounts:read"]
        )
        card = Principal(
            user_id="u_card", role="analyst", queues=["cards"], scopes=["accounts:read"]
        )

        # Deposits analyst sees the deposits account, not the cards one.
        assert (await tools.get_account(conn, dep, "ACC-DEP")) is not None
        assert (await tools.get_account(conn, dep, "ACC-CARD")) is None
        # Cards analyst sees the mirror image.
        assert (await tools.get_account(conn, card, "ACC-CARD")) is not None
        assert (await tools.get_account(conn, card, "ACC-DEP")) is None

        # An admin bypasses the queue filter.
        admin = Principal(user_id="root", role="admin", queues=[], scopes=[])
        assert (await tools.get_account(conn, admin, "ACC-DEP")) is not None
        assert (await tools.get_account(conn, admin, "ACC-CARD")) is not None
    finally:
        await conn.execute("DELETE FROM accounts WHERE account_id IN ('ACC-DEP','ACC-CARD')")
        await conn.execute("DELETE FROM user_queues WHERE user_id IN ('u_dep','u_card')")
        await conn.execute("DELETE FROM app_users WHERE user_id IN ('u_dep','u_card')")
        await conn.close()
