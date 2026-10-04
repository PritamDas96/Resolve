"""Rule-based PII detection + masking (PLAN §13.5).

A dependency-light recogniser set (email, phone, SSN, date, long account numbers,
context-tagged last-4) that detects PII and replaces it with typed placeholders at exact
offsets, so complaint narratives can be masked before any model sees them. Presidio with
spaCy NER would add PERSON/ADDRESS recall; it is deferred (onnxruntime/spaCy fragility on
this Py3.13 env, ADR-002) and this masker is the robust fallback. Span-level evaluation
uses :mod:`resolve.eval.metrics.spans`.
"""

from __future__ import annotations

import re

from resolve.eval.schemas import PiiSpan

__all__ = ["RECOGNISERS", "detect", "mask"]

# Ordered recognisers (earlier wins on overlap). Group 1, when present, is the span.
RECOGNISERS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL_ADDRESS", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("SSN", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    (
        "PHONE_NUMBER",
        re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"),
    ),
    ("DATE", re.compile(r"(?<!\d)\d{1,2}/\d{1,2}/\d{2,4}(?!\d)")),
    ("LAST4", re.compile(r"(?i)ending\s+(?:in|with)\s+(\d{4})(?!\d)")),
    ("ACCOUNT_NUMBER", re.compile(r"(?<!\d)\d{8,}(?!\d)")),
]


def detect(text: str) -> list[PiiSpan]:
    """Return non-overlapping PII spans, earliest-and-highest-priority recogniser first."""
    spans: list[PiiSpan] = []
    for entity_type, pattern in RECOGNISERS:
        for match in pattern.finditer(text):
            start, end = (
                (match.start(1), match.end(1)) if match.groups() else (match.start(), match.end())
            )
            if not any(s.start < end and start < s.end for s in spans):  # skip overlaps
                spans.append(PiiSpan(start=start, end=end, entity_type=entity_type))
    spans.sort(key=lambda s: s.start)
    return spans


def mask(text: str) -> tuple[str, list[PiiSpan]]:
    """Replace detected PII with typed placeholders; return (masked_text, original_spans)."""
    spans = detect(text)
    out: list[str] = []
    cursor = 0
    for span in spans:
        out.append(text[cursor : span.start])
        out.append(f"<{span.entity_type}>")
        cursor = span.end
    out.append(text[cursor:])
    return "".join(out), spans
