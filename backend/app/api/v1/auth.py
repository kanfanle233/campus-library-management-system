"""Authentication routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.database import get_db
from app.schemas.auth import LoginRequest, LoginResponse, ReaderIdentity
from app.schemas.reader import ReaderResponse
from app.services.auth_service import current_actor, login

router = APIRouter(prefix="/auth", tags=["auth"])


def _http_error(error: AppError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message, **error.details},
        headers={"WWW-Authenticate": "Bearer"} if error.status_code == 401 else None,
    )


@router.post("/login", response_model=LoginResponse)
def login_route(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    try:
        token, user = login(db, payload.username, payload.password)
    except AppError as error:
        raise _http_error(error) from error
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=ReaderIdentity(
            id=user.id,
            role=getattr(user.role, "value", user.role),
            name=user.name,
            student_id=user.student_id,
        ),
    )


@router.get("/me", response_model=ReaderResponse)
def me_route(actor=Depends(current_actor), db: Session = Depends(get_db)) -> ReaderResponse:
    # current_actor has already re-read the active account. Re-read the row
    # here as well so the response is never based on claims in the token.
    from app.repositories.user_repository import UserRepository

    user = UserRepository(db).get_by_id(actor.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID_CREDENTIALS", "message": "认证失败"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
