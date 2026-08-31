"""Book inventory API routes."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.database.database import get_db
from app.schemas.book import BookCreate, BookRead, BookUpdate, PageBookRead
from app.core.security import Actor, get_current_actor
from app.services.book_service import book_service

router = APIRouter(prefix="/books", tags=["books"])


def _http_error(error: AppError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message, **error.details},
    )


def _read_model(book) -> BookRead:
    return BookRead(
        id=book.id, book_code=book.book_code, title=book.title, author=book.author,
        isbn=book.isbn, publisher=book.publisher,
        price=f"{Decimal(book.price_cents) / Decimal(100):.2f}",
        category=book.category, total_quantity=book.total_quantity,
        available_quantity=book.available_quantity, is_active=book.is_active,
    )


@router.get("", response_model=PageBookRead)
def list_books(
    title: str | None = Query(default=None), author: str | None = Query(default=None),
    isbn: str | None = Query(default=None), category: str | None = Query(default=None),
    book_code: str | None = Query(default=None), page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: Actor = Depends(get_current_actor),
    session: Session = Depends(get_db),
) -> PageBookRead:
    try:
        books, total = book_service.list(
            session, current_user, title=title, author=author, isbn=isbn,
            category=category, book_code=book_code, page=page, page_size=page_size,
        )
        return PageBookRead(items=[_read_model(book) for book in books], total=total,
                            page=page, page_size=page_size)
    except AppError as error:
        raise _http_error(error) from error


@router.post("", response_model=BookRead, status_code=status.HTTP_201_CREATED)
def create_book(payload: BookCreate, current_user: Actor = Depends(get_current_actor)) -> BookRead:
    try:
        return _read_model(book_service.create(payload, current_user))
    except AppError as error:
        raise _http_error(error) from error


@router.get("/{book_id}", response_model=BookRead)
def get_book(
    book_id: int, current_user: Actor = Depends(get_current_actor),
    session: Session = Depends(get_db),
) -> BookRead:
    try:
        return _read_model(book_service.get(session, book_id, current_user))
    except AppError as error:
        raise _http_error(error) from error


@router.patch("/{book_id}", response_model=BookRead)
def update_book(book_id: int, payload: BookUpdate,
                current_user: Actor = Depends(get_current_actor)) -> BookRead:
    try:
        return _read_model(book_service.update(book_id, payload, current_user))
    except AppError as error:
        raise _http_error(error) from error


@router.delete("/{book_id}", response_model=BookRead)
def delete_book(book_id: int,
                current_user: Actor = Depends(get_current_actor)) -> BookRead:
    try:
        return _read_model(book_service.delete(book_id, current_user))
    except AppError as error:
        raise _http_error(error) from error
