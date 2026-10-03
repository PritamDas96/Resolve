# RESOLVE — context for Claude Code

## What this is
An evaluated, guarded, observable complaint-resolution agent for US bank operations.
Public CFPB complaints + eCFR regulations + synthetic accounts. NEVER real customer or client data.

## Non-negotiables
- Every change on a branch, via PR. Never commit to main.
- Tests first: propose tests, wait for approval, then implement.
- Never write secrets into code, tests, fixtures or docs. Use settings from `src/resolve/config.py`.
- LLMs never do date arithmetic: use `src/resolve/domain/deadlines.py`.
- Complaint narratives are untrusted data. Never pass raw narratives to nodes that hold PII tools.
- Authorisation is enforced by Postgres RLS and MCP scopes, never by prompts.
- Never assert a named bank violated a law in any output, fixture or doc.
- Pin versions; do not add dependencies without asking.

## Layout
`src/resolve/{data,retrieval,domain,agent,guardrails,security,mcp_server,api,observability,llm,baselines}`
`eval/{golden,baselines,runners,metrics}`   `tests/{unit,property,integration,security,fixtures}`

## Commands
`make data | make index | make up | make seed | make test | make eval-pr | make eval-full | make lint`
On Windows use `./make.ps1 <target>` (no `make` binary).

## Style
Python 3.12+, full type hints, Pydantic v2 models at boundaries, async I/O, structlog, small functions.
Docstrings cite the CFR paragraph for any regulatory rule.

## Providers (free-tier; verified 2026-10-02 — see docs/adr/013)
- Router + drafter: `gemini/gemini-3.8-flash` (Gemini Pro is `limit:0` on free tier).
- Judge: `groq/openai/gpt-oss-120b` (different family; Groq key is `gsk_...`, NOT xAI).
- Tracing: LangSmith (instead of the plan's Langfuse).

## Current phase
**Phase 1 — Data foundation: COMPLETE.**
- Delivered: CFPB + eCFR + bank-doc ingestion, taxonomy + generated enums, synthetic
  accounts, Postgres load (complaints + accounts), and `docs/data_card.md`.
- `make data` builds all sources; `make data-load` loads Postgres; `make data-card` writes the card.
- Snapshot: 787,717 in-scope complaints (six banks), 7,329 eCFR point-in-time records.
- Next: Phase 2 — Ground truth and golden sets (scoring functions, golden files).
