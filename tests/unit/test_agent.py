"""Unit tests for the single agent (offline — FakeGateway + fake retriever)."""

from __future__ import annotations

import json
from datetime import date

from resolve.agent import graph_single
from resolve.agent.router import route as route_complaint
from resolve.agent.state import Route
from resolve.llm.gateway import FakeGateway
from resolve.retrieval.search import SearchResult


def _router_json(family: str, issue: str) -> str:
    return json.dumps(
        {
            "family": family,
            "issue": issue,
            "confidence": 0.9,
            "legal_question": "time limit for provisional credit",
            "regulation_hint": "Reg E",
            "key_facts": ["unauthorized debit"],
        }
    )


def _fake_results() -> list[SearchResult]:
    return [
        SearchResult(
            chunk_id="1005.11(c)(1)@2023-01-01",
            citation_id="1005.11(c)(1)@2023-01-01",
            section="1005.11",
            regulation="Reg E",
            paragraph="(c)(1)",
            is_interpretation=False,
            interprets=None,
            heading_path="Reg E > §1005.11",
            text="Investigate promptly and provide provisional credit.",
            score=1.0,
        )
    ]


def _retriever(*_args: object, **_kwargs: object) -> list[SearchResult]:
    return _fake_results()


def test_router_returns_valid_route() -> None:
    gw = FakeGateway(_router_json("cards", "Fees or interest"))
    route, intent, usage = route_complaint(gw, "my card fees are wrong", model="fake/x")
    assert isinstance(route, Route)
    assert route.family == "cards"
    assert route.issue == "Fees or interest"
    assert intent.legal_question
    assert usage.prompt_tokens >= 1


def test_router_repairs_invalid_hierarchy() -> None:
    # First response: issue not valid for 'mortgage'; second: a valid mortgage issue.
    gw = FakeGateway(
        [
            _router_json("mortgage", "Fees or interest"),  # invalid for mortgage
            _router_json("mortgage", "Trouble during payment process"),  # valid
        ]
    )
    route, _, _ = route_complaint(gw, "mortgage escrow problem", model="fake/x")
    assert route.family == "mortgage"
    assert route.issue == "Trouble during payment process"


def test_run_case_produces_valid_citations() -> None:
    letter = {
        "subject": "Response regarding your debit card dispute",
        "sentences": [
            {
                "text": "Regulation E sets a time limit for provisional credit.",
                "is_factual_claim": True,
                "citations": [{"kind": "regulation", "ref": "1005.11(c)(1)@2023-01-01"}],
            },
            {
                "text": "We are reviewing your complaint.",
                "is_factual_claim": False,
                "citations": [],
            },
        ],
        "deadlines_referenced": [],
        "abstained": False,
    }
    gw = FakeGateway([_router_json("deposits", "Managing an account"), json.dumps(letter)])
    result = graph_single.run_case(
        gw,
        case_id="C-1",
        complaint="Someone used my debit card without permission.",
        retrieve=_retriever,
        router_model="fake/r",
        drafter_model="fake/d",
        as_of=date(2023, 6, 1),
    )
    assert result.route.family == "deposits"
    assert result.citations_valid is True
    assert result.ungrounded_refs == []
    assert result.trace == ["intake", "route", "retrieve", "draft", "validate"]
    assert "1005.11(c)(1)@2023-01-01" in result.evidence_refs


def test_run_case_flags_hallucinated_citation() -> None:
    letter = {
        "subject": "x",
        "sentences": [
            {
                "text": "A made-up rule applies.",
                "is_factual_claim": True,
                "citations": [{"kind": "regulation", "ref": "9999.99@2099-01-01"}],
            }
        ],
        "deadlines_referenced": [],
        "abstained": False,
    }
    gw = FakeGateway([_router_json("deposits", "Managing an account"), json.dumps(letter)])
    result = graph_single.run_case(
        gw,
        case_id="C-2",
        complaint="x",
        retrieve=_retriever,
        router_model="fake/r",
        drafter_model="fake/d",
    )
    assert result.citations_valid is False
    assert "9999.99@2099-01-01" in result.ungrounded_refs
