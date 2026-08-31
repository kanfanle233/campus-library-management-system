"""Populate an empty local database with deterministic demonstration data.

The records are synthetic.  The administrator password is ``admin123`` for
local demonstration only and must not be used outside that environment.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func, select

from app.core.enums import FineStatus, LoanStatus, UserRole
from app.database import begin_immediate, init_db, session_scope
from app.models import Book, Loan, User
from app.schemas.book import normalize_isbn
from app.services.auth_service import hash_password


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _read_csv(name: str) -> list[dict[str, str]]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _as_of(value: date | str | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def seed_database(as_of: date | str | None = None) -> bool:
    """Insert demonstration rows once; return whether rows were inserted."""

    today = _as_of(as_of)
    init_db()
    with session_scope() as session:
        begin_immediate(session)
        # Any existing row means this is an application database.  Leaving it
        # untouched prevents a demo command from ever resetting user data.
        if any(session.scalar(select(func.count()).select_from(model)) for model in (User, Book, Loan)):
            print("已存在，跳过")
            session.rollback()
            return False

        admin = User(
            login_name="admin",
            name="DEMO管理员",
            password_hash=hash_password("admin123"),
            role=UserRole.ADMIN,
            borrow_limit=5,
            is_active=True,
        )
        session.add(admin)
        for row in _read_csv("seed_readers.csv"):
            session.add(User(
                login_name=row["student_id"],
                student_id=row["student_id"],
                name=row["name"],
                contact=row["contact"],
                password_hash=hash_password("demo123"),
                role=UserRole.READER,
                borrow_limit=int(row["borrow_limit"]),
                is_active=True,
            ))
        session.flush()
        readers = {u.student_id: u.id for u in session.scalars(select(User)).all() if u.student_id}

        for index, row in enumerate(_read_csv("seed_books.csv"), start=1):
            session.add(Book(
                book_code=f"PENDING-{index:02d}",
                title=row["title"], author=row["author"], isbn=normalize_isbn(row["isbn"]),
                publisher=row["publisher"], price_cents=int(row["price_cents"]),
                category=row["category"], total_quantity=int(row["total_quantity"]),
                available_quantity=int(row["total_quantity"]), is_active=True,
            ))
        session.flush()
        books = {book.id: book for book in session.scalars(select(Book)).all()}
        for book in books.values():
            book.book_code = f"BK{book.id:06d}"

        # (reader, book number, days before as_of borrowed, returned, days
        # until return).  Seven active and five returned records cover normal,
        # overdue, returned, and zero-stock cases.
        plans = [
            ("DEMO-S001", 1, 5, False, None),
            ("DEMO-S002", 2, 45, False, None),
            ("DEMO-S003", 3, 40, False, None),
            ("DEMO-S004", 4, 8, False, None),
            ("DEMO-S005", 5, 12, False, None),
            ("DEMO-S006", 6, 60, False, None),
            ("DEMO-S007", 7, 4, False, None),
            ("DEMO-S008", 8, 50, True, 15),
            ("DEMO-S001", 9, 50, True, 20),
            ("DEMO-S002", 10, 40, True, 15),
            ("DEMO-S003", 11, 35, True, 5),
            ("DEMO-S004", 12, 25, True, 10),
        ]
        for index, (student, number, age, returned, return_age) in enumerate(plans, start=1):
            book = books[number]
            borrow_date = today - timedelta(days=age)
            due_date = borrow_date + timedelta(days=30)
            return_date = today - timedelta(days=return_age) if returned and return_age is not None else None
            overdue_days = max(((return_date or today) - due_date).days, 0)
            session.add(Loan(
                loan_no=f"PENDING-{index:02d}", reader_id=readers[student], book_id=book.id,
                borrow_date=borrow_date, due_date=due_date, return_date=return_date,
                status=LoanStatus.RETURNED if returned else LoanStatus.BORROWED,
                # Active loans only show a calculated estimate in read APIs.
                # A fine is registered after the book is actually returned.
                fine_cents=overdue_days * 10 if returned else 0,
                fine_status=FineStatus.UNPAID if returned and overdue_days else FineStatus.NONE,
            ))
            if not returned:
                book.available_quantity -= 1
        session.flush()
        for loan in session.scalars(select(Loan)).all():
            loan.loan_no = f"LN{loan.id:06d}"
        session.commit()
    print("演示数据已写入：1 个管理员、8 名读者、15 本图书、12 条借阅记录")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="写入本地图书管理系统演示数据")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today(), metavar="YYYY-MM-DD")
    args = parser.parse_args()
    seed_database(args.as_of)


if __name__ == "__main__":
    main()
