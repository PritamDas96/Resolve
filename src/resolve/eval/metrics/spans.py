"""Span-level PII scoring: exact and partial-overlap P/R/F1 per entity type (PLAN §12.2).

A span is ``(start, end, entity_type)`` with a half-open ``[start, end)`` range.
Matching is one-to-one (greedy): each gold span is consumed by at most one
prediction so overlapping predictions cannot inflate recall.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from enum import StrEnum

from resolve.eval.metrics._common import PRF, prf_from_counts

__all__ = ["MatchMode", "Span", "score_spans", "score_spans_by_type"]

# (start, end, entity_type)
Span = tuple[int, int, str]


class MatchMode(StrEnum):
    """How a predicted span is credited against a gold span."""

    EXACT = "exact"  # identical start, end and type
    OVERLAP = "overlap"  # same type and any character overlap


def _overlaps(a: Span, b: Span) -> bool:
    """True iff two same-type spans share at least one character position."""
    return a[2] == b[2] and a[0] < b[1] and b[0] < a[1]


def _matches(pred: Span, gold: Span, mode: MatchMode) -> bool:
    if mode is MatchMode.EXACT:
        return pred == gold
    return _overlaps(pred, gold)


def score_spans(
    gold: Sequence[Span], pred: Sequence[Span], *, mode: MatchMode = MatchMode.EXACT
) -> PRF:
    """Score predicted spans against gold with one-to-one matching.

    Args:
        gold: Ground-truth spans.
        pred: Predicted spans.
        mode: Exact or partial-overlap matching.

    Returns:
        Aggregate :class:`PRF`.
    """
    unmatched_gold = list(gold)
    tp = 0
    for p in pred:
        for i, g in enumerate(unmatched_gold):
            if _matches(p, g, mode):
                tp += 1
                unmatched_gold.pop(i)
                break
    fp = len(pred) - tp
    fn = len(unmatched_gold)
    return prf_from_counts(tp, fp, fn)


def score_spans_by_type(
    gold: Sequence[Span], pred: Sequence[Span], *, mode: MatchMode = MatchMode.EXACT
) -> dict[str, PRF]:
    """Per-entity-type :class:`PRF` over the union of observed types."""
    types: Iterable[str] = {s[2] for s in gold} | {s[2] for s in pred}
    return {
        t: score_spans([g for g in gold if g[2] == t], [p for p in pred if p[2] == t], mode=mode)
        for t in sorted(types)
    }
