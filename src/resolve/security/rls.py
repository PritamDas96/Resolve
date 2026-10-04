"""Row-level-security session helpers (PLAN §13.6).

Wraps a unit of work in a transaction that SET ROLEs into the non-privileged
``resolve_app`` role and sets ``app.user_id`` / ``app.role`` so the RLS policies in
``sql/002_rls.sql`` filter every queue-scoped query to the acting user's queues.
Because the settings are ``LOCAL``, they are scoped to the transaction and reset on
commit/rollback — no leakage between requests on a pooled connection.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from resolve.config import Settings, get_settings
from resolve.security.auth import Principal

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import asyncpg

__all__ = ["RLS_SQL_PATH", "apply_rls", "rls_session"]

RLS_SQL_PATH = Path(__file__).resolve().parents[3] / "sql" / "002_rls.sql"


async def apply_rls(conn: asyncpg.Connection) -> None:
    """Apply ``sql/002_rls.sql`` (role, policies). Idempotent; run as the DB owner."""
    await conn.execute(RLS_SQL_PATH.read_text(encoding="utf-8"))


@asynccontextmanager
async def rls_session(
    conn: asyncpg.Connection, principal: Principal, *, settings: Settings | None = None
) -> AsyncIterator[asyncpg.Connection]:
    """Open an RLS-scoped transaction for ``principal``.

    Inside the ``async with`` block, every query runs as ``resolve_app`` with
    ``app.user_id``/``app.role`` set, so RLS applies. Use for all account/complaint
    reads on behalf of a user.
    """
    settings = settings or get_settings()
    async with conn.transaction():
        await conn.execute(f"SET LOCAL ROLE {settings.resolve_app_role}")
        # Parameterised set_config avoids any injection via the ids.
        await conn.execute("SELECT set_config('app.user_id', $1, true)", principal.user_id)
        await conn.execute("SELECT set_config('app.role', $1, true)", principal.role)
        yield conn
