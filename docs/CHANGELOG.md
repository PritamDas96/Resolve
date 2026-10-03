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
- **eCFR ingestion** (`resolve.data.ecfr_ingest`, `make data-ecfr`): downloads
  point-in-time XML for the five in-scope regulations (Reg E/Z/X/DD/V in Title 12)
  at each part's real amendment dates, parses sections and their `(a)(1)(i)`
  paragraph hierarchy, links Supplement I official interpretations to the
  paragraphs they interpret, collapses identical text across snapshots into
  `valid_from`/`valid_to` ranges, and writes `regulations.jsonl` + a committed
  `ecfr.json` manifest. Validated end-to-end against the live API; fixture-based
  unit tests keep CI offline. `make data` now builds CFPB + eCFR.
- **ADR-015**: the eCFR API is not bot-walled (plain `httpx`), dates after the
  latest issue date 404 (so snapshots are driven by the per-part `versions`
  endpoint, no synthetic "today"), and point-in-time history begins ~2017.
- **Taxonomy normalisation** (`resolve.data.taxonomy`, `taxonomy_map.yaml`):
  maps every observed CFPB `product` string (all eras) to one of four stable,
  regulation-aligned families (deposits/cards/mortgage/credit_reporting) and
  normalises legacy `issue` strings to the current CFPB vocabulary, with anything
  unmappable marked `UNMAPPED`. Generates `taxonomy_enums.py` (`Family`, `Issue`,
  `FAMILY_ISSUES`) for structured-output grounding, kept in sync by a test. Map
  built from the live CFPB aggregations API, not from memory.
- **ADR-016**: CFPB revised the product taxonomy twice (2017 consolidation, ~2023
  split/rename), so the canonical scheme is stable regulation-aligned families
  rather than CFPB's shifting product strings.

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
