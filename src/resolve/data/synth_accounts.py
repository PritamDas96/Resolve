"""Synthetic account generation (PLAN §7.6).

Generates internally-consistent synthetic accounts, transactions and disputes for
the four product families, so that account / regulation / deadline joins in later
phases are meaningful. Generation is driven by ``data/account_scenarios.yaml`` and
is **fully seeded and deterministic**: the same ``(seed, as_of, count)`` always
produces byte-identical output.

Design:

* Pure generation (:func:`generate`) and invariant checking
  (:func:`validate_invariants`) have no I/O and are unit-tested offline.
* Loading into Postgres (:func:`load`) is isolated and exercised by an integration
  test that skips when no database is reachable.

Dates are built *backwards* from each dispute's notice date so the ordering
invariant (``opened_on <= posted_on <= statement_date <= notice_received_on <=
provisional_credit_on <= resolved_on``) always holds. ``as_of`` is an explicit
parameter (never ``today``) to keep runs reproducible.

All personal data (holder names/emails) is synthetic (Faker); no real customer
data is ever used (see CLAUDE.md).
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import yaml
from faker import Faker
from pydantic import BaseModel

from resolve import config
from resolve.config import Settings, get_settings
from resolve.logging import configure_logging, get_logger

if TYPE_CHECKING:
    import asyncpg

__all__ = [
    "Account",
    "Dispute",
    "GenerationResult",
    "Scenario",
    "Transaction",
    "apply_schema",
    "generate",
    "load",
    "load_scenarios",
    "main",
    "validate_invariants",
]

log = get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIOS_PATH = _REPO_ROOT / "data" / "account_scenarios.yaml"
SCHEMA_PATH = _REPO_ROOT / "sql" / "001_schema.sql"

# Default reference date for generation; fixed (not today) so runs are reproducible.
DEFAULT_AS_OF = date(2026, 1, 1)


class Account(BaseModel):
    """A synthetic account (maps to the ``accounts`` table)."""

    account_id: str
    queue_id: str
    bank: str
    product_type: str
    opened_on: date
    holder_name: str
    holder_email: str
    status: str


class Transaction(BaseModel):
    """A synthetic transaction (maps to the ``transactions`` table)."""

    txn_id: str
    account_id: str
    posted_on: date
    amount_cents: int
    channel: str
    merchant: str | None
    statement_date: date


class Dispute(BaseModel):
    """A synthetic dispute (maps to the ``disputes`` table)."""

    dispute_id: str
    account_id: str
    txn_id: str | None
    notice_received_on: date
    notice_channel: str
    provisional_credit_on: date | None
    resolved_on: date | None
    outcome: str | None


class Scenario(BaseModel):
    """One scenario template from ``account_scenarios.yaml``."""

    name: str
    family: str
    generator: str
    weight: int = 1
    params: dict[str, object] = {}


class GenerationResult(BaseModel):
    """The full synthetic dataset produced by :func:`generate`."""

    accounts: list[Account]
    transactions: list[Transaction]
    disputes: list[Dispute]

    def counts(self) -> dict[str, int]:
        """Return row counts per table."""
        return {
            "accounts": len(self.accounts),
            "transactions": len(self.transactions),
            "disputes": len(self.disputes),
        }


# --- generation context -----------------------------------------------------


class _Ctx:
    """Seeded generation context: RNG, Faker and the shared reference date."""

    def __init__(self, seed: int, as_of: date) -> None:
        self.rng = random.Random(seed)
        self.faker = Faker()
        self.faker.seed_instance(seed)
        self.as_of = as_of
        self.banks = sorted({strings[0] for strings in config.BANKS.values()})

    def _range(self, params: dict[str, object], key: str) -> int:
        bounds = params[key]
        assert isinstance(bounds, list), f"{key} must be a [min, max] list"
        return self.rng.randint(int(bounds[0]), int(bounds[1]))

    def _choice(self, params: dict[str, object], key: str) -> object:
        choices = params[key]
        assert isinstance(choices, list), f"{key} must be a list of choices"
        return self.rng.choice(choices)

    def _bank(self) -> str:
        return self.rng.choice(self.banks)

    def _holder(self) -> tuple[str, str]:
        name = self.faker.name()
        slug = name.lower().replace(" ", ".").replace("'", "")
        return name, f"{slug}@example.com"


class _Generator(Protocol):
    def __call__(
        self, ctx: _Ctx, scenario: Scenario, idx: int
    ) -> tuple[Account, list[Transaction], list[Dispute]]: ...


# --- per-family generators --------------------------------------------------


def _account(
    ctx: _Ctx, scenario: Scenario, idx: int, product_type: str, opened_on: date
) -> Account:
    """Build the account row shared by all generators."""
    name, email = ctx._holder()
    status = ctx.rng.choice(["open", "open", "open", "closed"])
    return Account(
        account_id=f"ACC-{idx:06d}",
        queue_id=scenario.family,
        bank=ctx._bank(),
        product_type=product_type,
        opened_on=opened_on,
        holder_name=name,
        holder_email=email,
        status=status,
    )


def _dispute_dates(
    ctx: _Ctx, params: dict[str, object], notice_on: date
) -> tuple[date | None, date | None, str | None]:
    """Derive provisional-credit, resolution dates and outcome from the notice date."""
    provisional = None
    if "provisional_credit" in params and bool(ctx._choice(params, "provisional_credit")):
        provisional = notice_on + timedelta(days=ctx.rng.randint(1, 10))
    resolved_on = None
    outcome = None
    if "resolved" in params and bool(ctx._choice(params, "resolved")):
        resolved_on = notice_on + timedelta(days=ctx.rng.randint(10, 90))
        outcome = ctx.rng.choice(["resolved_in_favor", "denied", "partially_resolved"])
    return provisional, resolved_on, outcome


def _txn_dispute_chain(
    ctx: _Ctx, scenario: Scenario, idx: int, account: Account, *, channels_key: str = "channel"
) -> tuple[list[Transaction], list[Dispute]]:
    """Build a disputed transaction and its dispute, dated backwards from notice."""
    params = scenario.params
    notice_delay = ctx._range(params, "notice_delay_days")
    notice_on = ctx.as_of - timedelta(days=ctx.rng.randint(5, 120))
    statement_date = notice_on - timedelta(days=notice_delay)
    posted_on = statement_date - timedelta(days=ctx.rng.randint(1, 20))

    txn = Transaction(
        txn_id=f"TXN-{idx:06d}-0",
        account_id=account.account_id,
        posted_on=posted_on,
        amount_cents=-ctx._range(params, "amount_cents"),
        channel=str(ctx._choice(params, channels_key)),
        merchant=ctx.faker.company(),
        statement_date=statement_date,
    )
    provisional, resolved_on, outcome = _dispute_dates(ctx, params, notice_on)
    dispute = Dispute(
        dispute_id=f"DSP-{idx:06d}",
        account_id=account.account_id,
        txn_id=txn.txn_id,
        notice_received_on=notice_on,
        notice_channel=ctx.rng.choice(["oral", "written"]),
        provisional_credit_on=provisional,
        resolved_on=resolved_on,
        outcome=outcome,
    )
    return [txn], [dispute]


def _disputed_account(
    ctx: _Ctx, scenario: Scenario, idx: int, product_type: str
) -> tuple[Account, list[Transaction], list[Dispute]]:
    """Build an account with a disputed transaction, opened before the earliest date.

    The transaction/dispute chain is created first (dated backwards from the notice
    date), then the account's ``opened_on`` is anchored before the earliest posting.
    """
    placeholder = _account(ctx, scenario, idx, product_type, ctx.as_of)
    txns, disputes = _txn_dispute_chain(ctx, scenario, idx, placeholder)
    age = ctx._range(scenario.params, "account_age_days")
    opened_on = min(t.posted_on for t in txns) - timedelta(days=age)
    account = placeholder.model_copy(update={"opened_on": opened_on})
    return account, txns, disputes


def _gen_reg_e(
    ctx: _Ctx, scenario: Scenario, idx: int
) -> tuple[Account, list[Transaction], list[Dispute]]:
    """Reg E error-resolution on a deposit account."""
    return _disputed_account(ctx, scenario, idx, str(ctx._choice(scenario.params, "product_type")))


def _gen_reg_z(
    ctx: _Ctx, scenario: Scenario, idx: int
) -> tuple[Account, list[Transaction], list[Dispute]]:
    """Reg Z billing-error on a credit card."""
    return _disputed_account(ctx, scenario, idx, str(ctx._choice(scenario.params, "product_type")))


def _gen_reg_x(
    ctx: _Ctx, scenario: Scenario, idx: int
) -> tuple[Account, list[Transaction], list[Dispute]]:
    """Reg X mortgage servicing: monthly payments, no transaction dispute."""
    params = scenario.params
    num = ctx._range(params, "num_payments")
    payments: list[Transaction] = []
    for k in range(num):
        posted_on = ctx.as_of - timedelta(days=30 * (k + 1))
        payments.append(
            Transaction(
                txn_id=f"TXN-{idx:06d}-{k}",
                account_id=f"ACC-{idx:06d}",
                posted_on=posted_on,
                amount_cents=-ctx._range(params, "payment_cents"),
                channel="ach",
                merchant=None,
                statement_date=posted_on + timedelta(days=ctx.rng.randint(1, 5)),
            )
        )
    earliest = min(p.posted_on for p in payments)
    age = ctx._range(params, "account_age_days")
    opened_on = earliest - timedelta(days=age)
    account = _account(ctx, scenario, idx, "mortgage", opened_on)
    return account, payments, []


def _gen_reg_v(
    ctx: _Ctx, scenario: Scenario, idx: int
) -> tuple[Account, list[Transaction], list[Dispute]]:
    """Reg V furnisher dispute: a reporting dispute with no underlying transaction."""
    params = scenario.params
    product_type = str(ctx._choice(params, "product_type"))
    notice_delay = ctx._range(params, "notice_delay_days")
    notice_on = ctx.as_of - timedelta(days=ctx.rng.randint(5, 120))
    age = ctx._range(params, "account_age_days")
    opened_on = notice_on - timedelta(days=notice_delay + age)
    account = _account(ctx, scenario, idx, product_type, opened_on)
    _, resolved_on, outcome = _dispute_dates(ctx, params, notice_on)
    dispute = Dispute(
        dispute_id=f"DSP-{idx:06d}",
        account_id=account.account_id,
        txn_id=None,
        notice_received_on=notice_on,
        notice_channel="written",
        provisional_credit_on=None,
        resolved_on=resolved_on,
        outcome=outcome,
    )
    return account, [], [dispute]


_GENERATORS: dict[str, _Generator] = {
    "reg_e_error_resolution": _gen_reg_e,
    "reg_z_billing_error": _gen_reg_z,
    "reg_x_servicing": _gen_reg_x,
    "reg_v_furnisher": _gen_reg_v,
}


# --- orchestration ----------------------------------------------------------


def load_scenarios(path: Path | str | None = None) -> list[Scenario]:
    """Load and validate scenario templates from YAML.

    Args:
        path: YAML file; defaults to :data:`SCENARIOS_PATH`.

    Returns:
        The parsed scenarios.
    """
    source = Path(path) if path is not None else SCENARIOS_PATH
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    return [Scenario.model_validate(entry) for entry in data["scenarios"]]


def generate(
    count: int,
    *,
    seed: int = 0,
    as_of: date = DEFAULT_AS_OF,
    scenarios: Sequence[Scenario] | None = None,
) -> GenerationResult:
    """Generate ``count`` synthetic accounts with their transactions and disputes.

    Scenarios are drawn by weight using the seeded RNG, so the output is fully
    determined by ``(count, seed, as_of, scenarios)``.

    Args:
        count: Number of accounts to generate.
        seed: RNG seed for reproducibility.
        as_of: Reference date all generation is anchored to.
        scenarios: Scenario templates; defaults to the committed YAML.

    Returns:
        The validated :class:`GenerationResult`.

    Raises:
        ValueError: If a scenario names an unknown generator, or invariants fail.
    """
    specs = list(scenarios) if scenarios is not None else load_scenarios()
    unknown = {s.generator for s in specs} - set(_GENERATORS)
    if unknown:
        raise ValueError(f"unknown generators: {sorted(unknown)}")

    ctx = _Ctx(seed=seed, as_of=as_of)
    population = [s for s in specs for _ in range(max(1, s.weight))]

    accounts: list[Account] = []
    transactions: list[Transaction] = []
    disputes: list[Dispute] = []
    for idx in range(count):
        scenario = ctx.rng.choice(population)
        account, txns, disp = _GENERATORS[scenario.generator](ctx, scenario, idx)
        accounts.append(account)
        transactions.extend(txns)
        disputes.extend(disp)

    result = GenerationResult(accounts=accounts, transactions=transactions, disputes=disputes)
    validate_invariants(result)
    return result


def validate_invariants(data: GenerationResult) -> None:
    """Assert every referential and temporal invariant holds.

    Args:
        data: The generated dataset.

    Raises:
        ValueError: On any dangling foreign key, non-monotonic date chain, unknown
            queue, or zero-amount transaction.
    """
    account_ids = {a.account_id for a in data.accounts}
    txn_ids = {t.txn_id for t in data.transactions}
    txn_by_id = {t.txn_id: t for t in data.transactions}
    valid_queues = {"deposits", "cards", "mortgage", "credit_reporting"}

    errors: list[str] = []
    for a in data.accounts:
        if a.queue_id not in valid_queues:
            errors.append(f"account {a.account_id} has unknown queue {a.queue_id!r}")

    for t in data.transactions:
        if t.account_id not in account_ids:
            errors.append(f"txn {t.txn_id} references missing account {t.account_id}")
        if t.amount_cents == 0:
            errors.append(f"txn {t.txn_id} has zero amount")
        if t.posted_on > t.statement_date:
            errors.append(f"txn {t.txn_id}: posted_on > statement_date")
        account = next((a for a in data.accounts if a.account_id == t.account_id), None)
        if account is not None and account.opened_on > t.posted_on:
            errors.append(f"txn {t.txn_id}: posted before account opened")

    for d in data.disputes:
        if d.account_id not in account_ids:
            errors.append(f"dispute {d.dispute_id} references missing account {d.account_id}")
        if d.txn_id is not None and d.txn_id not in txn_ids:
            errors.append(f"dispute {d.dispute_id} references missing txn {d.txn_id}")
        if d.txn_id is not None:
            stmt = txn_by_id[d.txn_id].statement_date
            if stmt > d.notice_received_on:
                errors.append(f"dispute {d.dispute_id}: statement after notice")
        if d.provisional_credit_on is not None and d.notice_received_on > d.provisional_credit_on:
            errors.append(f"dispute {d.dispute_id}: notice after provisional credit")
        if d.resolved_on is not None and d.notice_received_on > d.resolved_on:
            errors.append(f"dispute {d.dispute_id}: notice after resolution")

    if errors:
        raise ValueError("synthetic data invariant failures:\n  " + "\n  ".join(errors))


# --- Postgres load ----------------------------------------------------------


async def apply_schema(conn: asyncpg.Connection, schema_sql: str | None = None) -> None:
    """Apply the base schema DDL (idempotent).

    Args:
        conn: An open ``asyncpg`` connection.
        schema_sql: DDL to run; defaults to ``sql/001_schema.sql``.
    """
    sql = schema_sql if schema_sql is not None else SCHEMA_PATH.read_text(encoding="utf-8")
    await conn.execute(sql)


async def load(
    data: GenerationResult,
    *,
    dsn: str,
    truncate: bool = False,
    ensure_schema: bool = True,
) -> dict[str, int]:
    """Load synthetic accounts/transactions/disputes into Postgres.

    Idempotent per row (``ON CONFLICT DO NOTHING``). Intended for local/CI seeding.

    Args:
        data: The generated dataset.
        dsn: PostgreSQL DSN (``postgresql://...``).
        truncate: Clear the three tables first (CASCADE).
        ensure_schema: Apply ``sql/001_schema.sql`` before loading.

    Returns:
        Row counts loaded per table.
    """
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        if ensure_schema:
            await apply_schema(conn)
        if truncate:
            await conn.execute("TRUNCATE disputes, transactions, accounts CASCADE")
        await conn.executemany(
            "INSERT INTO accounts (account_id, queue_id, bank, product_type, opened_on, "
            "holder_name, holder_email, status) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) "
            "ON CONFLICT (account_id) DO NOTHING",
            [
                (
                    a.account_id,
                    a.queue_id,
                    a.bank,
                    a.product_type,
                    a.opened_on,
                    a.holder_name,
                    a.holder_email,
                    a.status,
                )
                for a in data.accounts
            ],
        )
        await conn.executemany(
            "INSERT INTO transactions (txn_id, account_id, posted_on, amount_cents, channel, "
            "merchant, statement_date) VALUES ($1,$2,$3,$4,$5,$6,$7) "
            "ON CONFLICT (txn_id) DO NOTHING",
            [
                (
                    t.txn_id,
                    t.account_id,
                    t.posted_on,
                    t.amount_cents,
                    t.channel,
                    t.merchant,
                    t.statement_date,
                )
                for t in data.transactions
            ],
        )
        await conn.executemany(
            "INSERT INTO disputes (dispute_id, account_id, txn_id, notice_received_on, "
            "notice_channel, provisional_credit_on, resolved_on, outcome) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT (dispute_id) DO NOTHING",
            [
                (
                    d.dispute_id,
                    d.account_id,
                    d.txn_id,
                    d.notice_received_on,
                    d.notice_channel,
                    d.provisional_credit_on,
                    d.resolved_on,
                    d.outcome,
                )
                for d in data.disputes
            ],
        )
    finally:
        await conn.close()
    return data.counts()


# --- CLI --------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="Generate and load synthetic account data.")
    parser.add_argument("--count", type=int, default=500, help="Number of accounts to generate.")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed.")
    parser.add_argument(
        "--as-of", type=date.fromisoformat, default=DEFAULT_AS_OF, help="Reference date."
    )
    parser.add_argument("--truncate", action="store_true", help="Clear tables before loading.")
    parser.add_argument("--dry-run", action="store_true", help="Generate and validate only; no DB.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m resolve.data.synth_accounts``."""
    args = _build_arg_parser().parse_args(argv)
    configure_logging()
    settings: Settings = get_settings()

    data = generate(args.count, seed=args.seed, as_of=args.as_of)
    log.info("synth_accounts_generated", seed=args.seed, as_of=str(args.as_of), **data.counts())

    if args.dry_run:
        return 0

    counts = asyncio.run(load(data, dsn=settings.postgres_dsn, truncate=args.truncate))
    log.info("synth_accounts_loaded", dsn=settings.postgres_dsn.split("@")[-1], **counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
