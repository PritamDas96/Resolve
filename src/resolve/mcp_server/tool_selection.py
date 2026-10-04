"""Tool-selection golden + baseline accuracy (PLAN §10, §10.6 step 6).

Authored prompts mapped to the tool that should handle them, plus a deterministic
keyword baseline selector so tool-selection accuracy can be *reported* without LLM
quota. Iterating the tool descriptions should push an LLM selector's accuracy above
this baseline; that run is added when quota is available.
"""

from __future__ import annotations

import sys

from pydantic import BaseModel

from resolve.eval.schemas import GOLDEN_DIR, write_jsonl
from resolve.logging import configure_logging, get_logger

__all__ = [
    "TOOL_SELECTION_PATH",
    "ToolSelectionItem",
    "baseline_select",
    "build",
    "main",
    "selection_accuracy",
]

log = get_logger(__name__)

TOOL_SELECTION_PATH = GOLDEN_DIR / "tool_selection.jsonl"
TOOLS = (
    "get_account",
    "get_account_disputes",
    "get_complaint",
    "search_regulations",
    "compute_deadlines",
)


class ToolSelectionItem(BaseModel):
    """One prompt and the tool that should handle it."""

    id: str
    prompt: str
    expected_tool: str


# (prompt, expected_tool)
_ITEMS: list[tuple[str, str]] = [
    ("Look up account ACC-00123 and its status", "get_account"),
    ("What is the current status of account ACC-55?", "get_account"),
    ("Show the disputes filed on account ACC-00123", "get_account_disputes"),
    ("List all dispute records for this account", "get_account_disputes"),
    ("Pull up complaint 7812345 metadata", "get_complaint"),
    ("What product and issue is complaint 991 routed to?", "get_complaint"),
    ("What does Regulation E say about provisional credit?", "search_regulations"),
    ("Find the CFR section on billing-error resolution time limits", "search_regulations"),
    ("Which rule governs mortgage servicer notices of error?", "search_regulations"),
    (
        "Compute the provisional-credit deadline for a notice received on 2025-02-03",
        "compute_deadlines",
    ),
    ("When is the Reg E determination due for a new account dispute?", "compute_deadlines"),
    ("Calculate the error-resolution deadlines for this debit-card dispute", "compute_deadlines"),
    ("Get the holder email on account ACC-9", "get_account"),
    ("Show the investigation timeline deadlines given the notice date", "compute_deadlines"),
    ("What are the disputes on account ACC-77 and their outcomes?", "get_account_disputes"),
    (
        "Retrieve the regulation text about unauthorized electronic fund transfers",
        "search_regulations",
    ),
]

# keyword -> tool (first match wins), for the deterministic baseline.
_KEYWORDS: list[tuple[str, str]] = [
    ("dispute", "get_account_disputes"),
    ("deadline", "compute_deadlines"),
    ("compute", "compute_deadlines"),
    ("calculate", "compute_deadlines"),
    ("due", "compute_deadlines"),
    ("complaint", "get_complaint"),
    ("account", "get_account"),
    ("regulation", "search_regulations"),
    ("cfr", "search_regulations"),
    ("rule", "search_regulations"),
    ("reg e", "search_regulations"),
    ("section", "search_regulations"),
]


def baseline_select(prompt: str) -> str:
    """Deterministic keyword tool selector (the yardstick for an LLM selector)."""
    lowered = prompt.lower()
    for keyword, tool in _KEYWORDS:
        if keyword in lowered:
            return tool
    return "search_regulations"


def items() -> list[ToolSelectionItem]:
    """Return the authored tool-selection golden items."""
    return [
        ToolSelectionItem(id=f"T-{i:03d}", prompt=p, expected_tool=t)
        for i, (p, t) in enumerate(_ITEMS, start=1)
    ]


def selection_accuracy() -> float:
    """Accuracy of the baseline selector on the golden items."""
    data = items()
    hits = sum(baseline_select(it.prompt) == it.expected_tool for it in data)
    return hits / len(data)


def build() -> int:
    """Write the tool-selection golden to disk; returns the item count."""
    return write_jsonl(TOOL_SELECTION_PATH, items())


def main() -> int:
    """CLI entry point: ``python -m resolve.mcp_server.tool_selection``."""
    configure_logging()
    count = build()
    log.info(
        "tool_selection_written", count=count, baseline_accuracy=round(selection_accuracy(), 3)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
