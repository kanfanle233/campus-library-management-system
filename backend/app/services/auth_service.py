"""Authentication, JWT actor loading, and permission helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.exceptions import AppError, ForbiddenError, UnauthorizedError
from app.database import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository


password_hash = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class LocalActor:
    """Stable actor shape consumed by all business services."""

    user_id: int
    role: UserRole
    student_id: str | None = None


Actor = LocalActor


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hash.verify(password, encoded)
    except Exception:
        # Malformed hashes must behave like a wrong password, never as a 500.
        return False


def _http_error(error: AppError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message, **error.details},
        headers={"WWW-Authenticate": "Bearer"} if error.status_code == 401 else None,
    )


def _role_value(role: object) -> str:
    return getattr(role, "value", role) if isinstance(getattr(role, "value", role), str) else str(role)


def _token_from_security(user_id: int, role: UserRole) -> str | None:
    """Use the shared security module's encoder when it is available."""

    try:
        from app.core import security
    except ModuleNotFoundError:
        return None
    encoder = getattr(security, "create_access_token", None)
    if encoder is None:
        return None
    role_value = _role_value(role)
    security_user = SimpleNamespace(
        id=user_id,
        role=role if isinstance(role, UserRole) else UserRole(role_value),
    )
    for kwargs in (
        {"user_id": user_id, "role": role_value},
        {"user_id": user_id, "role": role},
    ):
        try:
            return str(encoder(**kwargs))
        except TypeError:
            continue
    try:
        # Current security accepts either an id plus role or a user-like
        # object. Prefer the explicit form so it works with both signatures.
        return str(encoder(user_id, role_value))
    except (TypeError, ValueError):
        pass
    try:
        return str(encoder(security_user))
    except (TypeError, ValueError):
        return None


def create_access_token(user_id: int, role: UserRole) -> str:
    token = _token_from_security(user_id, role)
    if token:
        return token
    settings = get_settings()
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY 未配置")
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "role": _role_value(role),
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def _decode_token(token: str) -> dict[str, Any]:
    try:
        from app.core import security
        decoder = getattr(security, "decode_access_token", None)
        if decoder is not None:
            payload = decoder(token)
            if isinstance(payload, dict):
                return payload
    except (ModuleNotFoundError, TypeError, ValueError, jwt.PyJWTError):
        raise UnauthorizedError()
    settings = get_settings()
    if not settings.jwt_secret_key:
        raise UnauthorizedError()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise UnauthorizedError() from exc
    if not isinstance(payload, dict):
        raise UnauthorizedError()
    return payload


def _actor_for_user(user: User) -> LocalActor:
    return LocalActor(user_id=user.id, role=user.role)


def current_actor(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> LocalActor:
    """Decode the bearer token and re-read the account on every request."""

    try:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise UnauthorizedError()
        # Prefer the shared dependency implementation. It owns the canonical
        # JWT claim format and performs the required database re-read.
        try:
            from app.core import security

            loader = getattr(security, "get_current_actor", None)
            if loader is not None:
                loaded = loader(credentials=credentials, session=db)
                return LocalActor(
                    user_id=loaded.user_id,
                    role=loaded.role,
                    student_id=getattr(loaded, "student_id", None),
                )
        except (ModuleNotFoundError, TypeError):
            pass
        payload = _decode_token(credentials.credentials)
        user_id = payload.get("user_id")
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            raise UnauthorizedError()
        user = UserRepository(db).get_by_id(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError()
        if _role_value(user.role) not in {UserRole.ADMIN.value, UserRole.READER.value}:
            raise UnauthorizedError()
        return _actor_for_user(user)
    except AppError as error:
        # AppError remains the domain error used by services; this dependency
        # is also a FastAPI boundary, where it must become a valid HTTP reply.
        raise _http_error(error) from error


def require_admin(actor: LocalActor = Depends(current_actor)) -> LocalActor:
    if _role_value(actor.role) != UserRole.ADMIN.value:
        error = ForbiddenError()
        raise _http_error(error) from error
    return actor


def require_reader_or_admin(actor: LocalActor = Depends(current_actor)) -> LocalActor:
    if _role_value(actor.role) not in {UserRole.ADMIN.value, UserRole.READER.value}:
        error = ForbiddenError()
        raise _http_error(error) from error
    return actor


def require_self(actor: LocalActor, reader_id: int) -> LocalActor:
    """Allow an actor to address their own reader resource only."""

    if _role_value(actor.role) != UserRole.ADMIN.value and actor.user_id != reader_id:
        raise ForbiddenError()
    return actor


def authenticate_user(db: Session, username: str, password: str) -> User:
    username = username.strip()
    repo = UserRepository(db)
    user = repo.get_by_login_name(username)
    if user is None and username != "admin":
        user = repo.get_by_student_id(username)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise UnauthorizedError("用户名或密码错误")
    return user


def login(db: Session, username: str, password: str) -> tuple[str, User]:
    user = authenticate_user(db, username, password)
    return create_access_token(user.id, user.role), user


get_current_actor = current_actor
authenticate = authenticate_user
login_user = login
