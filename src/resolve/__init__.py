"""RESOLVE — an evaluated, guarded, observable complaint-resolution agent.

The package is organised by responsibility; each subpackage owns one slice of
the system (see ``docs/PLAN.md`` Section 6 for the full map):

* :mod:`resolve.config` — environment-driven, validated settings.
* :mod:`resolve.logging` — structured (JSON) logging setup.
* ``resolve.data`` — ingestion of CFPB complaints, eCFR regulations, bank
  documents and synthetic accounts.
* ``resolve.retrieval`` — chunking, indexing and point-in-time hybrid search.
* ``resolve.domain`` — typed domain models, the taxonomy and the deterministic
  deadline calculator.
* ``resolve.agent`` — the LangGraph orchestration (single- and multi-agent).
* ``resolve.guardrails`` — PII masking, injection screening, citation and
  output-policy checks.
* ``resolve.security`` — authorisation and the hash-chained audit log.
* ``resolve.mcp_server`` — the MCP tool server.
* ``resolve.api`` — the FastAPI application.
* ``resolve.observability`` — tracing, cost and drift monitoring.
* ``resolve.baselines`` — the classical (TF-IDF + logistic regression) router.
"""

__version__ = "0.0.0"
