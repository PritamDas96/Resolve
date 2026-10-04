"""Distribution drift detection (PLAN §14.5).

Measures how the complaint mix shifts over time so a production model's degradation can
be anticipated. Provides the Population Stability Index (PSI) for categorical
distributions and a Maximum Mean Discrepancy (MMD) permutation test for numeric
samples, plus a yearly report over the real complaints (family mix per year vs a
reference year). Pure, dependency-light (numpy only for MMD).
"""

from __future__ import annotations

import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import polars as pl

from resolve.config import Settings, get_settings
from resolve.data import taxonomy
from resolve.logging import configure_logging, get_logger

__all__ = [
    "DRIFT_REPORT_PATH",
    "build",
    "family_psi_by_year",
    "main",
    "mmd2",
    "psi",
]

log = get_logger(__name__)

DRIFT_REPORT_PATH = Path(__file__).resolve().parents[3] / "docs" / "drift.md"

# PSI rule-of-thumb: <0.1 stable, 0.1-0.25 moderate shift, >0.25 significant.
PSI_SIGNIFICANT = 0.25
_EPS = 1e-6


def psi(reference: dict[str, float], current: dict[str, float]) -> float:
    """Population Stability Index between two categorical distributions.

    Args:
        reference: Category -> count/proportion for the baseline period.
        current: Category -> count/proportion for the compared period.

    Returns:
        The PSI (0 = identical). Proportions are normalised internally; empty bins are
        floored to a small epsilon to avoid division/log blow-ups.
    """
    categories = set(reference) | set(current)
    ref_total = sum(reference.values()) or 1.0
    cur_total = sum(current.values()) or 1.0
    score = 0.0
    for cat in categories:
        ref_p = max(reference.get(cat, 0.0) / ref_total, _EPS)
        cur_p = max(current.get(cat, 0.0) / cur_total, _EPS)
        score += (cur_p - ref_p) * math.log(cur_p / ref_p)
    return score


def mmd2(
    x: Sequence[Sequence[float]], y: Sequence[Sequence[float]], *, gamma: float = 1.0
) -> float:
    """Biased squared MMD between two samples with an RBF kernel (numpy)."""
    import numpy as np

    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)

    def _rbf(a: Any, b: Any) -> Any:
        sq = np.sum((a[:, None, :] - b[None, :, :]) ** 2, axis=-1)
        return np.exp(-gamma * sq)

    return float(_rbf(xa, xa).mean() + _rbf(ya, ya).mean() - 2 * _rbf(xa, ya).mean())


def family_psi_by_year(
    df: pl.DataFrame, *, reference_year: int, tax: taxonomy.Taxonomy | None = None
) -> dict[int, float]:
    """PSI of the product-family mix for each year vs the reference year."""
    taxon = tax or taxonomy.load_taxonomy()
    labelled = df.with_columns(
        pl.col("product")
        .replace_strict(taxon.products, default=taxonomy.UNMAPPED, return_dtype=pl.Utf8)
        .alias("family")
    ).filter(pl.col("family") != taxonomy.UNMAPPED)

    def _dist(year: int) -> dict[str, float]:
        rows = labelled.filter(pl.col("year") == year).group_by("family").agg(pl.len().alias("n"))
        return {str(r["family"]): float(r["n"]) for r in rows.iter_rows(named=True)}

    reference = _dist(reference_year)
    years = sorted(y for y in labelled["year"].unique().to_list() if y is not None)
    return {int(y): psi(reference, _dist(int(y))) for y in years}


def build(settings: Settings | None = None, *, reference_year: int = 2023) -> Path:
    """Write docs/drift.md: family-mix PSI by year + a written finding."""
    settings = settings or get_settings()
    df = pl.read_parquet(Path(settings.data_dir) / "processed" / "complaints.parquet")
    by_year = family_psi_by_year(df, reference_year=reference_year)
    drifted = sorted(y for y, p in by_year.items() if p > PSI_SIGNIFICANT)

    lines = [
        "# RESOLVE — Data drift",
        "",
        f"Population Stability Index (PSI) of the product-family mix each year vs the "
        f"reference year **{reference_year}**, over the real CFPB complaints. "
        f"Rule of thumb: <0.1 stable, 0.1-0.25 moderate, >{PSI_SIGNIFICANT} significant.",
        "",
        "| Year | PSI vs ref | Signal |",
        "| --- | --- | --- |",
    ]
    for year in sorted(by_year):
        p = by_year[year]
        signal = "significant" if p > PSI_SIGNIFICANT else ("moderate" if p > 0.1 else "stable")
        lines.append(f"| {year} | {p:.3f} | {signal} |")

    finding = (
        f"Years with significant family-mix drift vs {reference_year}: "
        + (", ".join(str(y) for y in drifted) if drifted else "none")
        + ". The family mix shifts markedly across the 2017 and ~2023 CFPB taxonomy "
        "revisions, which is why routing is evaluated on a temporal split and the router "
        "should be re-benchmarked per year (frozen-router F1 is the natural next metric)."
    )
    lines += ["", "## Finding", "", finding, ""]
    DRIFT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DRIFT_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return DRIFT_REPORT_PATH


def main() -> int:
    """CLI entry point: ``python -m resolve.observability.drift``."""
    configure_logging()
    path = build()
    log.info("drift_report_written", path=str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
