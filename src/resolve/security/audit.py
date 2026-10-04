"""Tamper-evident audit log (PLAN §13.7).

Each privileged action is appended as a row whose ``hash`` chains the previous row's
hash with this row's canonical content. :func:`verify_chain` recomputes the whole chain
and reports the first row that does not match — so any later edit or deletion is
detectable. :func:`hash_event` is pure and unit-tested; the DB functions are covered by
an integration test (including a tamper case).

A hash chain proves integrity and ordering; it does not stop an attacker who can also
rewrite every subsequent hash (stated in ``THREAT_MODEL.md``).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    import asyncpg

__all__ = [
    "GENESIS",
    "AuditEvent",
    "ChainResult",
    "append_event",
    "apply_audit_schema",
    "hash_event",
    "verify_chain",
]

GENESIS = "GENESIS"


class AuditEvent(BaseModel):
    """One audit entry (before hashing)."""

    ts: str  # ISO-8601 timestamp
    actor: str
    action: str
    resource: str
    details: dict[str, Any] = {}


class ChainResult(BaseModel):
    """Result of verifying the audit chain."""

    ok: bool
    rows: int
    first_bad_seq: int | None = None


def hash_event(prev_hash: str, event: AuditEvent) -> str:
    """Compute the chained SHA-256 for an event given the previous row's hash."""
    payload = json.dumps(
        {
            "prev_hash": prev_hash,
            "ts": event.ts,
            "actor": event.actor,
            "action": event.action,
            "resource": event.resource,
            "details": event.details,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def apply_audit_schema(conn: asyncpg.Connection) -> None:
    """Apply ``sql/003_audit.sql`` (idempotent)."""
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "sql" / "003_audit.sql"
    await conn.execute(path.read_text(encoding="utf-8"))


async def append_event(
    conn: asyncpg.Connection,
    *,
    actor: str,
    action: str,
    resource: str,
    details: dict[str, Any] | None = None,
) -> str:
    """Append an audit event and return its hash (chained to the previous row)."""
    prev_hash = await conn.fetchval("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1")
    prev_hash = prev_hash or GENESIS
    event = AuditEvent(
        ts=dt.datetime.now(tz=dt.UTC).isoformat(),
        actor=actor,
        action=action,
        resource=resource,
        details=details or {},
    )
    row_hash = hash_event(prev_hash, event)
    await conn.execute(
        "INSERT INTO audit_log (ts, actor, action, resource, details, prev_hash, hash) "
        "VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)",
        event.ts,
        event.actor,
        event.action,
        event.resource,
        json.dumps(event.details),
        prev_hash,
        row_hash,
    )
    return row_hash


async def verify_chain(conn: asyncpg.Connection) -> ChainResult:
    """Recompute the chain from stored rows; report the first tampered row, if any."""
    rows = await conn.fetch(
        "SELECT seq, ts, actor, action, resource, details, prev_hash, hash "
        "FROM audit_log ORDER BY seq ASC"
    )
    expected_prev = GENESIS
    for row in rows:
        event = AuditEvent(
            ts=row["ts"].isoformat() if hasattr(row["ts"], "isoformat") else str(row["ts"]),
            actor=row["actor"],
            action=row["action"],
            resource=row["resource"],
            details=json.loads(row["details"])
            if isinstance(row["details"], str)
            else row["details"],
        )
        if row["prev_hash"] != expected_prev or hash_event(row["prev_hash"], event) != row["hash"]:
            return ChainResult(ok=False, rows=len(rows), first_bad_seq=int(row["seq"]))
        expected_prev = row["hash"]
    return ChainResult(ok=True, rows=len(rows))
