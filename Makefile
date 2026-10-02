# RESOLVE developer commands. On Windows (no `make`), use ./make.ps1 <target>.
.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck test \
        data index up down seed seed-ci eval-pr eval-full audit-verify load

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

# --- Targets implemented in later phases ------------------------------------
data:  ## (Phase 1) Build all data + manifests
	@echo "Not implemented until Phase 1."
index:  ## (Phase 3) Build/refresh Qdrant collections
	@echo "Not implemented until Phase 3."
up:  ## (Phase 1) Start the docker-compose stack
	@echo "Not implemented until Phase 1."
down:  ## (Phase 1) Stop the docker-compose stack
	@echo "Not implemented until Phase 1."
seed:  ## (Phase 6) Schema, RLS, audit, users + data into Postgres
	@echo "Not implemented until Phase 6."
seed-ci:  ## (Phase 5) Deterministic CI data slice
	@echo "Not implemented until Phase 5."
eval-pr:  ## (Phase 5) PR-subset evaluation vs baseline
	@echo "Not implemented until Phase 5."
eval-full:  ## (Phase 5) Full evaluation + drift + cost reports
	@echo "Not implemented until Phase 5."
audit-verify:  ## (Phase 8) Verify the audit hash chain
	@echo "Not implemented until Phase 8."
load:  ## (Phase 9) Locust load test
	@echo "Not implemented until Phase 9."
