"""Generate the retrieval golden set (``eval/golden/retrieval_golden.jsonl``, PLAN §8.7).

Hand-authored queries over the real eCFR corpus with known expected CFR sections.
Because the Tier C hand-labels are narrative-blocked (ADR-014), this purpose-built
set supplies ground truth for the retrieval ablation now. Every expected section was
verified to exist in ``regulations.jsonl``. Strata: single-hop, multi-hop (two
sections) and point-in-time (same question at different as-of dates).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from resolve.eval.schemas import GOLDEN_DIR, RetrievalQuery, write_jsonl
from resolve.logging import configure_logging, get_logger

__all__ = ["RETRIEVAL_PATH", "build", "generate_queries", "main"]

log = get_logger(__name__)

RETRIEVAL_PATH = GOLDEN_DIR / "retrieval_golden.jsonl"

_DEFAULT_AS_OF = date(2023, 6, 1)

# (stratum, query, regulation_hint, expected_sections, as_of)
_QUERIES: list[tuple[str, str, str | None, list[str], date]] = [
    # --- single-hop ---------------------------------------------------------
    (
        "single_hop",
        "time limit for provisional credit after an unauthorized debit card error notice",
        "Reg E",
        ["1005.11"],
        _DEFAULT_AS_OF,
    ),
    (
        "single_hop",
        "consumer liability for unauthorized electronic fund transfers from a lost or "
        "stolen access device",
        "Reg E",
        ["1005.6"],
        _DEFAULT_AS_OF,
    ),
    (
        "single_hop",
        "required initial disclosures of the terms and conditions of electronic fund "
        "transfer services",
        "Reg E",
        ["1005.7"],
        _DEFAULT_AS_OF,
    ),
    (
        "single_hop",
        "stop payment of a preauthorized electronic fund transfer",
        "Reg E",
        ["1005.10"],
        _DEFAULT_AS_OF,
    ),
    (
        "single_hop",
        "procedures for resolving errors and investigating a notice of error",
        "Reg E",
        ["1005.11"],
        _DEFAULT_AS_OF,
    ),
    (
        "single_hop",
        "time limit to resolve a credit card billing error dispute",
        "Reg Z",
        ["1026.13"],
        _DEFAULT_AS_OF,
    ),
    (
        "single_hop",
        "consumer right to withhold payment of a disputed amount during a billing error",
        "Reg Z",
        ["1026.13"],
        _DEFAULT_AS_OF,
    ),
    (
        "single_hop",
        "cardholder liability for unauthorized use of a credit card limited to fifty dollars",
        "Reg Z",
        ["1026.12"],
        _DEFAULT_AS_OF,
    ),
    (
        "single_hop",
        "mortgage servicer must acknowledge a notice of error within a set number of days",
        "Reg X",
        ["1024.35"],
        _DEFAULT_AS_OF,
    ),
    (
        "single_hop",
        "mortgage servicer response to a request for information",
        "Reg X",
        ["1024.36"],
        _DEFAULT_AS_OF,
    ),
    (
        "single_hop",
        "escrow account analysis and annual escrow statement requirements",
        "Reg X",
        ["1024.17"],
        _DEFAULT_AS_OF,
    ),
    (
        "single_hop",
        "annual percentage yield and account disclosures for a savings account",
        "Reg DD",
        ["1030.4"],
        _DEFAULT_AS_OF,
    ),
    (
        "single_hop",
        "subsequent disclosures when account terms change",
        "Reg DD",
        ["1030.5"],
        _DEFAULT_AS_OF,
    ),
    (
        "single_hop",
        "furnisher duty to investigate a consumer's direct dispute about credit report information",
        "Reg V",
        ["1022.43"],
        _DEFAULT_AS_OF,
    ),
    (
        "single_hop",
        "furnisher policies for the accuracy and integrity of information furnished to "
        "credit bureaus",
        "Reg V",
        ["1022.42"],
        _DEFAULT_AS_OF,
    ),
    # --- multi-hop (two sections) -------------------------------------------
    (
        "multi_hop",
        "a credit card billing error that also led to a dispute about information on the "
        "credit report",
        None,
        ["1026.13", "1022.43"],
        _DEFAULT_AS_OF,
    ),
    (
        "multi_hop",
        "unauthorized debit card transaction: consumer liability and the error-resolution "
        "procedure",
        "Reg E",
        ["1005.6", "1005.11"],
        _DEFAULT_AS_OF,
    ),
    # --- point-in-time (same question, different dates) ---------------------
    (
        "point_in_time",
        "time limit for provisional credit after a debit card error notice",
        "Reg E",
        ["1005.11"],
        date(2019, 6, 1),
    ),
    (
        "point_in_time",
        "time limit for provisional credit after a debit card error notice",
        "Reg E",
        ["1005.11"],
        date(2025, 6, 1),
    ),
    (
        "point_in_time",
        "escrow account analysis requirements in force",
        "Reg X",
        ["1024.17"],
        date(2020, 1, 1),
    ),
]


def generate_queries() -> list[RetrievalQuery]:
    """Return the authored retrieval golden queries with stable ids."""
    return [
        RetrievalQuery(
            id=f"Q-{i:03d}",
            stratum=stratum,
            query=query,
            regulation_hint=hint,
            as_of=as_of,
            expected_sections=sections,
        )
        for i, (stratum, query, hint, sections, as_of) in enumerate(_QUERIES, start=1)
    ]


def build(path: Path | None = None) -> int:
    """Write the retrieval golden to disk; returns the number of queries."""
    return write_jsonl(RETRIEVAL_PATH if path is None else path, generate_queries())


def main() -> int:
    """CLI entry point: ``python -m resolve.eval.golden.retrieval_gen``."""
    configure_logging()
    count = build()
    log.info("retrieval_golden_written", path=str(RETRIEVAL_PATH), count=count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
