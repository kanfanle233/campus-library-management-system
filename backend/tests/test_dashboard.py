"""Dashboard aggregation checks used by the frontend home page."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.enums import FineStatus, LoanStatus, UserRole
from app.database.base import Base
from app.models import Book, Loan, User
from app.services.analytics_service import get_analytics
from app.services.dashboard_service import get_stats


def test_dashboard_counts_active_inventory_readers_and_fines(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'dashboard.sqlite3'}")
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionFactory() as session:
        admin = User(login_name="admin", name="管理员", password_hash="x", role=UserRole.ADMIN)
        reader = User(
            login_name="R001",
            student_id="R001",
            name="读者",
            password_hash="x",
            role=UserRole.READER,
            is_active=True,
        )
        disabled = User(
            login_name="R002",
            student_id="R002",
            name="停用读者",
            password_hash="x",
            role=UserRole.READER,
            is_active=False,
        )
        book = Book(
            book_code="B001",
            title="在馆图书",
            author="作者",
            isbn="ISBN-1",
            publisher="出版社",
            category="测试",
            total_quantity=2,
            available_quantity=1,
        )
        another = Book(
            book_code="B002",
            title="第二本",
            author="作者",
            isbn="ISBN-2",
            publisher="出版社",
            category="测试",
            total_quantity=1,
            available_quantity=1,
        )
        hidden = Book(
            book_code="B003",
            title="已下架",
            author="作者",
            isbn="ISBN-3",
            publisher="出版社",
            category="测试",
            total_quantity=10,
            available_quantity=10,
            is_active=False,
        )
        session.add_all([admin, reader, disabled, book, another, hidden])
        session.flush()
        session.add_all(
            [
                Loan(
                    loan_no="LN000001",
                    reader_id=reader.id,
                    book_id=book.id,
                    borrow_date=date(2026, 1, 1),
                    due_date=date(2026, 1, 31),
                    status=LoanStatus.BORROWED,
                ),
                Loan(
                    loan_no="LN000002",
                    reader_id=reader.id,
                    book_id=another.id,
                    borrow_date=date(2026, 1, 1),
                    due_date=date(2026, 1, 10),
                    return_date=date(2026, 1, 20),
                    status=LoanStatus.RETURNED,
                    fine_cents=100,
                    fine_status=FineStatus.UNPAID,
                ),
            ]
        )
        session.commit()

        stats = get_stats(session, as_of=date(2026, 2, 1))
        assert stats.model_dump() == {
            "total_books": 2,
            "total_copies": 3,
            "available_copies": 2,
            "total_readers": 1,
            "active_loans": 1,
            "overdue_loans": 1,
            "unpaid_fines": "1.00",
        }
    engine.dispose()


def test_analytics_zero_fills_trends_and_orders_aggregates(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'analytics.sqlite3'}")
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionFactory() as session:
        reader = User(
            login_name="R001", student_id="R001", name="读者", password_hash="x",
            role=UserRole.READER, is_active=True,
        )
        first = Book(
            book_code="B001", title="第一本", author="作者", isbn="ISBN-1",
            category="算法", total_quantity=3, available_quantity=2,
        )
        second = Book(
            book_code="B002", title="第二本", author="作者", isbn="ISBN-2",
            category="算法", total_quantity=1, available_quantity=1,
        )
        third = Book(
            book_code="B003", title="第三本", author="作者", isbn="ISBN-3",
            category="文学", total_quantity=2, available_quantity=2,
        )
        session.add_all([reader, first, second, third])
        session.flush()
        session.add_all([
            Loan(
                loan_no="LN000001", reader_id=reader.id, book_id=first.id,
                borrow_date=date(2026, 2, 10), due_date=date(2026, 3, 12),
                status=LoanStatus.BORROWED,
            ),
            Loan(
                loan_no="LN000002", reader_id=reader.id, book_id=first.id,
                borrow_date=date(2026, 2, 5), due_date=date(2026, 3, 7),
                return_date=date(2026, 2, 8), status=LoanStatus.RETURNED,
            ),
            Loan(
                loan_no="LN000003", reader_id=reader.id, book_id=second.id,
                borrow_date=date(2026, 1, 1), due_date=date(2026, 1, 5),
                status=LoanStatus.BORROWED,
            ),
            Loan(
                loan_no="LN000004", reader_id=reader.id, book_id=third.id,
                borrow_date=date(2026, 1, 20), due_date=date(2026, 2, 5),
                status=LoanStatus.BORROWED,
            ),
        ])
        session.commit()

        result = get_analytics(session, days=7, as_of=date(2026, 2, 10))

        assert result.start_date == date(2026, 2, 4)
        assert result.end_date == date(2026, 2, 10)
        assert len(result.daily_trends) == 7
        assert result.daily_trends[0].borrowed == 0
        assert result.daily_trends[1].borrowed == 1
        assert result.daily_trends[4].returned == 1
        assert [(item.title, item.borrow_count) for item in result.popular_books] == [("第一本", 2)]
        assert [(item.category, item.copy_count) for item in result.category_distribution] == [("算法", 4), ("文学", 2)]
        assert [item.count for item in result.overdue_buckets] == [1, 0, 1]
    engine.dispose()
