"""Query rewriting into a structured search intent (PLAN §8.5).

A complaint narrative is long and noisy; retrieval works better on a focused legal
question plus key facts. The production rewriter is the router LLM (Phase 4); this
module defines the :class:`SearchIntent` contract and a **deterministic heuristic**
rewriter so the "raw narrative vs rewritten query" ablation can run now without an
LLM, and so there is a dependable fallback.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

__all__ = ["RegulationHint", "SearchIntent", "heuristic_rewrite", "query_text"]

RegulationHint = Literal["Reg E", "Reg Z", "Reg X", "Reg DD", "Reg V"]

# Keyword -> regulation hint (first match wins); lowercase substrings.
_REGULATION_KEYWORDS: list[tuple[str, RegulationHint]] = [
    ("debit card", "Reg E"),
    ("provisional credit", "Reg E"),
    ("electronic fund", "Reg E"),
    ("unauthorized transfer", "Reg E"),
    ("atm", "Reg E"),
    ("billing error", "Reg Z"),
    ("credit card", "Reg Z"),
    ("periodic statement", "Reg Z"),
    ("truth in lending", "Reg Z"),
    ("mortgage", "Reg X"),
    ("escrow", "Reg X"),
    ("loan servicer", "Reg X"),
    ("notice of error", "Reg X"),
    ("savings account", "Reg DD"),
    ("interest rate disclosure", "Reg DD"),
    ("annual percentage yield", "Reg DD"),
    ("credit report", "Reg V"),
    ("furnisher", "Reg V"),
    ("direct dispute", "Reg V"),
]

# Salient fact phrases to surface for BM25 (lowercase substrings).
_FACT_PHRASES = [
    "unauthorized",
    "provisional credit",
    "billing error",
    "notice of error",
    "escrow",
    "direct dispute",
    "foreign transaction",
    "point of sale",
    "new account",
    "statement",
    "deadline",
    "investigation",
]

_WS = re.compile(r"\s+")


class SearchIntent(BaseModel):
    """Structured retrieval intent extracted from a narrative (PLAN §8.5)."""

    legal_question: str
    regulation_hint: RegulationHint | None = None
    key_facts: list[str] = Field(default_factory=list)


def heuristic_rewrite(text: str) -> SearchIntent:
    """Deterministically derive a :class:`SearchIntent` from raw text.

    Picks a regulation hint by keyword, normalises whitespace for the legal
    question, and lifts any recognised salient fact phrases.
    """
    lowered = text.lower()
    hint: RegulationHint | None = next(
        (reg for kw, reg in _REGULATION_KEYWORDS if kw in lowered), None
    )
    facts = [phrase for phrase in _FACT_PHRASES if phrase in lowered]
    legal_question = _WS.sub(" ", text).strip()
    return SearchIntent(legal_question=legal_question, regulation_hint=hint, key_facts=facts)


def query_text(intent: SearchIntent, *, for_sparse: bool = False) -> str:
    """Render the query string; append key facts for the (lexical) sparse arm."""
    if for_sparse and intent.key_facts:
        return f"{intent.legal_question} {' '.join(intent.key_facts)}"
    return intent.legal_question
