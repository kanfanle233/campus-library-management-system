"""Book inventory business rules and transaction boundaries."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import LoanStatus, UserRole
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.database.database import SessionLocal, begin_immediate
from app.models.book import Book
from app.models.loan import Loan
from app.models.user import User
from app.repositories.book_repository import BookRepository, book_repository
from app.schemas.book import BookCreate, BookUpdate, normalize_isbn


def _actor_id(actor: Any) -> int | None:
    value = getattr(actor, "id", getattr(actor, "user_id", actor if isinstance(actor, int) else None))
    return value if isinstance(value, int) and value > 0 else None


class BookService:
    def __init__(self, repository: BookRepository | None = None,
                 session_factory: Callable[[], Session] | None = None) -> None:
        self.repository = repository or book_repository
        self.session_factory = session_factory or SessionLocal

    @staticmethod
    def _is_admin(actor: Any) -> bool:
        return getattr(actor, "role", None) in (UserRole.ADMIN, UserRole.ADMIN.value, "ADMIN")

    def _assert_admin(self, session: Session, actor: Any) -> User:
        actor_id = _actor_id(actor)
        if actor_id is None or not self._is_admin(actor):
            raise ForbiddenError()
        user = session.scalar(select(User).where(
            User.id == actor_id, User.role == UserRole.ADMIN, User.is_active.is_(True)
        ))
        if user is None:
            raise ForbiddenError()
        return user

    @staticmethod
    def _price_cents(price: Decimal | None) -> int:
        if price is None:
            return 0
        if price < 0 or price.as_tuple().exponent < -2:
            raise ValidationAppError("price must be a non-negative amount with at most two decimals")
        return int(price * 100)

    def create(self, payload: BookCreate, actor: Any) -> Book:
        session = self.session_factory()
        try:
            begin_immediate(session)
            self._assert_admin(session, actor)
            isbn = normalize_isbn(payload.isbn)
            if self.repository.get_by_isbn(session, isbn) is not None:
                raise ConflictError("ISBN_ALREADY_EXISTS", "ISBN 已存在")
            total = payload.total_quantity if payload.total_quantity is not None else payload.quantity
            total = 0 if total is None else total
            if total < 0:
                raise ValidationAppError("quantity must be non-negative")
            book = Book(book_code="PENDING", title=payload.title, author=payload.author,
                        isbn=isbn, publisher=payload.publisher,
                        price_cents=self._price_cents(payload.price), category=payload.category,
                        total_quantity=total, available_quantity=total, is_active=True)
            self.repository.add(session, book)
            session.flush()
            book.book_code = f"BK{book.id:06d}"
            session.flush()
            session.commit()
            return book
        except IntegrityError as exc:
            session.rollback()
            if "isbn" in str(exc).lower():
                raise ConflictError("ISBN_ALREADY_EXISTS", "ISBN 已存在") from exc
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get(self, session: Session, book_id: int, actor: Any) -> Book:
        book = self.repository.get(session, book_id, include_inactive=self._is_admin(actor))
        if book is None:
            raise NotFoundError("BOOK_NOT_FOUND", "图书不存在")
        return book

    def list(self, session: Session, actor: Any, **filters: Any) -> tuple[list[Book], int]:
        if filters.get("isbn"):
            filters["isbn"] = normalize_isbn(str(filters["isbn"]))
        filters["include_inactive"] = self._is_admin(actor)
        return self.repository.list(session, **filters)

    def update(self, book_id: int, payload: BookUpdate, actor: Any) -> Book:
        session = self.session_factory()
        try:
            begin_immediate(session)
            self._assert_admin(session, actor)
            book = self.repository.get(session, book_id, include_inactive=True)
            if book is None:
                raise NotFoundError("BOOK_NOT_FOUND", "图书不存在")
            values = payload.model_dump(exclude_unset=True)
            if "isbn" in values:
                isbn = normalize_isbn(values["isbn"])
                duplicate = self.repository.get_by_isbn(session, isbn)
                if duplicate is not None and duplicate.id != book.id:
                    raise ConflictError("ISBN_ALREADY_EXISTS", "ISBN 已存在")
                book.isbn = isbn
                values.pop("isbn")
            requested_total = values.pop("total_quantity", None)
            values.pop("quantity", None)
            if requested_total is not None:
                borrowed = book.total_quantity - book.available_quantity
                if requested_total < borrowed:
                    raise ValidationAppError(
                        "total_quantity cannot be less than currently borrowed quantity",
                        borrowed_quantity=borrowed,
                    )
                book.total_quantity = requested_total
                book.available_quantity = requested_total - borrowed
            for field, value in values.items():
                if field == "price":
                    value, field = self._price_cents(value), "price_cents"
                setattr(book, field, value)
            session.flush()
            session.commit()
            return book
        except IntegrityError as exc:
            session.rollback()
            if "isbn" in str(exc).lower():
                raise ConflictError("ISBN_ALREADY_EXISTS", "ISBN 已存在") from exc
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete(self, book_id: int, actor: Any) -> Book:
        session = self.session_factory()
        try:
            begin_immediate(session)
            self._assert_admin(session, actor)
            book = self.repository.get(session, book_id, include_inactive=True)
            if book is None:
                raise NotFoundError("BOOK_NOT_FOUND", "图书不存在")
            borrowed = int(session.scalar(select(func.count(Loan.id)).where(
                Loan.book_id == book.id, Loan.status == LoanStatus.BORROWED
            )) or 0)
            if borrowed:
                raise ConflictError("BOOK_CURRENTLY_BORROWED", "图书当前存在借阅记录，不能删除",
                                    borrowed_quantity=borrowed)
            book.is_active = False
            session.flush()
            session.commit()
            return book
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


book_service = BookService()


# Functional aliases match the other domain services and keep integrations
# independent from the concrete service object.
def create_book(actor: Any, data: BookCreate | dict[str, Any]) -> Book:
    payload = data if isinstance(data, BookCreate) else BookCreate.model_validate(data)
    return book_service.create(payload, actor)


def list_books(session: Session, actor: Any, **filters: Any) -> tuple[list[Book], int]:
    return book_service.list(session, actor, **filters)


def get_book(session: Session, book_id: int, actor: Any) -> Book:
    return book_service.get(session, book_id, actor)


def update_book(actor: Any, book_id: int, data: BookUpdate | dict[str, Any]) -> Book:
    payload = data if isinstance(data, BookUpdate) else BookUpdate.model_validate(data)
    return book_service.update(book_id, payload, actor)


def delete_book(actor: Any, book_id: int) -> Book:
    return book_service.delete(book_id, actor)
