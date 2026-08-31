"""Circulation use cases: borrowing, returning, fines and loan queries."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from typing import Iterator
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.enums import FineStatus, LoanStatus, UserRole
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.security import Actor
from app.database import SessionLocal, begin_immediate
from app.models import Book, Loan, User
from app.repositories import loan_repository
from app.schemas.book import normalize_isbn
from app.schemas.loan import LoanListResponse, LoanOut, ReturnPreview
from app.services.fine_service import (
    calculate_fine_cents,
    calculate_overdue_days,
    format_cents,
)


@contextmanager
def _write_session() -> Iterator[Session]:
    """Open one reserved SQLite transaction for a complete use case."""

    session = SessionLocal()
    try:
        begin_immediate(session)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
    finally:
        session.close()


@contextmanager
def _read_session() -> Iterator[Session]:
    """Open a short-lived read session that is easy to replace in tests."""

    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _today(as_of: date | None) -> date:
    return as_of or date.today()


def _is_admin(actor: Actor) -> bool:
    role = getattr(actor, "role", None)
    return role is UserRole.ADMIN or getattr(role, "value", role) == UserRole.ADMIN.value


def _actor_user_id(actor: Actor) -> int | None:
    value = getattr(actor, "user_id", getattr(actor, "id", None))
    return value if isinstance(value, int) and value > 0 else None


def _loan_out(loan: Loan, reader: User, book: Book, as_of: date) -> LoanOut:
    if loan.status is LoanStatus.RETURNED and loan.return_date is not None:
        fine_cents = loan.fine_cents
        overdue_days = calculate_overdue_days(loan.due_date, loan.return_date)
    else:
        fine_cents = calculate_fine_cents(loan.due_date, as_of)
        overdue_days = calculate_overdue_days(loan.due_date, as_of)
    return LoanOut(
        id=loan.id,
        loan_no=loan.loan_no,
        reader_id=reader.id,
        student_id=reader.student_id,
        reader_name=reader.name,
        book_id=book.id,
        book_code=book.book_code,
        book_title=book.title,
        isbn=book.isbn,
        borrow_date=loan.borrow_date,
        due_date=loan.due_date,
        return_date=loan.return_date,
        status=loan.status,
        overdue_days=overdue_days,
        fine_amount=format_cents(fine_cents),
        fine_status=loan.fine_status,
    )


def borrow_book(
    actor: Actor,
    *,
    book_id: int | None = None,
    isbn: str | None = None,
    book_code: str | None = None,
    reader_id: int | None = None,
    as_of: date | None = None,
) -> LoanOut:
    """Borrow one copy after checking every course business rule atomically."""

    today = _today(as_of)
    identifiers = [book_id is not None, isbn is not None, book_code is not None]
    if sum(identifiers) != 1:
        raise ValidationAppError("借书时必须提供且只能提供 book_id、ISBN 或图书编号中的一个")
    normalized_isbn = normalize_isbn(isbn.strip()) if isbn is not None else None
    normalized_code = book_code.strip() if book_code is not None else None
    admin = _is_admin(actor)
    actor_id = _actor_user_id(actor)
    target_reader_id = reader_id if admin else actor_id
    if target_reader_id is None:
        raise NotFoundError("READER_NOT_FOUND", "读者不存在")
    if not admin and target_reader_id != actor_id:
        raise ForbiddenError(message="读者只能为自己借书")

    with _write_session() as session:
        # Recheck identity inside the reserved transaction. A token does not
        # grant access after an account has been deactivated or demoted.
        reader = loan_repository.get_reader(session, target_reader_id)
        if reader is None:
            raise NotFoundError("READER_NOT_FOUND", "读者不存在或已停用")
        if not admin and reader.id != actor_id:
            raise ForbiddenError(message="读者只能为自己借书")

        book = loan_repository.get_book(
            session,
            book_id,
            isbn=normalized_isbn,
            book_code=normalized_code,
        )
        if book is None:
            raise NotFoundError("BOOK_NOT_FOUND", "图书不存在或已停用")
        if book.available_quantity <= 0:
            raise ConflictError("BOOK_OUT_OF_STOCK", "当前图书没有可借库存")

        active_count = loan_repository.count_active_loans(session, reader.id)
        if active_count >= reader.borrow_limit:
            raise ConflictError(
                "READER_BORROW_LIMIT_REACHED",
                "已达到读者借阅上限",
                borrow_limit=reader.borrow_limit,
            )
        if loan_repository.has_overdue_loan(session, reader.id, today):
            raise ConflictError("READER_HAS_OVERDUE_LOANS", "存在逾期未还图书")

        changed = session.execute(
            update(Book)
            .where(Book.id == book.id, Book.is_active.is_(True), Book.available_quantity > 0)
            .values(available_quantity=Book.available_quantity - 1)
        )
        if changed.rowcount != 1:
            raise ConflictError("BOOK_OUT_OF_STOCK", "当前图书没有可借库存")

        loan = Loan(
            # ``loan_no`` is non-null and unique, so give the row a private
            # placeholder for the first flush. It is replaced immediately
            # with the human-readable sequence after SQLite assigns the id.
            loan_no=f"PENDING-{uuid4().hex}",
            reader_id=reader.id,
            book_id=book.id,
            borrow_date=today,
            due_date=today + timedelta(days=30),
            status=LoanStatus.BORROWED,
            fine_cents=0,
            fine_status=FineStatus.NONE,
        )
        session.add(loan)
        session.flush()
        loan.loan_no = f"LN{loan.id:06d}"
        # Refresh the ORM instance because the conditional SQL UPDATE may
        # have synchronized it differently across SQLAlchemy versions.
        session.refresh(book)
        result = _loan_out(loan, reader, book, today)
    return result


def get_return_preview(actor: Actor, loan_id: int, *, as_of: date | None = None) -> ReturnPreview:
    today = _today(as_of)
    with _read_session() as session:
        loan = loan_repository.get_loan(session, loan_id)
        if loan is None:
            raise NotFoundError("LOAN_NOT_FOUND", "借阅记录不存在")
        if not _is_admin(actor) and loan.reader_id != _actor_user_id(actor):
            raise ForbiddenError(message="只能查看自己的借阅记录")
        if loan.status is LoanStatus.RETURNED:
            raise ConflictError("LOAN_ALREADY_RETURNED", "该图书已经归还")
        return ReturnPreview(
            loan_no=loan.loan_no,
            book_title=loan.book.title,
            due_date=loan.due_date,
            return_date=today,
            overdue_days=calculate_overdue_days(loan.due_date, today),
            fine_amount=format_cents(calculate_fine_cents(loan.due_date, today)),
            fine_status=(
                FineStatus.UNPAID
                if today > loan.due_date
                else FineStatus.NONE
            ),
        )


def return_book(actor: Actor, loan_id: int, *, as_of: date | None = None) -> LoanOut:
    """Return one active loan and restore exactly one available copy."""

    today = _today(as_of)
    with _write_session() as session:
        loan = loan_repository.get_loan(session, loan_id)
        if loan is None:
            raise NotFoundError("LOAN_NOT_FOUND", "借阅记录不存在")
        if not _is_admin(actor) and loan.reader_id != _actor_user_id(actor):
            raise ForbiddenError(message="只能归还自己的借阅记录")
        if loan.status is not LoanStatus.BORROWED or loan.return_date is not None:
            raise ConflictError("LOAN_ALREADY_RETURNED", "该图书已经归还")

        # Recheck with a conditional update so a repeated request cannot
        # create a second return or increment inventory twice.
        fine_cents = calculate_fine_cents(loan.due_date, today)
        fine_status = FineStatus.UNPAID if fine_cents > 0 else FineStatus.NONE
        changed = session.execute(
            update(Loan)
            .where(Loan.id == loan.id, Loan.status == LoanStatus.BORROWED, Loan.return_date.is_(None))
            .values(
                status=LoanStatus.RETURNED,
                return_date=today,
                fine_cents=fine_cents,
                fine_status=fine_status,
            )
        )
        if changed.rowcount != 1:
            raise ConflictError("LOAN_ALREADY_RETURNED", "该图书已经归还")

        inventory_changed = session.execute(
            update(Book)
            .where(Book.id == loan.book_id, Book.available_quantity < Book.total_quantity)
            .values(available_quantity=Book.available_quantity + 1)
        )
        if inventory_changed.rowcount != 1:
            # Do not commit a returned loan when its inventory cannot be
            # restored; the surrounding transaction rolls the status change
            # back so an administrator can repair the inconsistent row.
            raise ConflictError(
                "BOOK_INVENTORY_INCONSISTENT",
                "图书库存状态异常，归还未完成",
            )
        session.flush()
        session.refresh(loan)
        reader = session.get(User, loan.reader_id)
        book = session.get(Book, loan.book_id)
        if reader is None or book is None:
            raise NotFoundError("LOAN_REFERENCE_NOT_FOUND", "借阅关联数据不存在")
        result = _loan_out(loan, reader, book, today)
    return result


def mark_fine_paid(actor: Actor, loan_id: int) -> LoanOut:
    if not _is_admin(actor):
        raise ForbiddenError(message="仅管理员可以登记罚款")
    with _write_session() as session:
        loan = loan_repository.get_loan(session, loan_id)
        if loan is None:
            raise NotFoundError("LOAN_NOT_FOUND", "借阅记录不存在")
        if loan.status is not LoanStatus.RETURNED:
            raise ConflictError("FINE_NOT_PAYABLE", "图书归还后才能登记罚款")
        if loan.fine_cents <= 0:
            loan.fine_status = FineStatus.NONE
        else:
            loan.fine_status = FineStatus.PAID
        session.flush()
        reader = session.get(User, loan.reader_id)
        book = session.get(Book, loan.book_id)
        if reader is None or book is None:
            raise NotFoundError("LOAN_REFERENCE_NOT_FOUND", "借阅关联数据不存在")
        result = _loan_out(loan, reader, book, loan.return_date or date.today())
    return result


def list_loans(
    actor: Actor,
    *,
    loan_no: str | None = None,
    student_id: str | None = None,
    status: LoanStatus | None = None,
    overdue: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    as_of: date | None = None,
) -> LoanListResponse:
    today = _today(as_of)
    reader_id = _actor_user_id(actor) if not _is_admin(actor) else None
    with _read_session() as session:
        rows, total = loan_repository.list_loans(
            session,
            reader_id=reader_id,
            loan_no=loan_no,
            student_id=student_id if _is_admin(actor) else None,
            status=status,
            overdue=overdue,
            as_of=today,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        items = [_loan_out(loan, reader, book, today) for loan, reader, book in rows]
        return LoanListResponse(items=items, total=total, page=page, page_size=page_size)


def get_loan(actor: Actor, loan_id: int, *, as_of: date | None = None) -> LoanOut:
    today = _today(as_of)
    with _read_session() as session:
        loan = loan_repository.get_loan(session, loan_id)
        if loan is None:
            raise NotFoundError("LOAN_NOT_FOUND", "借阅记录不存在")
        if not _is_admin(actor) and loan.reader_id != _actor_user_id(actor):
            raise ForbiddenError(message="只能查看自己的借阅记录")
        reader = session.get(User, loan.reader_id)
        book = session.get(Book, loan.book_id)
        if reader is None or book is None:
            raise NotFoundError("LOAN_REFERENCE_NOT_FOUND", "借阅关联数据不存在")
        return _loan_out(loan, reader, book, today)
