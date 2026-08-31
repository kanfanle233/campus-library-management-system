"""Application errors mapped to stable HTTP responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AppError(Exception):
    """A domain error safe to expose to an API client."""

    code: str
    message: str
    status_code: int = 400
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # ``super()`` inside a slots dataclass can lose its zero-argument
        # binding after dataclass replaces the class object. Initialize the
        # built-in exception explicitly so every subclass is constructible.
        Exception.__init__(self, self.message)


class NotFoundError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=404)


class ConflictError(AppError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(
            code=code, message=message, status_code=409, details=details
        )


class ForbiddenError(AppError):
    def __init__(self, code: str = "FORBIDDEN", message: str = "无权执行此操作") -> None:
        super().__init__(code=code, message=message, status_code=403)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "认证失败") -> None:
        super().__init__(
            code="AUTH_INVALID_CREDENTIALS", message=message, status_code=401
        )


class ValidationAppError(AppError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(
            code="VALIDATION_ERROR", message=message, status_code=422, details=details
        )
