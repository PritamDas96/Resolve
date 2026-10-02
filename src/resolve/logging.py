"""Structured logging setup for RESOLVE.

We use :mod:`structlog` so every log line is a single JSON object with a stable
schema (timestamp, level, event, plus any bound context such as ``request_id``
or ``case_id``). JSON logs are trivial to query in production and to correlate
across the two services.

Usage:
    Call :func:`configure_logging` exactly once per process, at start-up (the
    FastAPI app, the MCP server, CLI entry points, the pytest session).
    Everywhere else, obtain a logger with :func:`get_logger` and bind context
    with ``logger.bind(...)``.
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.typing import FilteringBoundLogger


def configure_logging(*, level: str = "INFO", json_logs: bool = True) -> None:
    """Configure structlog for the current process.

    This is idempotent in effect: calling it again simply reconfigures the
    pipeline, which is convenient for tests that toggle ``level`` or
    ``json_logs``.

    Args:
        level: Minimum level to emit, e.g. ``"DEBUG"`` or ``"INFO"``. Records
            below this level are dropped cheaply, before rendering.
        json_logs: When ``True`` (the default, for production) render each event
            as JSON. When ``False`` use structlog's colourised console renderer,
            which is easier to read during local development.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Processors shared by both render modes. Order matters: context is merged
    # first, then metadata is added, then exceptions are formatted, and finally
    # the chosen renderer turns the event dict into a string.
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> FilteringBoundLogger:
    """Return a bound structlog logger.

    Args:
        name: Optional logical name for the logger, bound as the ``logger`` key
            so log lines can be filtered by component.

    Returns:
        A structlog bound logger ready for ``.info()``, ``.bind()``, etc.
    """
    logger: FilteringBoundLogger = structlog.get_logger()
    if name is not None:
        logger = logger.bind(logger=name)
    return logger
