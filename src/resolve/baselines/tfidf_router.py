"""Classical TF-IDF routing baseline (PLAN §9.10).

TF-IDF (word 1-2-grams) + logistic regression, one classifier per routing level
(family and canonical issue), trained on the **train** split and scored on the
**test** split (temporal, never random). It exists so the LLM router has a cheap,
deterministic yardstick — if the classical model matches it at a fraction of the cost,
that is a production decision worth stating.

.. note::
   CFPB no longer distributes narrative text (ADR-014), so the usual "narrative ->
   product" features are unavailable. This baseline uses the structured
   ``sub_product`` + ``sub_issue`` text as the input signal instead; the mechanics
   (vectoriser, per-level classifier, temporal split, macro-F1) are identical and
   transfer directly once synthetic narratives exist.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline

from resolve.config import Settings, get_settings
from resolve.data import taxonomy
from resolve.logging import configure_logging, get_logger

__all__ = ["Dataset", "LevelScore", "build_dataset", "evaluate_level", "main", "run"]

log = get_logger(__name__)

_REPORT_PATH = Path(__file__).resolve().parents[3] / "docs" / "baseline_routing.md"
_RANDOM_STATE = 0


@dataclass
class LevelScore:
    """Accuracy + macro-F1 for one routing level."""

    level: str
    accuracy: float
    macro_f1: float
    n_train: int
    n_test: int
    n_classes: int


@dataclass
class Dataset:
    """Train/test text + per-level labels (temporal split)."""

    train_text: list[str]
    test_text: list[str]
    train_family: list[str]
    test_family: list[str]
    train_issue: list[str]
    test_issue: list[str]


def _features(df: pl.DataFrame) -> pl.Series:
    """Build the input text from sub_product + sub_issue (narratives unavailable).

    The label fields themselves (``product``, ``issue``) are deliberately excluded to
    avoid predicting a label from itself; even so, these sub-category fields are
    taxonomy-derived, so the numbers are a pipeline demonstration, not a real
    narrative-routing benchmark (see the report caveat).
    """
    return df.select(
        (pl.col("sub_product").fill_null("") + " " + pl.col("sub_issue").fill_null("")).alias(
            "text"
        )
    )["text"]


def build_dataset(df: pl.DataFrame, *, tax: taxonomy.Taxonomy | None = None) -> Dataset:
    """Map to canonical family/issue, drop UNMAPPED, and split train vs test."""
    taxon = tax or taxonomy.load_taxonomy()
    labelled = taxonomy.normalize_frame(df, taxonomy=taxon).filter(
        (pl.col("family") != taxonomy.UNMAPPED) & (pl.col("canonical_issue") != taxonomy.UNMAPPED)
    )
    labelled = labelled.with_columns(_features(labelled).alias("text"))
    train = labelled.filter(pl.col("split") == "train")
    test = labelled.filter(pl.col("split") == "test")
    return Dataset(
        train_text=train["text"].to_list(),
        test_text=test["text"].to_list(),
        train_family=train["family"].to_list(),
        test_family=test["family"].to_list(),
        train_issue=train["canonical_issue"].to_list(),
        test_issue=test["canonical_issue"].to_list(),
    )


def _pipeline() -> Pipeline:
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=50_000)),
            ("clf", LogisticRegression(max_iter=1000, random_state=_RANDOM_STATE)),
        ]
    )


def evaluate_level(
    level: str,
    train_text: list[str],
    train_y: list[str],
    test_text: list[str],
    test_y: list[str],
) -> LevelScore:
    """Train a TF-IDF + logreg classifier for one level and score it on the test split."""
    model = _pipeline()
    model.fit(train_text, train_y)
    pred = model.predict(test_text)
    return LevelScore(
        level=level,
        accuracy=float(accuracy_score(test_y, pred)),
        macro_f1=float(f1_score(test_y, pred, average="macro", zero_division=0)),
        n_train=len(train_text),
        n_test=len(test_text),
        n_classes=len(set(train_y)),
    )


def _render(scores: list[LevelScore]) -> str:
    lines = [
        "# RESOLVE — Classical routing baseline",
        "",
        "TF-IDF (1-2-grams) + logistic regression per level, trained on the train split "
        "and scored on the test split (temporal). This is the cheap, deterministic "
        "yardstick for the LLM router (PLAN §9.10).",
        "",
        "> **Caveat.** Narratives are unavailable (ADR-014), so features are the "
        "structured `sub_product` + `sub_issue` text — themselves taxonomy-derived. These "
        "numbers therefore demonstrate the pipeline (vectoriser, per-level classifier, "
        "temporal split, macro-F1), **not** a real narrative→route benchmark; they will be "
        "re-run meaningfully once synthetic narratives exist. The LLM-router comparison "
        "column is pending LLM quota for a full golden-set run.",
        "",
        "| Level | Accuracy | Macro-F1 | classes | n train | n test |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {s.level} | {s.accuracy:.3f} | {s.macro_f1:.3f} | {s.n_classes} | "
        f"{s.n_train:,} | {s.n_test:,} |"
        for s in scores
    ]
    lines.append("")
    return "\n".join(lines)


def run(settings: Settings | None = None, *, write: bool = True) -> list[LevelScore]:
    """Train + score both routing levels on the real complaints; write the report."""
    settings = settings or get_settings()
    df = pl.read_parquet(Path(settings.data_dir) / "processed" / "complaints.parquet")
    data = build_dataset(df)
    scores = [
        evaluate_level(
            "family", data.train_text, data.train_family, data.test_text, data.test_family
        ),
        evaluate_level("issue", data.train_text, data.train_issue, data.test_text, data.test_issue),
    ]
    if write:
        _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _REPORT_PATH.write_text(_render(scores), encoding="utf-8")
    return scores


def main() -> int:
    """CLI entry point: ``python -m resolve.baselines.tfidf_router``."""
    configure_logging()
    scores = run()
    for score in scores:
        log.info(
            "baseline_level",
            level=score.level,
            accuracy=round(score.accuracy, 3),
            macro_f1=round(score.macro_f1, 3),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
