# Changelog

All notable changes are recorded here, newest first. The project follows a
phase-by-phase plan (see `docs/PLAN.md`).

## [Unreleased]

### Phase 1 — Data foundation

- Added the Phase 1 data-ingestion dependency stack (polars, duckdb, pyarrow,
  httpx, curl-cffi, lxml, faker, sqlalchemy[asyncio]+asyncpg, pyyaml, tenacity).
- **CFPB ingestion** (`resolve.data.cfpb_ingest`, `make data`): downloads real
  complaint **metadata** for the six in-scope banks from the CFPB filtered CSV
  export (via `curl_cffi` browser impersonation — the endpoint is Akamai-walled),
  normalises to a canonical schema, derives the temporal split, deduplicates, and
  writes `complaints.parquet` + a committed `cfpb.json` manifest with per-export
  and processed SHA-256s. Fixture-based unit tests keep CI offline.
- **ADR-014**: CFPB no longer distributes consumer-narrative text (verified
  across the API, CSV export, bulk zip and four mirrors), so this extract is
  metadata-only and narratives are generated synthetically from the real labels
  in a later task.

### Phase 0 — Setup and hygiene

- Initialised the `uv` project with a `src/` layout and pinned, phase-scoped
  dependencies.
- Added configuration (`resolve.config`) and structured logging
  (`resolve.logging`), with unit tests.
- Created the full package skeleton under `src/resolve/` with documented
  subpackages.
- Added the quality toolchain: ruff (lint + format), mypy (strict), pytest,
  pre-commit (incl. gitleaks) and a GitHub Actions CI workflow.
- Recorded the free-tier provider decision in ADR-013.
