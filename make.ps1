# RESOLVE developer commands for Windows PowerShell (a `make` shim).
# Usage:  ./make.ps1 <target>     e.g.  ./make.ps1 test
param(
    [Parameter(Position = 0)]
    [string]$Target = "help"
)

$ErrorActionPreference = "Stop"

switch ($Target) {
    "install"   { uv sync }
    "lint"      { uv run ruff check .; uv run ruff format --check .; uv run mypy }
    "format"    { uv run ruff format .; uv run ruff check --fix . }
    "typecheck" { uv run mypy }
    "test"      { uv run pytest }
    "data"      { uv run python -m resolve.data.cfpb_ingest; if ($?) { uv run python -m resolve.data.ecfr_ingest }; if ($?) { uv run python -m resolve.data.bank_docs_ingest } }
    "data-cfpb" { uv run python -m resolve.data.cfpb_ingest }
    "data-ecfr" { uv run python -m resolve.data.ecfr_ingest }
    "data-bankdocs" { uv run python -m resolve.data.bank_docs_ingest }
    "taxonomy-enums" { uv run python -m resolve.data.taxonomy --generate-enums }
    "data-complaints" { uv run python -m resolve.data.complaints_load --truncate }
    "data-accounts" { uv run python -m resolve.data.synth_accounts --truncate }
    # Accounts first: truncating accounts CASCADEs to complaints; loading complaints
    # afterwards leaves accounts intact, so both tables end up populated.
    "data-load" { uv run python -m resolve.data.synth_accounts --truncate; if ($?) { uv run python -m resolve.data.complaints_load --truncate } }
    "data-card" { uv run python -m resolve.data.data_card }
    "golden" {
        uv run python -m resolve.eval.golden.deadlines_gen
        if ($?) { uv run python -m resolve.eval.golden.routing_gen }
        if ($?) { uv run python -m resolve.data.pii_reinsert }
        if ($?) { uv run python -m resolve.eval.golden.injection_gen }
        if ($?) { uv run python -m resolve.eval.golden.tier_c_gen }
    }
    "golden-deadlines" { uv run python -m resolve.eval.golden.deadlines_gen }
    "golden-routing" { uv run python -m resolve.eval.golden.routing_gen }
    "golden-pii" { uv run python -m resolve.data.pii_reinsert }
    "golden-injection" { uv run python -m resolve.eval.golden.injection_gen }
    "golden-tierc" { uv run python -m resolve.eval.golden.tier_c_gen }
    "golden-retrieval" { uv run python -m resolve.eval.golden.retrieval_gen }
    "index" { uv run python -m resolve.retrieval.index }
    "index-sparse" { uv run python -m resolve.retrieval.index --no-dense }
    "retrieval-eval" { uv run python -m resolve.eval.runners.retrieval_eval }
    "retrieval-eval-dense" { uv run python -m resolve.eval.runners.retrieval_eval --with-dense }
    "up"        { docker compose -f docker/compose.yaml up -d }
    "down"      { docker compose -f docker/compose.yaml down }
    "ps"        { docker compose -f docker/compose.yaml ps }
    default {
        Write-Host "RESOLVE targets (Windows):"
        Write-Host "  install    Install project + dev dependencies (uv sync)"
        Write-Host "  lint       Ruff lint + format check + mypy"
        Write-Host "  format     Auto-format and auto-fix"
        Write-Host "  typecheck  Run mypy only"
        Write-Host "  test       Run the test suite"
        Write-Host "  data       Build all data sources (CFPB + eCFR + bank docs) + manifests"
        Write-Host "  data-cfpb  Ingest CFPB complaint metadata for the six banks"
        Write-Host "  data-ecfr  Ingest eCFR regulations (point-in-time, five rules)"
        Write-Host "  data-bankdocs   Ingest public bank documents (manifest + fee tables)"
        Write-Host "  taxonomy-enums  Regenerate taxonomy_enums.py from taxonomy_map.yaml"
        Write-Host "  data-complaints Load CFPB complaints into Postgres"
        Write-Host "  data-accounts   Generate synthetic accounts and load them into Postgres"
        Write-Host "  data-load       Load complaints + synthetic accounts into Postgres"
        Write-Host "  data-card       Generate docs/data_card.md from the ingested data"
        Write-Host "  golden          Rebuild all Phase 2 golden sets (deadlines, routing, pii, injection, tier-c)"
        Write-Host "  index-sparse    Index regulations into Qdrant (BM25 sparse; no embedding calls)"
        Write-Host "  index           Index regulations (dense + sparse; needs embedding quota)"
        Write-Host "  retrieval-eval  Run the retrieval ablation -> docs/retrieval_ablation.md"
        Write-Host "  up         Start the database stack (Postgres + Qdrant) via Docker"
        Write-Host "  down       Stop the database stack (keeps data)"
        Write-Host "  ps         Show database stack status"
        Write-Host ""
        Write-Host "Later phases (index/seed/eval-*) are available via the Makefile on Linux/CI."
    }
}
