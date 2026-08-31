"""Integration tests for administrator CSV file operations."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from io import StringIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.enums import LoanStatus, UserRole
from app.core.security import Actor, get_current_actor
from app.database import get_db
from app.database.base import Base
from app.main import app
from app.models import Book, Loan, User


@pytest.fixture()
def library(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'files.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    with session_factory() as session:
        admin = User(login_name="admin", name="管理员", password_hash="x", role=UserRole.ADMIN)
        reader = User(
            login_name="S001", student_id="S001", name="张三", contact="13800000000",
            password_hash="secret-hash", role=UserRole.READER,
        )
        session.add_all([admin, reader])
        session.commit()
        admin_actor = Actor(admin.id, UserRole.ADMIN, None)
        reader_actor = Actor(reader.id, UserRole.READER, reader.student_id)

    def db_override():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_actor] = lambda: admin_actor
    client = TestClient(app)
    try:
        yield client, session_factory, admin_actor, reader_actor
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def books_csv(*rows: list[str], bom: bool = False) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["title", "author", "isbn", "publisher", "price", "total_quantity", "category"])
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig" if bom else "utf-8")


def quantity_alias_csv() -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["title", "author", "isbn", "publisher", "price", "quantity", "category"])
    writer.writerow(["数量别名", "作者", "Q-1", "社", "1", "1", "类"])
    return output.getvalue().encode("utf-8")


def test_import_success_supports_bom_and_csv_quoting(library):
    client, session_factory, _, _ = library
    response = client.post(
        "/api/v1/files/books/import",
        files={"file": ("books.csv", books_csv(
            ["中文,书", "作者", "978-1", "出版社", "12.30", "2", "分类"],
            ["带换行", "作者\n二", "978-2", '社"名', "0", "1", "分类"],
            bom=True,
        ), "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"total": 2, "success": 2, "failed": 0, "errors": []}
    with session_factory() as session:
        books = session.query(Book).order_by(Book.id).all()
        assert [(book.book_code, book.title, book.isbn) for book in books] == [
            ("BK000001", "中文,书", "9781"),
            ("BK000002", "带换行", "9782"),
        ]


def test_import_accepts_quantity_column_alias(library):
    client, session_factory, _, _ = library
    response = client.post(
        "/api/v1/files/books/import",
        files={"file": ("books.csv", quantity_alias_csv(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    with session_factory() as session:
        book = session.query(Book).filter(Book.isbn == "Q1").one()
        assert book.total_quantity == book.available_quantity == 1


def test_import_reports_empty_or_wrong_header_as_row_one(library):
    client, session_factory, _, _ = library
    empty = client.post(
        "/api/v1/files/books/import",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert empty.status_code == 422
    assert empty.json()["errors"][0]["row"] == 1

    wrong_header = client.post(
        "/api/v1/files/books/import",
        files={"file": ("wrong.csv", b"wrong,header\r\nvalue\r\n", "text/csv")},
    )
    assert wrong_header.status_code == 422
    assert wrong_header.json()["errors"][0]["row"] == 1
    with session_factory() as session:
        assert session.query(Book).count() == 0


def test_duplicate_isbn_rolls_back_the_entire_batch(library):
    client, session_factory, _, _ = library
    first = client.post(
        "/api/v1/files/books/import",
        files={"file": ("books.csv", books_csv(["已有", "作者", "DUP", "社", "1", "1", "类"]), "text/csv")},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/v1/files/books/import",
        files={"file": ("books.csv", books_csv(
            ["新书", "作者", "NEW", "社", "1", "1", "类"],
            ["重复", "作者", "DUP", "社", "1", "1", "类"],
        ), "text/csv")},
    )
    assert second.status_code == 422
    body = second.json()
    assert body["success"] == 0
    assert body["errors"][0]["row"] == 3
    with session_factory() as session:
        assert session.query(Book).count() == 1
        assert session.query(Book).filter(Book.isbn == "NEW").count() == 0


def test_invalid_rows_are_reported_with_original_rows(library):
    client, session_factory, _, _ = library
    response = client.post(
        "/api/v1/files/books/import",
        files={"file": ("books.csv", books_csv(
            ["有效", "作者", "OK", "社", "1", "1", "类"],
            ["", "作者", "BAD", "社", "-1", "-2", "类"],
        ), "text/csv")},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["total"] == 2
    assert body["success"] == 0
    assert body["failed"] == 1
    assert body["errors"][0]["row"] == 3
    with session_factory() as session:
        assert session.query(Book).count() == 0


def test_exports_filter_password_hash_and_escape_formulas(library):
    client, session_factory, _, _ = library
    with session_factory() as session:
        session.add(Book(
            book_code="BK000001", title="=公式", author="作者", isbn="E1", publisher="社",
            price_cents=100, total_quantity=1, available_quantity=1, category="类",
        ))
        session.flush()
        reader = session.query(User).filter(User.student_id == "S001").one()
        book = session.query(Book).filter(Book.isbn == "E1").one()
        session.add(Loan(
            loan_no="LN000001", reader_id=reader.id, book_id=book.id,
            borrow_date=date.today() - timedelta(days=30), due_date=date.today() - timedelta(days=2),
            status=LoanStatus.BORROWED,
        ))
        session.commit()

    book_export = client.get("/api/v1/files/books/export")
    assert book_export.status_code == 200
    assert book_export.content.startswith(b"\xef\xbb\xbf")
    assert b"'=\xe5\x85\xac\xe5\xbc\x8f" in book_export.content
    reader_export = client.get("/api/v1/files/readers/export")
    assert b"password_hash" not in reader_export.content
    assert b"secret-hash" not in reader_export.content
    loan_export = client.get("/api/v1/files/loans/export")
    assert b"LN000001" in loan_export.content
    assert b"S001" in loan_export.content
    assert b"BK000001" in loan_export.content
    assert b"0.20" in loan_export.content
    assert b",NONE\r\n" in loan_export.content
    assert b"FineStatus.NONE" not in loan_export.content


def test_reader_cannot_export_or_import(library):
    client, _, _, reader_actor = library
    app.dependency_overrides[get_current_actor] = lambda: reader_actor
    assert client.get("/api/v1/files/books/export").status_code == 403
    response = client.post(
        "/api/v1/files/books/import",
        files={"file": ("books.csv", books_csv(["书", "作者", "1", "社", "1", "1", "类"]), "text/csv")},
    )
    assert response.status_code == 403
