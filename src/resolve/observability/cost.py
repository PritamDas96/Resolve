"""Cost and latency accounting (PLAN §14.3, §15.1).

Turns token usage into a per-node and per-case dollar estimate so the unit economics of
the system are visible (cost per approved case). Prices are per-million-token rates; the
free-tier models used here are 0.0, but representative paid rates are included so the
cost-per-case table is meaningful when a paid key is used.
"""

from __future__ import annotations

from pydantic import BaseModel

from resolve.llm.gateway import Usage

__all__ = ["PRICES_PER_MTOK", "CaseCost", "NodeCost", "case_cost", "estimate_cost"]

# (input_usd_per_mtok, output_usd_per_mtok). Free-tier here = 0.0; paid rates are
# representative so the cost model is non-trivial when a paid key is configured.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "gemini/gemini-3.8-flash": (0.0, 0.0),
    "groq/openai/gpt-oss-120b": (0.0, 0.0),
    # representative paid references (used only if selected):
    "gemini/gemini-2.5-pro": (1.25, 10.0),
}
_DEFAULT_PRICE = (0.0, 0.0)


class NodeCost(BaseModel):
    """Cost + tokens attributed to one node/model call."""

    node: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class CaseCost(BaseModel):
    """Aggregated cost for a whole case."""

    case_id: str
    nodes: list[NodeCost]
    total_cost_usd: float
    total_tokens: int


def estimate_cost(model: str, usage: Usage) -> float:
    """Estimate the dollar cost of one call from its model + token usage."""
    in_rate, out_rate = PRICES_PER_MTOK.get(model, _DEFAULT_PRICE)
    return (usage.prompt_tokens * in_rate + usage.completion_tokens * out_rate) / 1_000_000


def case_cost(case_id: str, calls: list[tuple[str, str, Usage]]) -> CaseCost:
    """Aggregate per-node costs into a :class:`CaseCost`.

    Args:
        case_id: The case id.
        calls: ``(node, model, usage)`` for each model call in the case.
    """
    nodes = [
        NodeCost(
            node=node,
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=estimate_cost(model, usage),
        )
        for node, model, usage in calls
    ]
    return CaseCost(
        case_id=case_id,
        nodes=nodes,
        total_cost_usd=sum(n.cost_usd for n in nodes),
        total_tokens=sum(n.prompt_tokens + n.completion_tokens for n in nodes),
    )
