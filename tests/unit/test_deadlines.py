"""Tests for :mod:`resolve.domain.deadlines` (PLAN §9.6).

Table-driven hand-computed cases (each citing the rule) plus Hypothesis property
tests. The deadline calculator must be 100% correct on these (Phase 2 DoD).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from resolve.domain import deadlines as dl

# --- federal holidays -------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2025, 1, 1), True),  # New Year's Day (Wed)
        (date(2025, 1, 20), True),  # MLK (3rd Mon Jan)
        (date(2025, 2, 17), True),  # Washington's Birthday (3rd Mon Feb)
        (date(2025, 5, 26), True),  # Memorial Day (last Mon May)
        (date(2025, 6, 19), True),  # Juneteenth
        (date(2025, 11, 27), True),  # Thanksgiving (4th Thu Nov)
        (date(2025, 12, 25), True),  # Christmas
        (date(2025, 7, 4), True),  # Independence Day (Fri)
        (date(2025, 7, 5), False),  # Saturday, not a holiday
        (date(2025, 2, 18), False),  # ordinary Tuesday
    ],
)
def test_is_federal_holiday(day: date, expected: bool) -> None:
    assert dl.is_federal_holiday(day) is expected


def test_federal_holiday_observation_rules() -> None:
    # 1 Jan 2022 was a Saturday -> observed Friday 31 Dec 2021 (belongs to 2022's
    # New Year's Day). is_federal_holiday does the cross-year lookup.
    assert date(2021, 12, 31) in dl.federal_holidays(2022)
    assert dl.is_federal_holiday(date(2021, 12, 31)) is True
    # 4 Jul 2026 is a Saturday -> observed Friday 3 Jul 2026.
    assert dl.is_federal_holiday(date(2026, 7, 3)) is True
    # Juneteenth did not exist as a federal holiday before 2021.
    assert date(2020, 6, 19) not in dl.federal_holidays(2020)


# --- add_business_days ------------------------------------------------------


def test_add_business_days_basic() -> None:
    # 10 business days from Mon 3 Feb 2025, skipping Presidents' Day (17 Feb).
    assert dl.add_business_days(date(2025, 2, 3), 10) == date(2025, 2, 18)


def test_add_business_days_zero_is_identity() -> None:
    assert dl.add_business_days(date(2025, 7, 5), 0) == date(2025, 7, 5)  # even on a Sat


def test_add_business_days_skips_holiday_and_weekend() -> None:
    # Thu 3 Jul 2025: Fri 4th is a holiday, 5-6 weekend -> next BD is Mon 7 Jul.
    assert dl.add_business_days(date(2025, 7, 3), 1) == date(2025, 7, 7)


def test_add_business_days_rejects_negative() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        dl.add_business_days(date(2025, 1, 1), -1)


# --- regulatory rules (hand-computed, cited) --------------------------------


def test_reg_e_error_resolution_standard() -> None:
    # PLAN §7.9 worked example: notice 3 Feb 2025 -> provisional credit due 18 Feb.
    out = dl.reg_e_error_resolution(date(2025, 2, 3))
    assert len(out) == 1
    (determination,) = out
    assert determination.name == "determination_or_provisional_credit"
    assert determination.due == date(2025, 2, 18)
    assert determination.rule == "12 CFR 1005.11(c)(1), (c)(3)"
    assert determination.basis is dl.Basis.BUSINESS


def test_reg_e_error_resolution_new_account_and_extension() -> None:
    out = dl.reg_e_error_resolution(
        date(2025, 2, 3), new_account=True, provisional_credit_given=True
    )
    determination, extended = out
    assert determination.due == date(2025, 3, 4)  # 20 business days
    # New account -> 90-day extended investigation from the notice date.
    assert extended.name == "extended_investigation"
    assert extended.due == date(2025, 2, 3) + timedelta(days=90)
    assert extended.rule == "12 CFR 1005.11(c)(2), (c)(3)"


def test_reg_e_extended_investigation_45_days() -> None:
    (_, extended) = dl.reg_e_error_resolution(date(2025, 2, 3), provisional_credit_given=True)
    assert extended.due == date(2025, 3, 20)  # 45 calendar days
    assert extended.basis is dl.Basis.CALENDAR


def test_reg_e_notice_timeliness() -> None:
    d = dl.reg_e_notice_timeliness(date(2025, 1, 1))
    assert d.due == date(2025, 3, 2)  # 60 calendar days
    assert d.rule == "12 CFR 1005.11(b)(1)"


def test_reg_e_report_results() -> None:
    d = dl.reg_e_report_results(date(2025, 7, 3))  # over the 4 Jul holiday + weekend
    assert d.due == date(2025, 7, 9)
    assert d.rule == "12 CFR 1005.11(c)(2)(iv)"


def test_reg_z_billing_error() -> None:
    ack, res = dl.reg_z_billing_error(date(2025, 1, 10), billing_cycle_days=30)
    assert ack.due == date(2025, 2, 9)  # 30 calendar days
    assert ack.rule == "12 CFR 1026.13(c)(1)"
    assert res.due == date(2025, 3, 11)  # two 30-day cycles < 90-day cap
    assert res.rule == "12 CFR 1026.13(c)(2)"


def test_reg_z_billing_error_caps_at_90_days() -> None:
    _, res = dl.reg_z_billing_error(date(2025, 1, 10))  # no cycle length -> 90-day cap
    assert res.due == date(2025, 4, 10)


def test_reg_z_notice_timeliness() -> None:
    assert dl.reg_z_notice_timeliness(date(2025, 1, 1)).due == date(2025, 3, 2)


def test_reg_x_error_resolution() -> None:
    ack, resp = dl.reg_x_error_resolution(date(2025, 2, 3))
    assert ack.due == date(2025, 2, 10)  # 5 business days
    assert ack.rule == "12 CFR 1024.35(d)"
    assert resp.due == date(2025, 3, 18)  # 30 business days
    assert resp.rule == "12 CFR 1024.35(e)(3)(i)(C)"


def test_reg_x_error_resolution_with_extension() -> None:
    _, resp = dl.reg_x_error_resolution(date(2025, 2, 3), extension=True)
    assert resp.due == date(2025, 4, 8)  # 45 business days
    assert "(e)(4)" in resp.rule


def test_reg_v_direct_dispute() -> None:
    d = dl.reg_v_direct_dispute(date(2025, 2, 3))
    assert d.due == date(2025, 3, 5)  # 30 calendar days
    assert d.rule == "12 CFR 1022.43(e)(1)"
    assert dl.reg_v_direct_dispute(date(2025, 2, 3), additional_info_provided=True).due == date(
        2025, 3, 20
    )  # +15


# --- Hypothesis properties --------------------------------------------------

_DATES = st.dates(min_value=date(2012, 1, 1), max_value=date(2030, 12, 31))
_COUNTS = st.integers(min_value=0, max_value=120)


@given(start=_DATES, n=_COUNTS)
def test_business_day_result_is_never_earlier(start: date, n: int) -> None:
    assert dl.add_business_days(start, n) >= start


@given(start=_DATES, n=st.integers(min_value=1, max_value=120))
def test_business_day_result_is_a_business_day(start: date, n: int) -> None:
    result = dl.add_business_days(start, n)
    assert result.weekday() < 5
    assert not dl.is_federal_holiday(result)


@given(start=_DATES, n=_COUNTS)
def test_business_days_strictly_monotonic_in_n(start: date, n: int) -> None:
    assert dl.add_business_days(start, n + 1) > dl.add_business_days(start, n)


@given(start1=_DATES, start2=_DATES, n=_COUNTS)
def test_business_days_monotonic_in_start(start1: date, start2: date, n: int) -> None:
    if start1 <= start2:
        assert dl.add_business_days(start1, n) <= dl.add_business_days(start2, n)


@given(start=_DATES, n=_COUNTS, extra=_DATES)
def test_adding_a_holiday_never_makes_it_earlier(start: date, n: int, extra: date) -> None:
    def with_extra(day: date) -> bool:
        return dl.is_federal_holiday(day) or day == extra

    assert dl.add_business_days(start, n, is_holiday=with_extra) >= dl.add_business_days(start, n)


@given(notice=_DATES, shift=st.integers(min_value=0, max_value=60))
def test_reg_e_deadline_monotonic_in_notice(notice: date, shift: int) -> None:
    later = notice + timedelta(days=shift)
    assert dl.reg_e_error_resolution(later)[0].due >= dl.reg_e_error_resolution(notice)[0].due
