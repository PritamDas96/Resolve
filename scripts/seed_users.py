"""Seed demo users, queue assignments, and print scoped JWTs (PLAN §10.4).

Applies the base schema + RLS, inserts one analyst per queue plus a reviewer and an
admin, and prints a signed JWT for each so you can exercise the MCP tools / API as
different roles. Run after `make up`:  ``uv run python scripts/seed_users.py``.
"""

from __future__ import annotations

import asyncio
import sys

from resolve.config import get_settings
from resolve.data.synth_accounts import apply_schema
from resolve.logging import configure_logging, get_logger
from resolve.security.auth import Principal, create_token
from resolve.security.rls import apply_rls

log = get_logger(__name__)

_QUEUES = ["deposits", "cards", "mortgage", "credit_reporting"]
_READ_SCOPES = ["cases:read", "accounts:read", "regulations:read", "deadlines:compute"]


def _demo_principals() -> list[Principal]:
    principals = [
        Principal(user_id=f"analyst_{q}", role="analyst", queues=[q], scopes=_READ_SCOPES)
        for q in _QUEUES
    ]
    principals.append(
        Principal(user_id="reviewer_all", role="reviewer", queues=_QUEUES, scopes=_READ_SCOPES)
    )
    principals.append(Principal(user_id="admin", role="admin", queues=[], scopes=[]))
    return principals


async def _seed() -> list[Principal]:
    import asyncpg

    settings = get_settings()
    conn = await asyncpg.connect(settings.postgres_dsn)
    try:
        await apply_schema(conn)
        await apply_rls(conn)
        principals = _demo_principals()
        for p in principals:
            await conn.execute(
                "INSERT INTO app_users (user_id, role) VALUES ($1, $2) "
                "ON CONFLICT (user_id) DO UPDATE SET role = EXCLUDED.role",
                p.user_id,
                p.role,
            )
            for queue in p.queues:
                await conn.execute(
                    "INSERT INTO user_queues (user_id, queue_id) VALUES ($1, $2) "
                    "ON CONFLICT DO NOTHING",
                    p.user_id,
                    queue,
                )
        return principals
    finally:
        await conn.close()


def main() -> int:
    """CLI entry point: ``uv run python scripts/seed_users.py``."""
    configure_logging()
    principals = asyncio.run(_seed())
    for p in principals:
        token = create_token(p, ttl_seconds=86400)
        print(f"\n# {p.user_id} ({p.role}; queues={p.queues or 'ALL'})")
        print(token)
    log.info("users_seeded", count=len(principals))
    return 0


if __name__ == "__main__":
    sys.exit(main())
