# FAILURES.md — observed failures and fixes

A running log of real failures seen while running RESOLVE on the dev set, per the
Phase 4 practice of reading every output. Newest first.

## F-003 (security) — API key leaked in an error URL · FIXED

**Seen:** the first live demo hit a Gemini `503`, and `httpx.raise_for_status()`
printed the full request URL — which included `?key=AIza...` — into the console.

**Root cause:** the gateway (and embedder) passed the API key as a `?key=` query
parameter, so it appeared in URLs and any error/trace that echoes the URL.

**Fix:** send the key via the `x-goog-api-key` **header** instead (both
`llm/gateway.py` and `retrieval/embeddings.py`); the gateway's retry helper raises a
sanitised `HTTP <status>` message that never includes the URL. Recommendation: rotate
the Gemini key as a precaution, since it was briefly displayed.

## F-002 — transient Gemini 503 aborted the run · FIXED

**Seen:** a one-off `503 Service Unavailable` from `generateContent` crashed the demo.

**Fix:** the gateway now retries transient `429/500/503` with exponential backoff
(5 attempts) before failing.

## F-001 — agent abstains on the Reg E provisional-credit demo · OPEN (retrieval)

**Seen:** for the synthetic "unauthorized debit, no provisional credit" complaint, the
agent routes correctly (deposits, confidence 0.95) and retrieves point-in-time Reg E
evidence, but the top-k is dominated by §1005.11 **interpretation comments**
(`1005.11-int...`) rather than the operative paragraph §1005.11(c). The drafter
therefore **abstains** — with valid citations and no fabricated rule — which is the
designed safe behaviour.

**Root cause:** sparse BM25 recall. The Phase 3 ablation already showed sparse is weak
on exactly this kind of query (multi-hop/operative-paragraph recall); interpretation
chunks share vocabulary with the query and outrank the rule text.

**Planned fix:** enable the dense/hybrid arm (ADR-002, currently quota-gated) which is
expected to surface §1005.11(c); and consider down-weighting interpretation-only
chunks in the drafter's evidence or raising `k`. Tracked, not a correctness bug — the
abstention is preferable to a hallucinated citation.
