"""Generate the Tier B deadline golden set (``eval/golden/deadlines.jsonl``, PLAN §7.8).

400 deterministic scenarios spanning every rule in :mod:`resolve.domain.deadlines`
and its parameter combinations. The calculator is the source of truth: each
scenario's ``expected`` is what the calculator returns, so the file is a living
regression — :func:`recompute` re-runs the rule from the stored inputs and the test
asserts an exact match. Scoring an LLM extraction pipeline compares its computed
deadlines against ``expected``.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from resolve.domain import deadlines as dl
from resolve.eval.schemas import (
    GOLDEN_DIR,
    DeadlineExpect,
    DeadlineScenario,
    read_jsonl,
    write_jsonl,
)
from resolve.logging import configure_logging, get_logger

__all__ = ["DEADLINES_PATH", "build", "generate_scenarios", "main", "recompute"]

log = get_logger(__name__)

DEADLINES_PATH = GOLDEN_DIR / "deadlines.jsonl"
TARGET_COUNT = 400

# Deterministic base dates: fixed start, fixed stride (never "today").
_BASE_DATES = [date(2023, 1, 3) + timedelta(days=13 * i) for i in range(25)]

# Input keys that are ISO date strings (parsed back to date in recompute).
_DATE_KEYS = frozenset({"statement_date", "investigation_completed", "notice_received", "received"})

# regulation display -> the Deadline.rule prefix is enough; keep a readable label.
_REG_E, _REG_Z, _REG_X, _REG_V = "Reg E", "Reg Z", "Reg X", "Reg V"


def _expect(deadlines: list[dl.Deadline]) -> list[DeadlineExpect]:
    return [
        DeadlineExpect(name=d.name, due=d.due, rule=d.rule, basis=str(d.basis)) for d in deadlines
    ]


def _specs_for_date(d: date) -> list[tuple[str, str, dict[str, object], list[dl.Deadline]]]:
    """Return ``(regulation, function, inputs, deadlines)`` tuples for one base date."""
    iso = d.isoformat()
    specs: list[tuple[str, str, dict[str, object], list[dl.Deadline]]] = [
        (
            _REG_E,
            "reg_e_notice_timeliness",
            {"statement_date": iso},
            [dl.reg_e_notice_timeliness(d)],
        ),
        (
            _REG_E,
            "reg_e_report_results",
            {"investigation_completed": iso},
            [dl.reg_e_report_results(d)],
        ),
    ]
    for new_account in (False, True):
        for pos_or_foreign in (False, True):
            for provisional in (False, True):
                specs.append(
                    (
                        _REG_E,
                        "reg_e_error_resolution",
                        {
                            "notice_received": iso,
                            "new_account": new_account,
                            "pos_or_foreign": pos_or_foreign,
                            "provisional_credit_given": provisional,
                        },
                        dl.reg_e_error_resolution(
                            d,
                            new_account=new_account,
                            pos_or_foreign=pos_or_foreign,
                            provisional_credit_given=provisional,
                        ),
                    )
                )
    specs.append(
        (
            _REG_Z,
            "reg_z_notice_timeliness",
            {"statement_date": iso},
            [dl.reg_z_notice_timeliness(d)],
        )
    )
    for cycle in (None, 28, 30, 31):
        specs.append(
            (
                _REG_Z,
                "reg_z_billing_error",
                {"notice_received": iso, "billing_cycle_days": cycle},
                dl.reg_z_billing_error(d, billing_cycle_days=cycle),
            )
        )
    for extension in (False, True):
        specs.append(
            (
                _REG_X,
                "reg_x_error_resolution",
                {"received": iso, "extension": extension},
                dl.reg_x_error_resolution(d, extension=extension),
            )
        )
    for additional in (False, True):
        specs.append(
            (
                _REG_V,
                "reg_v_direct_dispute",
                {"notice_received": iso, "additional_info_provided": additional},
                [dl.reg_v_direct_dispute(d, additional_info_provided=additional)],
            )
        )
    return specs


def generate_scenarios(count: int = TARGET_COUNT) -> list[DeadlineScenario]:
    """Return ``count`` deterministic deadline scenarios (default 400)."""
    flat: list[tuple[str, str, dict[str, object], list[dl.Deadline]]] = []
    for base in _BASE_DATES:
        flat.extend(_specs_for_date(base))
    scenarios = [
        DeadlineScenario(
            id=f"D-{i:04d}",
            regulation=regulation,
            function=function,
            inputs=inputs,
            expected=_expect(deadlines),
        )
        for i, (regulation, function, inputs, deadlines) in enumerate(flat[:count], start=1)
    ]
    if len(scenarios) < count:  # pragma: no cover - guards against too-few base dates
        raise RuntimeError(f"only generated {len(scenarios)} scenarios; need {count}")
    return scenarios


def recompute(scenario: DeadlineScenario) -> list[dl.Deadline]:
    """Re-run the calculator from a scenario's stored inputs (dates parsed back)."""
    func = getattr(dl, scenario.function)
    kwargs: dict[str, object] = {
        key: (date.fromisoformat(value) if key in _DATE_KEYS and isinstance(value, str) else value)
        for key, value in scenario.inputs.items()
    }
    result = func(**kwargs)
    return result if isinstance(result, list) else [result]


def build(path: Path | None = None) -> int:
    """Write the deadline golden set to disk; returns the number of scenarios."""
    destination = DEADLINES_PATH if path is None else path
    scenarios = generate_scenarios()
    return write_jsonl(destination, scenarios)


def main() -> int:
    """CLI entry point: ``python -m resolve.eval.golden.deadlines_gen``."""
    configure_logging()
    count = build()
    # Sanity: everything we just wrote recomputes to its stored expectation.
    recomputed_ok = all(
        {(e.name, e.due, e.rule, e.basis) for e in s.expected}
        == {(d.name, d.due, d.rule, str(d.basis)) for d in recompute(s)}
        for s in read_jsonl(DEADLINES_PATH, DeadlineScenario)
    )
    log.info(
        "deadlines_golden_written", path=str(DEADLINES_PATH), count=count, verified=recomputed_ok
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
