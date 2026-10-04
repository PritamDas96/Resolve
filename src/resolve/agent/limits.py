"""Agent stopping conditions (PLAN §9.5).

A :class:`Budget` bounds how far one case may run — steps, tool retrievals and tokens —
so a looping or runaway agent fails loudly instead of burning cost. Every node updates
the budget and calls :meth:`Budget.check`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Budget", "LimitExceededError", "Limits"]


class LimitExceededError(RuntimeError):
    """Raised when a case exceeds one of its configured limits."""


@dataclass(frozen=True)
class Limits:
    """Per-case ceilings."""

    max_steps: int = 12
    max_retrievals: int = 4
    max_tokens: int = 20_000


@dataclass
class Budget:
    """Mutable per-case usage, checked against :class:`Limits`."""

    limits: Limits = field(default_factory=Limits)
    steps: int = 0
    retrievals: int = 0
    tokens: int = 0

    def step(self) -> None:
        """Count a graph step and enforce the step ceiling."""
        self.steps += 1
        self.check()

    def add_retrieval(self) -> None:
        """Count a retrieval call and enforce the retrieval ceiling."""
        self.retrievals += 1
        self.check()

    def add_tokens(self, n: int) -> None:
        """Add token usage and enforce the token ceiling."""
        self.tokens += n
        self.check()

    def check(self) -> None:
        """Raise :class:`LimitExceededError` if any ceiling is breached."""
        if self.steps > self.limits.max_steps:
            raise LimitExceededError(f"max_steps exceeded ({self.steps} > {self.limits.max_steps})")
        if self.retrievals > self.limits.max_retrievals:
            raise LimitExceededError(
                f"max_retrievals exceeded ({self.retrievals} > {self.limits.max_retrievals})"
            )
        if self.tokens > self.limits.max_tokens:
            raise LimitExceededError(
                f"max_tokens exceeded ({self.tokens} > {self.limits.max_tokens})"
            )
