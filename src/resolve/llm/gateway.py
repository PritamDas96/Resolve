"""LLM gateway (PLAN §9.7, ADR-017).

A thin, typed wrapper over the chat APIs the agent uses, so call sites never touch
provider HTTP directly. Routes by model prefix (``gemini/...`` -> Google Generative
Language REST; ``groq/...`` -> Groq OpenAI-compatible REST), captures token usage and
cost, and offers :meth:`Gateway.structured` for validated JSON (one repair retry).

``FakeGateway`` returns scripted responses for deterministic, offline tests and CI —
no network, no API quota. We hand-roll this instead of LiteLLM to keep dependencies
light and the fake trivially deterministic (ADR-017).
"""

from __future__ import annotations

import abc
import json
from typing import TYPE_CHECKING, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from resolve.config import Settings, get_settings
from resolve.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "Completion",
    "FakeGateway",
    "Gateway",
    "HttpGateway",
    "Message",
    "Usage",
    "build_gateway",
]

log = get_logger(__name__)

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_GROQ_BASE = "https://api.groq.com/openai/v1"


class Message(BaseModel):
    """One chat message."""

    role: str  # "system" | "user" | "assistant"
    content: str


class Usage(BaseModel):
    """Token usage and (best-effort) cost for one call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


class Completion(BaseModel):
    """A model response with its usage."""

    text: str
    model: str
    usage: Usage


class Gateway(Protocol):
    """The interface the agent depends on (real or fake)."""

    def complete(
        self, messages: Sequence[Message], *, model: str, temperature: float = 0.0
    ) -> Completion:
        """Return a text completion for the given chat messages."""
        ...

    def structured[M: BaseModel](
        self, messages: Sequence[Message], *, model: str, schema: type[M], temperature: float = 0.0
    ) -> tuple[M, Usage]:
        """Return a validated ``schema`` instance parsed from a JSON completion."""
        ...


def _extract_json(text: str) -> str:
    """Pull the first JSON object out of a model response (tolerates code fences)."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```", 2)[1]
        if stripped.startswith("json"):
            stripped = stripped[4:]
    start, end = stripped.find("{"), stripped.rfind("}")
    return stripped[start : end + 1] if start != -1 and end != -1 else stripped


class _StructuredMixin(abc.ABC):
    """Shared structured-output logic: ask for JSON, validate, one repair retry."""

    @abc.abstractmethod
    def complete(
        self, messages: Sequence[Message], *, model: str, temperature: float = 0.0
    ) -> Completion:
        """Return a text completion (implemented by concrete gateways)."""

    def structured[M: BaseModel](
        self, messages: Sequence[Message], *, model: str, schema: type[M], temperature: float = 0.0
    ) -> tuple[M, Usage]:
        """Request JSON, validate against ``schema``; on failure retry once with the error."""
        instruction = Message(
            role="user",
            content=(
                "Respond with a single JSON object matching this schema "
                f"(no prose, no code fence):\n{json.dumps(schema.model_json_schema())}"
            ),
        )
        convo = [*messages, instruction]
        total = Usage()
        for attempt in range(2):
            completion = self.complete(convo, model=model, temperature=temperature)
            total = Usage(
                prompt_tokens=total.prompt_tokens + completion.usage.prompt_tokens,
                completion_tokens=total.completion_tokens + completion.usage.completion_tokens,
                cost_usd=total.cost_usd + completion.usage.cost_usd,
            )
            try:
                return schema.model_validate_json(_extract_json(completion.text)), total
            except (ValidationError, ValueError) as exc:
                if attempt == 1:
                    raise
                convo = [
                    *convo,
                    Message(role="assistant", content=completion.text),
                    Message(
                        role="user",
                        content=f"That failed validation: {exc}. Return valid JSON.",
                    ),
                ]
        raise RuntimeError("unreachable")


class HttpGateway(_StructuredMixin):
    """Real gateway: dispatches to Gemini or Groq by model prefix."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Capture provider keys from settings."""
        settings = settings or get_settings()
        self._gemini_key = settings.gemini_api_key.get_secret_value()
        self._groq_key = settings.groq_api_key.get_secret_value()

    def complete(
        self, messages: Sequence[Message], *, model: str, temperature: float = 0.0
    ) -> Completion:
        """Dispatch to the provider implied by the model prefix."""
        if model.startswith("gemini/"):
            return self._gemini(
                messages, model=model.removeprefix("gemini/"), temperature=temperature
            )
        if model.startswith("groq/"):
            return self._groq(messages, model=model.removeprefix("groq/"), temperature=temperature)
        raise ValueError(f"unknown model provider for {model!r}")

    def _gemini(self, messages: Sequence[Message], *, model: str, temperature: float) -> Completion:
        system = "\n".join(m.content for m in messages if m.role == "system")
        contents = [
            {"role": "user" if m.role != "assistant" else "model", "parts": [{"text": m.content}]}
            for m in messages
            if m.role != "system"
        ]
        body: dict[str, object] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        response = httpx.post(
            f"{_GEMINI_BASE}/models/{model}:generateContent",
            params={"key": self._gemini_key},
            json=body,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        meta = data.get("usageMetadata", {})
        usage = Usage(
            prompt_tokens=int(meta.get("promptTokenCount", 0)),
            completion_tokens=int(meta.get("candidatesTokenCount", 0)),
        )
        return Completion(text=text, model=f"gemini/{model}", usage=usage)

    def _groq(self, messages: Sequence[Message], *, model: str, temperature: float) -> Completion:
        response = httpx.post(
            f"{_GROQ_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {self._groq_key}"},
            json={
                "model": model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": temperature,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        meta = data.get("usage", {})
        usage = Usage(
            prompt_tokens=int(meta.get("prompt_tokens", 0)),
            completion_tokens=int(meta.get("completion_tokens", 0)),
        )
        return Completion(text=text, model=f"groq/{model}", usage=usage)


class FakeGateway(_StructuredMixin):
    """Deterministic gateway for tests/CI: returns scripted responses in order.

    Construct with a list of response strings (consumed FIFO) or a single string
    returned for every call. Records the messages it was called with.
    """

    def __init__(self, responses: list[str] | str) -> None:
        """Seed the scripted responses (list = FIFO queue; str = constant)."""
        self._responses = [responses] if isinstance(responses, str) else list(responses)
        self._index = 0
        self.calls: list[list[Message]] = []

    def complete(
        self, messages: Sequence[Message], *, model: str, temperature: float = 0.0
    ) -> Completion:
        """Return the next scripted response (repeats the last once exhausted)."""
        self.calls.append(list(messages))
        if not self._responses:
            raise RuntimeError("FakeGateway has no scripted responses")
        text = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return Completion(text=text, model=model, usage=Usage(prompt_tokens=1, completion_tokens=1))


def build_gateway(settings: Settings | None = None) -> Gateway:
    """Return the real HTTP gateway (the app's default)."""
    return HttpGateway(settings)
