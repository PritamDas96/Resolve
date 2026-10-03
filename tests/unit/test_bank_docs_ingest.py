"""Unit tests for :mod:`resolve.data.bank_docs_ingest`.

Runs against a tiny committed fixture PDF (``sample_fee_schedule.pdf``) that
contains a couple of fee lines, so real ``pdfplumber`` extraction is exercised
without shipping any real bank document.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pdfplumber
import pytest

from resolve import config
from resolve.data import bank_docs_ingest as bd

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_fee_schedule.pdf"


# --- pure helpers -----------------------------------------------------------


def test_discover_pdfs_sorted_and_empty_when_absent(tmp_path: Path) -> None:
    assert bd.discover_pdfs(tmp_path / "missing") == []
    root = tmp_path / "bank_docs"
    root.mkdir()
    (root / "b.pdf").write_bytes(b"%PDF-1.4")
    (root / "a.pdf").write_bytes(b"%PDF-1.4")
    (root / "notes.txt").write_text("ignore me")
    found = bd.discover_pdfs(root)
    assert [p.name for p in found] == ["a.pdf", "b.pdf"]


def test_infer_source_meta_from_filename_and_sources(tmp_path: Path) -> None:
    root = tmp_path / "bank_docs"
    root.mkdir()
    conv = root / "jpmorgan_chase__fee_schedule.pdf"
    conv.write_bytes(b"%PDF")
    assert bd.infer_source_meta(conv, root, {}) == ("jpmorgan_chase", "fee_schedule", None)

    plain = root / "misc.pdf"
    plain.write_bytes(b"%PDF")
    assert bd.infer_source_meta(plain, root, {}) == ("misc", "document", None)

    sources = {"misc.pdf": {"bank": "Citi", "doc_type": "deposit_agreement", "url": "https://x"}}
    assert bd.infer_source_meta(plain, root, sources) == ("Citi", "deposit_agreement", "https://x")


def test_to_cents() -> None:
    assert bd._to_cents("12.00") == 1200
    assert bd._to_cents("1,500") == 150000
    assert bd._to_cents("35") == 3500


# --- real extraction on the fixture -----------------------------------------


def test_extract_text_and_fee_rows_from_fixture() -> None:
    with pdfplumber.open(FIXTURE) as pdf:
        text = bd.extract_text(pdf)
        rows = bd.extract_fee_rows(pdf, bank="jpmorgan_chase", doc_type="fee_schedule")

    assert "Fee schedule" in text
    amounts = {r.amount_cents for r in rows}
    assert 1200 in amounts  # $12.00 monthly maintenance
    assert 3500 in amounts  # $35.00 overdraft item
    monthly = next(r for r in rows if r.amount_cents == 1200)
    assert "maintenance fee" in monthly.fee_name.lower()
    assert monthly.conditions is not None  # "waived with $1500 balance"
    assert all(r.bank == "jpmorgan_chase" for r in rows)


# --- orchestration ----------------------------------------------------------


@pytest.fixture
def _settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> config.Settings:
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("GROQ_API_KEY", "test")
    return config.Settings(data_dir=tmp_path / "data")


def test_ingest_writes_manifest_and_extracted_output(_settings: config.Settings) -> None:
    root = Path(_settings.data_dir) / "raw" / "bank_docs"
    root.mkdir(parents=True)
    shutil.copy(FIXTURE, root / "jpmorgan_chase__fee_schedule.pdf")

    result = bd.ingest(_settings, retrieved_on=date(2026, 10, 4))

    assert len(result.documents) == 1
    doc = result.documents[0]
    assert doc.bank == "jpmorgan_chase"
    assert doc.doc_type == "fee_schedule"
    assert doc.pages == 1
    assert doc.fee_rows >= 2
    assert len(doc.sha256) == 64

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["documents"][0]["sha256"] == doc.sha256
    assert manifest["fee_rows"] == result.fee_rows

    extracted = [
        json.loads(line) for line in result.output_path.read_text(encoding="utf-8").splitlines()
    ]
    assert extracted[0]["bank"] == "jpmorgan_chase"
    assert extracted[0]["fee_rows"]


def test_ingest_handles_empty_directory(_settings: config.Settings) -> None:
    (Path(_settings.data_dir) / "raw" / "bank_docs").mkdir(parents=True)

    result = bd.ingest(_settings, retrieved_on=date(2026, 10, 4))

    assert result.documents == []
    assert result.fee_rows == 0
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["documents"] == []
