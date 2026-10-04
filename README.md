# RESOLVE

**An evaluated, guarded, observable complaint-resolution agent for US bank operations.**

RESOLVE takes a consumer complaint about a large US bank, routes it to the right
product and issue, retrieves the federal regulation that governed it *on the
complaint date*, checks a synthetic account record, computes the regulatory
deadlines, and drafts a response letter in which every claim cites a regulation
section or an account record. **A human must approve every letter. Nothing is
ever sent automatically.**

Only public or synthetic data is used — CFPB complaints, eCFR regulations, banks'
public documents and synthetic account records. **No real customer or client
data, ever.**

---

## Headline results

Measured against committed ground truth. Some cells need embedding/LLM quota (noted);
see the linked reports for method.

| Capability | Metric | Result | Source |
|---|---|---|---|
| Deadline calculator | exact match | **100%** | `tests/unit/test_deadlines.py` |
| Retrieval (sparse, PIT on) | recall@5 | **0.78** | [`docs/retrieval_ablation.md`](docs/retrieval_ablation.md) |
| Retrieval reranking | recall@1 | **0.42 → 0.55** (lexical) | [`docs/retrieval_ablation.md`](docs/retrieval_ablation.md) |
| Classical routing baseline | accuracy / macro-F1 | reported | [`docs/baseline_routing.md`](docs/baseline_routing.md) |
| Cross-queue isolation (RLS) | enforced | **PASS** | `tests/integration/test_rls_db.py` |
| Audit tamper detection | detects altered row | **PASS** | `tests/integration/test_audit_db.py` |
| Prompt-injection suite | authored attacks | **80** (5 categories) | `eval/golden/injection_suite.jsonl` |
| Data drift (family mix) | PSI by year | significant 2012–17 vs 2023 | [`docs/drift.md`](docs/drift.md) |
| Dense/hybrid retrieval, judged N=3 + κ, injection ASR | — | *pending embedding/LLM quota* | ADR-002 |

Data snapshot: **787,717** in-scope complaints (six banks), **7,329** eCFR point-in-time
records. See [`docs/data_card.md`](docs/data_card.md).

---

## Status

**v0.2 — Phases 0–9 complete** (Phase 10 Azure deploy skipped by choice). Data
foundation, golden sets, retrieval, agent + API + eval gate, MCP/auth/RLS,
multi-agent + human-in-the-loop, security guardrails, and observability.

## Run it yourself

```bash
uv sync                      # 1. install (needs uv: https://docs.astral.sh/uv/)
./make.ps1 up                # 2. start Postgres + Qdrant (Docker Desktop must be running)
./make.ps1 index-sparse      # 3. build the regulation index (local, no API quota)
./make.ps1 ui                # 4. open the review console in your browser
```

The **review console** (Streamlit) has a **Demo mode** that works with no API quota or
even Qdrant — submit a complaint and watch it route → retrieve point-in-time regulation
→ draft a cited letter → show guardrails → human approve. **Live mode** uses the real
Gemini models (needs a key in `.env` and quota).

Prefer the API or a one-shot? `./make.ps1 serve` (FastAPI on :8000) or
`./make.ps1 demo` (one cited letter in the terminal).

### Developer commands

| Command | Does |
|---|---|
| `make test` / `make lint` | Test suite / ruff + mypy |
| `make data` · `make data-load` · `make index-sparse` | Build data, load Postgres, index Qdrant |
| `make golden` · `make eval-pr` | Rebuild golden sets · run the evaluation gate |
| `make ui` · `make serve` · `make demo` | Streamlit UI · FastAPI · terminal demo |
| `make drift` · `make baseline` · `make mcp` | Drift report · classical router · MCP server |

> On Windows, use `./make.ps1 <target>` (no `make` binary).

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — Mermaid diagrams of every flow.
- [`SYSTEM_CARD.md`](SYSTEM_CARD.md) · [`THREAT_MODEL.md`](THREAT_MODEL.md) · [`FAILURES.md`](FAILURES.md)
- [`docs/data_card.md`](docs/data_card.md) · [`docs/retrieval_ablation.md`](docs/retrieval_ablation.md) · [`docs/drift.md`](docs/drift.md)
- [`docs/adr/`](docs/adr/) — architecture decision records · [`CLAUDE.md`](CLAUDE.md) — working context.

## License

[MIT](LICENSE).
