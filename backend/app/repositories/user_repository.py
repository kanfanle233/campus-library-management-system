"""Persistence operations for users.

Repositories deliberately do not commit. Transaction ownership belongs to the
service that is coordinating the operation.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.models.user import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_login_name(self, login_name: str) -> User | None:
        return self.session.scalar(select(User).where(User.login_name == login_name))

    def get_by_student_id(self, student_id: str) -> User | None:
        return self.session.scalar(select(User).where(User.student_id == student_id))

    def get_reader_by_id(self, reader_id: int) -> User | None:
        return self.session.scalar(
            select(User).where(User.id == reader_id, User.role == UserRole.READER)
        )

    def list_readers(self) -> Sequence[User]:
        return self.session.scalars(
            select(User).where(User.role == UserRole.READER).order_by(User.id)
        ).all()

    def add(self, user: User) -> User:
        self.session.add(user)
        return user

    def delete(self, user: User) -> None:
        """Compatibility method: deletion is represented by soft deactivation."""

        user.is_active = False


# Functional aliases are useful to services and keep the repository easy to
# use in small tests without forcing callers to instantiate the class.
def get_user_by_id(session: Session, user_id: int) -> User | None:
    return UserRepository(session).get_by_id(user_id)


def get_user_by_login_name(session: Session, login_name: str) -> User | None:
    return UserRepository(session).get_by_login_name(login_name)


def get_user_by_student_id(session: Session, student_id: str) -> User | None:
    return UserRepository(session).get_by_student_id(student_id)

