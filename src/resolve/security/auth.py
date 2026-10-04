"""Scoped JWT authentication (PLAN §10.4, §13.6).

Mints and verifies signed JWTs carrying the acting user's role, assigned queues and
scopes. Authorisation is then enforced two ways that never trust the prompt: coarse
**scope** checks here, and fine **row-level security** in Postgres (keyed off the same
user id). Tokens are HMAC-signed with ``settings.jwt_secret``.
"""

from __future__ import annotations

import datetime as dt

import jwt
from pydantic import BaseModel, Field

from resolve.config import Settings, get_settings

__all__ = ["Principal", "ScopeError", "create_token", "require_scope", "verify_token"]


class ScopeError(PermissionError):
    """Raised when a principal lacks a required scope."""


class Principal(BaseModel):
    """The authenticated caller: identity, role, queues and scopes."""

    user_id: str
    role: str  # analyst | reviewer | auditor | admin
    queues: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)


def create_token(
    principal: Principal, *, settings: Settings | None = None, ttl_seconds: int = 3600
) -> str:
    """Sign a JWT for ``principal`` valid for ``ttl_seconds``.

    ``ttl_seconds`` is relative; the absolute ``iat``/``exp`` are set by the caller's
    clock at mint time (acceptable for a portfolio project).
    """
    settings = settings or get_settings()
    now = dt.datetime.now(tz=dt.UTC)
    claims = {
        "sub": principal.user_id,
        "role": principal.role,
        "queues": principal.queues,
        "scopes": principal.scopes,
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + dt.timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(
        claims, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def verify_token(token: str, *, settings: Settings | None = None) -> Principal:
    """Verify a JWT and return the :class:`Principal`.

    Raises:
        PermissionError: If the token is invalid, expired, or has the wrong issuer.
    """
    settings = settings or get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iss", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise PermissionError(f"invalid token: {exc}") from exc
    return Principal(
        user_id=str(claims["sub"]),
        role=str(claims.get("role", "analyst")),
        queues=list(claims.get("queues", [])),
        scopes=list(claims.get("scopes", [])),
    )


def require_scope(principal: Principal, scope: str) -> None:
    """Raise :class:`ScopeError` unless ``principal`` holds ``scope`` (admin bypasses)."""
    if principal.role == "admin" or scope in principal.scopes:
        return
    raise ScopeError(f"missing required scope: {scope}")
