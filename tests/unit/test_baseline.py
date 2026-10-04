"""Unit tests for the classical TF-IDF routing baseline (offline, synthetic)."""

from __future__ import annotations

import polars as pl

from resolve.baselines import tfidf_router as tr


def test_evaluate_level_learns_separable_classes() -> None:
    train_text = [
        "card fees problem",
        "card fees issue",
        "mortgage payment trouble",
        "mortgage payment late",
    ]
    train_y = ["cards", "cards", "mortgage", "mortgage"]
    score = tr.evaluate_level(
        "family", train_text, train_y, ["card fees", "mortgage payment"], ["cards", "mortgage"]
    )
    assert score.level == "family"
    assert 0.0 <= score.accuracy <= 1.0
    assert score.accuracy == 1.0  # trivially separable
    assert score.n_classes == 2


def test_build_dataset_maps_and_splits() -> None:
    df = pl.DataFrame(
        {
            "product": ["Credit card", "Mortgage", "Credit card"],
            "sub_product": [
                "General-purpose credit card",
                "Conventional home mortgage",
                "Store card",
            ],
            "issue": ["Fees or interest", "Trouble during payment process", "Fees or interest"],
            "sub_issue": ["Annual fee", "Trouble paying", "Late fee"],
            "split": ["train", "train", "test"],
        }
    )
    data = tr.build_dataset(df)
    assert data.train_family == ["cards", "mortgage"]
    assert data.test_family == ["cards"]
    assert all(isinstance(t, str) and t for t in data.train_text)
    assert data.train_issue == ["Fees or interest", "Trouble during payment process"]
