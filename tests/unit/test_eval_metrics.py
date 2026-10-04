"""Unit tests for :mod:`resolve.eval.metrics` (PLAN §12.2)."""

from __future__ import annotations

from datetime import date

import pytest

from resolve.domain.deadlines import Basis, Deadline
from resolve.eval import metrics as m
from resolve.eval.schemas import DeadlineExpect

# --- routing ----------------------------------------------------------------


def test_macro_f1_perfect() -> None:
    y = ["cards", "mortgage", "deposits"]
    assert m.macro_f1(y, y) == 1.0


def test_macro_f1_unweighted_over_classes() -> None:
    # 'a' perfect (F1=1); 'b' predicted once wrong -> one FN for b, one FP for b.
    y_true = ["a", "a", "b"]
    y_pred = ["a", "a", "a"]
    scores = m.per_class_prf(y_true, y_pred)
    assert scores["a"].recall == 1.0
    assert scores["b"].recall == 0.0
    # macro F1 = mean(F1_a=2*(2/3*1)/(2/3+1)=0.8 , F1_b=0) = 0.4
    assert m.macro_f1(y_true, y_pred) == pytest.approx(0.4)


def test_exact_path_accuracy() -> None:
    true = [("Mortgage", "Conv", "Trouble"), ("Credit card", "GP", "Fees")]
    pred = [("Mortgage", "Conv", "Trouble"), ("Credit card", "GP", "Other")]
    assert m.exact_path_accuracy(true, pred) == 0.5


def test_routing_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="same length"):
        m.macro_f1(["a"], ["a", "b"])


# --- spans ------------------------------------------------------------------


def test_span_exact_vs_overlap() -> None:
    gold = [(0, 5, "PERSON"), (10, 14, "LAST4")]
    pred = [(0, 5, "PERSON"), (10, 16, "LAST4")]  # 2nd overlaps but not exact
    exact = m.score_spans(gold, pred, mode=m.MatchMode.EXACT)
    assert (exact.tp, exact.fp, exact.fn) == (1, 1, 1)
    overlap = m.score_spans(gold, pred, mode=m.MatchMode.OVERLAP)
    assert (overlap.tp, overlap.fp, overlap.fn) == (2, 0, 0)
    assert overlap.f1 == 1.0


def test_span_overlap_requires_same_type() -> None:
    gold = [(0, 5, "PERSON")]
    pred = [(0, 5, "ADDRESS")]  # overlaps positionally but wrong type
    assert m.score_spans(gold, pred, mode=m.MatchMode.OVERLAP).tp == 0


def test_span_one_to_one_matching() -> None:
    # Two predictions overlapping a single gold must not both count.
    gold = [(0, 10, "PERSON")]
    pred = [(0, 3, "PERSON"), (4, 9, "PERSON")]
    overlap = m.score_spans(gold, pred, mode=m.MatchMode.OVERLAP)
    assert (overlap.tp, overlap.fp, overlap.fn) == (1, 1, 0)


def test_span_by_type() -> None:
    gold = [(0, 5, "PERSON"), (10, 14, "LAST4")]
    pred = [(0, 5, "PERSON")]
    by_type = m.score_spans_by_type(gold, pred)
    assert by_type["PERSON"].f1 == 1.0
    assert by_type["LAST4"].recall == 0.0


# --- deadlines --------------------------------------------------------------


def test_deadline_exact_match() -> None:
    expected = [
        DeadlineExpect(
            name="determination_or_provisional_credit",
            due=date(2025, 2, 18),
            rule="12 CFR 1005.11(c)(1), (c)(3)",
            basis="business",
        )
    ]
    computed = [
        Deadline(
            name="determination_or_provisional_credit",
            due=date(2025, 2, 18),
            rule="12 CFR 1005.11(c)(1), (c)(3)",
            basis=Basis.BUSINESS,
        )
    ]
    assert m.exact_match(expected, computed) is True
    wrong = [Deadline(name="x", due=date(2025, 2, 19), rule="r", basis=Basis.CALENDAR)]
    assert m.exact_match(expected, wrong) is False
    assert m.scenario_accuracy([(expected, computed), (expected, wrong)]) == 0.5


# --- retrieval --------------------------------------------------------------


def test_retrieval_metrics() -> None:
    relevant = {"1005.11(c)(1)", "1005.11(c)(2)"}
    ranked = ["1005.9", "1005.11(c)(1)", "1030.7", "1005.11(c)(2)"]
    assert m.recall_at_k(relevant, ranked, 2) == 0.5
    assert m.recall_at_k(relevant, ranked, 4) == 1.0
    assert m.mrr(relevant, ranked) == pytest.approx(0.5)  # first hit at rank 2
    assert m.mrr(set(), ranked) == 0.0


def test_ndcg_is_one_for_ideal_ranking() -> None:
    relevant = {"a", "b"}
    assert m.ndcg_at_k(relevant, ["a", "b", "c"], 3) == pytest.approx(1.0)
    # a worse ranking scores lower
    assert m.ndcg_at_k(relevant, ["c", "a", "b"], 3) < 1.0


# --- citations --------------------------------------------------------------


def test_citation_report_flags_ungrounded_and_uncited() -> None:
    sentences = [
        m.Sentence(text="Provisional credit was not issued.", is_factual_claim=True, refs=["E1"]),
        m.Sentence(text="The deadline was missed.", is_factual_claim=True, refs=["GHOST"]),
        m.Sentence(text="We are writing regarding your complaint.", is_factual_claim=False),
    ]
    report = m.citation_report(sentences, valid_refs={"E1", "E2"})
    assert report.ungrounded_refs == ["GHOST"]
    assert report.uncited_claims == []
    assert report.is_valid is False


def test_citation_report_valid() -> None:
    sentences = [m.Sentence(text="X happened.", is_factual_claim=True, refs=["E1"])]
    assert m.citation_report(sentences, valid_refs={"E1"}).is_valid is True


def test_citation_uncited_claim() -> None:
    sentences = [m.Sentence(text="X happened.", is_factual_claim=True, refs=[])]
    report = m.citation_report(sentences, valid_refs={"E1"})
    assert report.uncited_claims == ["X happened."]
    assert report.is_valid is False


# --- abstention + leakage ---------------------------------------------------


def test_abstention_prf() -> None:
    y_true = [True, True, False, False]
    y_pred = [True, False, False, True]  # 1 TP, 1 FN, 1 FP
    prf = m.abstention_prf(y_true, y_pred)
    assert (prf.tp, prf.fp, prf.fn) == (1, 1, 1)
    assert prf.precision == pytest.approx(0.5)
    assert prf.recall == pytest.approx(0.5)


def test_leakage_count() -> None:
    assert m.leakage_count("call me at 555-123-4567", ["555-123-4567", "ssn"]) == 1
    assert m.leakage_count("nothing here", ["555-123-4567"]) == 0
