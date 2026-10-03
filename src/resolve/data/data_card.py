"""Data card generation (PLAN §7.2 step 9, §7.12).

Renders ``docs/data_card.md`` from the ingested artifacts: the processed
``complaints.parquet`` (counts by bank, year and product family, plus temporal
splits and the UNMAPPED tally), the committed source manifests (CFPB, eCFR, bank
documents) and the taxonomy map. Synthetic-account counts are passed in by the
caller (read from Postgres after ``make data-accounts``), so this module needs
neither a database nor the network.

The card is a *reproducible* artifact: :func:`render_card` is a pure function of
:class:`DataCardStats`, so the same inputs always produce byte-identical markdown
(no wall-clock timestamps in the body — provenance dates come from the manifests).

Ethics (§7.12): the card states honestly that CFPB narratives are unverified,
consent-only (not a representative sample), that complaint volume tracks company
size (so the card never ranks a bank as "worst"), and that all account PII is
synthetic. RESOLVE never concludes that a named bank violated a law.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import BaseModel

from resolve.config import Settings, get_settings
from resolve.data import taxonomy
from resolve.logging import configure_logging, get_logger

__all__ = [
    "DataCardStats",
    "bank_counts",
    "build",
    "family_year_counts",
    "gather_stats",
    "main",
    "render_card",
    "split_counts",
    "unmapped_count",
]

log = get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_CARD_PATH = _REPO_ROOT / "docs" / "data_card.md"

# Temporal-split definitions (PLAN §7.2); mirrors cfpb_ingest's boundaries.
_SPLIT_ORDER = ("train", "val", "test")
_SPLIT_RANGES = {
    "train": "≤ 31 Dec 2023",
    "val": "2024",
    "test": "2025 - present",
}


class DataCardStats(BaseModel):
    """Everything :func:`render_card` needs — a pure, serialisable snapshot.

    Attributes:
        total_complaints: In-scope complaint rows in ``complaints.parquet``.
        counts_by_split: Rows per temporal split (train/val/test).
        counts_by_bank: Rows per display bank name.
        family_year_counts: One ``{bank, year, family, count}`` dict per cell,
            UNMAPPED families excluded.
        unmapped_complaints: Rows whose product maps to UNMAPPED (reported, not
            silently dropped).
        cfpb_manifest: Parsed ``cfpb.json`` manifest, if present.
        ecfr_manifest: Parsed ``ecfr.json`` manifest, if present.
        bank_docs_manifest: Parsed ``bank_docs.json`` manifest, if present.
        synthetic: ``{accounts, transactions, disputes}`` counts, if loaded.
    """

    total_complaints: int
    counts_by_split: dict[str, int]
    counts_by_bank: dict[str, int]
    family_year_counts: list[dict[str, Any]]
    unmapped_complaints: int
    cfpb_manifest: dict[str, Any] | None = None
    ecfr_manifest: dict[str, Any] | None = None
    bank_docs_manifest: dict[str, Any] | None = None
    synthetic: dict[str, int] | None = None


# --- pure counting ----------------------------------------------------------


def split_counts(df: pl.DataFrame) -> dict[str, int]:
    """Return complaint counts per temporal split, ordered train/val/test."""
    counts = {str(r["split"]): int(r["count"]) for r in _value_counts(df, "split")}
    return {split: counts.get(split, 0) for split in _SPLIT_ORDER if split in counts} or counts


def bank_counts(df: pl.DataFrame) -> dict[str, int]:
    """Return complaint counts per display bank name."""
    return {str(r["bank"]): int(r["count"]) for r in _value_counts(df, "bank")}


def family_year_counts(df: pl.DataFrame, *, tax: taxonomy.Taxonomy | None = None) -> pl.DataFrame:
    """Count complaints by bank x year x product family, excluding UNMAPPED.

    Args:
        df: Processed complaints (``bank``, ``year``, ``product`` columns).
        tax: Loaded taxonomy; defaults to the cached canonical map.

    Returns:
        A frame with columns ``bank``, ``year``, ``family``, ``count``, sorted.
    """
    taxon = tax or taxonomy.load_taxonomy()
    labelled = df.with_columns(
        pl.col("product")
        .replace_strict(taxon.products, default=taxonomy.UNMAPPED, return_dtype=pl.Utf8)
        .alias("family")
    ).filter(pl.col("family") != taxonomy.UNMAPPED)
    return (
        labelled.group_by(["bank", "year", "family"])
        .agg(pl.len().alias("count"))
        .sort(["bank", "year", "family"])
    )


def unmapped_count(df: pl.DataFrame, *, tax: taxonomy.Taxonomy | None = None) -> int:
    """Return how many rows map to UNMAPPED (out-of-scope / unknown family)."""
    taxon = tax or taxonomy.load_taxonomy()
    mapped = df.filter(pl.col("product").is_in(list(taxon.products)))
    return df.height - mapped.height


def _value_counts(df: pl.DataFrame, column: str) -> list[dict[str, Any]]:
    """Return ``[{column: value, count: n}, ...]`` sorted for determinism."""
    if column not in df.columns or df.height == 0:
        return []
    return df.group_by(column).agg(pl.len().alias("count")).sort(column).to_dicts()


# --- orchestration ----------------------------------------------------------


def _read_manifest(data_dir: Path, name: str) -> dict[str, Any] | None:
    """Return a parsed manifest under ``data_dir/manifests``, or None if absent."""
    path = data_dir / "manifests" / name
    if not path.exists():
        return None
    return dict(json.loads(path.read_text(encoding="utf-8")))


def gather_stats(
    settings: Settings,
    *,
    df: pl.DataFrame | None = None,
    tax: taxonomy.Taxonomy | None = None,
    synthetic: dict[str, int] | None = None,
) -> DataCardStats:
    """Assemble :class:`DataCardStats` from the processed data and manifests.

    Args:
        settings: Application settings (data dir).
        df: Pre-loaded complaints frame; read from parquet when omitted.
        tax: Loaded taxonomy; defaults to the cached canonical map.
        synthetic: ``{accounts, transactions, disputes}`` counts from Postgres.

    Returns:
        A populated :class:`DataCardStats`.
    """
    taxon = tax or taxonomy.load_taxonomy()
    data_dir = Path(settings.data_dir)
    if df is None:
        df = pl.read_parquet(data_dir / "processed" / "complaints.parquet")

    return DataCardStats(
        total_complaints=df.height,
        counts_by_split=split_counts(df),
        counts_by_bank=bank_counts(df),
        family_year_counts=family_year_counts(df, tax=taxon).to_dicts(),
        unmapped_complaints=unmapped_count(df, tax=taxon),
        cfpb_manifest=_read_manifest(data_dir, "cfpb.json"),
        ecfr_manifest=_read_manifest(data_dir, "ecfr.json"),
        bank_docs_manifest=_read_manifest(data_dir, "bank_docs.json"),
        synthetic=synthetic,
    )


# --- rendering --------------------------------------------------------------


def _md_table(headers: list[str], rows: list[list[object]]) -> str:
    """Render a GitHub-flavoured markdown table (header + rows)."""
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def _sources_section(stats: DataCardStats) -> list[str]:
    """Render the Sources section from whichever manifests are present."""
    lines = ["## Sources", ""]
    cfpb = stats.cfpb_manifest
    if cfpb:
        retrieved = cfpb.get("retrieved_at", "unknown")
        lines.append(
            f"- **CFPB Consumer Complaint Database** (public search API, CSV export). "
            f"Metadata only — CFPB no longer distributes narrative text. Retrieved {retrieved}."
        )
    else:
        lines.append("- **CFPB Consumer Complaint Database** — not yet ingested (run `make data`).")
    ecfr = stats.ecfr_manifest
    if ecfr:
        lines.append(
            "- **eCFR** point-in-time regulation snapshots (Title 12 parts, plus Supplement I)."
        )
    else:
        lines.append("- **eCFR** regulations — not yet ingested (run `make data`).")
    docs = stats.bank_docs_manifest
    doc_count = len(docs.get("documents", [])) if isinstance(docs, dict) else 0
    lines.append(
        f"- **Bank documents** (public deposit agreements and fee schedules): "
        f"{doc_count} document(s) ingested. PDFs and extracted text are never committed — "
        f"only the manifest."
    )
    lines.append(
        "- **Synthetic accounts, transactions and disputes** — generated locally, fully "
        "seeded; no real customer data is ever used."
    )
    return lines


def render_card(stats: DataCardStats, *, tax: taxonomy.Taxonomy | None = None) -> str:
    """Render the full data card markdown from a :class:`DataCardStats`.

    Pure and deterministic: the same ``stats`` always yield identical output.

    Args:
        stats: The gathered statistics.
        tax: Loaded taxonomy; defaults to the cached canonical map.

    Returns:
        The complete ``docs/data_card.md`` contents (trailing newline included).
    """
    taxon = tax or taxonomy.load_taxonomy()
    lines: list[str] = [
        "# RESOLVE — Data card",
        "",
        "Provenance, filters, counts and known limitations for the data foundation. "
        "All personal data is synthetic; no real customer or client data is used. "
        "Regenerate with `make data-card`.",
        "",
    ]

    lines += _sources_section(stats)

    # Filters
    lines += [
        "",
        "## Filters",
        "",
        "- Six banks (JPMorgan Chase, Bank of America, Wells Fargo, Citi, Capital One, U.S. Bank).",
        "- Complaints that originally had a consumer narrative (`has_narrative=true`).",
        "- Four in-scope, regulation-aligned product families (deposits, cards, mortgage, "
        "credit reporting as furnisher); all other products are out of scope.",
        "- Deduplicated on `complaint_id`.",
    ]

    # Counts
    lines += [
        "",
        "## Counts",
        "",
        f"- **Total in-scope complaints:** {stats.total_complaints:,}",
        f"- **UNMAPPED** (product outside the four families; excluded from routing "
        f"metrics, never silently dropped): {stats.unmapped_complaints:,}",
        "",
        "### By bank",
        "",
        _md_table(
            ["Bank", "Complaints"],
            [[bank, f"{count:,}"] for bank, count in sorted(stats.counts_by_bank.items())],
        ),
        "",
        "### By bank x year x product family",
        "",
        _md_table(
            ["Bank", "Year", "Family", "Count"],
            [
                [r["bank"], r["year"], r["family"], f"{int(r['count']):,}"]
                for r in stats.family_year_counts
            ],
        ),
        "",
        "### Synthetic data",
        "",
    ]
    if stats.synthetic:
        lines.append(
            _md_table(
                ["Table", "Rows"],
                [[name, f"{count:,}"] for name, count in sorted(stats.synthetic.items())],
            )
        )
    else:
        lines.append(
            "Not yet loaded. Run `make data-accounts` to generate and load synthetic accounts."
        )

    # Splits
    lines += [
        "",
        "## Splits",
        "",
        "Temporal split (never random) to prevent leakage into the routing golden set:",
        "",
        _md_table(
            ["Split", "Complaint dates", "Complaints"],
            [
                [split, _SPLIT_RANGES[split], f"{stats.counts_by_split.get(split, 0):,}"]
                for split in _SPLIT_ORDER
            ],
        ),
    ]

    # Taxonomy mapping
    lines += [
        "",
        "## Taxonomy mapping",
        "",
        "CFPB revised its product/issue categories (2017 consolidation; ~2023 split/rename), "
        "so raw product strings are mapped to four stable, regulation-aligned families "
        "(`data/taxonomy_map.yaml`, verified against observed values — never from memory):",
        "",
        _md_table(
            ["Family", "Label", "Governing regulation"],
            [
                [family, meta.get("label", ""), meta.get("regulation", "")]
                for family, meta in sorted(taxon.families.items())
            ],
        ),
        "",
        f"- {len(taxon.products)} CFPB product strings (all eras) map to these families; "
        f"{len(taxon.issues)} legacy issue strings are crosswalked to the current vocabulary.",
        "- Unmappable labels become `UNMAPPED`: excluded from routing metrics, counted above.",
    ]

    # Known biases
    lines += [
        "",
        "## Known biases and limitations",
        "",
        "- CFPB narratives are **consent-only** submissions and are **not a representative "
        "sample** of all complaints or of any bank's customers.",
        "- Complaint **volume depends on company size** and submission propensity; the counts "
        "above must not be read as a bank quality ranking.",
        "- CFPB states that narrative allegations are **unverified** consumer opinions. RESOLVE "
        "presents them as allegations only and never concludes that a named bank violated a law.",
        "- Narrative text is not distributed by CFPB; synthetic narratives (generated separately) "
        "are grounded in the real routing labels.",
        "- All account holders, transactions and disputes are **synthetic**; no attempt is made "
        "to re-identify anyone.",
    ]

    # Licence
    lines += [
        "",
        "## Licence",
        "",
        "- **CFPB Consumer Complaint Database:** U.S. Government work, public domain.",
        "- **eCFR:** U.S. Government work, public domain.",
        "- **Bank documents:** public materials, redistributed only as hashes/metadata "
        "(the PDFs themselves are not committed).",
        "- **Synthetic data:** produced by this project; no licence restrictions.",
        "",
    ]
    return "\n".join(lines)


def build(
    settings: Settings,
    *,
    out_path: Path | None = None,
    synthetic: dict[str, int] | None = None,
) -> Path:
    """Render the data card and write it to disk.

    Args:
        settings: Application settings (data dir).
        out_path: Destination; defaults to ``docs/data_card.md`` at the repo root.
        synthetic: Synthetic-table counts from Postgres, if available.

    Returns:
        The path the card was written to.
    """
    stats = gather_stats(settings, synthetic=synthetic)
    card = render_card(stats)
    destination = out_path or DATA_CARD_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(card, encoding="utf-8")
    return destination


async def _synthetic_counts(dsn: str) -> dict[str, int] | None:
    """Best-effort synthetic-table counts from Postgres (None if unreachable)."""
    try:
        import asyncpg

        conn = await asyncpg.connect(dsn, timeout=3)
    except Exception as exc:  # the card is still useful without a DB.
        log.warning("data_card_db_unreachable", error=str(exc))
        return None
    try:
        counts: dict[str, int] = {}
        for table in ("accounts", "transactions", "disputes"):
            value = await conn.fetchval(f"SELECT count(*) FROM {table}")
            counts[table] = int(value or 0)
        return counts
    except Exception as exc:  # tables may not be seeded yet.
        log.warning("data_card_synthetic_counts_failed", error=str(exc))
        return None
    finally:
        await conn.close()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m resolve.data.data_card``."""
    argparse.ArgumentParser(description="Generate docs/data_card.md.").parse_args(argv)
    configure_logging()
    settings = get_settings()
    synthetic = asyncio.run(_synthetic_counts(settings.postgres_dsn))
    path = build(settings, synthetic=synthetic)
    log.info("data_card_written", path=str(path), synthetic_loaded=synthetic is not None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
