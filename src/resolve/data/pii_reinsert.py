"""PII ground truth by re-insertion (PLAN §7.7).

CFPB replaces personal data in narratives with ``XXXX`` runs and dates with
``XX/XX/XXXX`` (the year is sometimes kept). Filling those positions with synthetic
values of a known type at known offsets yields exact span-level PII ground truth —
without ever handling a real person's data.

.. note::
   Per ADR-014 the CFPB no longer distributes narrative text, so there are no real
   masked narratives to process yet. This module is therefore exercised on synthetic
   masked narratives (:data:`SAMPLE_TEMPLATES`), and :func:`build` writes a small,
   clearly-labelled *sample* ``pii_spans_sample.jsonl``. Generating the full 500-item
   ``pii_spans.jsonl`` is deferred until narratives are synthesised (a later phase).

The entity *type* is inferred from the ~30 characters before each mask, so some
insertions read unnaturally; the offsets are always exact (stated in the data card).
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

from faker import Faker

from resolve.eval.schemas import GOLDEN_DIR, PiiItem, PiiSpan, write_jsonl
from resolve.logging import configure_logging, get_logger

__all__ = [
    "CONTEXT_RULES",
    "MASK",
    "PII_SAMPLE_PATH",
    "SAMPLE_TEMPLATES",
    "build",
    "main",
    "offsets_are_consistent",
    "reinsert",
]

log = get_logger(__name__)

PII_SAMPLE_PATH = GOLDEN_DIR / "pii_spans_sample.jsonl"

# CFPB masks: "XXXX" runs for names/numbers/places; dates as "XX/XX/XXXX" or
# "XX/XX/2023" (year sometimes kept).
MASK = re.compile(r"XX/XX/(?P<year>\d{4}|XXXX|\d{2}|XX)|X{2,}(?:\s+X{2,})*")

# (regex on the ~30 chars before the mask, entity type) — first match wins.
CONTEXT_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)ending\s*(in|with)?\s*$"), "LAST4"),
    (re.compile(r"(?i)account\s*(number|#|no\.?)?\s*(is)?\s*$"), "ACCOUNT_NUMBER"),
    (re.compile(r"(?i)(phone|call(ed)?|number)\s*(is|at)?\s*$"), "PHONE_NUMBER"),
    (re.compile(r"(?i)(email|e-mail)\s*(is|at)?\s*$"), "EMAIL_ADDRESS"),
    (re.compile(r"(?i)(live[sd]? (in|at)|address|located)\s*$"), "ADDRESS"),
    (
        re.compile(
            r"(?i)(mr\.?|mrs\.?|ms\.?|name is|named|spoke (to|with)|agent|representative)\s*$"
        ),
        "PERSON",
    ),
]

# Synthetic masked narratives resembling CFPB masking (no real data).
SAMPLE_TEMPLATES: list[str] = [
    "I called the bank and spoke with XXXX about a charge on my card ending in XXXX on XX/XX/2025.",
    "My account number is XXXX and I have been locked out since XX/XX/XXXX.",
    "The representative XXXX told me my address XXXX was wrong; my email is XXXX.",
    "On XX/XX/2024 an agent named XXXX said my phone number XXXX was not on file.",
    "I live at XXXX and the transfer of XX/XX/XXXX never posted to account XXXX.",
    "Mrs. XXXX from the branch called the number XXXX about the dispute filed XX/XX/2023.",
    "They emailed XXXX and mailed a letter to XXXX regarding the payment on XX/XX/XXXX.",
    "My card ending in XXXX was used on XX/XX/2025 by someone named XXXX.",
]


def _fake_date(fake: Faker, year: str) -> str:
    """Return a synthetic date string matching the mask's year format."""
    if year.isdigit():
        yr = int(year) if len(year) == 4 else 2000 + int(year)
        chosen = fake.date_between_dates(date(yr, 1, 1), date(yr, 12, 31))
    else:
        chosen = fake.date_between_dates(date(2012, 1, 1), date(2026, 6, 30))
    return chosen.strftime("%m/%d/%Y" if len(year) == 4 else "%m/%d/%y")


def _fake_value(fake: Faker, entity_type: str) -> str:
    """Return a synthetic value for a non-date entity type."""
    generators = {
        "LAST4": lambda: fake.numerify("####"),
        "ACCOUNT_NUMBER": lambda: fake.numerify("##########"),
        "PHONE_NUMBER": lambda: fake.phone_number(),
        "EMAIL_ADDRESS": lambda: fake.email(),
        "ADDRESS": lambda: fake.address().replace("\n", ", "),
        "PERSON": lambda: fake.name(),
    }
    return generators[entity_type]()


def reinsert(narrative: str, fake: Faker) -> tuple[str, list[PiiSpan]]:
    """Replace each CFPB mask with a synthetic value and record its exact span.

    Args:
        narrative: A CFPB-style masked narrative.
        fake: A (seeded) Faker instance for reproducibility.

    Returns:
        ``(text, spans)`` where ``text`` is the filled narrative and each span's
        ``[start, end)`` exactly bounds its inserted value.
    """
    out: list[str] = []
    spans: list[PiiSpan] = []
    cursor = 0
    for match in MASK.finditer(narrative):
        out.append(narrative[cursor : match.start()])
        if match.group("year") is not None:
            entity_type, value = "DATE", _fake_date(fake, match.group("year"))
        else:
            context = narrative[max(0, match.start() - 30) : match.start()]
            entity_type = next((t for rx, t in CONTEXT_RULES if rx.search(context)), "PERSON")
            value = _fake_value(fake, entity_type)
        start = sum(len(part) for part in out)
        out.append(value)
        spans.append(PiiSpan(start=start, end=start + len(value), entity_type=entity_type))
        cursor = match.end()
    out.append(narrative[cursor:])
    return "".join(out), spans


def offsets_are_consistent(text: str, spans: list[PiiSpan]) -> bool:
    """Self-check: spans are in bounds, ordered and non-overlapping (PLAN §7.7)."""
    previous_end = 0
    for span in spans:
        if not (0 <= span.start < span.end <= len(text)):
            return False
        if span.start < previous_end:  # overlap or out of order
            return False
        previous_end = span.end
    return True


def build(path: Path | None = None, *, seed: int = 20260101) -> int:
    """Write the synthetic PII sample set; returns the number of items written.

    Each template is filled with a per-item-seeded Faker so the output is
    reproducible, and every item's offsets are self-checked before writing.
    """
    destination = PII_SAMPLE_PATH if path is None else path
    items: list[PiiItem] = []
    for index, template in enumerate(SAMPLE_TEMPLATES):
        fake = Faker()
        fake.seed_instance(seed + index)
        text, spans = reinsert(template, fake)
        if not offsets_are_consistent(text, spans):  # pragma: no cover - defensive
            raise RuntimeError(f"inconsistent offsets for sample {index}")
        items.append(PiiItem(complaint_id=index, text=text, spans=spans, seed=seed + index))
    return write_jsonl(destination, items)


def main() -> int:
    """CLI entry point: ``python -m resolve.data.pii_reinsert``."""
    configure_logging()
    count = build()
    log.info(
        "pii_sample_written",
        path=str(PII_SAMPLE_PATH),
        count=count,
        note="synthetic sample; full pii_spans.jsonl deferred until narratives exist",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
