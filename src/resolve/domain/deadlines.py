"""Deterministic regulatory deadline calculator (PLAN §9.6).

The LLM **never** computes dates. It extracts event dates and scenario attributes
into a typed request; this module returns :class:`Deadline` objects, each carrying
the CFR paragraph that produced it. Every rule here cites its CFR paragraph in the
docstring and stamps it on the returned deadline, so an eval or a letter can always
show which regulation drove a date.

Business days are approximated as weekdays that are not U.S. **federal** holidays
(5 U.S.C. 6103), computed by a small self-contained calendar so there is no runtime
dependency; the holiday predicate is injectable (``is_holiday``) if a different
calendar is required. Reg X explicitly excludes "legal public holidays, Saturdays
and Sundays"; Reg E defines a business day by when the institution is open for
substantially all functions — both are approximated the same way here, and the
approximation is stated in the README.

.. warning::
   Not legal advice. This calculator exists to make evaluation deterministic. Every
   constant must be checked against the eCFR text that was ingested; RESOLVE is a
   portfolio project, not a compliance system.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from functools import lru_cache

__all__ = [
    "Basis",
    "Deadline",
    "add_business_days",
    "federal_holidays",
    "is_federal_holiday",
    "reg_e_error_resolution",
    "reg_e_notice_timeliness",
    "reg_e_report_results",
    "reg_v_direct_dispute",
    "reg_x_error_resolution",
    "reg_z_billing_error",
    "reg_z_notice_timeliness",
]

# A predicate that returns True when a date is a non-working holiday.
HolidayPredicate = Callable[[date], bool]

_MONDAY = 0
_THURSDAY = 3


class Basis(StrEnum):
    """Whether a deadline counts calendar days or business days."""

    CALENDAR = "calendar"
    BUSINESS = "business"


@dataclass(frozen=True)
class Deadline:
    """One computed regulatory deadline.

    Attributes:
        name: Stable machine name, e.g. ``"determination_or_provisional_credit"``.
        due: The date the obligation is due.
        rule: The CFR citation implemented, e.g. ``"12 CFR 1005.11(c)(1)"``.
        basis: Whether the window was counted in calendar or business days.
        note: Optional human-readable caveat (approximations, alternatives).
    """

    name: str
    due: date
    rule: str
    basis: Basis
    note: str = ""


# --- federal-holiday calendar (self-contained, 5 U.S.C. 6103) ----------------


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the ``n``-th ``weekday`` (Mon=0) in ``month`` of ``year`` (1-based n)."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last ``weekday`` (Mon=0) in ``month`` of ``year``."""
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = next_month - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(holiday: date) -> date:
    """Shift a fixed-date holiday to its observed day (Sat->Fri, Sun->Mon)."""
    if holiday.weekday() == 5:  # Saturday
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:  # Sunday
        return holiday + timedelta(days=1)
    return holiday


@lru_cache(maxsize=256)
def federal_holidays(year: int) -> frozenset[date]:
    """Return the observed U.S. federal holidays in ``year`` (5 U.S.C. 6103).

    Fixed-date holidays use the federal observation rule (a Saturday holiday is
    observed on the preceding Friday, a Sunday on the following Monday — so a
    New Year's Day on a Saturday is observed on 31 December of the prior year).
    Juneteenth is included from 2021, when it became a federal holiday.
    """
    days = {
        _observed(date(year, 1, 1)),  # New Year's Day
        _observed(date(year, 7, 4)),  # Independence Day
        _observed(date(year, 11, 11)),  # Veterans Day
        _observed(date(year, 12, 25)),  # Christmas Day
        _nth_weekday(year, 1, _MONDAY, 3),  # Birthday of MLK Jr.
        _nth_weekday(year, 2, _MONDAY, 3),  # Washington's Birthday
        _last_weekday(year, 5, _MONDAY),  # Memorial Day
        _nth_weekday(year, 9, _MONDAY, 1),  # Labor Day
        _nth_weekday(year, 10, _MONDAY, 2),  # Columbus Day
        _nth_weekday(year, 11, _THURSDAY, 4),  # Thanksgiving Day
    }
    if year >= 2021:
        days.add(_observed(date(year, 6, 19)))  # Juneteenth
    return frozenset(days)


def is_federal_holiday(day: date) -> bool:
    """Return whether ``day`` is an observed federal holiday.

    Checks the next year too so a 31 December observation of New Year's Day (when
    1 January falls on a Saturday) is recognised.
    """
    return day in federal_holidays(day.year) or day in federal_holidays(day.year + 1)


def add_business_days(
    start: date, n: int, *, is_holiday: HolidayPredicate = is_federal_holiday
) -> date:
    """Return the date ``n`` business days after ``start``.

    A business day is a weekday that is not a holiday. ``n == 0`` returns ``start``
    unchanged (even if ``start`` is itself a weekend/holiday — the count simply does
    not advance).

    Args:
        start: The day the clock starts (day 0).
        n: Number of business days to add (must be >= 0).
        is_holiday: Predicate marking non-working holidays; defaults to the U.S.
            federal calendar.

    Returns:
        The resulting date.

    Raises:
        ValueError: If ``n`` is negative.
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    current, added = start, 0
    while added < n:
        current += timedelta(days=1)
        if current.weekday() < 5 and not is_holiday(current):
            added += 1
    return current


# --- Reg E §1005.11 (Electronic Fund Transfers) -----------------------------


def reg_e_notice_timeliness(statement_date: date) -> Deadline:
    """Last day a consumer may assert an EFT error: 60 calendar days.

    12 CFR 1005.11(b)(1): notice is timely if received within 60 days after the
    financial institution transmitted the statement showing the error.
    """
    return Deadline(
        name="consumer_notice_timeliness",
        due=statement_date + timedelta(days=60),
        rule="12 CFR 1005.11(b)(1)",
        basis=Basis.CALENDAR,
        note="Consumer must notify within 60 days of the statement transmittal.",
    )


def reg_e_error_resolution(
    notice_received: date,
    *,
    new_account: bool = False,
    pos_or_foreign: bool = False,
    provisional_credit_given: bool = False,
    is_holiday: HolidayPredicate = is_federal_holiday,
) -> list[Deadline]:
    """Reg E error-resolution windows. 12 CFR 1005.11(c).

    Args:
        notice_received: Date the institution received the consumer's notice.
        new_account: True within 30 days of the first deposit (longer windows).
        pos_or_foreign: True for point-of-sale debit-card or foreign-initiated
            transfers (90-day extended investigation).
        provisional_credit_given: Whether provisional credit was issued, unlocking
            the extended investigation window.
        is_holiday: Business-day holiday predicate.

    Returns:
        The determination/provisional-credit deadline, plus the extended-
        investigation deadline when provisional credit was given.
    """
    determination_bd = 20 if new_account else 10
    out = [
        Deadline(
            name="determination_or_provisional_credit",
            due=add_business_days(notice_received, determination_bd, is_holiday=is_holiday),
            rule="12 CFR 1005.11(c)(1), (c)(3)",
            basis=Basis.BUSINESS,
            note=("20 business days for accounts open <= 30 days" if new_account else ""),
        )
    ]
    if provisional_credit_given:
        days = 90 if (new_account or pos_or_foreign) else 45
        out.append(
            Deadline(
                name="extended_investigation",
                due=notice_received + timedelta(days=days),
                rule="12 CFR 1005.11(c)(2), (c)(3)",
                basis=Basis.CALENDAR,
                note="90 days for new accounts, point-of-sale, or foreign-initiated transfers.",
            )
        )
    return out


def reg_e_report_results(
    investigation_completed: date, *, is_holiday: HolidayPredicate = is_federal_holiday
) -> Deadline:
    """Report investigation results: 3 business days after completion.

    12 CFR 1005.11(c)(2)(iv): the institution must report the results to the
    consumer within three business days after completing its investigation.
    """
    return Deadline(
        name="report_results",
        due=add_business_days(investigation_completed, 3, is_holiday=is_holiday),
        rule="12 CFR 1005.11(c)(2)(iv)",
        basis=Basis.BUSINESS,
    )


# --- Reg Z §1026.13 (Truth in Lending — billing errors) ---------------------


def reg_z_notice_timeliness(statement_date: date) -> Deadline:
    """Last day to assert a billing error: 60 calendar days.

    12 CFR 1026.13(b)(1): a billing-error notice is timely if received within 60
    days after the creditor transmitted the first periodic statement reflecting it.
    """
    return Deadline(
        name="billing_error_notice_timeliness",
        due=statement_date + timedelta(days=60),
        rule="12 CFR 1026.13(b)(1)",
        basis=Basis.CALENDAR,
        note="Within 60 days of the first statement reflecting the error.",
    )


def reg_z_billing_error(
    notice_received: date, *, billing_cycle_days: int | None = None
) -> list[Deadline]:
    """Reg Z billing-error acknowledgement and resolution windows. 12 CFR 1026.13(c).

    Args:
        notice_received: Date the creditor received the billing-error notice.
        billing_cycle_days: Length of one billing cycle, if known, to compute the
            "two complete billing cycles" bound; the 90-day cap always applies.

    Returns:
        The 30-day acknowledgement deadline and the resolution deadline (two
        complete billing cycles, never more than 90 days).
    """
    acknowledgement = Deadline(
        name="acknowledgement",
        due=notice_received + timedelta(days=30),
        rule="12 CFR 1026.13(c)(1)",
        basis=Basis.CALENDAR,
    )
    cap_90 = notice_received + timedelta(days=90)
    if billing_cycle_days is not None:
        two_cycles = notice_received + timedelta(days=2 * billing_cycle_days)
        due = min(two_cycles, cap_90)
        note = "Two complete billing cycles, capped at 90 days."
    else:
        due = cap_90
        note = "90-day cap; supply billing_cycle_days for the two-cycle bound."
    resolution = Deadline(
        name="resolution",
        due=due,
        rule="12 CFR 1026.13(c)(2)",
        basis=Basis.CALENDAR,
        note=note,
    )
    return [acknowledgement, resolution]


# --- Reg X §1024.35 / §1024.36 (RESPA servicing) ----------------------------


def reg_x_error_resolution(
    received: date,
    *,
    extension: bool = False,
    is_holiday: HolidayPredicate = is_federal_holiday,
) -> list[Deadline]:
    """Reg X servicing error-resolution windows (business days).

    12 CFR 1024.35(d) acknowledgement (5 business days) and 1024.35(e)(3)(i)(C)
    response (30 business days), where "business day" excludes legal public
    holidays, Saturdays and Sundays. One 15-business-day extension is permitted
    for the response under 1024.35(e)(4).

    Args:
        received: Date the servicer received the notice of error.
        extension: Whether the permitted 15-business-day response extension applies.
        is_holiday: Business-day holiday predicate.

    Returns:
        The acknowledgement and response deadlines.
    """
    acknowledgement = Deadline(
        name="acknowledgement",
        due=add_business_days(received, 5, is_holiday=is_holiday),
        rule="12 CFR 1024.35(d)",
        basis=Basis.BUSINESS,
        note="Excludes legal public holidays, Saturdays and Sundays.",
    )
    response_bd = 45 if extension else 30
    response = Deadline(
        name="response",
        due=add_business_days(received, response_bd, is_holiday=is_holiday),
        rule="12 CFR 1024.35(e)(3)(i)(C)" + (", (e)(4)" if extension else ""),
        basis=Basis.BUSINESS,
        note="Includes one permitted 15-business-day extension." if extension else "",
    )
    return [acknowledgement, response]


# --- Reg V §1022.43 (FCRA — furnisher direct disputes) ----------------------


def reg_v_direct_dispute(
    notice_received: date, *, additional_info_provided: bool = False
) -> Deadline:
    """Furnisher direct-dispute investigation period. 12 CFR 1022.43(e)(1).

    The furnisher must complete its investigation by the date a consumer reporting
    agency would be required to under FCRA §611(a)(1): 30 calendar days from
    receipt, extended to 45 if the consumer provides additional relevant
    information during the 30-day period.
    """
    days = 45 if additional_info_provided else 30
    return Deadline(
        name="direct_dispute_investigation",
        due=notice_received + timedelta(days=days),
        rule="12 CFR 1022.43(e)(1)",
        basis=Basis.CALENDAR,
        note="30 days from receipt; +15 if the consumer provides additional information.",
    )
