"""Database queries used by circulation services.

The repository never starts or commits a transaction.  The caller owns the
session and must establish the write transaction before invoking mutations.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.core.enums import LoanStatus
from app.models import Book, Loan, User


def get_reader(session: Session, reader_id: int) -> User | None:
    return session.scalar(
        select(User).where(
            User.id == reader_id,
            User.role == "READER",
            User.is_active.is_(True),
        )
    )


def get_book(
    session: Session,
    book_id: int | None = None,
    *,
    isbn: str | None = None,
    book_code: str | None = None,
) -> Book | None:
    statement = select(Book).where(Book.is_active.is_(True))
    if book_id is not None:
        statement = statement.where(Book.id == book_id)
    elif isbn is not None:
        statement = statement.where(Book.isbn == isbn)
    elif book_code is not None:
        statement = statement.where(Book.book_code == book_code)
    else:
        return None
    return session.scalar(statement)


def count_active_loans(session: Session, reader_id: int) -> int:
    return int(
        session.scalar(
            select(func.count(Loan.id)).where(
                Loan.reader_id == reader_id,
                Loan.status == LoanStatus.BORROWED,
            )
        )
        or 0
    )


def has_overdue_loan(session: Session, reader_id: int, as_of: date) -> bool:
    return bool(
        session.scalar(
            select(Loan.id)
            .where(
                Loan.reader_id == reader_id,
                Loan.status == LoanStatus.BORROWED,
                Loan.due_date < as_of,
            )
            .limit(1)
        )
    )


def get_loan(session: Session, loan_id: int) -> Loan | None:
    return session.scalar(select(Loan).where(Loan.id == loan_id))


def list_loans(
    session: Session,
    *,
    reader_id: int | None = None,
    loan_no: str | None = None,
    student_id: str | None = None,
    status: LoanStatus | None = None,
    overdue: bool | None = None,
    as_of: date | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[tuple[Loan, User, Book]], int]:
    conditions = []
    if reader_id is not None:
        conditions.append(Loan.reader_id == reader_id)
    if loan_no:
        conditions.append(Loan.loan_no == loan_no.strip())
    if student_id:
        conditions.append(User.student_id == student_id.strip())
    if status is not None:
        conditions.append(Loan.status == status)
    if overdue is True:
        conditions.extend(
            [Loan.status == LoanStatus.BORROWED, Loan.due_date < (as_of or date.today())]
        )
    if overdue is False:
        conditions.append(
            (Loan.status == LoanStatus.RETURNED)
            | ((Loan.status == LoanStatus.BORROWED) & (Loan.due_date >= (as_of or date.today())))
        )

    base = select(Loan, User, Book).join(User, Loan.reader_id == User.id).join(
        Book, Loan.book_id == Book.id
    )
    if conditions:
        base = base.where(and_(*conditions))
    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = list(
        session.execute(
            base.order_by(Loan.id.desc()).offset(offset).limit(limit)
        ).all()
    )
    return rows, total
