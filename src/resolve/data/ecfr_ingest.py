"""eCFR regulation ingestion (PLAN §7.4, ADR-015).

This module builds the point-in-time regulation half of the data foundation. For
each in-scope CFR part (Reg E/Z/X/DD/V — all in Title 12) it:

* resolves the dates on which the part actually changed, from the versioner
  ``versions`` endpoint (:func:`parse_versions`);
* downloads the full part XML as of each of those dates (:func:`fetch_part_xml`),
  caching every response — historical snapshots never change;
* parses sections and their paragraphs, reconstructing the ``(a)(1)(i)`` path
  from the inline markers (:func:`parse_sections`);
* parses **Supplement I** official interpretations and links each comment to the
  paragraph it interprets (:func:`parse_supplement`);
* collapses identical text across adjacent snapshots into one record with a
  ``valid_from`` / ``valid_to`` range (:func:`collapse_versions`), so
  point-in-time retrieval is a simple ``valid_from <= d <= valid_to`` filter;
* writes ``regulations.jsonl`` plus a committed manifest.

Three findings from verifying the live API on 2026-10-03 shape this module (see
ADR-015):

* The eCFR API is **not** bot-walled (unlike CFPB): plain ``httpx`` works, so no
  ``curl_cffi`` impersonation is needed here.
* Invalid issue dates are **not** 404'd — they are served as-of the nearest
  prior version. Snapshot dates are therefore driven by the ``versions``
  endpoint, never by probing arbitrary dates.
* Point-in-time history begins ~2017-01-01, so complaints before 2017 resolve to
  the earliest available snapshot.

As in :mod:`resolve.data.cfpb_ingest`, every transform is a pure function over
XML/text (unit-tested on fixtures) and all I/O is isolated in
:func:`fetch_versions`, :func:`fetch_part_xml`, :func:`download_all` and
:func:`ingest`.

Known limitation (ADR-015): paragraph-path reconstruction is correct for the
common four-level ``(a)(1)(i)(A)`` cycle but has a small tail (~0.5% of section
paragraphs on Reg E) where a genuine 9th lower-alpha ``(i)`` or a deep re-descent
into a repeated marker type is mislabelled. Supplement I linking is unaffected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from lxml import etree
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from resolve import config
from resolve.config import Settings, get_settings
from resolve.logging import configure_logging, get_logger

__all__ = [
    "RegChunk",
    "RegIngestResult",
    "collapse_versions",
    "download_all",
    "fetch_part_xml",
    "fetch_versions",
    "ingest",
    "main",
    "markers_in_order",
    "paragraph_path",
    "parse_sections",
    "parse_supplement",
    "parse_versions",
    "sha256_text",
    "write_manifest",
]

log = get_logger(__name__)

# An enumerator at the very start of a paragraph, e.g. "(a)", "(1)", "(ii)", "(A)".
_LEADING_MARKER_RE = re.compile(r"^\(([A-Za-z0-9]+)\)")

# A nested enumerator in the eCFR "run-in" style, where the first paragraph of a
# subsection introduces deeper levels after an em/en dash (U+2013 / U+2014), e.g.
# "(a) <I>Definition of error</I>-(1) <I>Types ...</I> The term ...". Mid-sentence
# cross-references like "SS 1005.10(a)" are not preceded by a dash, so are ignored.
_INLINE_MARKER_RE = re.compile(r"[–—]\(([A-Za-z0-9]+)\)")  # noqa: RUF001 (en/em dash)

# Roman-numeral letters, used to disambiguate "(i)"/"(v)"/"(x)" (roman) from the
# 9th/22nd/24th lower-alpha enumerators. The context (parent level) decides.
_ROMAN_LETTERS = set("ivxlcdm")

# A Supplement I paragraph-level heading, e.g. "11(c)" or "Paragraph 11(c)(1)".
# Group 1 is the section-within-part number; group 2 is the paragraph path.
_INTERP_HEAD_RE = re.compile(r"^(?:Paragraph\s+)?(\d+)((?:\([A-Za-z0-9]+\))+)\s*")

# A Supplement I section heading, e.g. "Section 1005.11 Procedures ...".
_INTERP_SECTION_RE = re.compile(r"^Section\s+(\d+\.\d+)\b")

# Marker type ranks, in canonical CFR nesting order.
_ALPHA, _ARABIC, _ROMAN, _UPPER = "alpha", "arabic", "roman", "upper"


class RegChunk(BaseModel):
    """One regulation paragraph or interpretation comment at a point in time.

    Attributes:
        chunk_id: Stable id ``"{section}{paragraph}@{valid_from}"`` (interpretation
            comments append ``"-int{n}"`` to stay unique).
        regulation: Display name, e.g. ``"Reg E"``.
        part: CFR part number, e.g. ``"1005"``.
        section: Section number, e.g. ``"1005.11"``.
        paragraph: Reconstructed paragraph path, e.g. ``"(c)(1)"`` ("" for intros).
        heading: Nearest heading text (section head, or interpretation head).
        text: The paragraph / comment text, markers included.
        is_interpretation: True for Supplement I official interpretations.
        interprets: For interpretations, the ``"{section}{paragraph}"`` target.
        valid_from: First snapshot date on which this exact text was in force.
        valid_to: Last date in force, or ``None`` if still current.
        source_url: The eCFR URL the record was parsed from.
        sha256: Hex SHA-256 of ``text`` (drives version collapsing).
    """

    chunk_id: str
    regulation: str
    part: str
    section: str
    paragraph: str
    heading: str
    text: str
    is_interpretation: bool
    interprets: str | None
    valid_from: date
    valid_to: date | None
    source_url: str
    sha256: str


class RegIngestResult(BaseModel):
    """Summary of one eCFR ingestion run, returned by :func:`ingest`.

    Attributes:
        output_path: Path to the written ``regulations.jsonl``.
        manifest_path: Path to the committed ``ecfr.json`` manifest.
        records: Number of collapsed records written.
        snapshots: Snapshot dates fetched, per part.
        records_by_regulation: Record count per display regulation name.
    """

    output_path: Path
    manifest_path: Path
    records: int
    snapshots: dict[str, list[str]]
    records_by_regulation: dict[str, int]


# --- pure transforms: paragraph-path reconstruction -------------------------


def _marker_type(token: str, *, parent_type: str | None) -> str:
    """Classify a paragraph marker token into a CFR nesting type.

    ``(i)``/``(v)``/``(x)`` are ambiguous — they are both lower-alpha and
    lower-roman letters — so a roman reading is chosen only when the parent level
    is arabic (the point in the ``(a)(1)(i)`` cycle where roman is expected).

    Args:
        token: The enumerator inside the parentheses, e.g. ``"a"``, ``"1"``, ``"ii"``.
        parent_type: Type of the current deepest marker on the stack, or ``None``.

    Returns:
        One of ``"alpha"``, ``"arabic"``, ``"roman"`` or ``"upper"``.
    """
    if token.isdigit():
        return _ARABIC
    if token.isupper():
        return _UPPER
    is_roman = all(ch in _ROMAN_LETTERS for ch in token)
    # Multi-letter roman ("ii") is unambiguous. A single-letter roman ("i"/"v"/"x")
    # continues a roman run only when we are already at — or directly below — a
    # numbered level (the "(1)(i)(ii)..." cycle); otherwise it is a lower-alpha
    # enumerator (e.g. the 9th item "(i)" of an "(a)(b)...(h)(i)" run).
    if is_roman and (len(token) > 1 or parent_type in (_ARABIC, _ROMAN)):
        return _ROMAN
    if len(token) == 1:
        return _ALPHA
    return _ROMAN


def _update_stack(stack: list[tuple[str, str]], token: str) -> None:
    """Fold one marker into the running path stack, in place.

    If the marker's type already appears on the stack it replaces that level and
    everything deeper (a sibling/pop); otherwise it is pushed (a descent).

    Args:
        stack: List of ``(token, type)`` pairs, mutated in place.
        token: The new enumerator token.
    """
    parent_type = stack[-1][1] if stack else None
    typ = _marker_type(token, parent_type=parent_type)
    for i in range(len(stack) - 1, -1, -1):
        if stack[i][1] == typ:
            del stack[i:]
            break
    stack.append((token, typ))


def paragraph_path(stack: list[tuple[str, str]]) -> str:
    """Render a marker stack as a paragraph path, e.g. ``"(a)(1)(i)"``."""
    return "".join(f"({token})" for token, _ in stack)


def markers_in_order(text: str) -> list[str]:
    """Return the enumerator tokens a paragraph introduces, in document order.

    This is the leading marker (if any) followed by any run-in markers that
    appear after an em/en dash — the eCFR convention for the first paragraph of a
    subsection, e.g. ``"(a) ...—(1) ..."`` introduces both ``a`` and ``1``.

    Args:
        text: The normalised paragraph text.

    Returns:
        Enumerator tokens, e.g. ``["a", "1"]`` (possibly empty for continuations).
    """
    tokens: list[str] = []
    lead = _LEADING_MARKER_RE.match(text)
    if lead:
        tokens.append(lead.group(1))
    tokens.extend(match.group(1) for match in _INLINE_MARKER_RE.finditer(text))
    return tokens


# --- pure transforms: XML parsing -------------------------------------------


def _element_text(element: etree._Element) -> str:
    """Return the normalised, whitespace-collapsed text of an element."""
    return re.sub(r"\s+", " ", "".join(str(part) for part in element.itertext())).strip()


def _part_root(xml: bytes) -> etree._Element:
    """Return the ``DIV5`` part element for an eCFR ``?part=`` XML response.

    The part export returns the ``DIV5`` as the document root, but this also
    tolerates a wrapped document by falling back to a descendant search.
    """
    root = etree.fromstring(xml)
    if root.tag == "DIV5":
        return root
    found = root.find(".//DIV5[@TYPE='PART']")
    if found is None:
        raise ValueError("no DIV5 PART element found in eCFR XML")
    return found


def parse_sections(
    xml: bytes, *, part: str, regulation: str, snapshot: date, source_url: str
) -> list[RegChunk]:
    """Parse a point-in-time part XML into one record per section paragraph.

    Each ``<P>`` in a ``DIV8`` section becomes a record. The paragraph path is
    reconstructed from the leading ``(x)`` marker of each ``<P>``, maintained as a
    stack across the section (so ``(2)`` after ``(a)(1)(i)`` resolves to
    ``(a)(2)``). Paragraphs with no leading marker inherit the current path.

    Args:
        xml: Raw part XML bytes (the ``full/{date}/title-N.xml?part=`` response).
        part: CFR part number, e.g. ``"1005"``.
        regulation: Display regulation name, e.g. ``"Reg E"``.
        snapshot: The issue date this XML represents.
        source_url: The URL this XML was fetched from.

    Returns:
        One :class:`RegChunk` per section paragraph, with ``valid_from=snapshot``
        and ``valid_to=None`` (ranges are assigned later by
        :func:`collapse_versions`).
    """
    root = _part_root(xml)
    records: list[RegChunk] = []
    for section_div in root.iterfind(".//DIV8[@TYPE='SECTION']"):
        section = section_div.get("N") or ""
        head_el = section_div.find("HEAD")
        heading = _element_text(head_el) if head_el is not None else ""
        stack: list[tuple[str, str]] = []
        for p_el in section_div.findall(".//P"):
            text = _element_text(p_el)
            if not text:
                continue
            for token in markers_in_order(text):
                _update_stack(stack, token)
            paragraph = paragraph_path(stack)
            records.append(
                _make_chunk(
                    regulation=regulation,
                    part=part,
                    section=section,
                    paragraph=paragraph,
                    heading=heading,
                    text=text,
                    is_interpretation=False,
                    interprets=None,
                    snapshot=snapshot,
                    source_url=source_url,
                )
            )
    return records


def _resolve_interpreted_target(
    part: str, section_heading: str, para_heading: str
) -> tuple[str, str | None]:
    """Resolve the ``(section, interprets)`` target for a Supplement I heading.

    The section number is taken from the paragraph heading's leading number
    combined with the known ``part`` (e.g. ``"17(k)(5)"`` under part ``1024`` →
    section ``1024.17``). This is robust to non-section ``HD1`` headings that would
    otherwise leave the enclosing section ambiguous. Section-level comments (no
    paragraph heading) fall back to the ``HD1`` section number.

    Args:
        part: CFR part number, e.g. ``"1024"``.
        section_heading: The enclosing ``HD1`` text, e.g. ``"Section 1024.5 ..."``.
        para_heading: The nearest paragraph heading (``HD2``/``HD3``), e.g.
            ``"11(c)"`` or ``"Paragraph 11(c)(1)"``; empty for section-level comments.

    Returns:
        A ``(section, interprets)`` tuple. ``interprets`` is ``"{section}{path}"``
        when a paragraph heading is present, else the bare section.
    """
    para_match = _INTERP_HEAD_RE.match(para_heading) if para_heading else None
    if para_match:
        section = f"{part}.{para_match.group(1)}"
        return section, f"{section}{para_match.group(2)}"
    section_match = _INTERP_SECTION_RE.match(section_heading)
    section = section_match.group(1) if section_match else ""
    return section, (section or None)


def parse_supplement(
    xml: bytes, *, part: str, regulation: str, snapshot: date, source_url: str
) -> list[RegChunk]:
    """Parse the Supplement I appendix into linked interpretation records.

    Supplement I is structured as ``HD1`` section headings, ``HD2``/``HD3``
    paragraph headings, and numbered ``<P>`` comments. Each comment is linked to
    the paragraph it interprets via the nearest preceding headings.

    Args:
        xml: Raw part XML bytes.
        part: CFR part number.
        regulation: Display regulation name.
        snapshot: The issue date this XML represents.
        source_url: The URL this XML was fetched from.

    Returns:
        One :class:`RegChunk` per interpretation comment, ``is_interpretation=True``.
    """
    root = _part_root(xml)
    supp = next(
        (
            d
            for d in root.iterfind(".//DIV9[@TYPE='APPENDIX']")
            if "Supplement I" in (d.get("N") or "")
        ),
        None,
    )
    if supp is None:
        return []

    records: list[RegChunk] = []
    section_heading = ""
    para_heading = ""
    comment_index = 0
    for el in supp.iter():
        if el.tag == "HD1":
            section_heading = _element_text(el)
            para_heading = ""
        elif el.tag in ("HD2", "HD3"):
            para_heading = _element_text(el)
        elif el.tag == "P":
            text = _element_text(el)
            if not text:
                continue
            section, interprets = _resolve_interpreted_target(part, section_heading, para_heading)
            comment_index += 1
            records.append(
                _make_chunk(
                    regulation=regulation,
                    part=part,
                    section=section,
                    paragraph="",
                    heading=para_heading or section_heading,
                    text=text,
                    is_interpretation=True,
                    interprets=interprets,
                    snapshot=snapshot,
                    source_url=source_url,
                    suffix=f"-int{comment_index}",
                )
            )
    return records


def _make_chunk(
    *,
    regulation: str,
    part: str,
    section: str,
    paragraph: str,
    heading: str,
    text: str,
    is_interpretation: bool,
    interprets: str | None,
    snapshot: date,
    source_url: str,
    suffix: str = "",
) -> RegChunk:
    """Construct a :class:`RegChunk` with a computed id and text hash."""
    chunk_id = f"{section}{paragraph}{suffix}@{snapshot.isoformat()}"
    return RegChunk(
        chunk_id=chunk_id,
        regulation=regulation,
        part=part,
        section=section,
        paragraph=paragraph,
        heading=heading,
        text=text,
        is_interpretation=is_interpretation,
        interprets=interprets,
        valid_from=snapshot,
        valid_to=None,
        source_url=source_url,
        sha256=sha256_text(text),
    )


# --- pure transforms: version collapsing ------------------------------------


def _collapse_key(chunk: RegChunk) -> tuple[str, str, bool, str | None, str]:
    """Identity of a record across snapshots (ignoring date and text)."""
    return (
        chunk.section,
        chunk.paragraph,
        chunk.is_interpretation,
        chunk.interprets,
        chunk.heading,
    )


def collapse_versions(snapshots: list[tuple[date, list[RegChunk]]]) -> list[RegChunk]:
    """Collapse per-snapshot records into validity ranges.

    For each logical paragraph (keyed by section/paragraph/interpretation, not by
    date or text), consecutive snapshots with identical text are merged into one
    record. When the text changes, the previous record's ``valid_to`` is set to
    the day before the changing snapshot and a new record opens. The final
    in-force record is left open (``valid_to=None``); a paragraph that disappears
    is closed at the day before the snapshot it vanished from.

    Args:
        snapshots: ``(date, records)`` pairs; order does not matter (sorted here).

    Returns:
        Collapsed records, sorted by ``(section, paragraph, interpretation, valid_from)``.
    """
    ordered = sorted(snapshots, key=lambda pair: pair[0])
    dates = [d for d, _ in ordered]
    by_key: dict[tuple[str, str, bool, str | None, str], dict[date, RegChunk]] = {}
    for snap_date, chunks in ordered:
        for chunk in chunks:
            by_key.setdefault(_collapse_key(chunk), {})[snap_date] = chunk

    out: list[RegChunk] = []
    for date_to_chunk in by_key.values():
        open_chunk: RegChunk | None = None
        prev_sha: str | None = None
        for snap_date in dates:
            current = date_to_chunk.get(snap_date)
            sha = current.sha256 if current else None
            if sha == prev_sha:
                continue
            if open_chunk is not None:
                out.append(
                    open_chunk.model_copy(update={"valid_to": snap_date - timedelta(days=1)})
                )
            open_chunk = current
            prev_sha = sha
        if open_chunk is not None:
            out.append(open_chunk)
    out.sort(key=lambda c: (c.section, c.paragraph, c.is_interpretation, c.valid_from))
    return out


# --- hashing / manifest -----------------------------------------------------


def sha256_text(text: str) -> str:
    """Return the hex SHA-256 of ``text`` (UTF-8)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_manifest(path: Path | str, **fields: object) -> None:
    """Write ``fields`` as a stable, pretty-printed JSON manifest."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(fields, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )


# --- network seam -----------------------------------------------------------


@retry(reraise=True, stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30))
def _get(url: str, params: dict[str, str] | None = None) -> httpx.Response:
    """GET a public eCFR URL (plain httpx; the API is not bot-walled)."""
    response = httpx.get(
        url,
        params=params,
        timeout=180,
        follow_redirects=True,
        headers={"User-Agent": "resolve-data-ingest/0.1 (+https://github.com)"},
    )
    if response.status_code >= 400:
        raise RuntimeError(f"eCFR returned HTTP {response.status_code} for {url}")
    return response


def parse_versions(payload: dict[str, object], *, since_year: int) -> list[date]:
    """Extract the distinct, in-range issue dates from a ``versions`` payload.

    Args:
        payload: The decoded ``versions/title-N.json?part=`` response.
        since_year: Drop snapshot dates before this year (eCFR history floor).

    Returns:
        Sorted, de-duplicated issue dates on/after ``since_year``.
    """
    raw = payload.get("content_versions", [])
    versions = raw if isinstance(raw, list) else []
    dates: set[date] = set()
    for version in versions:
        value = version.get("date") if isinstance(version, dict) else None
        if isinstance(value, str):
            parsed = date.fromisoformat(value)
            if parsed.year >= since_year:
                dates.add(parsed)
    return sorted(dates)


def fetch_versions(part: str, *, delay_s: float = 1.0) -> dict[str, object]:
    """Fetch the raw ``versions`` payload for one part. Network seam."""
    if delay_s > 0:
        time.sleep(delay_s)
    url = f"{config.ECFR_API_BASE}versions/title-{config.ECFR_TITLE}.json"
    result: dict[str, object] = _get(url, params={"part": part}).json()
    return result


def part_xml_url(part: str, snapshot: date) -> str:
    """Return the point-in-time full-XML URL for a part at a date."""
    return (
        f"{config.ECFR_API_BASE}full/{snapshot.isoformat()}/title-{config.ECFR_TITLE}.xml"
        f"?part={part}"
    )


def fetch_part_xml(part: str, snapshot: date, *, delay_s: float = 1.0) -> bytes:
    """Fetch one point-in-time part XML. Network seam."""
    if delay_s > 0:
        time.sleep(delay_s)
    url = f"{config.ECFR_API_BASE}full/{snapshot.isoformat()}/title-{config.ECFR_TITLE}.xml"
    return _get(url, params={"part": part}).content


# --- orchestration ----------------------------------------------------------


def download_all(
    part: str,
    snapshots: list[date],
    *,
    cache_dir: Path,
    delay_s: float,
    refresh: bool = False,
) -> list[tuple[date, Path]]:
    """Download (or reuse cached) part XML for each snapshot date.

    Args:
        part: CFR part number.
        snapshots: Issue dates to fetch.
        cache_dir: Root directory for cached XML.
        delay_s: Per-request throttle in seconds.
        refresh: Re-fetch even when a cached file exists.

    Returns:
        ``(date, path)`` pairs in snapshot order.
    """
    paths: list[tuple[date, Path]] = []
    for snapshot in snapshots:
        cache_path = cache_dir / part / f"{snapshot.isoformat()}.xml"
        if cache_path.exists() and not refresh:
            log.debug("ecfr_cache_hit", part=part, date=str(snapshot), path=str(cache_path))
        else:
            content = fetch_part_xml(part, snapshot, delay_s=delay_s)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(content)
            log.info("ecfr_fetched", part=part, date=str(snapshot), bytes=len(content))
        paths.append((snapshot, cache_path))
    return paths


def ingest(
    settings: Settings,
    *,
    refresh: bool = False,
    regulations: dict[str, str] | None = None,
) -> RegIngestResult:
    """Run the full eCFR ingestion and write the collapsed outputs.

    Args:
        settings: Application settings (data dir, since-year, request delay).
        refresh: Re-fetch all snapshots instead of reusing the cache.
        regulations: Override the default ``{display_name: part}`` map (smoke runs).

    Returns:
        A :class:`RegIngestResult` describing the written outputs.
    """
    regulations = regulations or config.IN_SCOPE_REGULATIONS
    data_dir = Path(settings.data_dir)
    cache_dir = data_dir / "raw" / "ecfr"
    output_path = data_dir / "processed" / "regulations.jsonl"
    manifest_path = data_dir / "manifests" / "ecfr.json"

    all_records: list[RegChunk] = []
    snapshots_by_reg: dict[str, list[str]] = {}
    counts_by_reg: dict[str, int] = {}

    # Snapshots are exactly the part's in-range version dates. The latest version
    # date already carries the current text, so there is no "plus today" snapshot
    # — issue dates after the title's latest issue date 404 (ADR-015), and the
    # newest record is left open-ended (``valid_to=None``) by collapse_versions.
    for regulation, part in regulations.items():
        snapshots = parse_versions(
            fetch_versions(part, delay_s=settings.ecfr_request_delay_s),
            since_year=settings.ecfr_since_year,
        )
        snapshots_by_reg[regulation] = [d.isoformat() for d in snapshots]

        paths = download_all(
            part,
            snapshots,
            cache_dir=cache_dir,
            delay_s=settings.ecfr_request_delay_s,
            refresh=refresh,
        )
        per_snapshot: list[tuple[date, list[RegChunk]]] = []
        for snapshot, path in paths:
            xml = path.read_bytes()
            url = part_xml_url(part, snapshot)
            chunks = parse_sections(
                xml, part=part, regulation=regulation, snapshot=snapshot, source_url=url
            ) + parse_supplement(
                xml, part=part, regulation=regulation, snapshot=snapshot, source_url=url
            )
            per_snapshot.append((snapshot, chunks))

        collapsed = collapse_versions(per_snapshot)
        counts_by_reg[regulation] = len(collapsed)
        all_records.extend(collapsed)

    all_records.sort(
        key=lambda c: (c.part, c.section, c.paragraph, c.is_interpretation, c.valid_from)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in all_records:
            handle.write(record.model_dump_json() + "\n")

    write_manifest(
        manifest_path,
        source="eCFR versioner API (point-in-time full XML, per part)",
        api_base=config.ECFR_API_BASE,
        title=config.ECFR_TITLE,
        retrieved_at=datetime.now(tz=UTC).isoformat(),
        regulations=dict(regulations),
        snapshots=snapshots_by_reg,
        processed={
            "path": str(output_path),
            "sha256": sha256_text(output_path.read_text(encoding="utf-8")),
            "records": len(all_records),
            "records_by_regulation": counts_by_reg,
        },
        note=(
            "Point-in-time history begins ~2017; invalid dates resolve to the nearest "
            "prior version, so snapshots are driven by the versions endpoint (ADR-015)."
        ),
    )

    log.info(
        "ecfr_ingest_complete",
        records=len(all_records),
        regulations=counts_by_reg,
        output=str(output_path),
    )
    return RegIngestResult(
        output_path=output_path,
        manifest_path=manifest_path,
        records=len(all_records),
        snapshots=snapshots_by_reg,
        records_by_regulation=counts_by_reg,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="Ingest eCFR regulations for five CFPB rules.")
    parser.add_argument(
        "--since-year", type=int, default=None, help="Override the earliest snapshot year."
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Re-fetch all snapshots, ignoring the cache."
    )
    parser.add_argument(
        "--only-reg",
        action="append",
        default=None,
        metavar="REG",
        help="Restrict ingestion to one or more display regulation names (smoke runs).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: ``python -m resolve.data.ecfr_ingest``."""
    args = _build_arg_parser().parse_args(argv)
    configure_logging()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    if args.since_year is not None:
        settings = settings.model_copy(update={"ecfr_since_year": args.since_year})

    regulations = config.IN_SCOPE_REGULATIONS
    if args.only_reg:
        regulations = {name: config.IN_SCOPE_REGULATIONS[name] for name in args.only_reg}

    result = ingest(settings, refresh=args.refresh, regulations=regulations)
    log.info(
        "ecfr_ingest_report",
        records=result.records,
        regulations=result.records_by_regulation,
    )


if __name__ == "__main__":
    main()
