"""Load CFPB complaint metadata into Postgres (PLAN §7.2 step 8, §7.6 step 7).

Reads the processed ``complaints.parquet`` (produced by
:mod:`resolve.data.cfpb_ingest`), assigns each complaint its routing ``queue_id``
= product family (via :mod:`resolve.data.taxonomy`, ADR-016), and loads the rows
into the ``complaints`` table. Narratives are not available yet (ADR-014), so
``narrative_raw`` / ``narrative_masked`` / ``account_id`` are left NULL and
backfilled by later tasks.

The pure row-preparation (:func:`prepare_rows`) is unit-tested offline; the async
load (:func:`load`) is isolated and covered by an integration test that skips when
no database is reachable.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

from resolve.config import Settings, get_settings
from resolve.data import taxonomy
from resolve.data.synth_accounts import apply_schema
from resolve.logging import configure_logging, get_logger

if TYPE_CHECKING:
    import asyncpg

__all__ = ["dropped_unmapped", "load", "main", "prepare_rows"]

log = get_logger(__name__)

# Columns inserted into the complaints table, in order.
_COLUMNS = (
    "complaint_id",
    "bank",
    "date_received",
    "product",
    "sub_product",
    "issue",
    "sub_issue",
    "queue_id",
    "split",
)


def prepare_rows(
    df: pl.DataFrame, *, tax: taxonomy.Taxonomy | None = None
) -> list[tuple[Any, ...]]:
    """Prepare complaint rows for insertion: assign queue, drop unmapped families.

    Args:
        df: Processed complaints (``cfpb_ingest`` schema).
        tax: Loaded taxonomy; defaults to the cached canonical map.

    Returns:
        One tuple per in-scope complaint, matching :data:`_COLUMNS`.
    """
    taxon = tax or taxonomy.load_taxonomy()
    mapping = taxon.products
    labelled = df.with_columns(
        pl.col("product")
        .replace_strict(mapping, default=taxonomy.UNMAPPED, return_dtype=pl.Utf8)
        .alias("queue_id")
    ).filter(pl.col("queue_id") != taxonomy.UNMAPPED)

    return [
        (
            int(row["complaint_id"]),
            row["bank"],
            row["date_received"],
            row["product"],
            row["sub_product"],
            row["issue"],
            row["sub_issue"],
            row["queue_id"],
            row["split"],
        )
        for row in labelled.iter_rows(named=True)
    ]


def dropped_unmapped(df: pl.DataFrame, *, tax: taxonomy.Taxonomy | None = None) -> int:
    """Return how many rows would be dropped as UNMAPPED (out-of-scope family)."""
    taxon = tax or taxonomy.load_taxonomy()
    mapped = df.filter(pl.col("product").is_in(list(taxon.products)))
    return df.height - mapped.height


async def load(
    parquet_path: Path | str,
    *,
    dsn: str,
    truncate: bool = False,
    ensure_schema: bool = True,
) -> dict[str, int]:
    """Load complaints from a parquet file into Postgres.

    Idempotent per row (``ON CONFLICT (complaint_id) DO NOTHING``).

    Args:
        parquet_path: Path to ``complaints.parquet``.
        dsn: PostgreSQL DSN.
        truncate: Clear the complaints table first.
        ensure_schema: Apply ``sql/001_schema.sql`` before loading.

    Returns:
        ``{"loaded": n, "dropped_unmapped": m}``.
    """
    import asyncpg

    df = pl.read_parquet(parquet_path)
    rows = prepare_rows(df)
    dropped = dropped_unmapped(df)

    conn: asyncpg.Connection = await asyncpg.connect(dsn)
    try:
        if ensure_schema:
            await apply_schema(conn)
        # Bulk path: stream the rows into an unconstrained temp table with COPY
        # (orders of magnitude faster than per-row INSERT for ~10^6 rows), then a
        # single set-based upsert preserves the idempotent ON CONFLICT contract.
        # The whole load is one transaction so TRUNCATE + upsert is atomic and the
        # ON COMMIT DROP temp table survives until the final commit.
        async with conn.transaction():
            if truncate:
                await conn.execute("TRUNCATE complaints CASCADE")
            await conn.execute(
                "CREATE TEMP TABLE _complaints_stage "
                "(LIKE complaints INCLUDING DEFAULTS) ON COMMIT DROP"
            )
            await conn.copy_records_to_table(
                "_complaints_stage", records=rows, columns=list(_COLUMNS)
            )
            await conn.execute(
                f"INSERT INTO complaints ({', '.join(_COLUMNS)}) "
                f"SELECT {', '.join(_COLUMNS)} FROM _complaints_stage "
                "ON CONFLICT (complaint_id) DO NOTHING"
            )
    finally:
        await conn.close()
    return {"loaded": len(rows), "dropped_unmapped": dropped}


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m resolve.data.complaints_load``."""
    parser = argparse.ArgumentParser(description="Load CFPB complaints into Postgres.")
    parser.add_argument("--truncate", action="store_true", help="Clear the table before loading.")
    args = parser.parse_args(argv)
    configure_logging()
    settings: Settings = get_settings()

    parquet_path = Path(settings.data_dir) / "processed" / "complaints.parquet"
    counts = asyncio.run(load(parquet_path, dsn=settings.postgres_dsn, truncate=args.truncate))
    log.info("complaints_loaded", dsn=settings.postgres_dsn.split("@")[-1], **counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
