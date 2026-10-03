"""Citation-grounding metrics (PLAN §9.8, §12.2).

Two deterministic checks on a drafted letter:

* every cited reference ID must exist in the evidence assembled for this case
  (no hallucinated citations);
* every sentence marked as a factual claim must carry at least one citation.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from pydantic import BaseModel

__all__ = ["CitationReport", "Sentence", "citation_report", "ungrounded_refs"]


class Sentence(BaseModel):
    """A letter sentence with its claim flag and cited reference IDs."""

    text: str
    is_factual_claim: bool
    refs: list[str] = []


class CitationReport(BaseModel):
    """Outcome of the citation checks for one letter."""

    ungrounded_refs: list[str]  # cited IDs absent from the evidence
    uncited_claims: list[str]  # factual-claim sentences with no citation
    is_valid: bool  # True iff both lists are empty


def ungrounded_refs(cited: Collection[str], valid: Collection[str]) -> list[str]:
    """Return the sorted cited IDs that are not present in the valid evidence set."""
    valid_set = set(valid)
    return sorted({ref for ref in cited if ref not in valid_set})


def citation_report(sentences: Sequence[Sentence], valid_refs: Collection[str]) -> CitationReport:
    """Validate citations for a letter's sentences against the case evidence.

    Args:
        sentences: The letter's sentences with claim flags and refs.
        valid_refs: Reference IDs that actually exist in this case's evidence.

    Returns:
        A :class:`CitationReport`; ``is_valid`` is True when nothing is ungrounded
        and every factual claim is cited.
    """
    all_cited = [ref for s in sentences for ref in s.refs]
    ungrounded = ungrounded_refs(all_cited, valid_refs)
    uncited = [s.text for s in sentences if s.is_factual_claim and not s.refs]
    return CitationReport(
        ungrounded_refs=ungrounded,
        uncited_claims=uncited,
        is_valid=not ungrounded and not uncited,
    )
