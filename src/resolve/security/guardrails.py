"""Output guardrails (PLAN §13.4).

Two checks run on any text the system is about to emit: a **policy** check that no
output concludes a named bank broke the law (CLAUDE.md non-negotiable, §7.12), and a
**PII scan** that no personal data (or known synthetic secret) leaks into the output.
Both are deterministic and used by the agent before returning a letter and by the
leak tests.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import BaseModel

from resolve.security.pii import detect

__all__ = ["ACCUSATION_PATTERNS", "GuardrailReport", "check_output"]

# Phrases that assert unlawful conduct by the bank (never permitted in output).
ACCUSATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\bviolat(?:e|ed|es|ing|ion)\b"),
    re.compile(r"(?i)\bbroke the law\b"),
    re.compile(r"(?i)\billegal(?:ly)?\b"),
    re.compile(r"(?i)\bunlawful(?:ly)?\b"),
    re.compile(r"(?i)\bbreached the law\b"),
]


class GuardrailReport(BaseModel):
    """Outcome of the output guardrail checks."""

    accusations: list[str]  # matched accusation phrases
    pii_types: list[str]  # entity types detected in the output
    leaked_secrets: list[str]  # known synthetic secrets found verbatim
    ok: bool


def check_output(text: str, *, secrets: Sequence[str] = ()) -> GuardrailReport:
    """Scan output text for legal accusations, PII and known secret leakage.

    Args:
        text: The output about to be returned.
        secrets: Known synthetic PII strings that must never appear (leak test).

    Returns:
        A :class:`GuardrailReport`; ``ok`` is True only when all three are clean.
    """
    accusations = sorted(
        {m.group(0).lower() for p in ACCUSATION_PATTERNS for m in p.finditer(text)}
    )
    pii_types = sorted({s.entity_type for s in detect(text)})
    leaked = sorted({s for s in secrets if s and s in text})
    return GuardrailReport(
        accusations=accusations,
        pii_types=pii_types,
        leaked_secrets=leaked,
        ok=not accusations and not pii_types and not leaked,
    )
