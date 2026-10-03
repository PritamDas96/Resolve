"""Scoring metrics for the golden sets (PLAN §12.2).

Deterministic, dependency-free implementations of every metric the eval gate needs:
routing (macro-F1, exact path), PII spans (exact + overlap), deadlines (exact
match), retrieval (recall@k, MRR, nDCG), citations (grounding) and abstention.
"""

from __future__ import annotations

from resolve.eval.metrics._common import PRF, prf_from_counts, safe_div
from resolve.eval.metrics.abstention import abstention_prf, leakage_count
from resolve.eval.metrics.citations import (
    CitationReport,
    Sentence,
    citation_report,
    ungrounded_refs,
)
from resolve.eval.metrics.deadlines import exact_match, scenario_accuracy
from resolve.eval.metrics.retrieval import mrr, ndcg_at_k, recall_at_k
from resolve.eval.metrics.routing import exact_path_accuracy, macro_f1, per_class_prf
from resolve.eval.metrics.spans import MatchMode, Span, score_spans, score_spans_by_type

__all__ = [
    "PRF",
    "CitationReport",
    "MatchMode",
    "Sentence",
    "Span",
    "abstention_prf",
    "citation_report",
    "exact_match",
    "exact_path_accuracy",
    "leakage_count",
    "macro_f1",
    "mrr",
    "ndcg_at_k",
    "per_class_prf",
    "prf_from_counts",
    "recall_at_k",
    "safe_div",
    "scenario_accuracy",
    "score_spans",
    "score_spans_by_type",
    "ungrounded_refs",
]
