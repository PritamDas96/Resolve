"""Unit tests for :mod:`resolve.data.cfpb_ingest`.

These tests are the specification for the ingestion module. They run fully
offline against a small committed fixture (``tests/fixtures/cfpb_sample.csv``)
that mirrors the real CFPB CSV export header and value formats (ISO datetimes,
string complaint ids, masked ZIPs). The only network seam —
``fetch_export_text`` — is monkeypatched so no HTTP ever happens in CI.

The fixture holds 12 rows chosen to exercise every branch:

* 8 in-scope rows across all six banks and several years (pre/post the 2017
  taxonomy change), spanning the train/val/test split boundaries;
* 1 out-of-scope **product** (Student loan) and 1 out-of-scope product
  (Debt collection) — dropped by the product filter;
* 1 out-of-scope **company** (DISCOVER BANK) — dropped by the bank filter;
* 1 duplicate ``Complaint ID`` (1005) — dropped by deduplication.

So: 12 parsed → 9 after scope filter → 8 after dedup.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from resolve import config
from resolve.data import cfpb_ingest

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "cfpb_sample.csv"
FIXTURE_TEXT = FIXTURE.read_text(encoding="utf-8")

# All CFPB company strings for the six in-scope banks, flattened.
BANK_STRINGS = {s for strings in config.BANKS.values() for s in strings}


# --- pure parsing / transformation ----------------------------------------


def test_parse_export_csv_canonical_columns_and_types() -> None:
    df = cfpb_ingest.parse_export_csv(FIXTURE_TEXT)

    assert df.height == 12
    expected = {
        "date_received",
        "product",
        "sub_product",
        "issue",
        "sub_issue",
        "company_public_response",
        "company",
        "state",
        "zip_code",
        "tags",
        "submitted_via",
        "date_sent_to_company",
        "company_response",
        "timely_response",
        "complaint_id",
        "year",
        "split",
    }
    assert expected <= set(df.columns)
    assert df.schema["complaint_id"] == pl.Int64
    assert df.schema["date_received"] == pl.Date
    assert df.schema["year"] == pl.Int32 or df.schema["year"] == pl.Int64


def test_parse_export_csv_derives_year_and_split() -> None:
    df = cfpb_ingest.parse_export_csv(FIXTURE_TEXT)
    by_id = {row["complaint_id"]: row for row in df.to_dicts()}

    assert by_id[1001]["year"] == 2023
    assert by_id[1001]["split"] == "train"  # <= 2023
    assert by_id[1002]["split"] == "val"  # 2024
    assert by_id[1003]["year"] == 2025
    assert by_id[1003]["split"] == "test"  # >= 2025
    assert by_id[1004]["year"] == 2016


def test_filter_in_scope_drops_out_of_scope_company_and_products() -> None:
    df = cfpb_ingest.parse_export_csv(FIXTURE_TEXT)
    scoped = cfpb_ingest.filter_in_scope(
        df, bank_strings=BANK_STRINGS, products=config.IN_SCOPE_PRODUCTS
    )

    ids = set(scoped["complaint_id"].to_list())
    assert scoped.height == 9  # 12 - 2 (product) - 1 (company)
    assert 1009 not in ids and 1010 not in ids  # out-of-scope products
    assert 1011 not in ids  # out-of-scope company (DISCOVER BANK)
    assert "DISCOVER BANK" not in set(scoped["company"].to_list())


def test_deduplicate_removes_duplicate_complaint_id() -> None:
    df = cfpb_ingest.parse_export_csv(FIXTURE_TEXT)
    scoped = cfpb_ingest.filter_in_scope(
        df, bank_strings=BANK_STRINGS, products=config.IN_SCOPE_PRODUCTS
    )

    deduped, dropped = cfpb_ingest.deduplicate(scoped)

    assert dropped == 1
    assert deduped.height == 8
    assert deduped["complaint_id"].n_unique() == 8
    assert deduped.filter(pl.col("complaint_id") == 1005).height == 1


def test_assign_bank_display_maps_company_strings() -> None:
    df = cfpb_ingest.parse_export_csv(FIXTURE_TEXT)
    scoped = cfpb_ingest.filter_in_scope(
        df, bank_strings=BANK_STRINGS, products=config.IN_SCOPE_PRODUCTS
    )

    labelled = cfpb_ingest.assign_bank_display(scoped, config.BANKS)

    assert "bank" in labelled.columns
    by_id = {row["complaint_id"]: row for row in labelled.to_dicts()}
    assert by_id[1001]["bank"] == "JPMorgan Chase"
    assert by_id[1002]["bank"] == "Bank of America"
    assert by_id[1006]["bank"] == "U.S. Bank"


def test_data_report_counts_by_bank_year_product() -> None:
    df = cfpb_ingest.parse_export_csv(FIXTURE_TEXT)
    scoped = cfpb_ingest.filter_in_scope(
        df, bank_strings=BANK_STRINGS, products=config.IN_SCOPE_PRODUCTS
    )
    deduped, _ = cfpb_ingest.deduplicate(scoped)
    labelled = cfpb_ingest.assign_bank_display(deduped, config.BANKS)

    report = cfpb_ingest.data_report(labelled)

    assert {"bank", "year", "product", "count"} <= set(report.columns)
    assert report["count"].sum() == 8
    chase = report.filter(pl.col("bank") == "JPMorgan Chase")["count"].sum()
    assert chase == 2  # ids 1001 (2023) + 1007 (2015)
    wells_2025 = report.filter((pl.col("bank") == "Wells Fargo") & (pl.col("year") == 2025))[
        "count"
    ].sum()
    assert wells_2025 == 1


# --- hashing / manifest -----------------------------------------------------


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    payload = b"resolve-cfpb-fixture"
    f = tmp_path / "blob.bin"
    f.write_bytes(payload)

    digest = cfpb_ingest.sha256_file(f)

    assert digest == hashlib.sha256(payload).hexdigest()
    assert cfpb_ingest.sha256_file(f) == digest  # stable


def test_write_manifest_writes_valid_json(tmp_path: Path) -> None:
    path = tmp_path / "manifests" / "cfpb.json"

    cfpb_ingest.write_manifest(path, source="CFPB", rows=8, sha256="abc")

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["source"] == "CFPB"
    assert loaded["rows"] == 8
    assert loaded["sha256"] == "abc"


# --- orchestrator (network seam monkeypatched) ------------------------------


def _fake_fetcher() -> object:
    """Return a drop-in for ``fetch_export_text`` backed by the fixture.

    It mimics the CFPB export's server-side ``company`` + date-window filtering:
    given a company string and a date range, it returns CSV text (original
    header) for the fixture rows matching that company and year range.
    """
    raw = pl.read_csv(FIXTURE, infer_schema_length=0)  # all columns as strings
    year = pl.col("Date received").str.slice(0, 4).cast(pl.Int64)

    def fetch(company: str, date_min: date, date_max: date, *, delay_s: float = 0.0) -> str:
        sub = raw.filter(
            (pl.col("Company") == company) & (year >= date_min.year) & (year <= date_max.year)
        )
        return sub.write_csv()

    return fetch


@pytest.fixture
def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> config.Settings:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    return config.Settings(
        data_dir=tmp_path / "data",
        cfpb_since_year=2015,
        cfpb_request_delay_s=0.0,
    )


def test_ingest_writes_parquet_and_manifest(
    monkeypatch: pytest.MonkeyPatch, _settings: config.Settings
) -> None:
    monkeypatch.setattr(cfpb_ingest, "fetch_export_text", _fake_fetcher())

    result = cfpb_ingest.ingest(_settings, refresh=True)

    assert result.rows == 8
    assert result.dropped_duplicates == 1
    assert result.output_path.exists()
    assert result.manifest_path.exists()

    out = pl.read_parquet(result.output_path)
    assert out.height == 8
    assert set(out["complaint_id"].to_list()) == {1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008}
    assert "bank" in out.columns

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["processed"]["rows"] == 8


def test_ingest_is_deterministic(
    monkeypatch: pytest.MonkeyPatch, _settings: config.Settings
) -> None:
    monkeypatch.setattr(cfpb_ingest, "fetch_export_text", _fake_fetcher())

    first = cfpb_ingest.ingest(_settings, refresh=True)
    sha_first = cfpb_ingest.sha256_file(first.output_path)

    second = cfpb_ingest.ingest(_settings, refresh=True)
    sha_second = cfpb_ingest.sha256_file(second.output_path)

    assert sha_first == sha_second  # same input -> identical processed parquet
