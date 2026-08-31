"""Integration coverage for authentication and reader management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.enums import LoanStatus, UserRole
from app.database import get_db
from app.database.base import Base
from app.main import create_app
from app.models import Book, Loan, User
from app.services.auth_service import hash_password


@pytest.fixture()
def client(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'auth-readers.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        session.add(
            User(
                login_name="admin",
                name="管理员",
                password_hash=hash_password("admin-pass"),
                role=UserRole.ADMIN,
                borrow_limit=5,
                is_active=True,
            )
        )
        session.commit()

    application = create_app()

    def override_db():
        with Session() as session:
            yield session

    application.dependency_overrides[get_db] = override_db
    with TestClient(application) as test_client:
        yield test_client, Session
    application.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_reader(client: TestClient, token: str, student_id: str = "S001") -> dict:
    response = client.post(
        "/api/v1/readers",
        headers=_auth(token),
        json={
            "name": "读者",
            "student_id": student_id,
            "contact": "13800000000",
            "borrow_limit": 2,
            "password": "reader-pass",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_and_reader_login_and_wrong_password(client):
    test_client, _ = client
    admin_token = _login(test_client, "admin", "admin-pass")
    assert test_client.get("/api/v1/auth/me", headers=_auth(admin_token)).status_code == 200
    reader = _create_reader(test_client, admin_token)
    reader_token = _login(test_client, "S001", "reader-pass")
    me = test_client.get("/api/v1/auth/me", headers=_auth(reader_token))
    assert me.status_code == 200
    assert me.json()["student_id"] == "S001"
    wrong = test_client.post(
        "/api/v1/auth/login", json={"username": "S001", "password": "wrong"}
    )
    assert wrong.status_code == 401


def test_expired_and_forged_tokens_are_rejected(client):
    test_client, _ = client
    expired = jwt.encode(
        {"sub": "1", "user_id": 1, "role": "ADMIN", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        get_settings().jwt_secret_key or "local-development-secret-change-me",
        algorithm="HS256",
    )
    assert test_client.get("/api/v1/auth/me", headers=_auth(expired)).status_code == 401
    assert test_client.get("/api/v1/auth/me", headers=_auth("forged.token.value")).status_code == 401


def test_admin_crud_duplicate_and_student_id_sync(client):
    test_client, _ = client
    admin_token = _login(test_client, "admin", "admin-pass")
    reader = _create_reader(test_client, admin_token)
    duplicate = test_client.post(
        "/api/v1/readers",
        headers=_auth(admin_token),
        json={"name": "另一人", "student_id": " S001 ", "contact": "x", "borrow_limit": 1, "password": "p"},
    )
    assert duplicate.status_code == 409
    invalid_limit = test_client.post(
        "/api/v1/readers",
        headers=_auth(admin_token),
        json={"name": "另一人", "student_id": "S002", "contact": "x", "borrow_limit": 0, "password": "p"},
    )
    assert invalid_limit.status_code == 422
    changed = test_client.patch(
        f"/api/v1/readers/{reader['id']}",
        headers=_auth(admin_token),
        json={"student_id": " S003 "},
    )
    assert changed.status_code == 200
    assert changed.json()["student_id"] == changed.json()["login_name"] == "S003"
    assert _login(test_client, "S003", "reader-pass")
    assert test_client.delete(f"/api/v1/readers/{reader['id']}", headers=_auth(admin_token)).status_code == 200
    assert test_client.post("/api/v1/auth/login", json={"username": "S003", "password": "reader-pass"}).status_code == 401


def test_reader_cannot_list_or_manage_other_readers(client):
    test_client, _ = client
    admin_token = _login(test_client, "admin", "admin-pass")
    mine = _create_reader(test_client, admin_token, "S001")
    other = _create_reader(test_client, admin_token, "S002")
    reader_token = _login(test_client, "S001", "reader-pass")
    assert test_client.get("/api/v1/readers", headers=_auth(reader_token)).status_code == 403
    assert test_client.get(f"/api/v1/readers/{mine['id']}", headers=_auth(reader_token)).status_code == 200
    assert test_client.get(f"/api/v1/readers/{other['id']}", headers=_auth(reader_token)).status_code == 403
    assert test_client.patch(f"/api/v1/readers/{mine['id']}", headers=_auth(reader_token), json={"name": "越权"}).status_code == 403
    assert test_client.delete(f"/api/v1/readers/{mine['id']}", headers=_auth(reader_token)).status_code == 403


def test_deactivate_reader_with_active_loan_is_rejected(client):
    test_client, Session = client
    admin_token = _login(test_client, "admin", "admin-pass")
    reader = _create_reader(test_client, admin_token)
    with Session() as session:
        book = Book(
            book_code="B001", title="书", author="作者", isbn="ISBN001",
            total_quantity=1, available_quantity=0,
        )
        session.add(book)
        session.flush()
        session.add(
            Loan(
                loan_no="LN000001", reader_id=reader["id"], book_id=book.id,
                due_date=datetime.now(timezone.utc).date() + timedelta(days=10),
                status=LoanStatus.BORROWED,
            )
        )
        session.commit()
    response = test_client.delete(f"/api/v1/readers/{reader['id']}", headers=_auth(admin_token))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "READER_HAS_ACTIVE_LOANS"

