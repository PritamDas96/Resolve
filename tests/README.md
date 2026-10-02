# Tests

Test layers (see `docs/PLAN.md` Section 17):

- `unit/` — fast, isolated unit tests (no network, no DB).
- `property/` — Hypothesis property-based tests (e.g. the deadline calculator).
- `integration/` — tests that span the API, MCP server and data stores.
- `security/` — injection suite, PII leakage, authorisation / RLS tests.
- `fixtures/` — recorded LLM responses and shared test data.

Run everything with `make test` (or `uv run pytest`).
