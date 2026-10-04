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
**Phase 2 — Ground truth and golden sets: COMPLETE.**
- Delivered: deterministic deadline calculator (`domain/deadlines.py`, Reg E/Z/X/V,
  100% on tests), `eval/metrics/` scoring (routing, spans, deadlines, retrieval,
  citations, abstention), golden sets `routing_test.jsonl` (3000) + `routing_pr.jsonl`
  (300) + `deadlines.jsonl` (400), `pii_reinsert.py`, `injection_suite.jsonl` (40),
  `docs/labelling_guide.md`. `make golden` rebuilds all sets reproducibly.
- Deferred (need synthesised narratives, ADR-014): full `pii_spans.jsonl` (500) and
  `e2e_tier_c.jsonl` (120 hand-labelled) + 30-item dev set — synthetic samples ship now.
- Next: Phase 3 — Retrieval (chunking, Qdrant hybrid index, point-in-time search, rerank).

## Phase 1 — Data foundation: COMPLETE.
- CFPB + eCFR + bank-doc ingestion, taxonomy + enums, synthetic accounts, Postgres
  load, `docs/data_card.md`. Snapshot: 787,717 complaints, 7,329 eCFR records.
