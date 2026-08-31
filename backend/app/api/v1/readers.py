"""Reader management routes."""

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.database import get_db
from app.schemas.reader import ReaderCreate, ReaderResponse, ReaderUpdate
from app.services import reader_service
from app.services.auth_service import LocalActor, current_actor, require_admin, require_self

router = APIRouter(prefix="/readers", tags=["readers"])


def _http_error(error: AppError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message, **error.details},
    )


@router.get("", response_model=list[ReaderResponse])
def list_readers_route(
    _admin: LocalActor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[ReaderResponse]:
    return reader_service.list_readers(db)


@router.post("", response_model=ReaderResponse, status_code=status.HTTP_201_CREATED)
def create_reader_route(
    payload: ReaderCreate,
    _admin: LocalActor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ReaderResponse:
    try:
        return reader_service.create_reader(db, payload)
    except AppError as error:
        raise _http_error(error) from error


@router.get("/{reader_id}", response_model=ReaderResponse)
def get_reader_route(
    reader_id: int = Path(gt=0),
    actor: LocalActor = Depends(current_actor),
    db: Session = Depends(get_db),
) -> ReaderResponse:
    try:
        require_self(actor, reader_id)
        return reader_service.get_reader(db, reader_id)
    except AppError as error:
        raise _http_error(error) from error


@router.patch("/{reader_id}", response_model=ReaderResponse)
def update_reader_route(
    payload: ReaderUpdate,
    reader_id: int = Path(gt=0),
    _admin: LocalActor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ReaderResponse:
    try:
        return reader_service.update_reader(db, reader_id, payload)
    except AppError as error:
        raise _http_error(error) from error


@router.delete("/{reader_id}", response_model=ReaderResponse)
def delete_reader_route(
    reader_id: int = Path(gt=0),
    _admin: LocalActor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ReaderResponse:
    try:
        return reader_service.deactivate_reader(db, reader_id)
    except AppError as error:
        raise _http_error(error) from error
