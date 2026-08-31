"""Read-only aggregates used by the analytics page."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.enums import LoanStatus
from app.models import Book, Loan
from app.schemas.analytics import (
    AnalyticsResponse,
    CategoryStat,
    DailyTrend,
    OverdueBucket,
    PopularBook,
)


BUCKET_LABELS = ("1–7 天", "8–30 天", "31 天以上")


def get_analytics(
    session: Session,
    *,
    days: int = 30,
    as_of: date | None = None,
) -> AnalyticsResponse:
    """Return bounded, deterministic aggregates for a requested time window."""

    today = as_of or date.today()
    start = today - timedelta(days=days - 1)

    borrowed_by_day = {
        day: int(count)
        for day, count in session.execute(
            select(Loan.borrow_date, func.count(Loan.id))
            .where(Loan.borrow_date.between(start, today))
            .group_by(Loan.borrow_date)
        ).all()
    }
    returned_by_day = {
        day: int(count)
        for day, count in session.execute(
            select(Loan.return_date, func.count(Loan.id))
            .where(
                Loan.return_date.is_not(None),
                Loan.return_date.between(start, today),
            )
            .group_by(Loan.return_date)
        ).all()
    }
    trends = [
        DailyTrend(
            date=start + timedelta(days=offset),
            borrowed=borrowed_by_day.get(start + timedelta(days=offset), 0),
            returned=returned_by_day.get(start + timedelta(days=offset), 0),
        )
        for offset in range(days)
    ]

    category_rows = session.execute(
        select(
            func.coalesce(Book.category, "未分类"),
            func.count(Book.id),
            func.coalesce(func.sum(Book.total_quantity), 0),
        )
        .where(Book.is_active.is_(True))
        .group_by(func.coalesce(Book.category, "未分类"))
        .order_by(func.coalesce(func.sum(Book.total_quantity), 0).desc(), func.coalesce(Book.category, "未分类"))
    ).all()
    categories = [
        CategoryStat(category=str(category), title_count=int(title_count), copy_count=int(copy_count))
        for category, title_count, copy_count in category_rows
    ]

    popular_rows = session.execute(
        select(Book.id, Book.book_code, Book.title, func.count(Loan.id).label("borrow_count"))
        .join(Loan, Loan.book_id == Book.id)
        .where(Loan.borrow_date.between(start, today))
        .group_by(Book.id, Book.book_code, Book.title)
        .order_by(func.count(Loan.id).desc(), Book.id.asc())
        .limit(5)
    ).all()
    popular = [
        PopularBook(
            book_id=int(book_id),
            book_code=str(book_code),
            title=str(title),
            borrow_count=int(borrow_count),
        )
        for book_id, book_code, title, borrow_count in popular_rows
    ]

    bucket = case(
        (Loan.due_date >= today - timedelta(days=7), BUCKET_LABELS[0]),
        (Loan.due_date >= today - timedelta(days=30), BUCKET_LABELS[1]),
        else_=BUCKET_LABELS[2],
    )
    overdue_rows = session.execute(
        select(bucket, func.count(Loan.id))
        .where(Loan.status == LoanStatus.BORROWED, Loan.due_date < today)
        .group_by(bucket)
    ).all()
    overdue_counts = {str(label): int(count) for label, count in overdue_rows}
    overdue = [OverdueBucket(label=label, count=overdue_counts.get(label, 0)) for label in BUCKET_LABELS]

    return AnalyticsResponse(
        as_of=today,
        start_date=start,
        end_date=today,
        daily_trends=trends,
        category_distribution=categories,
        popular_books=popular,
        overdue_buckets=overdue,
    )
