"""Embeddings for retrieval (PLAN §8.3; ADR-002).

Dense vectors come from the Gemini embeddings API (``gemini-embedding-001``) over
REST, reduced to ``embedding_dim`` and L2-normalised for cosine search; results are
cached to disk so re-indexing does not re-call the API. Sparse vectors are a
pure-Python BM25-style encoder (token term-frequencies at stable hashed indices)
scored by Qdrant's IDF modifier. This avoids ``fastembed``/``onnxruntime``, which
segfault on this Python 3.13 Windows environment.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter
from pathlib import Path

import httpx

from resolve.config import Settings, get_settings
from resolve.logging import get_logger

__all__ = [
    "BM25SparseEncoder",
    "GeminiDenseEmbedder",
    "SparseVector",
    "l2_normalise",
    "term_id",
    "tokenize",
]

log = get_logger(__name__)

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_BATCH = 50  # requests per batchEmbedContents call

# (indices, values) in Qdrant's sparse-vector shape.
SparseVector = tuple[list[int], list[float]]

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokeniser (shared by index and query)."""
    return _TOKEN_RE.findall(text.lower())


def term_id(token: str) -> int:
    """Map a token to a stable 32-bit index (no stored vocabulary needed)."""
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest(), "big")


def l2_normalise(vector: list[float]) -> list[float]:
    """Return the L2-normalised vector (unit length); unchanged if it is all-zero."""
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector


class BM25SparseEncoder:
    """Pure-Python BM25-style sparse encoder; Qdrant's IDF modifier does the weighting."""

    def encode_document(self, text: str) -> SparseVector:
        """Encode a document as (hashed term ids, term frequencies)."""
        counts = Counter(tokenize(text))
        indices = [term_id(tok) for tok in counts]
        values = [float(freq) for freq in counts.values()]
        return indices, values

    def encode_query(self, text: str) -> SparseVector:
        """Encode a query as (unique hashed term ids, 1.0 each)."""
        tokens = list(dict.fromkeys(tokenize(text)))
        return [term_id(tok) for tok in tokens], [1.0] * len(tokens)


class GeminiDenseEmbedder:
    """Dense embeddings via the Gemini REST API, L2-normalised, with a disk cache."""

    def __init__(self, settings: Settings | None = None, *, cache_path: Path | None = None) -> None:
        """Resolve the model/key, pick a cache path and warm the in-memory cache."""
        settings = settings or get_settings()
        self.model = settings.embedding_model
        self.dim = settings.embedding_dim
        self._key = settings.gemini_api_key.get_secret_value()
        self._cache_path = cache_path or (
            Path(settings.data_dir) / "interim" / f"embed_cache_{self.model}_{self.dim}.json"
        )
        self._cache: dict[str, list[float]] = {}
        if self._cache_path.exists():
            self._cache = json.loads(self._cache_path.read_text(encoding="utf-8"))

    def _cache_key(self, text: str, task_type: str) -> str:
        raw = f"{self.model}|{self.dim}|{task_type}|{text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _call_batch(self, texts: list[str], task_type: str) -> list[list[float]]:
        """One batchEmbedContents call (retried on transient failure)."""
        requests = [
            {
                "model": f"models/{self.model}",
                "content": {"parts": [{"text": t}]},
                "taskType": task_type,
                "outputDimensionality": self.dim,
            }
            for t in texts
        ]
        url = f"{_GEMINI_BASE}/models/{self.model}:batchEmbedContents"
        last_error = ""
        for attempt in range(5):
            response = httpx.post(
                url, params={"key": self._key}, json={"requests": requests}, timeout=120
            )
            if response.status_code == 200:
                return [l2_normalise(e["values"]) for e in response.json()["embeddings"]]
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            if response.status_code in (429, 500, 503):
                time.sleep(min(2**attempt, 30))
                continue
            break
        raise RuntimeError(f"Gemini embeddings failed: {last_error}")

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        """Embed texts, serving cache hits and batching the misses."""
        results: dict[int, list[float]] = {}
        misses: list[tuple[int, str]] = []
        for i, text in enumerate(texts):
            cached = self._cache.get(self._cache_key(text, task_type))
            if cached is not None:
                results[i] = cached
            else:
                misses.append((i, text))

        for start in range(0, len(misses), _BATCH):
            batch = misses[start : start + _BATCH]
            vectors = self._call_batch([t for _, t in batch], task_type)
            for (i, text), vector in zip(batch, vectors, strict=True):
                results[i] = vector
                self._cache[self._cache_key(text, task_type)] = vector
            log.info(
                "gemini_embed_batch", task=task_type, done=start + len(batch), total=len(misses)
            )

        if misses:
            self._flush_cache()
        return [results[i] for i in range(len(texts))]

    def _flush_cache(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(self._cache), encoding="utf-8")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed corpus chunks (RETRIEVAL_DOCUMENT task type)."""
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query (RETRIEVAL_QUERY task type)."""
        return self._embed([text], "RETRIEVAL_QUERY")[0]
