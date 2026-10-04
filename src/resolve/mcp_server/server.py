"""Authenticated MCP server exposing the five RESOLVE tools (PLAN §10.2-10.7).

The same server backs both the agent and an MCP client such as Claude Code. Every tool
takes a signed ``token``; authorisation is enforced by scope checks + Postgres RLS in
:mod:`resolve.mcp_server.tools`, never by the prompt. Run with
``python -m resolve.mcp_server.server`` (stdio transport).

Connections are opened lazily inside tool calls, so importing this module needs no
database or vector store (keeps it unit-testable).
"""

from __future__ import annotations

import sys
from datetime import date
from typing import Any

from mcp.server.mcpserver import MCPServer

from resolve.agent.tools import Retriever, make_retriever
from resolve.config import get_settings
from resolve.logging import configure_logging
from resolve.mcp_server import tools
from resolve.security.auth import verify_token

__all__ = ["main", "server"]

server = MCPServer("resolve")
_retriever: Retriever | None = None


def _get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = make_retriever()
    return _retriever


async def _connect() -> Any:
    import asyncpg

    return await asyncpg.connect(get_settings().postgres_dsn)


@server.tool()
def search_regulations(
    token: str, query: str, as_of: str | None = None, regulation: str | None = None, k: int = 5
) -> list[dict[str, Any]]:
    """Point-in-time regulation search. Requires scope regulations:read."""
    principal = verify_token(token)
    return tools.search_regulations(
        _get_retriever(),
        principal,
        query,
        as_of=date.fromisoformat(as_of) if as_of else None,
        regulation=regulation,
        k=k,
    )


@server.tool()
def compute_deadlines(
    token: str,
    notice_received: str,
    new_account: bool = False,
    pos_or_foreign: bool = False,
    provisional_credit_given: bool = False,
) -> list[dict[str, Any]]:
    """Compute Reg E error-resolution deadlines. Requires scope deadlines:compute."""
    principal = verify_token(token)
    return tools.compute_deadlines(
        principal,
        date.fromisoformat(notice_received),
        new_account=new_account,
        pos_or_foreign=pos_or_foreign,
        provisional_credit_given=provisional_credit_given,
    )


@server.tool()
async def get_account(token: str, account_id: str) -> dict[str, Any] | None:
    """Fetch an in-scope account. Requires scope accounts:read (RLS enforced)."""
    principal = verify_token(token)
    conn = await _connect()
    try:
        return await tools.get_account(conn, principal, account_id)
    finally:
        await conn.close()


@server.tool()
async def get_account_disputes(token: str, account_id: str) -> list[dict[str, Any]]:
    """Fetch disputes for an in-scope account. Requires scope accounts:read."""
    principal = verify_token(token)
    conn = await _connect()
    try:
        return await tools.get_account_disputes(conn, principal, account_id)
    finally:
        await conn.close()


@server.tool()
async def get_complaint(token: str, complaint_id: int) -> dict[str, Any] | None:
    """Fetch in-scope complaint metadata. Requires scope cases:read (RLS enforced)."""
    principal = verify_token(token)
    conn = await _connect()
    try:
        return await tools.get_complaint(conn, principal, complaint_id)
    finally:
        await conn.close()


def main() -> int:
    """CLI entry point: ``python -m resolve.mcp_server.server`` (stdio transport)."""
    configure_logging()
    server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
