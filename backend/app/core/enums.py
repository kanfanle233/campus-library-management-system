"""Enum values persisted by the library database."""

from enum import Enum


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    READER = "READER"


class LoanStatus(str, Enum):
    BORROWED = "BORROWED"
    RETURNED = "RETURNED"


class FineStatus(str, Enum):
    NONE = "NONE"
    UNPAID = "UNPAID"
    PAID = "PAID"


# ``Role`` is a convenient compatibility alias for callers that use the
# shorter name while UserRole remains the canonical public name.
Role = UserRole

