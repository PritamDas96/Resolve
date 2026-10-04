"""Versioned prompt files + loader (PLAN §9.7).

Prompts live as ``*.md`` files (version in the filename, e.g. ``router.v1.md``). The
hash of all prompt files is recorded in every eval report so a run is tied to the
exact prompt text. Untrusted complaint narratives are wrapped and labelled as data
inside the templates, never concatenated as instructions.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

__all__ = ["PROMPT_DIR", "load", "prompt_hash"]

PROMPT_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=32)
def load(name: str) -> str:
    """Load a prompt template by name (without the ``.md`` suffix)."""
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


def prompt_hash() -> str:
    """Return a stable SHA-256 over all prompt files (for eval provenance)."""
    digest = hashlib.sha256()
    for path in sorted(PROMPT_DIR.glob("*.md")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()
