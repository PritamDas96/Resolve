"""Unit tests for the judge + evaluation gate (offline — FakeJudge, no services)."""

from __future__ import annotations

import pytest

from resolve.eval.judge import FakeJudge, LetterJudgment
from resolve.eval.runners import gate


def test_fake_judge_and_judged_scores() -> None:
    judge = FakeJudge(
        LetterJudgment(
            regulatory_accuracy=4, completeness=4, clarity=4, tone=5, overall=4, rationale="x"
        )
    )
    scores = gate.judged_scores(judge, [("q1", "letter one"), ("q2", "letter two")], n=3)
    assert scores["judge_overall_mean"] == 4.0
    assert scores["judge_overall_stdev"] == 0.0  # deterministic judge -> no variance


def test_letter_judgment_bounds() -> None:
    with pytest.raises(ValueError, match="less than or equal to 5"):
        LetterJudgment(regulatory_accuracy=9, completeness=4, clarity=4, tone=4, overall=4)


def test_compare_flags_regression() -> None:
    metrics = gate._compare({"m": 0.80}, {"m": 0.90})
    assert metrics[0].regressed is True
    # within tolerance -> not a regression
    assert gate._compare({"m": 0.89}, {"m": 0.90})[0].regressed is False
    # no baseline -> never a regression
    assert gate._compare({"m": 0.1}, {})[0].regressed is False


def test_deadlines_metric_is_perfect() -> None:
    # The deadline golden must always recompute exactly (calculator is the source of truth).
    assert gate._deadlines_exact() == 1.0


def test_pii_offsets_metric_is_perfect() -> None:
    assert gate._pii_offsets_ok() == 1.0


def test_render_summary_shows_verdict() -> None:
    metrics = gate._compare({"deadlines_exact_match": 1.0}, {"deadlines_exact_match": 1.0})
    report = gate._render(metrics, passed=True)
    assert "Verdict:** PASS" in report
    assert "deadlines_exact_match" in report
