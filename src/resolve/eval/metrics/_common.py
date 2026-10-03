"""Shared primitives for the scoring metrics (precision/recall/F1 from counts)."""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ["PRF", "prf_from_counts", "safe_div"]


def safe_div(numerator: float, denominator: float) -> float:
    """Return ``numerator / denominator``, or 0.0 when the denominator is zero."""
    return numerator / denominator if denominator else 0.0


class PRF(BaseModel):
    """Precision / recall / F1 with the underlying counts."""

    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int

    @property
    def support(self) -> int:
        """Number of true positives + false negatives (gold instances)."""
        return self.tp + self.fn


def prf_from_counts(tp: int, fp: int, fn: int) -> PRF:
    """Build a :class:`PRF` from true/false positive/negative counts."""
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    return PRF(precision=precision, recall=recall, f1=f1, tp=tp, fp=fp, fn=fn)
