"""Single-agent pipeline: complaint -> route -> retrieve -> draft -> validate (PLAN §9.2).

One agent, tools as plain functions. It routes the (masked) complaint, retrieves the
governing regulation point-in-time, drafts a cited :class:`Letter`, and validates that
every factual sentence cites a ref that exists in the evidence (no hallucinated
citations). PII masking is a pass-through hook here and is implemented in Phase 8.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from resolve.agent.router import route as route_complaint
from resolve.agent.state import CaseResult, Evidence, Letter, Route
from resolve.agent.tools import Retriever
from resolve.eval.metrics.citations import Sentence, citation_report
from resolve.llm import prompts
from resolve.llm.gateway import Gateway, Message, Usage
from resolve.retrieval.rewrite import query_text

__all__ = ["draft_letter", "run_case"]


def _evidence_block(evidence: list[Evidence]) -> str:
    return "\n".join(f"- {e.ref}: {e.heading_path} — {e.text[:300]}" for e in evidence) or "(none)"


def draft_letter(
    gateway: Gateway,
    complaint: str,
    route: Route,
    evidence: list[Evidence],
    *,
    model: str,
) -> tuple[Letter, Usage]:
    """Draft a cited letter from the route and retrieved evidence."""
    prompt = (
        prompts.load("drafter.v1")
        .replace("{family}", str(route.family))
        .replace("{issue}", str(route.issue))
        .replace("{evidence}", _evidence_block(evidence))
        .replace("{complaint}", complaint)
    )
    return gateway.structured([Message(role="user", content=prompt)], model=model, schema=Letter)


def run_case(
    gateway: Gateway,
    *,
    case_id: str,
    complaint: str,
    retrieve: Retriever,
    router_model: str,
    drafter_model: str,
    as_of: date | None = None,
    k: int = 8,
    mask: Callable[[str], str] = lambda text: text,
) -> CaseResult:
    """Run one complaint end-to-end and return a validated :class:`CaseResult`.

    Args:
        gateway: LLM gateway (real or fake).
        case_id: Stable id for this case.
        complaint: Raw complaint text.
        retrieve: Retrieval tool (see :func:`resolve.agent.tools.make_retriever`).
        router_model: Model id for routing.
        drafter_model: Model id for drafting.
        as_of: Point-in-time date for regulation retrieval.
        k: Number of evidence chunks to retrieve.
        mask: PII-masking hook (identity until Phase 8).

    Returns:
        A :class:`CaseResult` with the route, letter, evidence refs, citation
        validity and token usage.
    """
    trace: list[str] = []
    masked = mask(complaint)
    trace.append("intake")

    route, intent, route_usage = route_complaint(gateway, masked, model=router_model)
    trace.append("route")

    # Scope retrieval to the router's regulation hint when present (sharper recall).
    results = retrieve(query_text(intent), as_of=as_of, regulation=intent.regulation_hint, k=k)
    evidence = [
        Evidence(ref=r.citation_id, section=r.section, heading_path=r.heading_path, text=r.text)
        for r in results
    ]
    trace.append("retrieve")

    letter, draft_usage = draft_letter(gateway, masked, route, evidence, model=drafter_model)
    trace.append("draft")

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
    trace.append("validate")

    return CaseResult(
        case_id=case_id,
        route=route,
        letter=letter,
        evidence_refs=sorted(valid_refs),
        citations_valid=report.is_valid,
        ungrounded_refs=report.ungrounded_refs,
        uncited_claims=report.uncited_claims,
        prompt_tokens=route_usage.prompt_tokens + draft_usage.prompt_tokens,
        completion_tokens=route_usage.completion_tokens + draft_usage.completion_tokens,
        trace=trace,
    )
