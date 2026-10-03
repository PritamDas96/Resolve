"""Unit tests for :mod:`resolve.data.taxonomy`.

These tests are the specification for taxonomy normalisation. They run against the
committed, data-derived ``data/taxonomy_map.yaml`` (the curated canonical map) and
the generated ``taxonomy_enums`` module, plus small in-memory frames. No network.
"""

from __future__ import annotations

import polars as pl
import pytest

from resolve.data import taxonomy
from resolve.data.taxonomy import UNMAPPED
from resolve.data.taxonomy_enums import FAMILY_ISSUES, Family, Issue

TAX = taxonomy.load_taxonomy()


# --- loading / consistency --------------------------------------------------


def test_load_taxonomy_is_internally_consistent() -> None:
    # families referenced by products and family_issues all exist
    assert set(TAX.products.values()) <= set(TAX.families)
    assert set(TAX.family_issues) == set(TAX.families)
    # every legacy issue maps to a canonical issue
    assert set(TAX.issues.values()) <= TAX.canonical_issue_set()


def test_validate_consistency_rejects_bad_family_reference() -> None:
    bad = taxonomy.Taxonomy(
        families={"cards": {"label": "Cards", "regulation": "Reg Z"}},
        products={"Mortgage": "mortgage"},  # unknown family
        family_issues={"cards": ["Fees or interest"]},
        issues={},
    )
    with pytest.raises(ValueError, match="unknown families"):
        taxonomy._validate_consistency(bad)


def test_validate_consistency_rejects_legacy_issue_to_noncanonical() -> None:
    bad = taxonomy.Taxonomy(
        families={"cards": {"label": "Cards", "regulation": "Reg Z"}},
        products={"Credit card": "cards"},
        family_issues={"cards": ["Fees or interest"]},
        issues={"APR or interest rate": "Nonexistent canonical issue"},
    )
    with pytest.raises(ValueError, match="non-canonical"):
        taxonomy._validate_consistency(bad)


# --- product normalisation --------------------------------------------------


def test_normalize_product_maps_all_eras_to_families() -> None:
    assert taxonomy.normalize_product("Checking or savings account") == "deposits"
    assert taxonomy.normalize_product("Bank account or service") == "deposits"  # pre-2017
    assert taxonomy.normalize_product("Credit card") == "cards"
    assert taxonomy.normalize_product("Credit card or prepaid card") == "cards"  # 2017-2022
    assert taxonomy.normalize_product("Prepaid card") == "cards"
    assert taxonomy.normalize_product("Mortgage") == "mortgage"
    assert taxonomy.normalize_product("Credit reporting") == "credit_reporting"  # pre-2017
    assert (
        taxonomy.normalize_product("Credit reporting or other personal consumer reports")
        == "credit_reporting"
    )


def test_normalize_product_unmapped_for_out_of_scope_and_none() -> None:
    assert taxonomy.normalize_product("Student loan") == UNMAPPED
    assert taxonomy.normalize_product("Debt collection") == UNMAPPED
    assert taxonomy.normalize_product(None) == UNMAPPED


# --- issue normalisation ----------------------------------------------------


def test_normalize_issue_identity_for_canonical() -> None:
    assert taxonomy.normalize_issue("Fees or interest") == "Fees or interest"
    assert (
        taxonomy.normalize_issue("Incorrect information on your report")
        == "Incorrect information on your report"
    )


def test_normalize_issue_applies_legacy_renames() -> None:
    assert (
        taxonomy.normalize_issue("Incorrect information on credit report")  # pre-2017
        == "Incorrect information on your report"
    )
    assert (
        taxonomy.normalize_issue(
            "Problem with a credit reporting company's investigation into an existing problem"
        )
        == "Problem with a company's investigation into an existing problem"
    )
    assert taxonomy.normalize_issue("APR or interest rate") == "Fees or interest"
    assert (
        taxonomy.normalize_issue("Loan modification,collection,foreclosure")
        == "Struggling to pay mortgage"
    )


def test_normalize_issue_unmapped_for_unknown_and_none() -> None:
    assert taxonomy.normalize_issue("Totally made up issue") == UNMAPPED
    assert taxonomy.normalize_issue(None) == UNMAPPED


# --- path validity ----------------------------------------------------------


def test_is_valid_path() -> None:
    assert taxonomy.is_valid_path("cards", "Fees or interest") is True
    assert taxonomy.is_valid_path("mortgage", "Trouble during payment process") is True
    # right issue, wrong family
    assert taxonomy.is_valid_path("mortgage", "Fees or interest") is False
    assert taxonomy.is_valid_path("UNMAPPED", "Fees or interest") is False


# --- frame normalisation ----------------------------------------------------


def test_normalize_frame_adds_family_issue_and_validity() -> None:
    df = pl.DataFrame(
        {
            "product": [
                "Credit card or prepaid card",  # cards
                "Bank account or service",  # deposits
                "Student loan",  # out of scope
                "Mortgage",  # mortgage
            ],
            "issue": [
                "APR or interest rate",  # -> Fees or interest (valid for cards)
                "Problems caused by my funds being low",  # -> canonical deposits issue
                "Dealing with your lender or servicer",  # out-of-scope product
                "Fees or interest",  # valid issue but wrong family -> invalid path
            ],
        }
    )

    out = taxonomy.normalize_frame(df)

    assert out["family"].to_list() == ["cards", "deposits", UNMAPPED, "mortgage"]
    assert out["canonical_issue"].to_list() == [
        "Fees or interest",
        "Problem caused by your funds being low",
        "Dealing with your lender or servicer",
        "Fees or interest",
    ]
    # cards+Fees valid; deposits+funds valid; UNMAPPED family invalid; mortgage+Fees invalid
    assert out["taxonomy_valid"].to_list() == [True, True, False, False]


# --- generated enums --------------------------------------------------------


def test_generated_enums_match_map() -> None:
    assert {f.value for f in Family} == set(TAX.families)
    assert {i.value for i in Issue} == TAX.canonical_issue_set()
    for family, issues in TAX.family_issues.items():
        assert {i.value for i in FAMILY_ISSUES[Family(family)]} == set(issues)


def test_enums_module_is_in_sync_with_map() -> None:
    # fails if someone edits taxonomy_map.yaml without regenerating the enums
    assert taxonomy.enums_in_sync(taxonomy=TAX)


def test_render_enums_module_is_deterministic() -> None:
    assert taxonomy.render_enums_module(TAX) == taxonomy.render_enums_module(TAX)


# --- definition of done (PLAN §7.3 step 5) ----------------------------------


def test_representative_current_labels_map_to_valid_paths() -> None:
    # A sample of real current (product, issue) pairs — every one must resolve to
    # a valid family/issue enum path (the §7.3 "test split maps cleanly" property).
    current_pairs = [
        ("Checking or savings account", "Managing an account"),
        ("Credit card", "Problem with a purchase shown on your statement"),
        ("Prepaid card", "Trouble using the card"),
        ("Mortgage", "Struggling to pay mortgage"),
        (
            "Credit reporting or other personal consumer reports",
            "Incorrect information on your report",
        ),
    ]
    for product, issue in current_pairs:
        family = taxonomy.normalize_product(product)
        canonical = taxonomy.normalize_issue(issue)
        assert family != UNMAPPED, product
        assert canonical != UNMAPPED, issue
        assert taxonomy.is_valid_path(family, canonical), (product, issue)
