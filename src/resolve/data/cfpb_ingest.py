"""CFPB complaint ingestion (PLAN §7.2, ADR-014).

This module builds the real-metadata half of the data foundation: it downloads
consumer-complaint records for the six in-scope banks from the CFPB search API's
filtered CSV **export**, normalises them, deduplicates, and writes a single
``complaints.parquet`` plus a committed manifest.

Why the export and not the bulk file or the JSON search (see ADR-014):

* CFPB no longer distributes the consumer-narrative text through any endpoint, so
  this extract is **metadata only** — real routing labels (product / sub-product
  / issue / sub-issue), dates and ids. Synthetic narratives are generated
  separately and grounded in these labels.
* The endpoint is Akamai-protected: plain ``curl``/``httpx`` get a 403, so the
  single network seam (:func:`fetch_export_text`) uses ``curl_cffi`` with a
  browser TLS fingerprint.
* The paginated JSON search caps ``from + size`` at 10k; the filtered CSV export
  streams the full scoped set, so we fetch per ``(company, year)`` window.

The module is split so that every transform is a pure function over a Polars
frame (unit-tested on a fixture) and all I/O is isolated in
:func:`fetch_export_text`, :func:`download_all` and :func:`ingest`.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from resolve import config
from resolve.config import Settings, get_settings
from resolve.logging import configure_logging, get_logger

__all__ = [
    "IngestResult",
    "assign_bank_display",
    "build_export_params",
    "data_report",
    "deduplicate",
    "download_all",
    "fetch_export_text",
    "filter_in_scope",
    "ingest",
    "main",
    "parse_export_csv",
    "sha256_file",
    "write_manifest",
]

log = get_logger(__name__)

# CFPB CSV export header -> canonical snake_case column names.
_COLUMN_RENAME: dict[str, str] = {
    "Date received": "date_received",
    "Product": "product",
    "Sub-product": "sub_product",
    "Issue": "issue",
    "Sub-issue": "sub_issue",
    "Company public response": "company_public_response",
    "Company": "company",
    "State": "state",
    "ZIP code": "zip_code",
    "Tags": "tags",
    "Submitted via": "submitted_via",
    "Date sent to company": "date_sent_to_company",
    "Company response to consumer": "company_response",
    "Timely response?": "timely_response",
    "Complaint ID": "complaint_id",
}

# CFPB timestamps look like ``2024-01-01T10:01:54.000Z``.
_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S%.fZ"

# Temporal split boundaries (PLAN §7.2): train <= 2023, val = 2024, test >= 2025.
_TRAIN_MAX_YEAR = 2023
_VAL_YEAR = 2024


class IngestResult(BaseModel):
    """Summary of one ingestion run, returned by :func:`ingest`.

    Attributes:
        output_path: Path to the written ``complaints.parquet``.
        manifest_path: Path to the committed ``cfpb.json`` manifest.
        rows: Number of complaints in the processed output.
        dropped_duplicates: Rows removed by :func:`deduplicate`.
        banks: Row count per display bank name.
    """

    output_path: Path
    manifest_path: Path
    rows: int
    dropped_duplicates: int
    banks: dict[str, int]


# --- pure transforms --------------------------------------------------------


def parse_export_csv(text: str) -> pl.DataFrame:
    """Parse one CFPB CSV export into the canonical complaint schema.

    Columns are renamed to snake_case, ``complaint_id`` is cast to ``Int64``,
    the two timestamp columns are reduced to ``Date``, and ``year`` / ``split``
    are derived from ``date_received``.

    Args:
        text: Raw CSV text (with the standard CFPB export header). A header-only
            string is valid and yields a zero-row frame with the full schema.

    Returns:
        A Polars frame with the canonical columns plus ``year`` and ``split``.
    """
    df = pl.read_csv(io.BytesIO(text.encode("utf-8")), infer_schema_length=0)
    rename = {src: dst for src, dst in _COLUMN_RENAME.items() if src in df.columns}
    df = df.rename(rename)

    df = df.with_columns(
        pl.col("complaint_id").cast(pl.Int64),
        pl.col("date_received").str.to_datetime(_ISO_FORMAT, strict=False).dt.date(),
        pl.col("date_sent_to_company").str.to_datetime(_ISO_FORMAT, strict=False).dt.date(),
    )
    df = df.with_columns(pl.col("date_received").dt.year().alias("year"))
    return df.with_columns(
        pl.when(pl.col("year") <= _TRAIN_MAX_YEAR)
        .then(pl.lit("train"))
        .when(pl.col("year") == _VAL_YEAR)
        .then(pl.lit("val"))
        .otherwise(pl.lit("test"))
        .alias("split")
    )


def filter_in_scope(
    df: pl.DataFrame, *, bank_strings: set[str], products: frozenset[str] | set[str]
) -> pl.DataFrame:
    """Keep only rows for the in-scope banks and product families.

    Args:
        df: Parsed complaints.
        bank_strings: Exact CFPB ``company`` strings for the six banks.
        products: In-scope CFPB ``product`` strings (current + legacy).

    Returns:
        The subset of ``df`` whose company and product are both in scope.
    """
    return df.filter(
        pl.col("company").is_in(list(bank_strings)) & pl.col("product").is_in(list(products))
    )


def deduplicate(df: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    """Drop rows that repeat a ``complaint_id``, keeping the first occurrence.

    Args:
        df: Complaints, possibly with duplicate ids (overlapping export windows).

    Returns:
        A ``(deduplicated_frame, dropped_count)`` tuple.
    """
    before = df.height
    deduped = df.unique(subset=["complaint_id"], keep="first", maintain_order=True)
    return deduped, before - deduped.height


def assign_bank_display(df: pl.DataFrame, banks: dict[str, tuple[str, ...]]) -> pl.DataFrame:
    """Add a ``bank`` column mapping each CFPB company string to its display name.

    Args:
        df: Complaints with a ``company`` column.
        banks: Mapping of display name to the CFPB company string(s).

    Returns:
        ``df`` with an added ``bank`` column (null for unmapped companies).
    """
    mapping = {string: display for display, strings in banks.items() for string in strings}
    return df.with_columns(
        pl.col("company").replace_strict(mapping, default=None, return_dtype=pl.Utf8).alias("bank")
    )


def data_report(df: pl.DataFrame) -> pl.DataFrame:
    """Count complaints by bank, year and product (PLAN §7.2 step 9).

    Args:
        df: Processed complaints with ``bank``, ``year`` and ``product`` columns.

    Returns:
        A frame with columns ``bank``, ``year``, ``product`` and ``count``.
    """
    return (
        df.group_by(["bank", "year", "product"])
        .agg(pl.len().alias("count"))
        .sort(["bank", "year", "product"])
    )


# --- hashing / manifest -----------------------------------------------------


def sha256_file(path: Path | str) -> str:
    """Return the hex SHA-256 of a file, read in chunks.

    Args:
        path: File to hash.

    Returns:
        The lowercase hexadecimal digest.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(path: Path | str, **fields: object) -> None:
    """Write ``fields`` as a stable, pretty-printed JSON manifest.

    Keys are sorted and non-JSON values (e.g. ``Path``) are stringified so the
    output is deterministic given the same inputs.

    Args:
        path: Destination file; parent directories are created.
        **fields: Arbitrary JSON-serialisable manifest fields.
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(fields, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )


# --- network seam -----------------------------------------------------------


def build_export_params(
    company: str, date_min: date, date_max: date, *, has_narrative: bool = True
) -> list[tuple[str, str]]:
    """Build the CFPB CSV-export query parameters for one company/date window.

    Args:
        company: Exact CFPB ``company`` string.
        date_min: Inclusive lower bound on ``date_received``.
        date_max: Inclusive upper bound on ``date_received``.
        has_narrative: Restrict to complaints that originally had a narrative.

    Returns:
        A list of ``(key, value)`` query-parameter pairs.
    """
    params = [
        ("format", "csv"),
        ("company", company),
        ("date_received_min", date_min.isoformat()),
        ("date_received_max", date_max.isoformat()),
    ]
    if has_narrative:
        params.append(("has_narrative", "true"))
    return params


@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=2, min=5, max=120),
)
def _get_export(params: list[tuple[str, str]]) -> str:
    """GET the CFPB export, impersonating a browser to pass Akamai (ADR-014).

    The endpoint rate-limits sustained scraping with HTTP 429; the retry uses a
    long exponential backoff (up to ~2 min) so a full six-bank crawl rides out
    transient throttling. Honours a ``Retry-After`` header when present.
    """
    from curl_cffi import requests as cffi_requests

    response = cffi_requests.get(
        config.CFPB_API_BASE,
        params=params,
        impersonate=config.CFPB_IMPERSONATE,
        timeout=180,
    )
    status = int(response.status_code)
    if status == 429:
        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            time.sleep(min(int(retry_after), 120))
        raise RuntimeError("CFPB export rate-limited (HTTP 429)")
    if status >= 400:
        raise RuntimeError(f"CFPB export returned HTTP {status}")
    return str(response.text)


def fetch_export_text(company: str, date_min: date, date_max: date, *, delay_s: float = 1.0) -> str:
    """Fetch one CFPB CSV export, throttled and retried.

    This is the module's single network seam; tests monkeypatch it.

    Args:
        company: Exact CFPB ``company`` string.
        date_min: Inclusive lower bound on ``date_received``.
        date_max: Inclusive upper bound on ``date_received``.
        delay_s: Polite delay applied before the request (~1 req/s).

    Returns:
        The CSV response body (standard export header).
    """
    if delay_s > 0:
        time.sleep(delay_s)
    return _get_export(build_export_params(company, date_min, date_max))


# --- orchestration ----------------------------------------------------------


def _slug(company: str) -> str:
    """Return a filesystem-safe slug for a company string."""
    return re.sub(r"[^a-z0-9]+", "_", company.lower()).strip("_")


def download_all(
    companies: list[str],
    *,
    start_year: int,
    end_year: int,
    cache_dir: Path,
    delay_s: float,
    refresh: bool = False,
) -> list[Path]:
    """Download (or reuse cached) CSV exports for every company and year.

    Each ``(company, year)`` export is cached to disk so re-runs are resumable
    and reproduce an identical processed output without re-hitting the API.

    Args:
        companies: CFPB company strings to fetch.
        start_year: First complaint year (inclusive).
        end_year: Last complaint year (inclusive).
        cache_dir: Root directory for cached exports.
        delay_s: Per-request throttle in seconds.
        refresh: Re-fetch even when a cached file exists.

    Returns:
        The list of cached CSV paths, in fetch order.
    """
    paths: list[Path] = []
    for company in companies:
        slug = _slug(company)
        for year in range(start_year, end_year + 1):
            cache_path = cache_dir / slug / f"{year}.csv"
            if cache_path.exists() and not refresh:
                log.debug("cfpb_cache_hit", company=company, year=year, path=str(cache_path))
                paths.append(cache_path)
                continue
            text = fetch_export_text(company, date(year, 1, 1), date(year, 12, 31), delay_s=delay_s)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(text, encoding="utf-8")
            log.info("cfpb_fetched", company=company, year=year, bytes=len(text))
            paths.append(cache_path)
    return paths


def ingest(
    settings: Settings,
    *,
    refresh: bool = False,
    banks: dict[str, tuple[str, ...]] | None = None,
) -> IngestResult:
    """Run the full CFPB ingestion and write the processed outputs.

    Args:
        settings: Application settings (data dir, since-year, request delay).
        refresh: Re-fetch all exports instead of reusing the cache.
        banks: Override the default six-bank mapping (used by the CLI smoke run).

    Returns:
        An :class:`IngestResult` describing the written outputs.
    """
    banks = banks or config.BANKS
    data_dir = Path(settings.data_dir)
    cache_dir = data_dir / "raw" / "cfpb"
    output_path = data_dir / "processed" / "complaints.parquet"
    manifest_path = data_dir / "manifests" / "cfpb.json"

    companies = [string for strings in banks.values() for string in strings]
    start_year = settings.cfpb_since_year
    end_year = datetime.now(tz=UTC).year

    paths = download_all(
        companies,
        start_year=start_year,
        end_year=end_year,
        cache_dir=cache_dir,
        delay_s=settings.cfpb_request_delay_s,
        refresh=refresh,
    )

    # Filter each export to in-scope rows *before* concatenating. The raw exports
    # include every product for a company (auto loans, debt collection, ...); the
    # in-scope subset is far smaller, so filtering per-file keeps peak memory low
    # enough for a full six-bank crawl.
    bank_strings = set(companies)
    scoped_frames: list[pl.DataFrame] = []
    exports: list[dict[str, object]] = []
    for path in paths:
        frame = parse_export_csv(path.read_text(encoding="utf-8"))
        exports.append({"path": str(path), "sha256": sha256_file(path), "rows": frame.height})
        scoped_frames.append(
            filter_in_scope(frame, bank_strings=bank_strings, products=config.IN_SCOPE_PRODUCTS)
        )
        del frame

    combined = pl.concat(scoped_frames, how="vertical")
    deduped, dropped = deduplicate(combined)
    labelled = assign_bank_display(deduped, banks)
    final = labelled.sort("complaint_id")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.write_parquet(output_path)

    bank_counts: dict[str, int] = {
        str(row["bank"]): int(row["count"])
        for row in final.group_by("bank").agg(pl.len().alias("count")).to_dicts()
    }

    write_manifest(
        manifest_path,
        source="CFPB Consumer Complaint Database (live search API, CSV export)",
        api_base=config.CFPB_API_BASE,
        retrieved_at=datetime.now(tz=UTC).isoformat(),
        filters={
            "banks": {display: list(strings) for display, strings in banks.items()},
            "products": sorted(config.IN_SCOPE_PRODUCTS),
            "has_narrative": True,
            "since_year": start_year,
        },
        exports=exports,
        processed={
            "path": str(output_path),
            "sha256": sha256_file(output_path),
            "rows": final.height,
            "dropped_duplicates": dropped,
            "counts_by_bank": bank_counts,
        },
        note=(
            "Narratives are NOT distributed by CFPB; this extract is metadata-only. "
            "Synthetic narratives are generated separately (ADR-014)."
        ),
    )

    log.info(
        "cfpb_ingest_complete",
        rows=final.height,
        dropped_duplicates=dropped,
        banks=bank_counts,
        output=str(output_path),
    )
    return IngestResult(
        output_path=output_path,
        manifest_path=manifest_path,
        rows=final.height,
        dropped_duplicates=dropped,
        banks=bank_counts,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="Ingest CFPB complaint metadata for six banks.")
    parser.add_argument(
        "--since-year", type=int, default=None, help="Override the earliest complaint year."
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Re-fetch all exports, ignoring the cache."
    )
    parser.add_argument(
        "--only-bank",
        action="append",
        default=None,
        metavar="DISPLAY_NAME",
        help="Restrict ingestion to one or more display bank names (smoke runs).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: ``python -m resolve.data.cfpb_ingest``.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).
    """
    args = _build_arg_parser().parse_args(argv)
    configure_logging()
    # Polars renders tables with box-drawing glyphs; force UTF-8 so the human
    # summary does not crash on Windows' legacy console code page.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    if args.since_year is not None:
        settings = settings.model_copy(update={"cfpb_since_year": args.since_year})

    banks = config.BANKS
    if args.only_bank:
        banks = {name: config.BANKS[name] for name in args.only_bank}

    result = ingest(settings, refresh=args.refresh, banks=banks)
    report = data_report(pl.read_parquet(result.output_path))
    log.info("cfpb_ingest_report", rows=result.rows, banks=result.banks)
    with pl.Config(tbl_rows=100, tbl_cols=-1):
        print(report)


if __name__ == "__main__":
    main()
