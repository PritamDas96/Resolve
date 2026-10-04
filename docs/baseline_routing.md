# RESOLVE — Classical routing baseline

TF-IDF (1-2-grams) + logistic regression per level, trained on the train split and scored on the test split (temporal). This is the cheap, deterministic yardstick for the LLM router (PLAN §9.10).

> **Caveat.** Narratives are unavailable (ADR-014), so features are the structured `sub_product` + `sub_issue` text — themselves taxonomy-derived. These numbers therefore demonstrate the pipeline (vectoriser, per-level classifier, temporal split, macro-F1), **not** a real narrative→route benchmark; they will be re-run meaningfully once synthetic narratives exist. The LLM-router comparison column is pending LLM quota for a full golden-set run.

| Level | Accuracy | Macro-F1 | classes | n train | n test |
| --- | --- | --- | --- | --- | --- |
| family | 0.999 | 0.999 | 4 | 441,742 | 190,714 |
| issue | 1.000 | 0.991 | 32 | 441,742 | 190,714 |
