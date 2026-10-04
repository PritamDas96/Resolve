# RESOLVE — Operations runbook

Practical steps for running, observing and recovering the system (PLAN §14.8).

## Start / stop

```bash
./make.ps1 up            # Postgres + Qdrant (docker compose)
./make.ps1 index-sparse  # build the regulations index (BM25; no API quota)
./make.ps1 data-load     # load complaints + synthetic accounts into Postgres
./make.ps1 serve         # run the API on :8000
./make.ps1 down          # stop the DB stack (keeps data)
```

Health: `GET /health` (liveness), `GET /ready` (checks Qdrant has the index).

## Day-to-day

| Task | Command |
|---|---|
| Draft a cited letter for a dev complaint | `./make.ps1 demo` |
| Run the eval gate (blocks on regression) | `./make.ps1 eval-pr` |
| Rebuild golden sets | `./make.ps1 golden` |
| Data-drift report | `./make.ps1 drift` → `docs/drift.md` |
| Classical routing baseline | `./make.ps1 baseline` |
| Mint demo JWTs (per role/queue) | `uv run python scripts/seed_users.py` |
| Verify the audit chain | `uv run python -c "import asyncio,asyncpg; from resolve.security.audit import verify_chain; from resolve.config import get_settings; print(asyncio.run((lambda: None)()))"` (see `security/audit.py`) |

## Common issues

- **`/ready` returns 503 "regulations collection empty"** → run `make index-sparse`.
- **Gemini 429 / quota exceeded** → embeddings/LLM free-tier quota is exhausted; the
  gateway retries transient 5xx but a hard quota needs a paid key. Sparse retrieval and
  all deterministic paths keep working.
- **`onnxruntime` segfault** → do not install `fastembed`; dense embeddings use the
  Gemini API instead (ADR-002).
- **A paused multi-agent case did not survive a restart** → the committed checkpointer
  is in-memory; configure `AsyncPostgresSaver` for durable resume (ADR-004).

## Incident response

- **Suspected tampering** → run `verify_chain`; it returns the first altered `seq`.
- **PII in an output/log** → the output guardrail (`security/guardrails.check_output`)
  should block it pre-send; treat any leak as a Sev-1, rotate affected secrets.
- **Leaked API key** (e.g. in a URL) → rotate immediately; keys are sent as headers,
  never URLs (FAILURES F-003).

## Rollback

- Code: revert the merge commit on `main`; CI (`ci.yaml`) + the eval gate
  (`eval-gate.yaml`) must pass before re-merge.
- Data/index: re-run `make data` / `make index-sparse`; manifests pin the source
  snapshot (identical hashes on re-run).
