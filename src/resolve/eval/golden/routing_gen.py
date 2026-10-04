"""Generate the Tier A routing golden set (``eval/golden/routing_test.jsonl``, PLAN §7.8).

Stratified sample from the **test split** of ``complaints.parquet`` (never train/val),
balanced across the four product families, plus a smaller PR subset for the fast CI
gate. Selection is fully deterministic (sort by ``complaint_id``, then take evenly
spaced indices per family) so re-running produces an identical file.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import polars as pl

from resolve.config import Settings, get_settings
from resolve.data import taxonomy
from resolve.eval.schemas import GOLDEN_DIR, RoutingItem, write_jsonl
from resolve.logging import configure_logging, get_logger

__all__ = [
    "PR_PATH",
    "ROUTING_PATH",
    "TARGET_PR",
    "TARGET_TOTAL",
    "build",
    "main",
    "stratified_sample",
]

log = get_logger(__name__)

ROUTING_PATH = GOLDEN_DIR / "routing_test.jsonl"
PR_PATH = GOLDEN_DIR / "routing_pr.jsonl"
TARGET_TOTAL = 3000
TARGET_PR = 300


def _even_indices(n_available: int, n_want: int) -> list[int]:
    """Return ``n_want`` evenly spaced indices into ``range(n_available)`` (deterministic)."""
    if n_available <= n_want:
        return list(range(n_available))
    step = n_available / n_want
    return [int(i * step) for i in range(n_want)]


def stratified_sample(
    df: pl.DataFrame, *, total: int, tax: taxonomy.Taxonomy | None = None
) -> list[RoutingItem]:
    """Deterministically sample ``total`` test-split complaints, balanced by family.

    Args:
        df: Processed complaints frame (must include ``split`` and ``product``).
        total: Target number of items; split evenly across families, capped by
            availability.
        tax: Loaded taxonomy; defaults to the cached canonical map.

    Returns:
        ``RoutingItem`` records, sorted by family then ``complaint_id`` for a stable
        output order and ids.
    """
    taxon = tax or taxonomy.load_taxonomy()
    test = (
        df.filter(pl.col("split") == "test")
        .with_columns(
            pl.col("product")
            .replace_strict(taxon.products, default=taxonomy.UNMAPPED, return_dtype=pl.Utf8)
            .alias("family")
        )
        .filter(pl.col("family") != taxonomy.UNMAPPED)
    )

    families = sorted(test["family"].unique().to_list())
    per_family = total // len(families) if families else 0

    picked: list[dict[str, Any]] = []
    for family in families:
        rows = test.filter(pl.col("family") == family).sort("complaint_id").to_dicts()
        for idx in _even_indices(len(rows), per_family):
            picked.append(rows[idx])

    picked.sort(key=lambda r: (str(r["family"]), int(r["complaint_id"])))
    return [
        RoutingItem(
            id=f"R-{i:04d}",
            complaint_id=int(r["complaint_id"]),
            bank=str(r["bank"]),
            product=str(r["product"]),
            sub_product=r["sub_product"],
            issue=str(r["issue"]),
            sub_issue=r["sub_issue"],
            family=str(r["family"]),
            split="test",
        )
        for i, r in enumerate(picked, start=1)
    ]


def _pr_subset(items: list[RoutingItem], n_want: int) -> list[RoutingItem]:
    """Evenly spaced per-family subset of ``items`` for the fast CI gate."""
    families = sorted({it.family for it in items})
    per_family = n_want // len(families) if families else 0
    out: list[RoutingItem] = []
    for family in families:
        fam_items = [it for it in items if it.family == family]
        out.extend(fam_items[idx] for idx in _even_indices(len(fam_items), per_family))
    return out


def build(settings: Settings | None = None) -> dict[str, int]:
    """Generate and write both routing golden files; returns the counts written."""
    settings = settings or get_settings()
    df = pl.read_parquet(Path(settings.data_dir) / "processed" / "complaints.parquet")
    items = stratified_sample(df, total=TARGET_TOTAL)
    pr_items = _pr_subset(items, TARGET_PR)
    return {
        "routing_test": write_jsonl(ROUTING_PATH, items),
        "routing_pr": write_jsonl(PR_PATH, pr_items),
    }


def main() -> int:
    """CLI entry point: ``python -m resolve.eval.golden.routing_gen``."""
    configure_logging()
    counts = build()
    log.info("routing_golden_written", **counts, path=str(ROUTING_PATH))
    return 0


if __name__ == "__main__":
    sys.exit(main())
