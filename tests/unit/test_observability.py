"""Unit tests for drift (PSI/MMD) + cost accounting (offline)."""

from __future__ import annotations

import polars as pl

from resolve.llm.gateway import Usage
from resolve.observability import cost, drift


def test_psi_zero_for_identical() -> None:
    dist = {"cards": 50.0, "mortgage": 30.0, "deposits": 20.0}
    assert drift.psi(dist, dist) == 0.0


def test_psi_grows_with_shift() -> None:
    ref = {"cards": 50.0, "mortgage": 50.0}
    small = {"cards": 55.0, "mortgage": 45.0}
    large = {"cards": 95.0, "mortgage": 5.0}
    assert drift.psi(ref, large) > drift.psi(ref, small) > 0.0


def test_mmd_larger_for_separated_samples() -> None:
    near_a = [[0.0], [0.1], [0.0]]
    near_b = [[0.0], [0.1], [0.05]]
    far_b = [[10.0], [10.1], [10.0]]
    assert drift.mmd2(near_a, far_b) > drift.mmd2(near_a, near_b)


def test_family_psi_by_year() -> None:
    df = pl.DataFrame(
        {
            "product": ["Credit card", "Mortgage", "Credit card", "Mortgage", "Mortgage"],
            "year": [2023, 2023, 2024, 2024, 2024],
        }
    )
    by_year = drift.family_psi_by_year(df, reference_year=2023)
    assert by_year[2023] == 0.0  # vs itself
    assert by_year[2024] > 0.0  # mix shifted toward mortgage


def test_cost_estimate_and_aggregate() -> None:
    # Free-tier model -> zero cost but tokens still counted.
    free = cost.estimate_cost(
        "gemini/gemini-3.8-flash", Usage(prompt_tokens=1000, completion_tokens=500)
    )
    assert free == 0.0
    paid = cost.estimate_cost(
        "gemini/gemini-2.5-pro", Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    )
    assert paid == 1.25 + 10.0

    result = cost.case_cost(
        "C-1",
        [
            ("router", "gemini/gemini-3.8-flash", Usage(prompt_tokens=100, completion_tokens=20)),
            ("drafter", "gemini/gemini-3.8-flash", Usage(prompt_tokens=300, completion_tokens=150)),
        ],
    )
    assert result.total_tokens == 570
    assert result.total_cost_usd == 0.0
    assert [n.node for n in result.nodes] == ["router", "drafter"]
