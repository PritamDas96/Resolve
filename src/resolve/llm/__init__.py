"""LLM access layer.

Wraps the LiteLLM gateway: model routing (router/drafter/judge), retries,
fallbacks and per-call cost accounting. Implemented from Phase 4 onward.
"""
