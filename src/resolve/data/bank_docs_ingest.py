"""Bank document ingestion (PLAN §7.5).

Hashes the public bank documents you place in ``data/raw/bank_docs/`` (deposit
agreements and fee schedules), extracts their text and fee tables with
``pdfplumber``, and writes a committed manifest. The PDFs and the extracted text
are **never committed** — only ``data/manifests/bank_docs.json`` (ADR/§7.5).

You download the PDFs yourself (they are not reliably fetchable); drop them in
``data/raw/bank_docs/`` and run ``make data-bankdocs``. An empty directory is
handled gracefully (empty manifest + a warning), so the pipeline never blocks.

Filename convention (overridable by a ``sources.yaml`` in the same directory):
``<bank>__<doc_type>.pdf`` — e.g. ``jpmorgan_chase__fee_schedule.pdf``. The
optional ``sources.yaml`` maps a filename to ``{bank, doc_type, url}`` so the
public source URL is recorded in the manifest.

Pure parsing (:func:`extract_fee_rows`, :func:`extract_text`) is tested on a tiny
committed fixture PDF; all filesystem I/O is in :func:`ingest`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pdfplumber
import yaml
from pdfplumber.pdf import PDF
from pydantic import BaseModel

from resolve.config import Settings, get_settings
from resolve.logging import configure_logging, get_logger

__all__ = [
    "BankDoc",
    "BankDocsResult",
    "FeeRow",
    "discover_pdfs",
    "extract_fee_rows",
    "extract_text",
    "infer_source_meta",
    "ingest",
    "main",
    "sha256_file",
]

log = get_logger(__name__)

# A currency amount, e.g. "$12.00", "$1,500", "$ 35".
_AMOUNT_RE = re.compile(r"\$\s?([\d,]+(?:\.\d{1,2})?)")


class FeeRow(BaseModel):
    """One extracted fee-table row.

    Attributes:
        bank: Bank identifier (from filename or ``sources.yaml``).
        doc_type: Document type, e.g. ``"fee_schedule"``.
        page: 1-based page number the row was found on.
        fee_name: Text preceding the amount on the line.
        amount_cents: The parsed amount in cents.
        conditions: Text following the amount, if any.
    """

    bank: str
    doc_type: str
    page: int
    fee_name: str
    amount_cents: int
    conditions: str | None


class BankDoc(BaseModel):
    """One ingested document (a manifest entry).

    Attributes:
        path: Source path, relative to the repo root.
        bank: Bank identifier.
        doc_type: Document type.
        url: Public source URL, if recorded in ``sources.yaml``.
        sha256: Hex SHA-256 of the PDF bytes.
        pages: Page count.
        fee_rows: Number of fee rows extracted.
        retrieved_on: Date the file was recorded.
    """

    path: str
    bank: str
    doc_type: str
    url: str | None
    sha256: str
    pages: int
    fee_rows: int
    retrieved_on: date


class BankDocsResult(BaseModel):
    """Summary of one ingestion run, returned by :func:`ingest`."""

    manifest_path: Path
    output_path: Path
    documents: list[BankDoc]
    fee_rows: int


# --- pure helpers -----------------------------------------------------------


def sha256_file(path: Path | str) -> str:
    """Return the hex SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_pdfs(root: Path | str) -> list[Path]:
    """Return every ``*.pdf`` under ``root``, sorted (empty if the dir is absent)."""
    base = Path(root)
    if not base.exists():
        return []
    return sorted(base.rglob("*.pdf"))


def infer_source_meta(
    path: Path, root: Path, sources: dict[str, dict[str, str]]
) -> tuple[str, str, str | None]:
    """Resolve ``(bank, doc_type, url)`` for a PDF.

    Uses an explicit ``sources.yaml`` entry if present, else infers from the
    ``<bank>__<doc_type>.pdf`` filename convention.

    Args:
        path: The PDF path.
        root: The ``bank_docs`` root (for the relative lookup key).
        sources: Parsed ``sources.yaml`` (filename -> {bank, doc_type, url}).

    Returns:
        A ``(bank, doc_type, url)`` tuple.
    """
    rel = path.relative_to(root).as_posix()
    meta = sources.get(rel) or sources.get(path.name)
    if meta:
        return meta["bank"], meta.get("doc_type", "document"), meta.get("url")
    stem = path.stem
    if "__" in stem:
        bank, doc_type = stem.split("__", 1)
        return bank, doc_type, None
    return stem, "document", None


def extract_text(pdf: PDF) -> str:
    """Return the full document text, one form-feed-separated page per page."""
    return "\f".join((page.extract_text() or "") for page in pdf.pages)


def extract_fee_rows(pdf: PDF, *, bank: str, doc_type: str) -> list[FeeRow]:
    """Extract best-effort fee rows: any text line that contains a dollar amount.

    Args:
        pdf: An open ``pdfplumber`` document.
        bank: Bank identifier to stamp on each row.
        doc_type: Document type to stamp on each row.

    Returns:
        One :class:`FeeRow` per line with a parseable amount (fee name before it,
        conditions after it).
    """
    rows: list[FeeRow] = []
    for page_number, page in enumerate(pdf.pages, start=1):
        for line in (page.extract_text() or "").splitlines():
            match = _AMOUNT_RE.search(line)
            if match is None:
                continue
            fee_name = line[: match.start()].strip(" .:-\t")
            if not fee_name:
                continue
            conditions = line[match.end() :].strip(" .:-\t") or None
            rows.append(
                FeeRow(
                    bank=bank,
                    doc_type=doc_type,
                    page=page_number,
                    fee_name=fee_name,
                    amount_cents=_to_cents(match.group(1)),
                    conditions=conditions,
                )
            )
    return rows


def _to_cents(amount: str) -> int:
    """Convert a currency string like ``"1,500.00"`` to integer cents."""
    return round(float(amount.replace(",", "")) * 100)


# --- orchestration ----------------------------------------------------------


def _load_sources(root: Path) -> dict[str, dict[str, str]]:
    """Load the optional ``sources.yaml`` metadata map (empty if absent)."""
    sources_path = root / "sources.yaml"
    if not sources_path.exists():
        return {}
    data = yaml.safe_load(sources_path.read_text(encoding="utf-8")) or {}
    return dict(data)


def ingest(settings: Settings, *, retrieved_on: date | None = None) -> BankDocsResult:
    """Hash and extract every bank PDF, writing the manifest and extracted text.

    Args:
        settings: Application settings (data dir).
        retrieved_on: Date to record; defaults to today (UTC).

    Returns:
        A :class:`BankDocsResult`. If no PDFs are present, the manifest is written
        with an empty document list and a warning is logged.
    """
    retrieved_on = retrieved_on or datetime.now(tz=UTC).date()
    data_dir = Path(settings.data_dir)
    root = data_dir / "raw" / "bank_docs"
    manifest_path = data_dir / "manifests" / "bank_docs.json"
    output_path = data_dir / "processed" / "bank_docs.jsonl"

    pdfs = discover_pdfs(root)
    sources = _load_sources(root)
    if not pdfs:
        log.warning("bank_docs_none_found", root=str(root))

    documents: list[BankDoc] = []
    extracted: list[dict[str, object]] = []
    total_fee_rows = 0
    for pdf_path in pdfs:
        bank, doc_type, url = infer_source_meta(pdf_path, root, sources)
        with pdfplumber.open(pdf_path) as pdf:
            text = extract_text(pdf)
            fee_rows = extract_fee_rows(pdf, bank=bank, doc_type=doc_type)
            page_count = len(pdf.pages)
        documents.append(
            BankDoc(
                path=pdf_path.relative_to(data_dir.parent).as_posix()
                if data_dir.parent in pdf_path.parents
                else str(pdf_path),
                bank=bank,
                doc_type=doc_type,
                url=url,
                sha256=sha256_file(pdf_path),
                pages=page_count,
                fee_rows=len(fee_rows),
                retrieved_on=retrieved_on,
            )
        )
        extracted.append(
            {
                "bank": bank,
                "doc_type": doc_type,
                "text": text,
                "fee_rows": [row.model_dump() for row in fee_rows],
            }
        )
        total_fee_rows += len(fee_rows)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "source": "Public bank deposit agreements and fee schedules (downloaded manually)",
                "retrieved_on": retrieved_on.isoformat(),
                "note": "PDFs and extracted text are not committed; only this manifest (§7.5).",
                "documents": [doc.model_dump(mode="json") for doc in documents],
                "fee_rows": total_fee_rows,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for entry in extracted:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    log.info(
        "bank_docs_ingest_complete",
        documents=len(documents),
        fee_rows=total_fee_rows,
        manifest=str(manifest_path),
    )
    return BankDocsResult(
        manifest_path=manifest_path,
        output_path=output_path,
        documents=documents,
        fee_rows=total_fee_rows,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m resolve.data.bank_docs_ingest``."""
    argparse.ArgumentParser(description="Ingest public bank documents.").parse_args(argv)
    configure_logging()
    settings = get_settings()
    result = ingest(settings)
    log.info("bank_docs_ingest_report", documents=len(result.documents), fee_rows=result.fee_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
