"""Unit tests for the prompt-injection suite generator (PLAN §7.8)."""

from __future__ import annotations

from pathlib import Path

from resolve.eval.golden import injection_gen as ig
from resolve.eval.schemas import InjectionCategory, InjectionItem, read_jsonl


def test_generates_40_items_with_unique_ids() -> None:
    items = ig.generate_items()
    assert len(items) == 80
    assert len({it.id for it in items}) == 80
    assert items[0].id == "INJ-001" and items[-1].id == "INJ-080"


def test_covers_all_categories_evenly() -> None:
    items = ig.generate_items()
    counts: dict[InjectionCategory, int] = {}
    for it in items:
        counts[it.category] = counts.get(it.category, 0) + 1
    assert set(counts) == set(InjectionCategory)
    assert all(c == 16 for c in counts.values())  # 16 per category x 5 = 80


def test_every_success_detector_uses_known_verbs() -> None:
    for it in ig.generate_items():
        clauses = ig.detector_clauses(it.success_detector)
        assert clauses, it.id
        for clause in clauses:
            assert ig.detector_verb(clause) in ig.DETECTOR_VERBS, (it.id, clause)


def test_items_are_well_formed() -> None:
    for it in ig.generate_items():
        assert it.payload.strip()
        assert it.attack_goal.strip()
        assert it.expected_behaviour.strip()
        assert it.vector in {"narrative", "field", "metadata"}


def test_build_writes_and_round_trips(tmp_path: Path) -> None:
    out = tmp_path / "injection_suite.jsonl"
    assert ig.build(out) == 80
    loaded = read_jsonl(out, InjectionItem)
    assert loaded == ig.generate_items()


def test_detector_parsing() -> None:
    assert ig.detector_clauses("status_changed OR regex:\\d+") == ["status_changed", "regex:\\d+"]
    assert ig.detector_verb("tool_called:send_letter") == "tool_called"
    assert ig.detector_verb("status_changed") == "status_changed"
