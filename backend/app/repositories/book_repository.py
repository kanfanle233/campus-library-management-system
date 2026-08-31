"""Persistence operations for books; methods never commit."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.book import Book


class BookRepository:
    def get(self, session: Session, book_id: int, *, include_inactive: bool = True) -> Book | None:
        statement = select(Book).where(Book.id == book_id)
        if not include_inactive:
            statement = statement.where(Book.is_active.is_(True))
        return session.scalar(statement)

    def list(
        self, session: Session, *, title: str | None = None, author: str | None = None,
        isbn: str | None = None, category: str | None = None, book_code: str | None = None,
        page: int = 1, page_size: int = 20, include_inactive: bool = False,
    ) -> tuple[list[Book], int]:
        conditions = []
        if not include_inactive:
            conditions.append(Book.is_active.is_(True))
        for field, value in {
            "title": title, "author": author, "isbn": isbn,
            "category": category, "book_code": book_code,
        }.items():
            value = value.strip() if isinstance(value, str) else value
            if value:
                conditions.append(getattr(Book, field).ilike(f"%{value}%"))
        total = int(session.scalar(select(func.count(Book.id)).where(*conditions)) or 0)
        statement = (
            select(Book).where(*conditions).order_by(Book.id)
            .offset((page - 1) * page_size).limit(page_size)
        )
        return list(session.scalars(statement).all()), total

    def get_by_isbn(self, session: Session, isbn: str) -> Book | None:
        return session.scalar(select(Book).where(Book.isbn == isbn))

    def add(self, session: Session, book: Book) -> Book:
        session.add(book)
        return book


book_repository = BookRepository()
