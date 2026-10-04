"""FastAPI service for RESOLVE (PLAN §11).

Endpoints: ``/health`` (liveness), ``/ready`` (Qdrant reachable), ``/v1/route``
(classify a complaint) and ``/v1/cases`` (draft a cited letter). A request-id
middleware stamps every request/response, and errors are returned as
``application/problem+json`` (RFC 7807).

The LLM gateway and retriever are injected via FastAPI dependencies so tests override
them with the FakeGateway + a fake retriever — no network or quota in CI.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from resolve.agent.graph_multi import CaseGraphState, build_graph, resume_case, start_case
from resolve.agent.graph_single import run_case
from resolve.agent.router import route as route_complaint
from resolve.agent.state import CaseResult, Route
from resolve.agent.tools import Retriever, make_retriever
from resolve.config import Settings, get_settings
from resolve.llm.gateway import Gateway, build_gateway
from resolve.logging import get_logger

__all__ = ["app", "create_app", "get_gateway", "get_retriever"]

log = get_logger(__name__)


# --- request/response models ------------------------------------------------


class RouteRequest(BaseModel):
    """Body for ``POST /v1/route``."""

    complaint: str
    as_of: date | None = None


class RouteResponse(BaseModel):
    """Routing result."""

    route: Route
    legal_question: str
    regulation_hint: str | None


class CaseRequest(BaseModel):
    """Body for ``POST /v1/cases``."""

    complaint: str
    as_of: date | None = None
    case_id: str | None = None


class DecisionRequest(BaseModel):
    """Body for ``POST /v1/cases/{case_id}/decision`` (human review)."""

    decision: str  # approve | reject | edit


# --- dependencies (overridden in tests) -------------------------------------


def get_gateway() -> Gateway:
    """Provide the real LLM gateway (overridden by tests)."""
    return build_gateway()


def get_retriever() -> Retriever:
    """Provide the real retrieval tool (overridden by tests)."""
    return make_retriever()


_multi_graph: object | None = None


def get_multi_graph() -> object:
    """Provide a process-wide multi-agent graph (lazy singleton; overridden by tests).

    A single instance is required so a paused case's checkpoint survives between the
    start call and the later /decision resume.
    """
    global _multi_graph
    if _multi_graph is None:
        settings = get_settings()
        _multi_graph = build_graph(
            build_gateway(settings),
            make_retriever(settings),
            router_model=settings.router_model,
            drafter_model=settings.drafter_model,
        )
    return _multi_graph


GatewayDep = Annotated[Gateway, Depends(get_gateway)]
RetrieverDep = Annotated[Retriever, Depends(get_retriever)]
MultiGraphDep = Annotated[object, Depends(get_multi_graph)]


def _problem(status: int, title: str, detail: str, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": detail,
            "instance": getattr(request.state, "request_id", ""),
        },
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application."""
    settings = settings or get_settings()
    application = FastAPI(title="RESOLVE", version="0.1.0")

    @application.middleware("http")
    async def request_id_mw(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @application.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.error("api_unhandled_error", error=str(exc), path=request.url.path)
        return _problem(500, "Internal Server Error", str(exc), request)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/ready")
    async def ready(request: Request) -> JSONResponse:
        try:
            from qdrant_client import QdrantClient

            client = QdrantClient(url=settings.qdrant_url, timeout=3)
            name = settings.qdrant_collection_regulations
            ok = client.collection_exists(name) and client.count(name).count > 0
        except Exception as exc:
            return _problem(503, "Not Ready", f"qdrant: {exc}", request)
        if not ok:
            return _problem(503, "Not Ready", "regulations collection empty", request)
        return JSONResponse({"status": "ready"})

    @application.post("/v1/route", response_model=RouteResponse)
    async def route_endpoint(body: RouteRequest, gateway: GatewayDep) -> RouteResponse:
        route, intent, _ = route_complaint(gateway, body.complaint, model=settings.router_model)
        return RouteResponse(
            route=route,
            legal_question=intent.legal_question,
            regulation_hint=intent.regulation_hint,
        )

    @application.post("/v1/cases", response_model=CaseResult)
    async def cases_endpoint(
        body: CaseRequest, gateway: GatewayDep, retrieve: RetrieverDep
    ) -> CaseResult:
        return run_case(
            gateway,
            case_id=body.case_id or str(uuid.uuid4()),
            complaint=body.complaint,
            retrieve=retrieve,
            router_model=settings.router_model,
            drafter_model=settings.drafter_model,
            as_of=body.as_of,
        )

    @application.post("/v1/cases/multi")
    async def cases_multi_endpoint(body: CaseRequest, graph: MultiGraphDep) -> dict[str, Any]:
        """Run the multi-agent graph until it pauses for human review."""
        case_id = body.case_id or str(uuid.uuid4())
        state: CaseGraphState = {
            "case_id": case_id,
            "complaint": body.complaint,
            "as_of": body.as_of.isoformat() if body.as_of else None,
        }
        result = start_case(graph, state)
        letter = result.get("letter")
        return {
            "case_id": case_id,
            "paused": "__interrupt__" in result and "decision" not in result,
            "citations_valid": result.get("citations_valid"),
            "letter": letter.model_dump() if letter is not None else None,
        }

    @application.post("/v1/cases/{case_id}/decision")
    async def case_decision_endpoint(
        case_id: str, body: DecisionRequest, graph: MultiGraphDep
    ) -> dict[str, Any]:
        """Resume a paused case with a human decision (approve/reject/edit)."""
        result = resume_case(graph, case_id, body.decision)
        return {"case_id": case_id, "decision": result.get("decision")}

    return application


app = create_app()
