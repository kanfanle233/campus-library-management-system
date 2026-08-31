"""Book loan and fine ORM model."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import FineStatus, LoanStatus
from app.database.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.book import Book
    from app.models.user import User


class Loan(Base):
    __tablename__ = "loans"
    __table_args__ = (
        CheckConstraint("fine_cents >= 0", name="ck_loans_fine_nonnegative"),
        CheckConstraint("due_date >= borrow_date", name="ck_loans_due_after_borrow"),
        CheckConstraint(
            "(status = 'BORROWED' AND return_date IS NULL) OR "
            "(status = 'RETURNED' AND return_date IS NOT NULL)",
            name="ck_loans_return_matches_status",
        ),
        Index("ix_loans_reader_status", "reader_id", "status"),
        Index("ix_loans_book_status", "book_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    loan_no: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    reader_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    borrow_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[LoanStatus] = mapped_column(
        Enum(
            LoanStatus,
            name="loan_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        nullable=False,
        default=LoanStatus.BORROWED,
        server_default=LoanStatus.BORROWED.value,
        index=True,
    )
    fine_cents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    fine_status: Mapped[FineStatus] = mapped_column(
        Enum(
            FineStatus,
            name="fine_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        nullable=False,
        default=FineStatus.NONE,
        server_default=FineStatus.NONE.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    reader: Mapped["User"] = relationship(
        "User",
        back_populates="loans",
        foreign_keys=[reader_id],
    )
    book: Mapped["Book"] = relationship("Book", back_populates="loans")
