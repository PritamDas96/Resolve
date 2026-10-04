"""Unit tests for auth (JWT scopes) + tool scope enforcement (offline, no DB)."""

from __future__ import annotations

from datetime import date

import pytest

from resolve.mcp_server import tools
from resolve.retrieval.search import SearchResult
from resolve.security.auth import (
    Principal,
    ScopeError,
    create_token,
    require_scope,
    verify_token,
)


def _principal(scopes: list[str], role: str = "analyst") -> Principal:
    return Principal(user_id="u1", role=role, queues=["deposits"], scopes=scopes)


def test_token_round_trip() -> None:
    token = create_token(_principal(["cases:read"]))
    p = verify_token(token)
    assert p.user_id == "u1"
    assert p.role == "analyst"
    assert p.queues == ["deposits"]
    assert "cases:read" in p.scopes


def test_verify_rejects_tampered_token() -> None:
    token = create_token(_principal(["cases:read"]))
    with pytest.raises(PermissionError):
        verify_token(token + "tamper")


def test_require_scope() -> None:
    require_scope(_principal(["accounts:read"]), "accounts:read")  # ok
    with pytest.raises(ScopeError):
        require_scope(_principal([]), "accounts:read")
    # admin bypasses scope checks
    require_scope(_principal([], role="admin"), "accounts:read")


def _fake_retriever(*_a: object, **_k: object) -> list[SearchResult]:
    return [
        SearchResult(
            chunk_id="1005.11@2023-01-01",
            citation_id="1005.11@2023-01-01",
            section="1005.11",
            regulation="Reg E",
            paragraph="",
            is_interpretation=False,
            interprets=None,
            heading_path="Reg E > §1005.11",
            text="Error resolution procedures.",
            score=1.0,
        )
    ]


def test_search_regulations_requires_scope() -> None:
    with pytest.raises(ScopeError):
        tools.search_regulations(_fake_retriever, _principal([]), "errors")
    out = tools.search_regulations(_fake_retriever, _principal(["regulations:read"]), "errors")
    assert out[0]["ref"] == "1005.11@2023-01-01"


def test_compute_deadlines_tool() -> None:
    with pytest.raises(ScopeError):
        tools.compute_deadlines(_principal([]), date(2025, 2, 3))
    out = tools.compute_deadlines(_principal(["deadlines:compute"]), date(2025, 2, 3))
    assert out[0]["name"] == "determination_or_provisional_credit"
    assert out[0]["due"] == "2025-02-18"
    assert "1005.11" in out[0]["rule"]
