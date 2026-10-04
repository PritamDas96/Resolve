# RESOLVE — System card

## What it is
An evaluated, guarded, observable agent that drafts **cited, point-in-time** responses
to US consumer banking complaints, grounded in public CFPB complaint metadata and eCFR
regulations, with synthetic account data. A portfolio project, **not** a compliance
system.

## Intended use
- Demonstrate a production-grade GenAI system: retrieval, routing, a multi-agent graph
  with human review, an automated evaluation gate, security guardrails, and observability.
- Draft a *suggested* response for a human reviewer to approve or edit — never auto-send.

## Out-of-scope use
- Real legal or compliance advice; automated decisions affecting real customers.
- Any use with **real** customer/PII data (the system uses synthetic PII only).
- Concluding that a named bank broke the law — explicitly prevented by an output guardrail.

## Data
- **CFPB complaints**: public, metadata-only (narratives are not distributed, ADR-014);
  787,717 in-scope rows, six banks. Consent-only, not a representative sample.
- **eCFR regulations**: public-domain, point-in-time snapshots (Reg E/Z/X/DD/V).
- **Accounts/transactions/disputes**: fully synthetic (Faker), internally consistent.
- Provenance (URLs, timestamps, SHA-256) committed in `data/manifests/`; see `docs/data_card.md`.

## Evaluation
- Deterministic gate (`make eval-pr`): deadline calculator 100%, PII offsets 100%,
  retrieval recall@5 ~0.78 (sparse); blocks merges on regression.
- Retrieval ablation (`docs/retrieval_ablation.md`), classical vs LLM routing
  (`docs/baseline_routing.md`), drift (`docs/drift.md`), rubric judge (`eval/judge.py`).

## Limitations (honest)
- **Dense/hybrid retrieval** and **judged N=3 / Cohen's κ** need embedding/LLM quota;
  the committed numbers use the sparse arm and deterministic metrics.
- **PII masking** is rule-based (no NER): PERSON/ADDRESS recall is low until Presidio is
  enabled (ADR-002).
- The agent often **abstains** on hard queries because sparse retrieval misses the
  operative paragraph — safe (no fabrication) but lower answer rate than hybrid would give.
- Durable multi-agent resume uses an in-memory checkpointer in the committed tests
  (`AsyncPostgresSaver` is the production swap).

## Risks and mitigations
- Prompt injection → router has no tools (trust boundary); 80-item injection suite.
- PII leakage → input masking + output PII scan + leak tests.
- Cross-queue access → Postgres row-level security (`sql/002_rls.sql`).
- Tampering → hash-chained audit log (`security/audit.py`).
See `THREAT_MODEL.md` for the full mapping to the OWASP LLM Top 10.
