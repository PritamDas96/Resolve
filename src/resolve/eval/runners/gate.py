"""Evaluation gate (PLAN §12.4-12.7).

Runs the deterministic golden metrics, compares them to a committed baseline, writes
``eval/reports/summary.{md,json}``, and exits non-zero on a regression so a PR cannot
merge if it degrades a measured capability. The judged (LLM-rubric) metrics are
implemented in :mod:`resolve.eval.judge` and exposed here via :func:`judged_scores`
(repeat N times for non-determinism, §12.4); they are opt-in because they need LLM
quota and agent-generated letters.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from resolve.config import Settings, get_settings
from resolve.data import pii_reinsert
from resolve.eval.golden import deadlines_gen
from resolve.eval.judge import Judge, LetterJudgment
from resolve.eval.metrics import exact_match
from resolve.llm.prompts import prompt_hash
from resolve.logging import configure_logging, get_logger

__all__ = ["GateMetric", "deterministic_metrics", "judged_scores", "main", "run_gate"]

log = get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_BASELINE_PATH = _REPO_ROOT / "eval" / "baselines" / "gate_baseline.json"
_REPORT_DIR = _REPO_ROOT / "eval" / "reports"
_TOLERANCE = 0.02  # a metric may dip this much before it counts as a regression


@dataclass
class GateMetric:
    """One gate metric vs its baseline."""

    name: str
    value: float
    baseline: float | None
    regressed: bool


def _deadlines_exact() -> float:
    """Fraction of deadline scenarios that recompute to their stored expectation."""
    scenarios = deadlines_gen.generate_scenarios()
    hits = sum(exact_match(s.expected, deadlines_gen.recompute(s)) for s in scenarios)
    return hits / len(scenarios)


def _pii_offsets_ok() -> float:
    """Fraction of synthetic PII samples whose reinsertion offsets are self-consistent."""
    from faker import Faker

    total, ok = 0, 0
    for index, template in enumerate(pii_reinsert.SAMPLE_TEMPLATES):
        fake = Faker()
        fake.seed_instance(20260101 + index)
        text, spans = pii_reinsert.reinsert(template, fake)
        total += 1
        ok += pii_reinsert.offsets_are_consistent(text, spans)
    return ok / total if total else 0.0


def _retrieval_recall5(settings: Settings) -> float | None:
    """Mean recall@5 of the sparse arm on the retrieval golden (None if Qdrant is down)."""
    try:
        from qdrant_client import QdrantClient

        from resolve.eval.golden.retrieval_gen import RETRIEVAL_PATH
        from resolve.eval.metrics import recall_at_k
        from resolve.eval.schemas import RetrievalQuery, read_jsonl
        from resolve.retrieval.embeddings import BM25SparseEncoder
        from resolve.retrieval.search import SearchMode, search

        client = QdrantClient(url=settings.qdrant_url, timeout=3)
        name = settings.qdrant_collection_regulations
        if not client.collection_exists(name) or client.count(name).count == 0:
            return None
        enc = BM25SparseEncoder()
        queries = read_jsonl(RETRIEVAL_PATH, RetrievalQuery)
        recalls = []
        for q in queries:
            results = search(
                client,
                name,
                mode=SearchMode.SPARSE,
                sparse=enc.encode_query(q.query),
                as_of=q.as_of,
                k=20,
            )
            ranked = list(dict.fromkeys(r.section for r in results))
            recalls.append(recall_at_k(set(q.expected_sections), ranked, 5))
        return sum(recalls) / len(recalls) if recalls else None
    except Exception as exc:
        log.warning("gate_retrieval_skipped", error=str(exc))
        return None


def deterministic_metrics(settings: Settings | None = None) -> dict[str, float]:
    """Compute the deterministic gate metrics (retrieval omitted if Qdrant is down)."""
    settings = settings or get_settings()
    metrics = {
        "deadlines_exact_match": _deadlines_exact(),
        "pii_offsets_ok": _pii_offsets_ok(),
    }
    recall = _retrieval_recall5(settings)
    if recall is not None:
        metrics["retrieval_recall_at_5"] = recall
    return metrics


def judged_scores(judge: Judge, samples: list[tuple[str, str]], *, n: int = 3) -> dict[str, float]:
    """Judge each (question, letter) sample ``n`` times; return mean + stdev of overall.

    Repeating handles judge non-determinism (§12.4). With a deterministic judge the
    stdev is 0.
    """
    overalls: list[float] = []
    for question, letter in samples:
        for _ in range(n):
            judgment: LetterJudgment = judge.judge(question, letter)
            overalls.append(float(judgment.overall))
    return {
        "judge_overall_mean": statistics.mean(overalls) if overalls else 0.0,
        "judge_overall_stdev": statistics.pstdev(overalls) if len(overalls) > 1 else 0.0,
    }


def _data_version() -> str:
    """SHA-256 over the committed data manifests (PLAN §7.11 DATA_VERSION)."""
    digest = hashlib.sha256()
    manifests = sorted((_REPO_ROOT / "data" / "manifests").glob("*.json"))
    for path in manifests:
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16] if manifests else "none"


def _compare(current: dict[str, float], baseline: dict[str, float]) -> list[GateMetric]:
    out: list[GateMetric] = []
    for name, value in sorted(current.items()):
        base = baseline.get(name)
        regressed = base is not None and value < base - _TOLERANCE
        out.append(GateMetric(name=name, value=value, baseline=base, regressed=regressed))
    return out


def _render(metrics: list[GateMetric], *, passed: bool) -> str:
    lines = [
        "# RESOLVE — Evaluation gate summary",
        "",
        f"- **Verdict:** {'PASS' if passed else 'REGRESSION'}",
        f"- **data_version:** `{_data_version()}`",
        f"- **prompt_hash:** `{prompt_hash()[:16]}`",
        "",
        "| Metric | Value | Baseline | Status |",
        "| --- | --- | --- | --- |",
    ]
    for m in metrics:
        base = "—" if m.baseline is None else f"{m.baseline:.3f}"
        status = "REGRESSED" if m.regressed else "ok"
        lines.append(f"| {m.name} | {m.value:.3f} | {base} | {status} |")
    lines.append("")
    return "\n".join(lines)


def run_gate(settings: Settings | None = None, *, update_baseline: bool = False) -> int:
    """Run the gate; write the summary; return 0 (pass) or 1 (regression)."""
    settings = settings or get_settings()
    current = deterministic_metrics(settings)
    baseline: dict[str, float] = {}
    if _BASELINE_PATH.exists():
        baseline = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))

    metrics = _compare(current, baseline)
    passed = not any(m.regressed for m in metrics)

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / "summary.md").write_text(_render(metrics, passed=passed), encoding="utf-8")
    (_REPORT_DIR / "summary.json").write_text(
        json.dumps(
            {
                "passed": passed,
                "data_version": _data_version(),
                "prompt_hash": prompt_hash()[:16],
                "metrics": current,
                "baseline": baseline,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    if update_baseline or not baseline:
        _BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _BASELINE_PATH.write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        log.info("gate_baseline_written", path=str(_BASELINE_PATH))

    log.info("gate_complete", passed=passed, metrics=current)
    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m resolve.eval.runners.gate``."""
    parser = argparse.ArgumentParser(description="Run the RESOLVE evaluation gate.")
    parser.add_argument(
        "--update-baseline", action="store_true", help="Overwrite the committed baseline."
    )
    args = parser.parse_args(argv)
    configure_logging()
    return run_gate(update_baseline=args.update_baseline)


if __name__ == "__main__":
    sys.exit(main())
