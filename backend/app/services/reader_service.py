"""Reader management use cases."""

from __future__ import annotations

from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import LoanStatus, UserRole
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.database import begin_immediate
from app.models.loan import Loan
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.reader import ReaderCreate, ReaderUpdate
from app.services.auth_service import hash_password


def _begin_write(session: Session) -> None:
    """Acquire SQLite's writer lock before changing a reader row."""

    # A dependency which loaded the actor has an open read transaction. End it
    # before BEGIN IMMEDIATE; all writes in this service then share one lock.
    if session.in_transaction():
        session.rollback()
    begin_immediate(session)


def _duplicate_student_id() -> ConflictError:
    return ConflictError(
        "DUPLICATE_STUDENT_ID",
        "学号已存在",
        field="student_id",
    )


def list_readers(session: Session) -> list[User]:
    return list(UserRepository(session).list_readers())


def get_reader(session: Session, reader_id: int) -> User:
    reader = UserRepository(session).get_reader_by_id(reader_id)
    if reader is None:
        raise NotFoundError("READER_NOT_FOUND", "读者不存在")
    return reader


def create_reader(session: Session, data: ReaderCreate | dict[str, Any]) -> User:
    payload = data if isinstance(data, ReaderCreate) else ReaderCreate.model_validate(data)
    student_id = payload.student_id.strip()
    repo = UserRepository(session)
    if repo.get_by_student_id(student_id) is not None:
        raise _duplicate_student_id()
    _begin_write(session)
    # Re-check after taking the writer lock to close the check-then-insert race.
    if repo.get_by_student_id(student_id) is not None:
        session.rollback()
        raise _duplicate_student_id()
    reader = User(
        login_name=student_id,
        student_id=student_id,
        name=payload.name.strip(),
        contact=payload.contact.strip(),
        password_hash=hash_password(payload.password),
        role=UserRole.READER,
        borrow_limit=payload.borrow_limit,
        is_active=True,
    )
    repo.add(reader)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise _duplicate_student_id() from exc
    session.refresh(reader)
    return reader


def update_reader(
    session: Session,
    reader_id: int,
    data: ReaderUpdate | dict[str, Any],
) -> User:
    payload = data if isinstance(data, ReaderUpdate) else ReaderUpdate.model_validate(data)
    values = payload.model_dump(exclude_unset=True)
    reader = get_reader(session, reader_id)
    _begin_write(session)
    # get_reader loaded an ORM object before the rollback; refresh it in the
    # write transaction so an update cannot overwrite a concurrent change.
    reader = get_reader(session, reader_id)
    repo = UserRepository(session)
    if "student_id" in values:
        student_id = values["student_id"].strip() if values["student_id"] is not None else None
        if student_id is None:
            session.rollback()
            raise ValidationAppError("student_id不能为空", field="student_id")
        duplicate = repo.get_by_student_id(student_id)
        if duplicate is not None and duplicate.id != reader_id:
            session.rollback()
            raise _duplicate_student_id()
        reader.student_id = student_id
        reader.login_name = student_id
    if "name" in values:
        reader.name = values["name"].strip() if values["name"] is not None else reader.name
    if "contact" in values:
        reader.contact = values["contact"].strip() if values["contact"] is not None else None
    if "borrow_limit" in values:
        reader.borrow_limit = values["borrow_limit"]
    if "password" in values and values["password"] is not None:
        reader.password_hash = hash_password(values["password"])
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise _duplicate_student_id() from exc
    session.refresh(reader)
    return reader


def deactivate_reader(session: Session, reader_id: int) -> User:
    reader = get_reader(session, reader_id)
    _begin_write(session)
    reader = get_reader(session, reader_id)
    active_loan = session.scalar(
        select(
            exists().where(
                Loan.reader_id == reader_id,
                Loan.status == LoanStatus.BORROWED,
            )
        )
    )
    if active_loan:
        session.rollback()
        raise ConflictError(
            "READER_HAS_ACTIVE_LOANS",
            "读者存在未归还借阅，不能注销",
        )
    reader.is_active = False
    session.commit()
    session.refresh(reader)
    return reader


# Service names used by some integrations.
delete_reader = deactivate_reader
disable_reader = deactivate_reader
