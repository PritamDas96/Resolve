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
    "data"      { uv run python -m resolve.data.cfpb_ingest }
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
        Write-Host "  data       Ingest CFPB complaint metadata for the six banks"
        Write-Host "  up         Start the database stack (Postgres + Qdrant) via Docker"
        Write-Host "  down       Stop the database stack (keeps data)"
        Write-Host "  ps         Show database stack status"
        Write-Host ""
        Write-Host "Later phases (index/seed/eval-*) are available via the Makefile on Linux/CI."
    }
}
