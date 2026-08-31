"""Reader and administrator ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import UserRole
from app.database.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.loan import Loan


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("borrow_limit >= 0", name="ck_users_borrow_limit_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Administrators authenticate with the single fixed value ``admin``;
    # readers authenticate with student_id. Nullable unique columns permit
    # multiple reader rows without a login_name while keeping the admin login
    # unique.
    login_name: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    student_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact: Mapped[str | None] = mapped_column(String(100), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        nullable=False,
        default=UserRole.READER,
        server_default=UserRole.READER.value,
    )
    borrow_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        server_default=text("5"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    loans: Mapped[list["Loan"]] = relationship(
        "Loan",
        back_populates="reader",
        foreign_keys="Loan.reader_id",
    )
