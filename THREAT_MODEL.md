# RESOLVE — Threat model

Scope: the complaint-resolution agent, its tools, data stores and API. All customer
data is synthetic; the system never asserts a named bank broke the law. This maps the
main threats to the defences built in Phases 6–8 and to the OWASP LLM Top 10.

## Trust boundaries

| Boundary | Untrusted input | Defence |
|---|---|---|
| B1: API request → service | Client JSON, JWT | Pydantic validation; scoped JWT verified (`security/auth.py`); problem+json errors |
| B2: Complaint narrative → models | Text written by strangers | PII masked before any model sees it (`security/pii.py`); injection screened; narrative wrapped as **data** in prompts; the router that reads it holds **no tools** |
| B3: Agent → account data | Tool arguments | Postgres **row-level security** by queue (`sql/002_rls.sql`); coarse **scopes**; not-found == not-permitted |
| B4: Agent → outbound letter | Drafter output | Output policy guardrail (no legal accusation) + output PII scan (`security/guardrails.py`); citations validated against evidence |
| B5: Actions → audit | — | Append-only, hash-chained `audit_log` (`security/audit.py`) |

## Key threats and mitigations

- **Prompt injection (direct & indirect).** The only component reading the untrusted
  narrative (router) has no tools, so an injected instruction has no path to a
  privileged action (ADR-004). Measured by the 80-item `injection_suite.jsonl` (ASR
  per category; before/after defences).
- **PII leakage.** Masking before model input; an output PII scan; a leak test that
  no known synthetic secret appears in any output/log/trace.
- **Confused deputy / cross-queue access.** RLS keys every queue-scoped row to the
  acting user's queues; proven by `test_rls_db` (deposits analyst cannot read a cards
  account). Authorisation is in the database, never the prompt.
- **Privilege escalation / unsafe actions.** The drafting agent cannot send letters,
  move money, change case status, or grant roles; such requests are refused
  (injection suite `privilege_escalation`).
- **Tampering with the record.** The audit log is hash-chained; `verify_chain`
  detects any altered or deleted past row (`test_audit_db`).
- **Over-reliance / hallucinated citations.** Every factual sentence must cite
  evidence that exists for the case; unsupported claims fail validation and the agent
  abstains rather than fabricate.

## OWASP LLM Top 10 mapping

| OWASP | Where addressed |
|---|---|
| LLM01 Prompt Injection | Trust boundary (router has no tools); injection suite; input screening |
| LLM02 Insecure Output Handling | Output policy + PII scan; citations validated |
| LLM03 Training-data poisoning | N/A (no training); data provenance in manifests |
| LLM04 Model DoS | Stopping conditions (`limits.py`); request timeouts |
| LLM06 Sensitive Info Disclosure | PII masking, RLS, output scan, leak tests |
| LLM07 Insecure Plugin/Tool Design | MCP tools validate inputs, enforce scope + RLS |
| LLM08 Excessive Agency | Least privilege; no send/pay/close; human-in-the-loop review |
| LLM09 Overreliance | Abstention; citation grounding; eval gate |
| LLM10 Model Theft | N/A (hosted models); keys via headers/secrets, not URLs (FAILURES F-003) |

## Honest limitations

- A hash chain proves integrity/ordering but does not stop an attacker who can rewrite
  every subsequent hash; a real deployment would also ship the head hash off-box.
- The rule-based PII masker lacks NER, so PERSON/ADDRESS recall is low until Presidio
  is enabled (ADR-002).
- Injection ASR and PII precision/recall tables are produced by the harness; the full
  numeric run needs LLM/embedding quota.
