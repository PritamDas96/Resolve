"""Offline unit tests for the retrieval building blocks (no Qdrant, no network)."""

from __future__ import annotations

import math
from datetime import date

from resolve.retrieval import embeddings as emb
from resolve.retrieval import index as idx
from resolve.retrieval import rewrite as rw
from resolve.retrieval import search as se
from resolve.retrieval.chunking import Chunk

# --- embeddings -------------------------------------------------------------


def test_tokenize_and_term_id_stable() -> None:
    assert emb.tokenize("Provisional CREDIT, 10 days!") == ["provisional", "credit", "10", "days"]
    assert emb.term_id("credit") == emb.term_id("credit")  # deterministic
    assert 0 <= emb.term_id("credit") < 2**32


def test_l2_normalise() -> None:
    v = emb.l2_normalise([3.0, 4.0])
    assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0)
    assert emb.l2_normalise([0.0, 0.0]) == [0.0, 0.0]  # all-zero unchanged


def test_bm25_encoder() -> None:
    enc = emb.BM25SparseEncoder()
    indices, values = enc.encode_document("credit credit days")
    by_term = dict(zip(indices, values, strict=True))
    assert by_term[emb.term_id("credit")] == 2.0  # term frequency
    assert by_term[emb.term_id("days")] == 1.0
    q_idx, q_val = enc.encode_query("credit credit days")
    assert set(q_val) == {1.0}  # query values are 1.0
    assert len(q_idx) == 2  # unique terms


# --- index ------------------------------------------------------------------


def _chunk() -> Chunk:
    return Chunk(
        chunk_id="1005.11(c)(1)@2023-01-01",
        regulation="Reg E",
        part="1005",
        section="1005.11",
        paragraph="(c)(1)",
        heading="Procedures",
        is_interpretation=False,
        interprets=None,
        valid_from=date(2023, 1, 1),
        valid_to=date(2024, 3, 15),
        text="Investigate promptly.",
        heading_path="Reg E > §1005.11 Procedures > (c)(1)",
    )


def test_point_id_is_deterministic_uuid5() -> None:
    assert idx.point_id("1005.11(c)(1)@2023-01-01") == idx.point_id("1005.11(c)(1)@2023-01-01")
    assert idx.point_id("a") != idx.point_id("b")


def test_chunk_payload_has_ordinals_and_facets() -> None:
    payload = idx.chunk_payload(_chunk())
    assert payload["valid_from_ord"] == date(2023, 1, 1).toordinal()
    assert payload["valid_to_ord"] == date(2024, 3, 15).toordinal()
    assert payload["regulation"] == "Reg E"
    assert payload["citation_id"] == "1005.11(c)(1)@2023-01-01"


# --- point-in-time filter ---------------------------------------------------


def test_pit_filter_builds_range_conditions() -> None:
    flt = se.pit_filter(date(2023, 6, 1), "Reg E")
    assert flt is not None
    keys = {c.key for c in flt.must}  # type: ignore[union-attr]
    assert {"valid_from_ord", "valid_to_ord", "regulation"} <= keys


def test_pit_filter_none_without_as_of_or_regulation() -> None:
    assert se.pit_filter(None, None) is None
    # regulation alone still yields a filter
    assert se.pit_filter(None, "Reg E") is not None


# --- rewrite ----------------------------------------------------------------


def test_heuristic_rewrite_detects_regulation_and_facts() -> None:
    intent = rw.heuristic_rewrite(
        "My debit card had an unauthorized charge; the bank owes provisional credit."
    )
    assert intent.regulation_hint == "Reg E"
    assert "unauthorized" in intent.key_facts
    assert "provisional credit" in intent.key_facts


def test_query_text_appends_facts_for_sparse() -> None:
    intent = rw.SearchIntent(
        legal_question="time limit for provisional credit",
        regulation_hint="Reg E",
        key_facts=["provisional credit"],
    )
    assert rw.query_text(intent) == "time limit for provisional credit"
    assert "provisional credit" in rw.query_text(intent, for_sparse=True)


def test_heuristic_rewrite_normalises_whitespace() -> None:
    intent = rw.heuristic_rewrite("  too    many\n\nspaces  ")
    assert intent.legal_question == "too many spaces"
