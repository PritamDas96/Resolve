# ADR-016: canonical taxonomy = stable regulation-aligned families

- **Status:** accepted
- **Date:** 2026-10-03
- **Deciders:** Pritam Das

## Context

`PLAN.md` §7.3 calls for normalising the CFPB product/issue taxonomy so labels are
comparable across years, and specifies mapping legacy labels to the **current CFPB
product strings** (e.g. pre-2017 `Bank account or service` → `Checking or savings
account`). The implicit assumption is that there is a single, stable "current"
CFPB product vocabulary to normalise toward.

Verification against the live CFPB aggregations API on 2026-10-03 (counts by
product/issue across the pre-2017, 2018–2022 and 2024–2026 windows) showed the
product taxonomy has changed **twice**, not once:

- **2017 consolidation:** `Bank account or service` → `Checking or savings
  account`; `Credit card` + `Prepaid card` → the combined `Credit card or prepaid
  card`; the credit-reporting products were merged.
- **~2023 revision:** `Credit card or prepaid card` was **split back** into
  separate `Credit card` and `Prepaid card` products, and the credit-reporting
  product was renamed again to `Credit reporting or other personal consumer
  reports`.

So "the current CFPB product string" is a moving target, and the 2017–2022
combined `Credit card or prepaid card` cannot be cleanly split back into the two
current products without guessing from sub-product — mapping *to current strings*
would strand a whole era of data as `UNMAPPED`.

## Decision

Normalise the **product** dimension to four stable, regulation-aligned
**families**, not to CFPB's shifting product strings:

| Family | Regulation | CFPB product strings (all eras) |
|---|---|---|
| `deposits` | Reg E / Reg DD | Checking or savings account; Bank account or service |
| `cards` | Reg Z | Credit card; Prepaid card; Credit card or prepaid card |
| `mortgage` | Reg X | Mortgage |
| `credit_reporting` | Reg V | Credit reporting or other personal consumer reports; Credit reporting, credit repair services, …; Credit reporting |

Families are stable across both revisions, align with the regulation each queue is
governed by, and match the authorisation/queue model (§13.6, where `queue =
product family`). The **issue** dimension is normalised to the current CFPB issue
vocabulary per family (the authority for valid `family → issue` paths); legacy
issue strings are mapped via a conservative, data-derived crosswalk, and anything
ambiguous is left `UNMAPPED` (excluded from routing metrics, counted in the data
card). Sub-product normalisation is deferred.

The curated map lives in `data/taxonomy_map.yaml` (built from the observed API
counts, committed, human-verified). `resolve.data.taxonomy` loads it and exposes
`normalize_product` / `normalize_issue` / `is_valid_path` / `normalize_frame`.
`resolve.data.taxonomy_enums` (`Family`, `Issue`, `FAMILY_ISSUES`) is **generated**
from the map so structured outputs are constrained to valid values; a test asserts
the generated module stays in sync with the map.

## Consequences

- **Positive:** one stable routing/queue target across all three taxonomy eras; no
  era stranded as `UNMAPPED` at the product level; the `family → issue` enum
  encodes valid paths for structured-output grounding; the canonical vocabulary is
  data-derived and reproducible, not assumed.
- **Negative / trade-offs:**
  - Product routing is a 4-class problem; finer product granularity (e.g.
    distinguishing credit vs prepaid card) must come from the sub-product
    dimension, which is deferred.
  - The legacy **issue** crosswalk is conservative and therefore incomplete —
    pre-2017 granular card issues in particular are mostly left `UNMAPPED`. This
    affects only the (older) train split; the 2025+ routing golden set uses current
    issues, which map by identity. Counted in the data card.
- **Divergence from plan:** supersedes §7.3's "map to current CFPB product string";
  recorded here rather than silently diverging.
