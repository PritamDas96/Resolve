"""End-to-end demo: draft a cited letter for a synthetic dev complaint (PLAN §Phase 4 DoD).

Runs the single agent against the **real** gateway and the sparse regulations index, so
``make demo`` (after ``make up`` + ``make index-sparse``) produces a cited, point-in-time
letter. The complaint is synthetic (CFPB narratives are unavailable, ADR-014).

Requires Gemini quota for two LLM calls (route + draft); if quota is exhausted the run
reports the error rather than fabricating a letter.
"""

from __future__ import annotations

import sys
from datetime import date

from resolve.agent.graph_single import run_case
from resolve.agent.tools import make_retriever
from resolve.config import get_settings
from resolve.llm.gateway import build_gateway
from resolve.logging import configure_logging, get_logger

__all__ = ["DEV_COMPLAINT", "main"]

log = get_logger(__name__)

DEV_COMPLAINT = (
    "Someone made two charges on my debit card that I did not authorize. I called the "
    "bank on 02/03/2025 to report the error, but weeks later they still have not given "
    "me provisional credit while they investigate. What are they required to do?"
)


def main() -> int:
    """CLI entry point: ``python -m resolve.agent.demo``."""
    configure_logging()
    settings = get_settings()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    result = run_case(
        build_gateway(settings),
        case_id="demo-001",
        complaint=DEV_COMPLAINT,
        retrieve=make_retriever(settings),
        router_model=settings.router_model,
        drafter_model=settings.drafter_model,
        as_of=date(2025, 3, 14),
    )

    print(
        f"\nRoute: {result.route.family} / {result.route.issue} "
        f"(confidence {result.route.confidence:.2f})"
    )
    print(f"Evidence refs: {', '.join(result.evidence_refs) or '(none)'}")
    print(f"Citations valid: {result.citations_valid}")
    print(f"\nSubject: {result.letter.subject}")
    for sentence in result.letter.sentences:
        cites = ", ".join(c.ref for c in sentence.citations)
        print(f"  - {sentence.text}" + (f"  [{cites}]" if cites else ""))
    if result.letter.abstained:
        print(f"\nABSTAINED: {result.letter.abstain_reason}")
    log.info(
        "demo_complete",
        route=f"{result.route.family}/{result.route.issue}",
        citations_valid=result.citations_valid,
        tokens=result.prompt_tokens + result.completion_tokens,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
