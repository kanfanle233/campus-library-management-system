"""Integration tests for the book API and service using a temporary SQLite DB."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.enums import LoanStatus, UserRole
from app.core.security import Actor, get_current_actor
from app.database import get_db
from app.database.base import Base
from app.main import app
from app.models import Book, Loan, User
from app.services.book_service import BookService
from app.api.v1 import books as books_api


@pytest.fixture()
def library(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'library.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    with session_factory() as session:
        admin = User(login_name="admin", name="管理员", password_hash="x", role=UserRole.ADMIN)
        reader = User(login_name="reader", student_id="R001", name="读者", password_hash="x")
        session.add_all([admin, reader])
        session.commit()
        admin_actor = Actor(admin.id, UserRole.ADMIN, None)
        reader_actor = Actor(reader.id, UserRole.READER, reader.student_id)

    service = BookService(session_factory=session_factory)
    monkeypatch.setattr(books_api, "book_service", service)
    app.dependency_overrides[get_current_actor] = lambda: admin_actor
    app.dependency_overrides[get_db] = lambda: session_factory()
    client = TestClient(app)
    try:
        yield client, service, session_factory, admin_actor, reader_actor
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def add_book(client: TestClient, **overrides):
    data = {
        "title": "Python 入门",
        "author": "张三",
        "isbn": "978-7-111-12345-6",
        "publisher": "出版社",
        "price": "12.30",
        "category": "编程",
        "quantity": 3,
    }
    data.update(overrides)
    response = client.post("/api/v1/books", json=data)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_query_all_fields(library):
    client, _, _, _, _ = library
    created = add_book(client)
    assert created["book_code"] == f"BK{created['id']:06d}"
    assert created["isbn"] == "9787111123456"
    assert created["price"] == "12.30"
    response = client.get("/api/v1/books", params={"title": "Python", "author": "张三"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert client.get("/api/v1/books", params={"isbn": "9787111123456"}).json()["total"] == 1
    assert client.get("/api/v1/books", params={"category": "编程"}).json()["total"] == 1
    assert client.get("/api/v1/books", params={"book_code": created["book_code"]}).json()["total"] == 1


def test_update_quantity_preserves_borrowed_copies(library):
    client, service, session_factory, admin, _ = library
    created = add_book(client, quantity=4)
    with session_factory() as session:
        book = session.get(Book, created["id"])
        book.available_quantity = 2
        session.commit()
    updated = client.patch(f"/api/v1/books/{created['id']}", json={"quantity": 5})
    assert updated.status_code == 200
    assert updated.json()["total_quantity"] == 5
    assert updated.json()["available_quantity"] == 3
    rejected = client.patch(f"/api/v1/books/{created['id']}", json={"quantity": 1})
    assert rejected.status_code == 422


def test_delete_without_loans_is_soft_delete_and_hidden_from_reader(library):
    client, _, _, _, reader = library
    created = add_book(client)
    response = client.delete(f"/api/v1/books/{created['id']}")
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    app.dependency_overrides[get_current_actor] = lambda: reader
    assert client.get("/api/v1/books").json()["total"] == 0
    assert client.get(f"/api/v1/books/{created['id']}").status_code == 404


def test_delete_borrowed_book_conflicts_and_history_remains(library):
    client, _, session_factory, _, reader = library
    created = add_book(client)
    with session_factory() as session:
        session.add(Loan(
            loan_no="LN000001", reader_id=reader.user_id, book_id=created["id"],
            borrow_date=date.today(), due_date=date.today() + timedelta(days=30),
            status=LoanStatus.BORROWED,
        ))
        session.commit()
    response = client.delete(f"/api/v1/books/{created['id']}")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BOOK_CURRENTLY_BORROWED"
    with session_factory() as session:
        assert session.query(Loan).count() == 1


def test_duplicate_isbn_and_invalid_values(library):
    client, _, _, _, _ = library
    add_book(client)
    duplicate = client.post("/api/v1/books", json={"title": "x", "author": "y", "isbn": "978 7-111-12345-6", "publisher": "p", "category": "c", "quantity": 1})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "ISBN_ALREADY_EXISTS"
    assert client.post("/api/v1/books", json={"title": "x", "author": "y", "isbn": "2", "publisher": "p", "category": "c", "quantity": -1}).status_code == 422
    assert client.post("/api/v1/books", json={"title": "x", "author": "y", "isbn": "3", "publisher": "p", "category": "c", "quantity": 1, "price": "-0.01"}).status_code == 422


def test_create_requires_publisher_category_and_quantity(library):
    client, _, _, _, _ = library
    base = {"title": "x", "author": "y", "isbn": "missing"}
    assert client.post("/api/v1/books", json=base).status_code == 422
    assert client.post("/api/v1/books", json={**base, "publisher": "", "category": "c", "quantity": 1}).status_code == 422
    assert client.post("/api/v1/books", json={**base, "publisher": "p", "category": "", "quantity": 1}).status_code == 422
    assert client.post("/api/v1/books", json={**base, "publisher": "p", "category": "c"}).status_code == 422


def test_reader_cannot_write(library):
    client, _, _, _, reader = library
    app.dependency_overrides[get_current_actor] = lambda: reader
    response = client.post("/api/v1/books", json={"title": "x", "author": "y", "isbn": "1", "publisher": "p", "category": "c", "quantity": 1})
    assert response.status_code == 403
