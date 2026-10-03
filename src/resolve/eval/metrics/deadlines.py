"""Deadline metric: exact match of computed deadlines against ground truth (PLAN §12.2).

Tier B is scored by exact match: the set of ``(name, due, rule, basis)`` tuples the
calculator produced must equal the expected set. This keeps the scorer agnostic to
ordering while still demanding the right rule and basis, not just the right date.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from resolve.domain.deadlines import Deadline
from resolve.eval.metrics._common import safe_div
from resolve.eval.schemas import DeadlineExpect

__all__ = ["exact_match", "scenario_accuracy"]

_Key = tuple[str, str, str, str]


def _expected_key(d: DeadlineExpect) -> _Key:
    return (d.name, d.due.isoformat(), d.rule, d.basis)


def _computed_key(d: Deadline) -> _Key:
    return (d.name, d.due.isoformat(), d.rule, str(d.basis))


def exact_match(expected: Sequence[DeadlineExpect], computed: Sequence[Deadline]) -> bool:
    """True iff the computed deadlines exactly equal the expected set (order-insensitive)."""
    return {_expected_key(e) for e in expected} == {_computed_key(c) for c in computed}


def scenario_accuracy(
    pairs: Iterable[tuple[Sequence[DeadlineExpect], Sequence[Deadline]]],
) -> float:
    """Fraction of (expected, computed) scenario pairs that match exactly."""
    results = [exact_match(exp, comp) for exp, comp in pairs]
    return safe_div(sum(results), len(results))
