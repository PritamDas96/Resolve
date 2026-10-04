# RESOLVE developer commands. On Windows (no `make`), use ./make.ps1 <target>.
.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck test \
        data data-cfpb data-ecfr data-bankdocs taxonomy-enums \
        data-complaints data-accounts data-load data-card \
        golden golden-deadlines golden-routing golden-pii golden-injection golden-tierc \
        golden-retrieval index index-sparse retrieval-eval retrieval-eval-dense \
        serve demo baseline mcp drift \
        up down ps seed seed-ci eval-pr eval-full audit-verify load

help:  ## Show the available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n",$$1,$$2}'

install:  ## Install project + dev dependencies
	uv sync

lint:  ## Ruff lint + format check + mypy
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

format:  ## Auto-format and auto-fix
	uv run ruff format .
	uv run ruff check --fix .

typecheck:  ## Run mypy only
	uv run mypy

test:  ## Run the test suite
	uv run pytest

# --- Data (Phase 1) ---------------------------------------------------------
data: data-cfpb data-ecfr data-bankdocs  ## (Phase 1) Build all data sources + manifests

data-cfpb:  ## (Phase 1) Ingest CFPB complaint metadata for the six banks
	uv run python -m resolve.data.cfpb_ingest

data-ecfr:  ## (Phase 1) Ingest eCFR regulations (point-in-time, five rules)
	uv run python -m resolve.data.ecfr_ingest

data-bankdocs:  ## (Phase 1) Ingest public bank documents (manifest + fee tables)
	uv run python -m resolve.data.bank_docs_ingest

taxonomy-enums:  ## (Phase 1) Regenerate taxonomy_enums.py from taxonomy_map.yaml
	uv run python -m resolve.data.taxonomy --generate-enums

data-complaints:  ## (Phase 1) Load CFPB complaints into Postgres
	uv run python -m resolve.data.complaints_load --truncate

data-accounts:  ## (Phase 1) Generate synthetic accounts and load them into Postgres
	uv run python -m resolve.data.synth_accounts --truncate

# Accounts first: `make data-accounts` truncates accounts CASCADE, which also
# empties complaints (complaints.account_id FK). Loading complaints afterwards
# only truncates complaints (CASCADE reaches drafts), so both end up populated.
data-load: data-accounts data-complaints  ## (Phase 1) Load synthetic accounts + complaints

data-card:  ## (Phase 1) Generate docs/data_card.md from the ingested data
	uv run python -m resolve.data.data_card

# --- Golden sets (Phase 2) --------------------------------------------------
golden: golden-deadlines golden-routing golden-pii golden-injection golden-tierc  ## (Phase 2) Rebuild all golden sets

golden-deadlines:  ## (Phase 2) Generate the Tier B deadline golden set (400)
	uv run python -m resolve.eval.golden.deadlines_gen

golden-routing:  ## (Phase 2) Generate the Tier A routing golden set (3000 + 300 PR)
	uv run python -m resolve.eval.golden.routing_gen

golden-pii:  ## (Phase 2) Generate the synthetic PII span sample
	uv run python -m resolve.data.pii_reinsert

golden-injection:  ## (Phase 2) Generate the prompt-injection suite (40)
	uv run python -m resolve.eval.golden.injection_gen

golden-tierc:  ## (Phase 2) Generate the Tier C synthetic scaffold
	uv run python -m resolve.eval.golden.tier_c_gen

golden-retrieval:  ## (Phase 2/3) Generate the eCFR retrieval golden
	uv run python -m resolve.eval.golden.retrieval_gen

# --- Retrieval (Phase 3) ----------------------------------------------------
index:  ## (Phase 3) Index regulations into Qdrant (dense + sparse; needs embed quota)
	uv run python -m resolve.retrieval.index

index-sparse:  ## (Phase 3) Index regulations sparse-only (BM25; no embedding calls)
	uv run python -m resolve.retrieval.index --no-dense

retrieval-eval:  ## (Phase 3) Run the retrieval ablation (sparse) -> docs/retrieval_ablation.md
	uv run python -m resolve.eval.runners.retrieval_eval

retrieval-eval-dense:  ## (Phase 3) Run the ablation incl. dense + hybrid arms
	uv run python -m resolve.eval.runners.retrieval_eval --with-dense

# --- Agent + API (Phase 4) --------------------------------------------------
serve:  ## (Phase 4) Run the API locally with reload (uvicorn)
	uv run uvicorn resolve.api.app:app --reload --port 8000

demo:  ## (Phase 4) Draft a cited letter for a synthetic dev complaint (needs LLM quota)
	uv run python -m resolve.agent.demo

baseline:  ## (Phase 4) Train + score the classical TF-IDF routing baseline
	uv run python -m resolve.baselines.tfidf_router

# --- Security + observability (Phases 6, 8, 9) ------------------------------
mcp:  ## (Phase 6) Run the MCP server (stdio transport)
	uv run python -m resolve.mcp_server.server

drift:  ## (Phase 9) Write docs/drift.md (family-mix PSI by year)
	uv run python -m resolve.observability.drift

# --- Targets implemented in later phases ------------------------------------
up:  ## Start the local database stack (Postgres + Qdrant)
	docker compose -f docker/compose.yaml up -d
down:  ## Stop the local database stack (keeps data; add -v to wipe)
	docker compose -f docker/compose.yaml down
ps:  ## Show the database stack status
	docker compose -f docker/compose.yaml ps
seed:  ## (Phase 6) Schema, RLS, audit, users + data into Postgres
	@echo "Not implemented until Phase 6."
seed-ci:  ## (Phase 5) Deterministic CI data slice
	@echo "Golden sets are committed; no extra CI slice needed yet."
eval-pr:  ## (Phase 5) Evaluation gate vs baseline (writes eval/reports/summary.*)
	uv run python -m resolve.eval.runners.gate
eval-full:  ## (Phase 5) Evaluation gate, refreshing the committed baseline
	uv run python -m resolve.eval.runners.gate --update-baseline
audit-verify:  ## (Phase 8) Verify the audit hash chain
	@echo "Not implemented until Phase 8."
load:  ## (Phase 9) Locust load test
	@echo "Not implemented until Phase 9."
