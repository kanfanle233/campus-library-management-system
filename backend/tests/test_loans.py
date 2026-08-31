"""Acceptance tests for the atomic borrowing and return rules."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.enums import FineStatus, LoanStatus, UserRole
from app.core.exceptions import ConflictError, ForbiddenError
from app.core.security import Actor
from app.database import get_db
from app.database.base import Base
from app.core.security import get_current_actor
from app.main import create_app
from app.models import Book, User
from app.services import loan_service


@pytest.fixture()
def library(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'loans.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    with SessionFactory() as session:
        admin = User(
            login_name="admin",
            name="管理员",
            password_hash="x",
            role=UserRole.ADMIN,
            borrow_limit=5,
        )
        reader = User(
            login_name="R001",
            student_id="R001",
            name="读者",
            password_hash="x",
            role=UserRole.READER,
            borrow_limit=2,
        )
        books = [
            Book(
                book_code=f"B00{index}",
                title=f"书{index}",
                author="作者",
                isbn=f"ISBN{index}",
                publisher="出版社",
                category="测试",
                total_quantity=1,
                available_quantity=1,
            )
            for index in range(1, 4)
        ]
        session.add_all([admin, reader, *books])
        session.commit()
        admin_actor = Actor(admin.id, UserRole.ADMIN, None)
        reader_actor = Actor(reader.id, UserRole.READER, reader.student_id)
        book_ids = [book.id for book in books]

    # The production service uses the application session factory. Replacing
    # that one symbol keeps these tests on an isolated temporary database.
    monkeypatch.setattr(loan_service, "SessionLocal", SessionFactory)
    try:
        yield SessionFactory, admin_actor, reader_actor, book_ids
    finally:
        engine.dispose()


def test_borrow_checks_rules_and_updates_stock_atomically(library):
    _session, admin, reader, book_ids = library
    first = loan_service.borrow_book(
        reader, book_id=book_ids[0], as_of=date(2026, 1, 1)
    )
    assert first.loan_no == "LN000001"
    assert first.borrow_date == date(2026, 1, 1)
    assert first.due_date == date(2026, 1, 31)
    assert first.fine_amount == "0.00"

    with pytest.raises(ConflictError) as out_of_stock:
        loan_service.borrow_book(reader, book_id=book_ids[0], as_of=date(2026, 1, 2))
    assert out_of_stock.value.code == "BOOK_OUT_OF_STOCK"

    with _session() as session:
        book = session.get(Book, book_ids[0])
        assert book is not None
        assert book.available_quantity == 0
        assert session.query(Book).count() == 3

    # An administrator can perform the same circulation action for a reader.
    second = loan_service.borrow_book(
        admin,
        book_id=book_ids[1],
        reader_id=reader.user_id,
        as_of=date(2026, 1, 2),
    )
    assert second.reader_id == reader.user_id

    with pytest.raises(ConflictError) as limit:
        loan_service.borrow_book(reader, book_id=book_ids[2], as_of=date(2026, 1, 2))
    assert limit.value.code == "READER_BORROW_LIMIT_REACHED"


def test_overdue_blocks_new_borrow_and_return_calculates_fine(library):
    SessionFactory, admin, reader, book_ids = library
    loan = loan_service.borrow_book(
        reader, book_id=book_ids[0], as_of=date(2026, 1, 1)
    )
    # Move the due date into the past while keeping the loan active. This
    # models a real loan that has crossed its deadline.
    with SessionFactory() as session:
        row = session.get(loan_service.Loan, loan.id)
        assert row is not None
        row.due_date = date(2026, 1, 2)
        session.commit()

    with pytest.raises(ConflictError) as overdue:
        loan_service.borrow_book(reader, book_id=book_ids[1], as_of=date(2026, 1, 3))
    assert overdue.value.code == "READER_HAS_OVERDUE_LOANS"

    preview = loan_service.get_return_preview(reader, loan.id, as_of=date(2026, 1, 5))
    assert preview.overdue_days == 3
    assert preview.fine_amount == "0.30"
    assert preview.fine_status is FineStatus.UNPAID

    returned = loan_service.return_book(reader, loan.id, as_of=date(2026, 1, 5))
    assert returned.status is LoanStatus.RETURNED
    assert returned.return_date == date(2026, 1, 5)
    assert returned.overdue_days == 3
    assert returned.fine_amount == "0.30"
    assert returned.fine_status is FineStatus.UNPAID

    with SessionFactory() as session:
        book = session.get(Book, book_ids[0])
        assert book is not None
        assert book.available_quantity == book.total_quantity

    paid = loan_service.mark_fine_paid(admin, loan.id)
    assert paid.fine_status is FineStatus.PAID
    with pytest.raises(ConflictError) as repeated:
        loan_service.return_book(reader, loan.id, as_of=date(2026, 1, 6))
    assert repeated.value.code == "LOAN_ALREADY_RETURNED"


def test_borrow_accepts_book_code_and_isbn_identifiers(library):
    _session, _admin, reader, book_ids = library
    by_code = loan_service.borrow_book(
        reader, book_code=" B001 ", as_of=date(2026, 1, 1)
    )
    assert by_code.book_id == book_ids[0]
    loan_service.return_book(reader, by_code.id, as_of=date(2026, 1, 1))

    by_isbn = loan_service.borrow_book(
        reader, isbn=" ISBN-2 ", as_of=date(2026, 1, 1)
    )
    assert by_isbn.book_id == book_ids[1]


def test_list_and_owner_checks(library):
    _session, admin, reader, book_ids = library
    loan = loan_service.borrow_book(reader, book_id=book_ids[0], as_of=date(2026, 1, 1))
    listed = loan_service.list_loans(reader, status=LoanStatus.BORROWED, as_of=date(2026, 1, 2))
    assert listed.total == 1
    assert listed.items[0].loan_no == loan.loan_no
    assert loan_service.get_loan(admin, loan.id).loan_no == loan.loan_no

    other = Actor(reader.user_id + 99, UserRole.READER, "OTHER")
    with pytest.raises(ForbiddenError):
        loan_service.get_loan(other, loan.id)


def test_loan_routes_return_receipt_and_structured_errors(library):
    SessionFactory, _admin, reader, book_ids = library
    application = create_app()

    def db_override():
        with SessionFactory() as session:
            yield session

    application.dependency_overrides[get_db] = db_override
    application.dependency_overrides[get_current_actor] = lambda: reader
    try:
        with TestClient(application) as client:
            borrowed = client.post("/api/v1/loans/borrow", json={"book_code": "B001"})
            assert borrowed.status_code == 201, borrowed.text
            loan_id = borrowed.json()["id"]
            receipt = client.get(f"/api/v1/loans/{loan_id}/receipt")
            assert receipt.status_code == 200
            assert receipt.json()["loan_no"] == borrowed.json()["loan_no"]

            repeated = client.post("/api/v1/loans/{0}/return".format(loan_id))
            assert repeated.status_code == 200
            second_return = client.post("/api/v1/loans/{0}/return".format(loan_id))
            assert second_return.status_code == 409
            assert second_return.json()["detail"]["code"] == "LOAN_ALREADY_RETURNED"
    finally:
        application.dependency_overrides.clear()
