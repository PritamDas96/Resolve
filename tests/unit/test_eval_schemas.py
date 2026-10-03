"""Unit tests for :mod:`resolve.eval.schemas` (round-trip + validation)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from resolve.eval import schemas as s


def test_routing_item_round_trip(tmp_path: Path) -> None:
    items = [
        s.RoutingItem(
            id="R-0001",
            complaint_id=42,
            bank="Citi",
            product="Credit card or prepaid card",
            sub_product="General-purpose credit card",
            issue="Fees or interest",
            sub_issue=None,
            family="cards",
            split="test",
        )
    ]
    path = tmp_path / "routing.jsonl"
    assert s.write_jsonl(path, items) == 1
    loaded = s.read_jsonl(path, s.RoutingItem)
    assert loaded == items


def test_deadline_scenario_round_trip(tmp_path: Path) -> None:
    item = s.DeadlineScenario(
        id="D-0001",
        regulation="reg_e",
        function="reg_e_error_resolution",
        inputs={"notice_received": "2025-02-03", "new_account": False},
        expected=[
            s.DeadlineExpect(
                name="determination_or_provisional_credit",
                due=date(2025, 2, 18),
                rule="12 CFR 1005.11(c)(1), (c)(3)",
                basis="business",
            )
        ],
    )
    path = tmp_path / "deadlines.jsonl"
    s.write_jsonl(path, [item])
    assert s.read_jsonl(path, s.DeadlineScenario) == [item]


def test_injection_category_is_validated() -> None:
    with pytest.raises(ValueError, match="category"):
        s.InjectionItem(
            id="INJ-001",
            category="not_a_real_category",
            vector="narrative",
            payload="...",
            attack_goal="x",
            success_detector="regex:y",
            expected_behaviour="z",
        )


def test_read_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "x.jsonl"
    path.write_text('{"start": 0, "end": 4, "entity_type": "PERSON"}\n\n', encoding="utf-8")
    assert s.read_jsonl(path, s.PiiSpan) == [s.PiiSpan(start=0, end=4, entity_type="PERSON")]
