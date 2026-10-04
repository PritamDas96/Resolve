"""Integration test: the audit hash chain detects tampering (skips without a DB)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from resolve.config import get_settings
from resolve.security.audit import append_event, apply_audit_schema, verify_chain

if TYPE_CHECKING:
    import asyncpg


async def _connect_or_skip() -> asyncpg.Connection:
    import asyncpg

    try:
        return await asyncpg.connect(get_settings().postgres_dsn, timeout=3)
    except Exception as exc:
        pytest.skip(f"Postgres not reachable ({exc}); start it with `make up`.")


async def test_audit_chain_detects_tamper() -> None:
    conn = await _connect_or_skip()
    try:
        await conn.execute("DROP TABLE IF EXISTS audit_log")  # ensure the current schema
        await apply_audit_schema(conn)

        await append_event(conn, actor="u1", action="draft.created", resource="case/1")
        await append_event(conn, actor="u1", action="case.approved", resource="case/1")
        await append_event(conn, actor="u2", action="draft.created", resource="case/2")

        intact = await verify_chain(conn)
        assert intact.ok is True
        assert intact.rows == 3

        # Tamper with the middle row's details; the chain must break there.
        await conn.execute(
            "UPDATE audit_log SET details = '{\"tampered\": true}'::jsonb WHERE seq = 2"
        )
        broken = await verify_chain(conn)
        assert broken.ok is False
        assert broken.first_bad_seq == 2
    finally:
        await conn.execute("TRUNCATE audit_log RESTART IDENTITY")
        await conn.close()
