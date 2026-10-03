"""Routing metrics: macro-F1 per level and exact-path accuracy (PLAN §12.2).

Pure, deterministic scikit-learn-free implementations so the eval harness has no
heavy dependency. Compared against the real CFPB labels in ``routing_test``.
"""

from __future__ import annotations

from collections.abc import Sequence

from resolve.eval.metrics._common import PRF, prf_from_counts, safe_div

__all__ = ["exact_path_accuracy", "macro_f1", "per_class_prf"]


def per_class_prf(y_true: Sequence[str], y_pred: Sequence[str]) -> dict[str, PRF]:
    """Return per-class precision/recall/F1 over the union of observed labels.

    Args:
        y_true: Gold labels.
        y_pred: Predicted labels (same length as ``y_true``).

    Returns:
        Label -> :class:`PRF`.

    Raises:
        ValueError: If the inputs differ in length.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    labels = sorted(set(y_true) | set(y_pred))
    out: dict[str, PRF] = {}
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == label and p != label)
        out[label] = prf_from_counts(tp, fp, fn)
    return out


def macro_f1(y_true: Sequence[str], y_pred: Sequence[str]) -> float:
    """Macro-averaged F1 (unweighted mean of per-class F1 over observed labels)."""
    scores = per_class_prf(y_true, y_pred)
    return safe_div(sum(prf.f1 for prf in scores.values()), len(scores))


def exact_path_accuracy(
    true_paths: Sequence[tuple[str, ...]], pred_paths: Sequence[tuple[str, ...]]
) -> float:
    """Fraction of items whose full (product, sub-product, issue) path matches exactly."""
    if len(true_paths) != len(pred_paths):
        raise ValueError("true_paths and pred_paths must have the same length")
    if not true_paths:
        return 0.0
    correct = sum(1 for t, p in zip(true_paths, pred_paths, strict=True) if t == p)
    return correct / len(true_paths)
