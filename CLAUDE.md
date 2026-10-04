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
**Phase 11 — Proof & publication: COMPLETE → v1.0.** (Phase 10 Azure deploy skipped by choice.)
- Professional Streamlit review console (`make ui`): Demo mode (no quota/Qdrant) + Live mode.
- README results-first; `SYSTEM_CARD.md`, `THREAT_MODEL.md`, `docs/architecture.md` (Mermaid),
  `FAILURES.md` (5 real failures), `docs/runbook.md`, ADR-002/003/004/009/013-017.
- Phases 0-9 shipped (data, golden sets, retrieval, agent+API+gate, MCP/auth/RLS, multi-agent+HITL,
  security, observability). 230 tests pass.
- A detailed `TECHNICAL_GUIDE.md` exists **uncommitted** (personal study doc, gitignored intent).
- Carried gaps (quota/data): dense retrieval numbers, judged N=3/κ, Presidio NER, Langfuse,
  Locust run, Tier C 120 hand-labels (narratives, ADR-014).

## Phases 6-9 — MCP/auth/RLS, multi-agent+HITL, security, observability: COMPLETE → v0.2.
- Phase 6: `sql/002_rls.sql` queue-isolation RLS + `resolve_app` role; scoped JWTs
  (`security/auth.py`), RLS session (`security/rls.py`); 5 MCP tools (`mcp_server/`,
  mcp 2.x) enforce scope + RLS; `seed_users.py`; tool-selection baseline 0.875. Cross-queue
  isolation proven by an integration test.
- Phase 7: `agent/graph_multi.py` (LangGraph: router->parallel reg+account->draft->review
  interrupt; low-confidence abstains; evidence reducer); `limits.py`; `/v1/cases/multi` +
  `/v1/cases/{id}/decision` resume; MemorySaver (AsyncPostgresSaver = durability swap); ADR-004.
- Phase 8: hash-chained `audit_log` (`security/audit.py`, tamper-detected); rule-based PII
  masker (`security/pii.py`); output guardrails (`security/guardrails.py`); 80-item injection
  suite; `THREAT_MODEL.md` (OWASP LLM Top 10).
- Phase 9: `observability/drift.py` (PSI/MMD -> `docs/drift.md`; real finding across the CFPB
  taxonomy revisions); `observability/cost.py` (per-case USD); `docs/runbook.md`.
- 230 tests pass. Carried gaps (quota/data): dense retrieval, judged N=3/kappa, Presidio NER,
  Langfuse, Locust run, Tier C 120 hand-labels (narratives, ADR-014).
- Next: Phase 10 — Azure deployment (v0.3); Phase 11 — proof + publication (v1.0).

## Phases 4 & 5 — Agent, API, eval gate: COMPLETE → v0.1.
- Phase 4: LLM gateway (Gemini/Groq + FakeGateway, key via header, ADR-017); single
  agent (router→retrieve→draft→validate) with citation grounding + safe abstention;
  classical TF-IDF baseline (`docs/baseline_routing.md`); FastAPI (`/health /ready
  /v1/route /v1/cases`, request-id, problem+json); Docker (`docker/Dockerfile`, compose
  `app` profile). `make demo` drafts/abstains a cited letter end-to-end. `FAILURES.md` started.
- Phase 5: rubric judge (Groq family + FakeJudge); eval gate (`eval/runners/gate.py`)
  with baseline compare + `eval/reports/summary.*`, blocks on regression; CI workflow
  `eval-gate.yaml`; `make eval-pr/eval-full`. Gate: deadlines 1.0, pii 1.0, retrieval@5 0.78.
- Carried gaps: dense/hybrid retrieval + judged N=3/kappa need embedding/LLM quota; narratives (ADR-014).
- Next: Phase 6 — MCP server, auth, Postgres row-level security.

## Phase 3 — Retrieval: COMPLETE.
- Delivered: structure-aware chunking (`retrieval/chunking.py`), Qdrant index
  (dense+sparse, PIT ordinals, idempotent UUIDv5), point-in-time dense/sparse/hybrid-RRF
  search, SearchIntent + heuristic rewrite, lexical rerank + parent-child expansion,
  eCFR retrieval golden (20 queries) and an ablation (`docs/retrieval_ablation.md`).
  ADR-002/003/009.
- Env constraint (ADR-002): `fastembed`/`onnxruntime` segfault on Py3.13 Windows, so
  dense = Gemini embeddings API + pure-Python BM25 sparse. Free-tier embed quota is too
  small to vector the ~5.9k-chunk corpus, so the committed index/ablation use the
  **sparse** arm (`make index-sparse`); dense/hybrid run via `--with-dense` when quota allows.
- Sparse ablation: recall@5 0.78 (PIT on), lexical rerank lifts recall@1 0.42->0.55.
- Next: Phase 4 — baseline agent, classical router, API, Docker.

## Phase 2 — Ground truth and golden sets: COMPLETE.
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
