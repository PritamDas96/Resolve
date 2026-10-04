"""Unit tests for the FastAPI app (offline — fake gateway + fake retriever)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from resolve.api.app import create_app, get_gateway, get_retriever
from resolve.llm.gateway import FakeGateway
from resolve.retrieval.search import SearchResult


def _router_json(family: str = "deposits", issue: str = "Managing an account") -> str:
    return json.dumps(
        {
            "family": family,
            "issue": issue,
            "confidence": 0.9,
            "legal_question": "provisional credit time limit",
            "regulation_hint": "Reg E",
            "key_facts": ["unauthorized debit"],
        }
    )


def _letter_json() -> str:
    return json.dumps(
        {
            "subject": "Response to your dispute",
            "sentences": [
                {
                    "text": "Regulation E governs error resolution.",
                    "is_factual_claim": True,
                    "citations": [{"kind": "regulation", "ref": "1005.11(c)(1)@2023-01-01"}],
                }
            ],
            "deadlines_referenced": [],
            "abstained": False,
        }
    )


def _fake_retriever(*_a: object, **_k: object) -> list[SearchResult]:
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
            text="Investigate promptly.",
            score=1.0,
        )
    ]


def _client(responses: list[str]) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_gateway] = lambda: FakeGateway(responses)
    app.dependency_overrides[get_retriever] = lambda: _fake_retriever
    return TestClient(app)


def test_health_and_request_id() -> None:
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers.get("X-Request-ID")  # middleware stamped it


def test_route_endpoint() -> None:
    client = _client([_router_json("cards", "Fees or interest")])
    resp = client.post("/v1/route", json={"complaint": "my card fees are wrong"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["route"]["family"] == "cards"
    assert body["legal_question"]


def test_cases_endpoint_drafts_cited_letter() -> None:
    client = _client([_router_json(), _letter_json()])
    resp = client.post(
        "/v1/cases",
        json={"complaint": "Someone used my debit card.", "as_of": "2023-06-01", "case_id": "C-9"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["case_id"] == "C-9"
    assert body["citations_valid"] is True
    assert body["route"]["family"] == "deposits"
    assert "1005.11(c)(1)@2023-01-01" in body["evidence_refs"]


def test_multi_case_pauses_then_resumes() -> None:
    from resolve.agent.graph_multi import build_graph
    from resolve.api.app import get_multi_graph

    graph = build_graph(
        FakeGateway([_router_json(), _letter_json()]),
        _fake_retriever,
        router_model="fake/r",
        drafter_model="fake/d",
    )
    app = create_app()
    app.dependency_overrides[get_multi_graph] = lambda: graph
    client = TestClient(app)

    started = client.post(
        "/v1/cases/multi", json={"complaint": "unauthorized debit", "case_id": "M-1"}
    )
    assert started.status_code == 200
    assert started.json()["paused"] is True
    assert started.json()["letter"]["subject"]

    decided = client.post("/v1/cases/M-1/decision", json={"decision": "approve"})
    assert decided.status_code == 200
    assert decided.json()["decision"] == "approve"


def test_problem_json_on_error() -> None:
    # A gateway that returns unparseable JSON twice makes structured() raise -> 500.
    app = create_app()
    app.dependency_overrides[get_gateway] = lambda: FakeGateway(["not json", "still not json"])
    app.dependency_overrides[get_retriever] = lambda: _fake_retriever
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/v1/route", json={"complaint": "x"})
    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["status"] == 500
