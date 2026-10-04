"""Unit tests for the golden-set generators (offline — no DB, no real parquet)."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from resolve.eval.golden import deadlines_gen as dg
from resolve.eval.golden import routing_gen as rg
from resolve.eval.metrics import exact_match
from resolve.eval.schemas import DeadlineScenario, RoutingItem, read_jsonl

# --- deadlines generator ----------------------------------------------------


def test_generate_scenarios_count_and_ids() -> None:
    scenarios = dg.generate_scenarios()
    assert len(scenarios) == dg.TARGET_COUNT == 400
    ids = [s.id for s in scenarios]
    assert len(set(ids)) == 400
    assert ids[0] == "D-0001" and ids[-1] == "D-0400"
    assert {s.regulation for s in scenarios} == {"Reg E", "Reg Z", "Reg X", "Reg V"}


def test_every_scenario_recomputes_to_expected() -> None:
    # The golden file is a living regression against the calculator.
    for scenario in dg.generate_scenarios():
        assert exact_match(scenario.expected, dg.recompute(scenario)), scenario.id


def test_deadlines_generation_is_deterministic(tmp_path: Path) -> None:
    first = [s.model_dump_json() for s in dg.generate_scenarios()]
    second = [s.model_dump_json() for s in dg.generate_scenarios()]
    assert first == second


# --- routing generator ------------------------------------------------------


def _complaints_frame() -> pl.DataFrame:
    # 50 rows per family across train/val/test; only test should be sampled.
    rows = []
    cid = 1000
    specs = [
        ("cards", "Credit card or prepaid card", "General-purpose credit card", "Fees or interest"),
        ("mortgage", "Mortgage", "Conventional home mortgage", "Trouble during payment process"),
        ("deposits", "Checking or savings account", "Checking account", "Managing an account"),
        (
            "credit_reporting",
            "Credit reporting or other personal consumer reports",
            "Credit reporting",
            "Incorrect information on your report",
        ),
    ]
    for _family, product, sub_product, issue in specs:
        for i in range(60):
            split = "test" if i < 40 else ("val" if i < 50 else "train")
            rows.append(
                {
                    "complaint_id": (cid := cid + 1),
                    "bank": "Citi",
                    "product": product,
                    "sub_product": sub_product,
                    "issue": issue,
                    "sub_issue": None,
                    "year": 2025,
                    "split": split,
                }
            )
    # One out-of-scope row that must be excluded.
    rows.append(
        {
            "complaint_id": 999999,
            "bank": "Citi",
            "product": "Student loan",
            "sub_product": None,
            "issue": "Dealing with lender",
            "sub_issue": None,
            "year": 2025,
            "split": "test",
        }
    )
    return pl.DataFrame(rows)


def test_stratified_sample_balances_families_and_uses_test_only() -> None:
    items = rg.stratified_sample(_complaints_frame(), total=80)
    assert len(items) == 80  # 20 per family x 4
    by_family: dict[str, int] = {}
    for it in items:
        by_family[it.family] = by_family.get(it.family, 0) + 1
        assert it.split == "test"
    assert by_family == {"cards": 20, "mortgage": 20, "deposits": 20, "credit_reporting": 20}
    # out-of-scope product never appears
    assert all(it.product != "Student loan" for it in items)
    # ids are unique and ordered
    assert len({it.id for it in items}) == 80


def test_stratified_sample_is_deterministic() -> None:
    frame = _complaints_frame()
    a = [it.model_dump_json() for it in rg.stratified_sample(frame, total=40)]
    b = [it.model_dump_json() for it in rg.stratified_sample(frame, total=40)]
    assert a == b


def test_even_indices_spacing() -> None:
    assert rg._even_indices(10, 5) == [0, 2, 4, 6, 8]
    assert rg._even_indices(3, 10) == [0, 1, 2]  # fewer available than wanted


# --- committed golden files -------------------------------------------------


def test_committed_deadlines_golden_recomputes() -> None:
    if not dg.DEADLINES_PATH.exists():
        pytest.skip("deadlines.jsonl not generated; run `make golden`.")
    scenarios = read_jsonl(dg.DEADLINES_PATH, DeadlineScenario)
    assert len(scenarios) == 400
    for scenario in scenarios:
        assert exact_match(scenario.expected, dg.recompute(scenario)), scenario.id


def test_committed_routing_golden_is_well_formed() -> None:
    if not rg.ROUTING_PATH.exists():
        pytest.skip("routing_test.jsonl not generated; run `make golden`.")
    items = read_jsonl(rg.ROUTING_PATH, RoutingItem)
    assert len(items) == rg.TARGET_TOTAL
    assert all(it.split == "test" for it in items)
    assert len({it.id for it in items}) == len(items)
    pr_items = read_jsonl(rg.PR_PATH, RoutingItem)
    assert len(pr_items) == rg.TARGET_PR
    # every PR complaint is drawn from the full set
    full_ids = {it.complaint_id for it in items}
    assert all(it.complaint_id in full_ids for it in pr_items)
