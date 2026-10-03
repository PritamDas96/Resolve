"""Unit tests for :mod:`resolve.data.synth_accounts` (offline — no database)."""

from __future__ import annotations

from datetime import date

import pytest

from resolve import config
from resolve.data import synth_accounts as sa
from resolve.data.synth_accounts import GenerationResult

BANK_STRINGS = {strings[0] for strings in config.BANKS.values()}

AS_OF = date(2026, 1, 1)


def _generate(count: int = 200, seed: int = 7) -> GenerationResult:
    return sa.generate(count, seed=seed, as_of=AS_OF)


# --- scenarios --------------------------------------------------------------


def test_committed_scenarios_reference_known_generators() -> None:
    scenarios = sa.load_scenarios()
    assert scenarios
    assert {s.generator for s in scenarios} <= set(sa._GENERATORS)
    assert {s.family for s in scenarios} == {"deposits", "cards", "mortgage", "credit_reporting"}


# --- generation -------------------------------------------------------------


def test_generation_is_deterministic() -> None:
    first = _generate()
    second = _generate()
    assert first.model_dump() == second.model_dump()


def test_generation_count_and_unique_ids() -> None:
    data = _generate(count=150)
    assert len(data.accounts) == 150
    assert len({a.account_id for a in data.accounts}) == 150
    assert len({t.txn_id for t in data.transactions}) == len(data.transactions)
    assert len({d.dispute_id for d in data.disputes}) == len(data.disputes)


def test_accounts_queue_matches_family_and_product_type_valid() -> None:
    data = _generate()
    valid_products = {"checking", "savings", "credit_card", "mortgage"}
    valid_queues = {"deposits", "cards", "mortgage", "credit_reporting"}
    for a in data.accounts:
        assert a.queue_id in valid_queues
        assert a.product_type in valid_products
        assert a.bank in BANK_STRINGS


def test_all_families_represented_with_enough_accounts() -> None:
    data = _generate(count=400)
    seen = {a.queue_id for a in data.accounts}
    assert seen == {"deposits", "cards", "mortgage", "credit_reporting"}


# --- invariants -------------------------------------------------------------


def test_generated_data_passes_invariants() -> None:
    # generate() validates internally; calling again must not raise
    sa.validate_invariants(_generate(count=300))


def test_mortgage_has_payments_no_disputes_and_reg_v_has_dispute_without_txn() -> None:
    data = sa.generate(300, seed=3, as_of=AS_OF)
    by_account = {a.account_id: a for a in data.accounts}

    mortgage_accounts = {a.account_id for a in data.accounts if a.queue_id == "mortgage"}
    mortgage_disputes = [d for d in data.disputes if d.account_id in mortgage_accounts]
    assert mortgage_disputes == []  # Reg X servicing has no transaction disputes

    cr_accounts = {a.account_id for a in data.accounts if a.queue_id == "credit_reporting"}
    cr_disputes = [d for d in data.disputes if d.account_id in cr_accounts]
    assert cr_disputes  # at least some
    assert all(d.txn_id is None for d in cr_disputes)  # furnisher disputes have no txn
    assert all(by_account[d.account_id].queue_id == "credit_reporting" for d in cr_disputes)


def test_dispute_date_chain_is_monotonic() -> None:
    data = _generate(count=300)
    txn_by_id = {t.txn_id: t for t in data.transactions}
    for d in data.disputes:
        if d.txn_id is not None:
            assert txn_by_id[d.txn_id].statement_date <= d.notice_received_on
        if d.provisional_credit_on is not None:
            assert d.notice_received_on <= d.provisional_credit_on
        if d.resolved_on is not None:
            assert d.notice_received_on <= d.resolved_on


def test_validate_invariants_detects_dangling_and_bad_dates() -> None:
    bad = GenerationResult(
        accounts=[
            sa.Account(
                account_id="ACC-1",
                queue_id="deposits",
                bank="JPMORGAN CHASE & CO.",
                product_type="checking",
                opened_on=date(2020, 1, 1),
                holder_name="Jane Doe",
                holder_email="jane@example.com",
                status="open",
            )
        ],
        transactions=[
            sa.Transaction(
                txn_id="TXN-1",
                account_id="ACC-MISSING",  # dangling FK
                posted_on=date(2026, 2, 1),
                amount_cents=0,  # zero amount
                channel="pos",
                merchant="X",
                statement_date=date(2026, 1, 1),  # statement before posted
            )
        ],
        disputes=[],
    )
    with pytest.raises(ValueError, match="invariant failures"):
        sa.validate_invariants(bad)


def test_unknown_generator_raises() -> None:
    bogus = [sa.Scenario(name="x", family="deposits", generator="does_not_exist")]
    with pytest.raises(ValueError, match="unknown generators"):
        sa.generate(5, scenarios=bogus)
