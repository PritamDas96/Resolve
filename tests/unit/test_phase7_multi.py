"""Unit tests for limits + the multi-agent graph with human-in-the-loop (offline)."""

from __future__ import annotations

import json

import pytest

from resolve.agent.graph_multi import CaseGraphState, build_graph, resume_case, start_case
from resolve.agent.limits import Budget, LimitExceededError, Limits
from resolve.llm.gateway import FakeGateway
from resolve.retrieval.search import SearchResult

# --- limits -----------------------------------------------------------------


def test_budget_enforces_each_limit() -> None:
    limits = Limits(max_steps=2, max_retrievals=1, max_tokens=10)
    b = Budget(limits=limits)
    b.step()
    b.step()
    with pytest.raises(LimitExceededError, match="max_steps"):
        b.step()

    b2 = Budget(limits=limits)
    b2.add_retrieval()
    with pytest.raises(LimitExceededError, match="max_retrievals"):
        b2.add_retrieval()

    b3 = Budget(limits=limits)
    with pytest.raises(LimitExceededError, match="max_tokens"):
        b3.add_tokens(11)


# --- multi-agent graph ------------------------------------------------------


def _router_json(
    confidence: float, family: str = "deposits", issue: str = "Managing an account"
) -> str:
    return json.dumps(
        {
            "family": family,
            "issue": issue,
            "confidence": confidence,
            "legal_question": "provisional credit time limit",
            "regulation_hint": "Reg E",
            "key_facts": [],
        }
    )


def _letter_json() -> str:
    return json.dumps(
        {
            "subject": "Response",
            "sentences": [
                {
                    "text": "Reg E sets the error-resolution timeline.",
                    "is_factual_claim": True,
                    "citations": [{"kind": "regulation", "ref": "1005.11@2023-01-01"}],
                }
            ],
            "deadlines_referenced": [],
            "abstained": False,
        }
    )


def _retriever(*_a: object, **_k: object) -> list[SearchResult]:
    return [
        SearchResult(
            chunk_id="1005.11@2023-01-01",
            citation_id="1005.11@2023-01-01",
            section="1005.11",
            regulation="Reg E",
            paragraph="",
            is_interpretation=False,
            interprets=None,
            heading_path="Reg E > §1005.11",
            text="Error resolution procedures.",
            score=1.0,
        )
    ]


def _graph(responses: list[str]):
    return build_graph(
        FakeGateway(responses), _retriever, router_model="fake/r", drafter_model="fake/d"
    )


def test_case_pauses_for_review_then_resumes() -> None:
    graph = _graph([_router_json(0.9), _letter_json()])
    state: CaseGraphState = {
        "case_id": "C-1",
        "complaint": "unauthorized debit",
        "as_of": "2023-06-01",
    }
    paused = start_case(graph, state)
    # Drafted but paused at review (no decision yet).
    assert paused["letter"].subject == "Response"
    assert paused["citations_valid"] is True
    assert "decision" not in paused
    assert "__interrupt__" in paused  # langgraph signals the interrupt

    resumed = resume_case(graph, "C-1", "approve")
    assert resumed["decision"] == "approve"


def test_low_confidence_abstains_without_review() -> None:
    graph = _graph([_router_json(0.1)])
    state: CaseGraphState = {"case_id": "C-2", "complaint": "vague complaint", "as_of": None}
    result = start_case(graph, state)
    assert result["letter"].abstained is True
    assert "decision" not in result  # abstain path skips human review


def test_evidence_reducer_merges_parallel_agents() -> None:
    # account_facts contributes extra evidence that must merge with regulation evidence.
    from resolve.agent.state import Evidence

    def account_facts(_case_id: str) -> list[Evidence]:
        return [Evidence(ref="acct/ACC-1", section="", heading_path="account", text="balance low")]

    graph = build_graph(
        FakeGateway([_router_json(0.9), _letter_json()]),
        _retriever,
        router_model="fake/r",
        drafter_model="fake/d",
        account_facts=account_facts,
    )
    state: CaseGraphState = {"case_id": "C-3", "complaint": "x", "as_of": None}
    paused = start_case(graph, state)
    refs = {e.ref for e in paused["evidence"]}
    assert "1005.11@2023-01-01" in refs  # from regulation agent
    assert "acct/ACC-1" in refs  # from account agent (merged by reducer)
