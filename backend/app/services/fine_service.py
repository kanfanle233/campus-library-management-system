"""Pure date and money calculations for circulation."""

from __future__ import annotations

from datetime import date

DAILY_FINE_CENTS = 10


def calculate_overdue_days(due_date: date, as_of: date) -> int:
    """Count whole calendar days after the due date."""

    return max((as_of - due_date).days, 0)


def calculate_fine_cents(due_date: date, as_of: date) -> int:
    return calculate_overdue_days(due_date, as_of) * DAILY_FINE_CENTS


def format_cents(cents: int) -> str:
    """Return a stable two-decimal amount without floating-point arithmetic."""

    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    return f"{sign}{absolute // 100}.{absolute % 100:02d}"

