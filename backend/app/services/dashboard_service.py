"""Read-only aggregate queries for the dashboard."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import FineStatus, LoanStatus, UserRole
from app.models import Book, Loan, User
from app.schemas.dashboard import DashboardStats
from app.services.fine_service import format_cents


def get_stats(session: Session, *, as_of: date | None = None) -> DashboardStats:
    """Return current counts without loading every row into Python."""

    today = as_of or date.today()
    total_books = int(
        session.scalar(select(func.count(Book.id)).where(Book.is_active.is_(True))) or 0
    )
    total_copies = int(
        session.scalar(
            select(func.coalesce(func.sum(Book.total_quantity), 0)).where(Book.is_active.is_(True))
        )
        or 0
    )
    available_copies = int(
        session.scalar(
            select(func.coalesce(func.sum(Book.available_quantity), 0)).where(Book.is_active.is_(True))
        )
        or 0
    )
    total_readers = int(
        session.scalar(
            select(func.count(User.id)).where(
                User.role == UserRole.READER,
                User.is_active.is_(True),
            )
        )
        or 0
    )
    active_loans = int(
        session.scalar(select(func.count(Loan.id)).where(Loan.status == LoanStatus.BORROWED)) or 0
    )
    overdue_loans = int(
        session.scalar(
            select(func.count(Loan.id)).where(
                Loan.status == LoanStatus.BORROWED,
                Loan.due_date < today,
            )
        )
        or 0
    )
    unpaid_cents = int(
        session.scalar(
            select(func.coalesce(func.sum(Loan.fine_cents), 0)).where(
                Loan.fine_status == FineStatus.UNPAID
            )
        )
        or 0
    )
    return DashboardStats(
        total_books=total_books,
        total_copies=total_copies,
        available_copies=available_copies,
        total_readers=total_readers,
        active_loans=active_loans,
        overdue_loans=overdue_loans,
        unpaid_fines=format_cents(unpaid_cents),
    )


# Keep a descriptive alias for callers that use the noun first.
dashboard_stats = get_stats
