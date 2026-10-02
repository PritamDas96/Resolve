# Changelog

All notable changes are recorded here, newest first. The project follows a
phase-by-phase plan (see `docs/PLAN.md`).

## [Unreleased]

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
