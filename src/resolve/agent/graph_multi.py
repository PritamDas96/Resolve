"""Multi-agent graph with human-in-the-loop (PLAN §9.1, §9.3, Phase 7).

A LangGraph state machine: the router classifies, then the **regulation** and
**account** agents run in parallel (fan-out) and their evidence is merged by a reducer
(fan-in), the drafter writes a cited letter, and a **review** node ``interrupt()``s for
a human decision before the case is finalised. A low-confidence route short-circuits to
an abstention. Trust boundary: the router reads the untrusted narrative but has no
tools; the account agent has account access but never sees the raw narrative.

Checkpointing uses an in-memory saver here (interrupt/resume is fully exercised in
tests). Swapping in ``AsyncPostgresSaver`` (one dependency + a DSN) makes a paused case
survive an API restart — the production configuration.
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from datetime import date
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from resolve.agent.router import route as route_complaint
from resolve.agent.state import Evidence, Letter, LetterSentence, Route
from resolve.agent.tools import Retriever
from resolve.eval.metrics.citations import Sentence, citation_report
from resolve.llm import prompts
from resolve.llm.gateway import Gateway, Message

__all__ = ["CaseGraphState", "build_graph", "resume_case", "start_case"]


class CaseGraphState(TypedDict, total=False):
    """Durable state threaded through the graph (evidence merged by a reducer)."""

    case_id: str
    complaint: str
    as_of: str | None
    confidence: float
    route: Route
    legal_question: str
    regulation_hint: str | None
    evidence: Annotated[list[Evidence], operator.add]
    letter: Letter
    citations_valid: bool
    decision: str


def build_graph(
    gateway: Gateway,
    retrieve: Retriever,
    *,
    router_model: str,
    drafter_model: str,
    confidence_threshold: float = 0.4,
    account_facts: Callable[[str], list[Evidence]] | None = None,
) -> Any:
    """Compile the multi-agent graph with an in-memory checkpointer.

    Args:
        gateway: LLM gateway.
        retrieve: Regulation retrieval tool.
        router_model: Model id for the router node.
        drafter_model: Model id for the drafter node.
        confidence_threshold: Below this the case abstains instead of drafting.
        account_facts: Optional hook returning account evidence for a case id.
    """

    def router_node(state: CaseGraphState) -> dict[str, Any]:
        route, intent, _ = route_complaint(gateway, state["complaint"], model=router_model)
        return {
            "route": route,
            "confidence": route.confidence,
            "legal_question": intent.legal_question,
            "regulation_hint": intent.regulation_hint,
        }

    def regulation_node(state: CaseGraphState) -> dict[str, Any]:
        as_of_str = state.get("as_of")
        as_of = date.fromisoformat(as_of_str) if as_of_str else None
        results = retrieve(
            state["legal_question"], as_of=as_of, regulation=state.get("regulation_hint"), k=6
        )
        evidence = [
            Evidence(ref=r.citation_id, section=r.section, heading_path=r.heading_path, text=r.text)
            for r in results
        ]
        return {"evidence": evidence}

    def account_node(state: CaseGraphState) -> dict[str, Any]:
        # The account agent never sees the narrative; it works from the case id only.
        facts = account_facts(state["case_id"]) if account_facts else []
        return {"evidence": facts}

    def draft_node(state: CaseGraphState) -> dict[str, Any]:
        evidence = state.get("evidence", [])
        block = (
            "\n".join(f"- {e.ref}: {e.heading_path} — {e.text[:300]}" for e in evidence) or "(none)"
        )
        route = state["route"]
        prompt = (
            prompts.load("drafter.v1")
            .replace("{family}", str(route.family))
            .replace("{issue}", str(route.issue))
            .replace("{evidence}", block)
            .replace("{complaint}", state["complaint"])
        )
        letter, _ = gateway.structured(
            [Message(role="user", content=prompt)], model=drafter_model, schema=Letter
        )
        valid_refs = {e.ref for e in evidence}
        report = citation_report(
            [
                Sentence(
                    text=s.text,
                    is_factual_claim=s.is_factual_claim,
                    refs=[c.ref for c in s.citations],
                )
                for s in letter.sentences
            ],
            valid_refs,
        )
        return {"letter": letter, "citations_valid": report.is_valid}

    def abstain_node(state: CaseGraphState) -> dict[str, Any]:
        reason = "Routing confidence below threshold; escalating to a human."
        return {
            "letter": Letter(
                subject="Escalation required",
                sentences=[LetterSentence(text=reason, is_factual_claim=False)],
                abstained=True,
                abstain_reason=reason,
            ),
            "citations_valid": True,
        }

    def review_node(state: CaseGraphState) -> dict[str, Any]:
        decision = interrupt({"letter": state.get("letter"), "case_id": state["case_id"]})
        return {"decision": str(decision)}

    def _after_router(state: CaseGraphState) -> list[str] | str:
        if state["confidence"] < confidence_threshold:
            return "abstain"
        return ["regulation", "account"]  # fan-out

    graph = StateGraph(CaseGraphState)
    graph.add_node("router", router_node)
    graph.add_node("regulation", regulation_node)
    graph.add_node("account", account_node)
    graph.add_node("draft", draft_node)
    graph.add_node("abstain", abstain_node)
    graph.add_node("review", review_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", _after_router, ["regulation", "account", "abstain"])
    graph.add_edge("regulation", "draft")
    graph.add_edge("account", "draft")
    graph.add_edge("draft", "review")
    graph.add_edge("review", END)
    graph.add_edge("abstain", END)

    return graph.compile(checkpointer=MemorySaver())


def start_case(graph: Any, state: CaseGraphState) -> dict[str, Any]:
    """Run a case until it pauses for review (or finishes if it abstains)."""
    config = {"configurable": {"thread_id": state["case_id"]}}
    result: dict[str, Any] = graph.invoke(state, config=config)
    return result


def resume_case(graph: Any, case_id: str, decision: str) -> dict[str, Any]:
    """Resume a paused case with a human decision (approve/reject/edit)."""
    from langgraph.types import Command

    config = {"configurable": {"thread_id": case_id}}
    result: dict[str, Any] = graph.invoke(Command(resume=decision), config=config)
    return result
