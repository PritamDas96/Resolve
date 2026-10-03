"""Taxonomy normalisation (PLAN §7.3, ADR-016).

CFPB revised its product/issue categories twice (the 2017 consolidation and a
~2023 split/rename), so raw CFPB product strings are not a stable routing target.
This module maps every observed in-scope CFPB ``product`` string to one of four
stable, regulation-aligned **families** (deposits, cards, mortgage,
credit_reporting), and normalises legacy ``issue`` strings to the current CFPB
issue vocabulary. The canonical vocabulary and the legacy crosswalk live in the
committed, data-derived :data:`TAXONOMY_MAP_PATH` (``data/taxonomy_map.yaml``).

Anything not covered maps to :data:`UNMAPPED`, which routing metrics exclude and
the data card counts (never silently dropped).

The generated :mod:`resolve.data.taxonomy_enums` constrains structured outputs to
valid values and encodes the valid ``family -> issue`` paths; it is produced by
:func:`render_enums_module` (``python -m resolve.data.taxonomy --generate-enums``)
and kept in sync by :func:`enums_in_sync`.
"""

from __future__ import annotations

import argparse
import re
import sys
from functools import lru_cache
from pathlib import Path

import polars as pl
import yaml
from pydantic import BaseModel

from resolve.logging import configure_logging, get_logger

__all__ = [
    "TAXONOMY_ENUMS_PATH",
    "TAXONOMY_MAP_PATH",
    "UNMAPPED",
    "Taxonomy",
    "canonical_issues",
    "enums_in_sync",
    "is_valid_path",
    "load_taxonomy",
    "main",
    "normalize_frame",
    "normalize_issue",
    "normalize_product",
    "render_enums_module",
]

log = get_logger(__name__)

# Sentinel for labels outside the canonical taxonomy (excluded from routing
# metrics, counted in the data card).
UNMAPPED = "UNMAPPED"

# Repo-root-relative locations of the curated map and the generated enums.
_REPO_ROOT = Path(__file__).resolve().parents[3]
TAXONOMY_MAP_PATH = _REPO_ROOT / "data" / "taxonomy_map.yaml"
TAXONOMY_ENUMS_PATH = Path(__file__).resolve().parent / "taxonomy_enums.py"


class Taxonomy(BaseModel):
    """The canonical taxonomy loaded from ``taxonomy_map.yaml``.

    Attributes:
        families: Family key -> metadata (``label``, ``regulation``).
        products: CFPB product string -> family key.
        family_issues: Family key -> ordered canonical issue strings.
        issues: Legacy/renamed issue string -> canonical issue string.
    """

    families: dict[str, dict[str, str]]
    products: dict[str, str]
    family_issues: dict[str, list[str]]
    issues: dict[str, str]

    def canonical_issue_set(self) -> frozenset[str]:
        """Return every canonical issue string across all families."""
        return frozenset(issue for issues in self.family_issues.values() for issue in issues)

    def issue_lookup(self) -> dict[str, str]:
        """Return a combined ``raw issue -> canonical issue`` map.

        Canonical issues map to themselves; legacy strings map via ``issues``.
        """
        lookup = {issue: issue for issue in self.canonical_issue_set()}
        lookup.update(self.issues)
        return lookup


@lru_cache(maxsize=4)
def load_taxonomy(path: Path | str | None = None) -> Taxonomy:
    """Load and validate the taxonomy map (cached per path).

    Args:
        path: Map file to load; defaults to :data:`TAXONOMY_MAP_PATH`.

    Returns:
        The validated :class:`Taxonomy`.
    """
    source = Path(path) if path is not None else TAXONOMY_MAP_PATH
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    taxonomy = Taxonomy.model_validate(data)
    _validate_consistency(taxonomy)
    return taxonomy


def _validate_consistency(taxonomy: Taxonomy) -> None:
    """Fail fast on an internally inconsistent map.

    Raises:
        ValueError: If a product/issue references an unknown family, or a legacy
            issue maps to a string that is not a canonical issue.
    """
    family_keys = set(taxonomy.families)
    unknown_products = {f for f in taxonomy.products.values() if f not in family_keys}
    if unknown_products:
        raise ValueError(f"products reference unknown families: {sorted(unknown_products)}")
    unknown_issue_families = set(taxonomy.family_issues) - family_keys
    if unknown_issue_families:
        raise ValueError(
            f"family_issues reference unknown families: {sorted(unknown_issue_families)}"
        )
    canonical = taxonomy.canonical_issue_set()
    bad_targets = {v for v in taxonomy.issues.values() if v not in canonical}
    if bad_targets:
        raise ValueError(f"legacy issues map to non-canonical issues: {sorted(bad_targets)}")


# --- scalar normalisation ---------------------------------------------------


def normalize_product(product: str | None, *, taxonomy: Taxonomy | None = None) -> str:
    """Map a CFPB product string to its family, or :data:`UNMAPPED`.

    Args:
        product: Raw CFPB ``product`` value (any era); ``None`` is unmapped.
        taxonomy: Loaded taxonomy; defaults to the cached canonical map.

    Returns:
        A family key (e.g. ``"cards"``) or :data:`UNMAPPED`.
    """
    tax = taxonomy or load_taxonomy()
    if product is None:
        return UNMAPPED
    return tax.products.get(product, UNMAPPED)


def normalize_issue(issue: str | None, *, taxonomy: Taxonomy | None = None) -> str:
    """Map a CFPB issue string to the canonical issue, or :data:`UNMAPPED`.

    Args:
        issue: Raw CFPB ``issue`` value (any era); ``None`` is unmapped.
        taxonomy: Loaded taxonomy; defaults to the cached canonical map.

    Returns:
        A canonical issue string or :data:`UNMAPPED`.
    """
    tax = taxonomy or load_taxonomy()
    if issue is None:
        return UNMAPPED
    return tax.issue_lookup().get(issue, UNMAPPED)


def is_valid_path(family: str, issue: str, *, taxonomy: Taxonomy | None = None) -> bool:
    """Return whether ``issue`` is a canonical issue of ``family``.

    Args:
        family: A family key.
        issue: A canonical issue string.
        taxonomy: Loaded taxonomy; defaults to the cached canonical map.

    Returns:
        True iff ``family`` is known and ``issue`` is one of its canonical issues.
    """
    tax = taxonomy or load_taxonomy()
    return issue in set(tax.family_issues.get(family, []))


def canonical_issues(*, taxonomy: Taxonomy | None = None) -> frozenset[str]:
    """Return every canonical issue string (all families)."""
    return (taxonomy or load_taxonomy()).canonical_issue_set()


# --- frame normalisation ----------------------------------------------------


def normalize_frame(
    df: pl.DataFrame,
    *,
    product_col: str = "product",
    issue_col: str = "issue",
    taxonomy: Taxonomy | None = None,
) -> pl.DataFrame:
    """Add canonical ``family``, ``canonical_issue`` and ``taxonomy_valid`` columns.

    Args:
        df: Complaints with product and issue columns.
        product_col: Name of the raw product column.
        issue_col: Name of the raw issue column.
        taxonomy: Loaded taxonomy; defaults to the cached canonical map.

    Returns:
        ``df`` with three added columns: ``family`` (or ``UNMAPPED``),
        ``canonical_issue`` (or ``UNMAPPED``) and ``taxonomy_valid`` (bool — both
        mapped and the issue valid for the family).
    """
    tax = taxonomy or load_taxonomy()
    valid_paths = {f"{fam}\x1f{iss}" for fam, issues in tax.family_issues.items() for iss in issues}
    return df.with_columns(
        pl.col(product_col)
        .replace_strict(tax.products, default=UNMAPPED, return_dtype=pl.Utf8)
        .alias("family"),
        pl.col(issue_col)
        .replace_strict(tax.issue_lookup(), default=UNMAPPED, return_dtype=pl.Utf8)
        .alias("canonical_issue"),
    ).with_columns(
        pl.concat_str([pl.col("family"), pl.col("canonical_issue")], separator="\x1f")
        .is_in(valid_paths)
        .alias("taxonomy_valid")
    )


# --- enum generation --------------------------------------------------------


def _slug(value: str) -> str:
    """Turn a taxonomy string into an UPPER_SNAKE Python identifier."""
    return re.sub(r"[^0-9a-zA-Z]+", "_", value).strip("_").upper()


def render_enums_module(taxonomy: Taxonomy) -> str:
    """Render the ``taxonomy_enums`` module source from a taxonomy.

    The output is deterministic (families and issues sorted) so a committed copy
    can be checked for drift against the map.

    Args:
        taxonomy: The taxonomy to render.

    Returns:
        The full Python source of the generated module.

    Raises:
        ValueError: If two distinct strings slug to the same enum member name.
    """
    families = sorted(taxonomy.families)
    issues = sorted(taxonomy.canonical_issue_set())

    _assert_unique_slugs(families, "family")
    _assert_unique_slugs(issues, "issue")

    lines: list[str] = [
        '"""Generated taxonomy enums (PLAN §7.3, ADR-016). Do not edit by hand.',
        "",
        "Regenerate with: python -m resolve.data.taxonomy --generate-enums",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from enum import StrEnum",
        "",
        "",
        "class Family(StrEnum):",
        '    """Canonical, regulation-aligned product families."""',
        "",
    ]
    lines += [f'    {_slug(f)} = "{f}"' for f in families]
    lines += [
        "",
        "",
        "class Issue(StrEnum):",
        '    """Canonical current CFPB issue strings."""',
        "",
    ]
    lines += [f'    {_slug(i)} = "{_escape(i)}"' for i in issues]
    lines += ["", "", "FAMILY_ISSUES: dict[Family, frozenset[Issue]] = {"]
    for family in families:
        members = ", ".join(f"Issue.{_slug(i)}" for i in sorted(taxonomy.family_issues[family]))
        lines.append(f"    Family.{_slug(family)}: frozenset({{{members}}}),")
    lines += ["}", ""]
    return "\n".join(lines)


def _escape(value: str) -> str:
    """Escape a string for embedding in a double-quoted Python literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _assert_unique_slugs(values: list[str], kind: str) -> None:
    """Raise if any two values collide on their slug."""
    seen: dict[str, str] = {}
    for value in values:
        slug = _slug(value)
        if slug in seen:
            raise ValueError(f"{kind} slug collision: {seen[slug]!r} and {value!r} -> {slug}")
        seen[slug] = value


def enums_in_sync(*, taxonomy: Taxonomy | None = None) -> bool:
    """Return whether the committed enums module matches the current map."""
    tax = taxonomy or load_taxonomy()
    if not TAXONOMY_ENUMS_PATH.exists():
        return False
    return TAXONOMY_ENUMS_PATH.read_text(encoding="utf-8") == render_enums_module(tax)


# --- CLI --------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="Taxonomy normalisation and enum generation.")
    parser.add_argument(
        "--generate-enums", action="store_true", help="Write the generated enums module."
    )
    parser.add_argument(
        "--check", action="store_true", help="Exit non-zero if the enums module is out of sync."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m resolve.data.taxonomy``.

    Returns:
        Process exit code (0 on success, 1 if ``--check`` finds drift).
    """
    args = _build_arg_parser().parse_args(argv)
    configure_logging()
    taxonomy = load_taxonomy()

    if args.check:
        in_sync = enums_in_sync(taxonomy=taxonomy)
        log.info("taxonomy_enums_check", in_sync=in_sync, path=str(TAXONOMY_ENUMS_PATH))
        return 0 if in_sync else 1

    if args.generate_enums:
        TAXONOMY_ENUMS_PATH.write_text(render_enums_module(taxonomy), encoding="utf-8")
        log.info("taxonomy_enums_written", path=str(TAXONOMY_ENUMS_PATH))
        return 0

    log.info(
        "taxonomy_loaded",
        families=sorted(taxonomy.families),
        products=len(taxonomy.products),
        canonical_issues=len(taxonomy.canonical_issue_set()),
        legacy_issue_mappings=len(taxonomy.issues),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
