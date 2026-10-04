"""LLM router: masked complaint -> structured route + search intent (PLAN §9.8).

Returns a validated :class:`RouterOutput`; if the chosen issue is not valid for the
chosen family (taxonomy hierarchy), it does one repair call with the error before
giving up. The router reads untrusted narrative text but holds no tools, so an
injected instruction has no privileged path to act (PLAN §9, defence in depth).
"""

from __future__ import annotations

from resolve.agent.state import Route, RouterOutput
from resolve.data import taxonomy
from resolve.llm import prompts
from resolve.llm.gateway import Gateway, Message, Usage
from resolve.retrieval.rewrite import SearchIntent

__all__ = ["route"]


def _is_valid(output: RouterOutput, tax: taxonomy.Taxonomy) -> bool:
    return taxonomy.is_valid_path(str(output.family), str(output.issue), taxonomy=tax)


def route(
    gateway: Gateway,
    complaint: str,
    *,
    model: str,
    tax: taxonomy.Taxonomy | None = None,
) -> tuple[Route, SearchIntent, Usage]:
    """Classify a (masked) complaint into a route + search intent.

    Args:
        gateway: LLM gateway.
        complaint: Masked complaint text (treated as data by the prompt).
        model: Router model id (e.g. ``gemini/gemini-3.8-flash``).
        tax: Loaded taxonomy; defaults to the cached canonical map.

    Returns:
        ``(route, search_intent, usage)``.
    """
    taxon = tax or taxonomy.load_taxonomy()
    base = prompts.load("router.v1").replace("{complaint}", complaint)
    messages = [Message(role="user", content=base)]
    output, usage = gateway.structured(messages, model=model, schema=RouterOutput)

    if not _is_valid(output, taxon):
        repair = [
            *messages,
            Message(
                role="user",
                content=(
                    f"The issue {output.issue!r} is not valid for family "
                    f"{output.family!r}. Choose an issue that belongs to that family."
                ),
            ),
        ]
        output, extra = gateway.structured(repair, model=model, schema=RouterOutput)
        usage = Usage(
            prompt_tokens=usage.prompt_tokens + extra.prompt_tokens,
            completion_tokens=usage.completion_tokens + extra.completion_tokens,
            cost_usd=usage.cost_usd + extra.cost_usd,
        )

    route_result = Route(family=output.family, issue=output.issue, confidence=output.confidence)
    intent = SearchIntent(
        legal_question=output.legal_question,
        regulation_hint=output.regulation_hint,
        key_facts=output.key_facts,
    )
    return route_result, intent, usage
