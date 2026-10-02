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

> This table is the product; the agent is the vehicle. Numbers are filled in as
> each configuration is built and evaluated against ground truth.

| Configuration | Routing macro-F1 | Retrieval recall@5 | Faithfulness | Abstention F1 | Injection ASR | PII recall | p95 latency | Cost / complaint |
|---|---|---|---|---|---|---|---|---|
| Classical baseline (TF-IDF + LR) | — | — | — | — | — | — | — | — |
| Single agent, dense retrieval | — | — | — | — | — | — | — | — |
| + hybrid search | — | — | — | — | — | — | — | — |
| + reranker | — | — | — | — | — | — | — | — |
| + multi-agent (trust-boundary split) | — | — | — | — | — | — | — | — |
| + guardrails + PII masking | — | — | — | — | — | — | — | — |
| + model routing + caching | — | — | — | — | — | — | — | — |

---

## Status

**Phase 0 — Setup and hygiene.** Repository scaffolding, configuration, logging,
quality toolchain and CI. See [`docs/CHANGELOG.md`](docs/CHANGELOG.md) for
progress and [`docs/PLAN.md`](docs/PLAN.md) for the full build plan.

## Quick start

```bash
# 1. Install uv (https://docs.astral.sh/uv/), then install the project:
uv sync

# 2. Copy the environment template and fill in your keys (never commit .env):
cp .env.example .env

# 3. Run the checks:
make test        # or, on Windows:  ./make.ps1 test
make lint        # ruff + mypy
```

### Developer commands

| Command | Does |
|---|---|
| `make install` | Install project + dev dependencies (`uv sync`) |
| `make lint` | Ruff lint, format check, and mypy |
| `make format` | Auto-format and auto-fix |
| `make test` | Run the test suite |

> On Windows, `make` is not installed by default — use the equivalent
> `./make.ps1 <target>` shim, or call `uv run pytest` / `uv run ruff check .`
> directly.

## Documentation

- [`docs/PLAN.md`](docs/PLAN.md) — the full, phase-by-phase project plan.
- [`docs/adr/`](docs/adr/) — architecture decision records.
- [`CLAUDE.md`](CLAUDE.md) — working context and non-negotiables.

## License

[MIT](LICENSE).
