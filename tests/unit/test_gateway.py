"""Unit tests for :mod:`resolve.llm.gateway` (offline — FakeGateway, no network)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from resolve.llm.gateway import FakeGateway, Message, _extract_json


class _Schema(BaseModel):
    product: str
    confidence: float


def test_fake_gateway_fifo() -> None:
    gw = FakeGateway(["a", "b"])
    msgs = [Message(role="user", content="hi")]
    assert gw.complete(msgs, model="x").text == "a"
    assert gw.complete(msgs, model="x").text == "b"
    assert gw.complete(msgs, model="x").text == "b"  # repeats last once exhausted
    assert len(gw.calls) == 3


def test_structured_parses_json() -> None:
    gw = FakeGateway('{"product": "cards", "confidence": 0.9}')
    obj, usage = gw.structured([Message(role="user", content="route")], model="x", schema=_Schema)
    assert obj.product == "cards"
    assert obj.confidence == 0.9
    assert usage.prompt_tokens >= 1


def test_structured_repairs_once() -> None:
    gw = FakeGateway(["not json at all", '{"product": "mortgage", "confidence": 0.5}'])
    obj, _ = gw.structured([Message(role="user", content="route")], model="x", schema=_Schema)
    assert obj.product == "mortgage"


def test_structured_raises_after_two_failures() -> None:
    gw = FakeGateway(["nope", "still nope"])
    with pytest.raises((ValueError, Exception)):
        gw.structured([Message(role="user", content="x")], model="x", schema=_Schema)


def test_extract_json_handles_code_fence() -> None:
    assert _extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _extract_json('prefix {"a": 1} suffix') == '{"a": 1}'
