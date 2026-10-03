# ADR-015: eCFR regulation ingestion — versions-driven point-in-time snapshots

- **Status:** accepted
- **Date:** 2026-10-03
- **Deciders:** Pritam Das

## Context

`PLAN.md` §7.4 specifies ingesting the five CFPB-administered regulations (Reg E
= 12 CFR 1005, Reg Z = 1026, Reg X = 1024, Reg DD = 1030, Reg V = 1022),
including Supplement I official interpretations, as **point-in-time** records so a
complaint can be answered with the regulation as it stood on the complaint date.
The plan assumed two things about the eCFR versioner API that were worth
verifying before writing the ingestion code, given that the CFPB assumptions
turned out to be wrong (ADR-014).

Verification against the live eCFR API on 2026-10-03 found:

1. **The API is not bot-walled.** Unlike the CFPB endpoint (Akamai 403 → required
   `curl_cffi` browser impersonation), the eCFR versioner answers plain `httpx`
   requests. No impersonation dependency is needed here.
2. **Invalid issue dates are not 404'd — with one exception.** A date *within* the
   available range that is not itself an issue date (e.g. `2023-01-02`) is served
   as-of the nearest prior version (HTTP 200). But a date *after* the title's
   latest issue date (e.g. "today", when the latest issue is a few days earlier)
   returns **404**. So the plan's "fetch every change date plus today" would fail
   on the "today" fetch.
3. **Point-in-time history begins ~2017-01-01.** The per-part `versions` endpoint
   returns no content versions before 2017, so complaints from 2012–2016 can only
   be matched against the earliest available (2017) snapshot.
4. **XML shape.** `full/{date}/title-12.xml?part={part}` returns the part as a
   `DIV5` *root* element (`DIV6`=subpart, `DIV8`=section, `DIV9`=appendix;
   Supplement I is the `DIV9` named `"Supplement I to Part {part}"`). Paragraphs
   are flat `<P>` elements whose hierarchy (`(a)(1)(i)`) is encoded in **inline
   text markers**, not attributes — including a "run-in" first paragraph that
   introduces two levels at once: `(a) <I>Heading</I>—(1) <I>Heading</I> text`.
   This is the fiddly parsing risk flagged as R2 in the plan.

## Decision

Ingest each in-scope part at **exactly the issue dates returned by the per-part
`versions` endpoint** (filtered to ≥ 2017), never by probing arbitrary dates and
never adding a synthetic "today" snapshot. The latest version date already carries
the current text (nothing has changed since), so its records are left open-ended
(`valid_to = null`); historical records get a closed `valid_from`/`valid_to`
range. Fetch with plain `httpx`; cache every snapshot to disk (historical
snapshots never change). Parse sections and Supplement I interpretations, collapse
identical text across adjacent snapshots into validity ranges, and write
`regulations.jsonl` plus a committed `data/manifests/ecfr.json` manifest.

Paragraph paths are reconstructed with a type-aware marker stack that captures
both the leading marker and run-in markers after an em/en dash, and that
disambiguates single-letter roman numerals (`(i)`/`(v)`/`(x)`) from lower-alpha
enumerators by context. Supplement I comments are linked to the paragraph they
interpret by combining the known part number with the leading number of the
nearest interpretation heading (e.g. heading `17(k)(5)` under part `1024` →
`interprets = "1024.17(k)(5)"`), which is robust to non-section `HD1` headings.

## Consequences

- **Positive:** real, reproducible, public-domain (17 U.S.C. §105) regulation
  text with exact point-in-time validity ranges; a simple
  `valid_from <= date <= valid_to` filter answers "the rule as of the complaint
  date"; Supplement I interpretations are linked to their paragraphs for
  parent–child retrieval expansion (PLAN §8.6). Validated end-to-end against the
  live API across all five parts (0 mislinked interpretations).
- **Negative / limitations:**
  - **Pre-2017 complaints** resolve to the 2017 snapshot, not the text truly in
    force on the complaint date. Stated in the data card.
  - **Paragraph-path reconstruction** is correct for the common 4-level cycle but
    has a small tail (≈0.5% of section paragraphs on Reg E) where a genuine 9th
    lower-alpha enumerator `(i)` or a deep re-descent into a repeated marker type
    is mislabelled. Supplement I linking is unaffected. Acceptable for retrieval;
    revisit if citation precision requires it.
- **Reproducibility:** the manifest pins each snapshot date and the processed
  `regulations.jsonl` SHA-256; re-running against the cached raw snapshots
  reproduces an identical processed hash. Raw XML and the processed JSONL are
  git-ignored; the manifest is committed.
- **Divergence from plan:** supersedes §7.4's "plus today" and its implicit
  "404 on invalid dates" assumption; recorded here rather than silently diverging.
