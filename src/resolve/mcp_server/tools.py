"""The five RESOLVE tools, behind scope + RLS enforcement (PLAN §10.2-10.6).

Each tool checks a coarse JWT **scope** and, for queue-scoped data, runs inside an
**RLS session** so Postgres filters rows to the caller's queues. Not-found and
not-permitted return the same shape (``None`` / empty), so cross-queue existence never
leaks. These functions are the single source of truth; the MCP server
(:mod:`resolve.mcp_server.server`) and the agent both call them.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from resolve.domain import deadlines as dl
from resolve.security.auth import Principal, require_scope
from resolve.security.rls import rls_session

if TYPE_CHECKING:
    import asyncpg

    from resolve.agent.tools import Retriever

__all__ = [
    "compute_deadlines",
    "get_account",
    "get_account_disputes",
    "get_complaint",
    "search_regulations",
]


async def get_account(
    conn: asyncpg.Connection, principal: Principal, account_id: str
) -> dict[str, Any] | None:
    """Return an account the caller is allowed to see, else None (scope: accounts:read)."""
    require_scope(principal, "accounts:read")
    async with rls_session(conn, principal) as scoped:
        row = await scoped.fetchrow(
            "SELECT account_id, queue_id, bank, product_type, status, opened_on "
            "FROM accounts WHERE account_id = $1",
            account_id,
        )
    return dict(row) if row else None


async def get_account_disputes(
    conn: asyncpg.Connection, principal: Principal, account_id: str
) -> list[dict[str, Any]]:
    """Return disputes for an in-scope account (scope: accounts:read)."""
    require_scope(principal, "accounts:read")
    async with rls_session(conn, principal) as scoped:
        rows = await scoped.fetch(
            "SELECT dispute_id, account_id, notice_received_on, provisional_credit_on, "
            "resolved_on, outcome FROM disputes WHERE account_id = $1 ORDER BY dispute_id",
            account_id,
        )
    return [dict(r) for r in rows]


async def get_complaint(
    conn: asyncpg.Connection, principal: Principal, complaint_id: int
) -> dict[str, Any] | None:
    """Return complaint metadata the caller may see, else None (scope: cases:read)."""
    require_scope(principal, "cases:read")
    async with rls_session(conn, principal) as scoped:
        row = await scoped.fetchrow(
            "SELECT complaint_id, bank, product, issue, queue_id, split "
            "FROM complaints WHERE complaint_id = $1",
            complaint_id,
        )
    return dict(row) if row else None


def search_regulations(
    retriever: Retriever,
    principal: Principal,
    query: str,
    *,
    as_of: date | None = None,
    regulation: str | None = None,
    k: int = 5,
) -> list[dict[str, Any]]:
    """Point-in-time regulation search (scope: regulations:read). No PII, no RLS."""
    require_scope(principal, "regulations:read")
    results = retriever(query, as_of=as_of, regulation=regulation, k=k)
    return [
        {
            "ref": r.citation_id,
            "section": r.section,
            "heading_path": r.heading_path,
            "text": r.text[:400],
        }
        for r in results
    ]


def compute_deadlines(
    principal: Principal,
    notice_received: date,
    *,
    new_account: bool = False,
    pos_or_foreign: bool = False,
    provisional_credit_given: bool = False,
) -> list[dict[str, Any]]:
    """Compute Reg E error-resolution deadlines (scope: deadlines:compute).

    The LLM never computes dates; it extracts the facts and this tool returns the
    deadlines with the CFR paragraph each implements (other regulations are available
    via :mod:`resolve.domain.deadlines`).
    """
    require_scope(principal, "deadlines:compute")
    deadlines = dl.reg_e_error_resolution(
        notice_received,
        new_account=new_account,
        pos_or_foreign=pos_or_foreign,
        provisional_credit_given=provisional_credit_given,
    )
    return [
        {"name": d.name, "due": d.due.isoformat(), "rule": d.rule, "basis": str(d.basis)}
        for d in deadlines
    ]
