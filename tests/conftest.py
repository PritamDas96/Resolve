"""Shared test configuration.

Set dummy provider keys before any test module imports application code, so modules
that construct ``Settings`` at import time (e.g. ``resolve.api.app``) work in CI
without a ``.env``. Tests never make real provider calls — the LLM gateway and
embedder are faked — so placeholder values are safe.
"""

from __future__ import annotations

import os

os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
