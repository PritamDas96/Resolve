"""Typed records and JSONL helpers for the golden sets (PLAN §7.8, §7.9).

Every committed golden file in ``eval/golden/`` is a JSON Lines file whose rows
validate against one of these Pydantic models. Keeping the schemas in one place
means the generators, the scoring metrics and the tests all agree on the shape of
ground truth, and a malformed record fails loudly at load time.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "GOLDEN_DIR",
    "DeadlineExpect",
    "DeadlineScenario",
    "InjectionCategory",
    "InjectionItem",
    "PiiItem",
    "PiiSpan",
    "RoutingItem",
    "Stratum",
    "TierCExpected",
    "TierCItem",
    "read_jsonl",
    "write_jsonl",
]

# Repo-root-relative location of the committed golden JSONL files.
_REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_DIR = _REPO_ROOT / "eval" / "golden"


# --- Tier A: routing --------------------------------------------------------


class RoutingItem(BaseModel):
    """One routing ground-truth row (``routing_test.jsonl``).

    The labels are the real CFPB metadata for a test-split complaint; the task is
    product -> sub-product -> issue classification.
    """

    id: str
    complaint_id: int
    bank: str
    product: str
    sub_product: str | None
    issue: str
    sub_issue: str | None
    family: str
    split: str


# --- Tier A: PII spans ------------------------------------------------------


class PiiSpan(BaseModel):
    """A character span of synthetic PII within a narrative (half-open ``[start, end)``)."""

    start: int
    end: int
    entity_type: str


class PiiItem(BaseModel):
    """One PII ground-truth row (``pii_spans.jsonl``): text with known-offset spans."""

    complaint_id: int
    text: str
    spans: list[PiiSpan]
    seed: int


# --- Tier B: deadlines ------------------------------------------------------


class DeadlineExpect(BaseModel):
    """An expected deadline in a scenario (mirrors :class:`resolve.domain.deadlines.Deadline`)."""

    name: str
    due: date
    rule: str
    basis: str


class DeadlineScenario(BaseModel):
    """One deadline ground-truth row (``deadlines.jsonl``).

    ``inputs`` are the arguments passed to ``function`` in
    :mod:`resolve.domain.deadlines`; ``expected`` is what that function returns.
    """

    id: str
    regulation: str
    function: str
    inputs: dict[str, object]
    expected: list[DeadlineExpect]


# --- Tier C: end-to-end -----------------------------------------------------


class Stratum(StrEnum):
    """The five Tier C strata (PLAN §7.8)."""

    SINGLE_HOP_REGULATION = "single_hop_regulation"
    ACCOUNT_REGULATION_JOIN = "account_regulation_join"
    MULTI_HOP = "multi_hop"
    UNANSWERABLE = "unanswerable"
    POLICY_SENSITIVE = "policy_sensitive"


class TierCExpected(BaseModel):
    """The labelled expectation for a Tier C item (PLAN §7.9)."""

    route: dict[str, str]
    regulation_sections: list[str] = []
    interpretations: list[str] = []
    facts: dict[str, object] = {}
    deadlines: dict[str, object] = {}
    must_include: list[str] = []
    must_not_include: list[str] = []
    should_abstain: bool = False


class TierCItem(BaseModel):
    """One end-to-end ground-truth row (``e2e_tier_c.jsonl``)."""

    id: str
    stratum: Stratum
    complaint_id: int | None = None
    account_id: str | None = None
    as_of_date: date | None = None
    question: str
    expected: TierCExpected
    labeller: str
    labelled_on: date | None = None
    notes: str = ""


# --- Tier C: injection ------------------------------------------------------


class InjectionCategory(StrEnum):
    """Prompt-injection attack categories (PLAN §7.8, §7.9)."""

    INDIRECT_IN_NARRATIVE = "indirect_in_narrative"
    INSTRUCTION_OVERRIDE = "instruction_override"
    PII_EXFILTRATION = "pii_exfiltration"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    PROMPT_LEAK = "prompt_leak"


class InjectionItem(BaseModel):
    """One prompt-injection attack row (``injection_suite.jsonl``)."""

    id: str
    category: InjectionCategory
    vector: str
    payload: str
    attack_goal: str
    success_detector: str
    expected_behaviour: str


# --- JSONL helpers ----------------------------------------------------------


def read_jsonl[ModelT: BaseModel](path: Path | str, model: type[ModelT]) -> list[ModelT]:
    """Load a JSONL file into a list of validated ``model`` instances."""
    text = Path(path).read_text(encoding="utf-8")
    return [model.model_validate_json(line) for line in text.splitlines() if line.strip()]


def write_jsonl(path: Path | str, items: Iterable[BaseModel]) -> int:
    """Write ``items`` as JSONL (one compact JSON object per line). Returns the count."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with destination.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(item.model_dump_json() + "\n")
            count += 1
    return count
