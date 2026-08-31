"""Password hashing, JWT handling, and request identity dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.database import get_db
from app.models import User


password_hasher = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Actor:
    """Database-backed identity passed from the API layer to services."""

    user_id: int
    role: UserRole
    student_id: str | None = None


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password, password_hash)
    except Exception:
        # A corrupted database hash is treated as a failed login, never as a
        # server error that leaks password-hash details.
        return False


def create_access_token(
    user: User | int | None = None,
    role: UserRole | str | None = None,
    *,
    expires_minutes: int | None = None,
    user_id: int | None = None,
) -> str:
    settings = get_settings()
    minutes = expires_minutes or settings.jwt_expire_minutes
    now = datetime.now(timezone.utc)
    if user is None:
        user = user_id
    if user is None:
        raise ValueError("user or user_id is required")
    user_id = user.id if isinstance(user, User) else user
    user_role = user.role if isinstance(user, User) else role
    if user_role is None:
        raise ValueError("role is required when creating a token from an id")
    role_value = user_role.value if isinstance(user_role, UserRole) else str(user_role)
    payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "role": role_value,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    secret = settings.jwt_secret_key or "local-development-secret-change-me"
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, object]:
    """Decode a token and expose both legacy ``user_id`` and JWT ``sub``."""

    payload = _decode_token(token)
    try:
        payload["user_id"] = int(str(payload["sub"]))
    except (TypeError, ValueError, KeyError) as exc:
        raise UnauthorizedError("令牌用户身份无效") from exc
    return payload


def _decode_token(token: str) -> dict[str, object]:
    settings = get_settings()
    secret = settings.jwt_secret_key or "local-development-secret-change-me"
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("令牌无效或已过期") from exc
    if not isinstance(payload.get("sub"), str):
        raise UnauthorizedError("令牌缺少用户身份")
    return payload


def get_current_actor(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_db)],
) -> Actor:
    if credentials is None:
        raise UnauthorizedError("请先登录")
    payload = _decode_token(credentials.credentials)
    try:
        user_id = int(str(payload["sub"]))
    except (TypeError, ValueError) as exc:
        raise UnauthorizedError("令牌用户身份无效") from exc
    user = session.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise UnauthorizedError("账户不存在或已停用")
    return Actor(user_id=user.id, role=user.role, student_id=user.student_id)


CurrentActor = Annotated[Actor, Depends(get_current_actor)]


def require_admin(actor: CurrentActor) -> Actor:
    if actor.role is not UserRole.ADMIN:
        raise ForbiddenError(message="仅管理员可以执行此操作")
    return actor


AdminActor = Annotated[Actor, Depends(require_admin)]


def require_owner_or_admin(actor: Actor, owner_id: int) -> None:
    if actor.role is not UserRole.ADMIN and actor.user_id != owner_id:
        raise ForbiddenError(message="只能操作自己的借阅记录")
