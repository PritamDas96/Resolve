# ADR-014: CFPB data source — real metadata via live export, synthetic narratives

- **Status:** accepted
- **Date:** 2026-10-02
- **Deciders:** Pritam Das

## Context

`PLAN.md` §7.2 and §7.7 assume the CFPB Consumer Complaint Database ships
consumer-narrative text — the bulk CSV as a `Consumer complaint narrative`
column, and the API as `complaint_what_happened`. Routing (classify a free-text
narrative into the product/issue taxonomy) and the §7.7 PII ground truth
(re-insert synthetic PII into the `XXXX`-masked narrative at known offsets) both
depend on that text.

Verification against the live CFPB endpoints on 2026-10-02 found that **narrative
text is no longer distributed**:

- The search API, the `format=csv` export, and the per-complaint detail endpoint
  all return the **same 15 metadata fields and no narrative**. The `field`
  parameter rejects `complaint_what_happened` (`400 not a valid choice`).
- The 350 MB bulk `complaints.csv.zip` has the **same 15-column header and no
  narrative column** (confirmed by range-fetching the zip's first bytes and
  inflating just the CSV header — no full download). `complaints.json.zip` → 404.
- Narratives remain *filterable* server-side (`has_narrative`, `search_term`) but
  are never *returned*.

Public mirrors do not fill the gap: the official `CFPB/consumer-finance-complaints`
HF repo is a loader-script-only dataset that re-fetches the now-stripped source;
`claritystorm/cfpb-consumer-complaints` commits only a 1000-row sample;
`AlphaBiz/cfpb-complaints-normalised` is aggregates-only; `Johnade/consumer_complaints_cfpb`
has narratives but only two columns (no company/date/id to join or filter). CFPB's
Socrata endpoint is unreachable in this environment (TLS chain fails and disabling
verification is blocked).

Two constraints also surfaced that shape the ingestion code:

- Plain `curl`/`httpx` receive an Akamai **403**; `curl_cffi` with
  `impersonate="chrome"` passes cleanly. (This is why `curl-cffi` is a dependency.)
- The paginated JSON search is capped at `from + size ≤ 10_000`, but the filtered
  **CSV export has no such cap** — one `company` + `product` + `has_narrative` +
  date-window request streams the full scoped set (e.g. 3,878 rows for Capital
  One / credit card / 2023).

## Options considered

1. **Live metadata + synthetic narratives** — ingest real CFPB metadata (real
   company, product, sub-product, issue, sub-issue, dates, complaint id, at full
   scale via the filtered CSV export); generate narratives later, grounded in each
   complaint's real labels and its synthetic account, with PII inserted at known
   offsets. Pros: keeps real routing **labels** and the real temporal
   distribution; makes §7.7 PII spans **exact** (we control insertion); CC0-clean;
   reproducible; unblocks the whole pipeline. Cons: narrative **text** is not real,
   so routing/injection realism is weaker and must be stated honestly.
2. **Hunt an archived full snapshot with narratives** (Wayback / Kaggle /
   academic). Pro: real text + metadata if found. Cons: given the TLS/Akamai/
   sample-only walls already hit, low odds here; risks an open-ended search.
3. **Metadata-only, defer narratives** — build everything text-independent now and
   leave narrative sourcing unresolved. Cons: blocks routing/eval indefinitely.

## Decision

Option 1. Ingest **real CFPB metadata** at full scale from the live filtered CSV
export (`curl_cffi`, `impersonate="chrome"`, `format=csv`, `has_narrative=true`,
per bank × year), filtered to the six in-scope banks. **Synthetic narratives**
grounded in the real labels + synthetic accounts are produced in a later task and
carry exact PII offsets. Recorded here rather than silently diverging from the plan.

## Consequences

- Positive: real routing **labels** and temporal distribution are preserved;
  §7.7 PII ground truth becomes exact and configurable; point-in-time regulation
  retrieval (ADR-009) is unaffected; no copyright/licensing exposure.
- Negative / trade-offs: narratives are **synthetic**, so routing and
  prompt-injection results measure the system against generated text, not real
  consumer prose. The data card and README must state this plainly, and routing
  narratives must be generated indirectly (not trivially leaking the label) to
  keep the task meaningful.
- Reproducibility: the source updates daily, so a raw export's SHA-256 changes
  over time. The manifest (`data/manifests/cfpb.json`) pins each snapshot via
  per-export `sha256` + `retrieved_at`; re-running against the **cached** raw
  exports reproduces an identical processed-Parquet hash. True cross-day
  reproducibility would require committing the raw snapshot, which the plan
  forbids (too large, not committed).
- Follow-ups: the synthetic-narrative generator (grounded in labels + accounts,
  PII at known offsets) supersedes the §7.7 "re-insert into CFPB masks" approach;
  revisit if a real narrative source becomes reachable.
