"""Agent state and structured-output models (PLAN §9.1, §9.8).

Typed boundaries for the single-agent pipeline: the router's structured decision,
the retrieved evidence, and the drafter's :class:`Letter`. Enums (``Family``,
``Issue``) make invalid routing labels unrepresentable; the drafter's citations are
validated against the evidence refs assembled for the case.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from resolve.data.taxonomy_enums import Family, Issue
from resolve.retrieval.rewrite import RegulationHint

__all__ = [
    "CaseResult",
    "Citation",
    "Evidence",
    "Letter",
    "LetterSentence",
    "Route",
    "RouterOutput",
]


class RouterOutput(BaseModel):
    """What the router LLM returns in one structured call (route + search intent)."""

    family: Family
    issue: Issue
    confidence: float = Field(ge=0.0, le=1.0)
    legal_question: str
    regulation_hint: RegulationHint | None = None
    key_facts: list[str] = Field(default_factory=list)


class Route(BaseModel):
    """The routing decision: queue (= family) + issue + confidence (ADR-016)."""

    family: Family
    issue: Issue
    confidence: float = Field(ge=0.0, le=1.0)


class Evidence(BaseModel):
    """One retrieved regulation chunk offered to the drafter as a citable source."""

    ref: str  # citation id, e.g. "1005.11(c)(1)@2023-01-01"
    section: str
    heading_path: str
    text: str


class Citation(BaseModel):
    """A citation on a letter sentence."""

    kind: str  # "regulation" | "account_record" | "bank_doc"
    ref: str


class LetterSentence(BaseModel):
    """One sentence of the drafted letter, with its claim flag and citations."""

    text: str
    is_factual_claim: bool = False
    citations: list[Citation] = Field(default_factory=list)


class Letter(BaseModel):
    """The drafted response letter (drafter structured output)."""

    subject: str
    sentences: list[LetterSentence] = Field(default_factory=list)
    deadlines_referenced: list[str] = Field(default_factory=list)
    abstained: bool = False
    abstain_reason: str | None = None


class CaseResult(BaseModel):
    """The full outcome of running one case through the single agent."""

    case_id: str
    route: Route
    letter: Letter
    evidence_refs: list[str] = Field(default_factory=list)
    citations_valid: bool = True
    ungrounded_refs: list[str] = Field(default_factory=list)
    uncited_claims: list[str] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    trace: list[str] = Field(default_factory=list)
