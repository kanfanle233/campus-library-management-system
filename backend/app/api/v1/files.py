"""Administrator-only CSV import and export routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.security import Actor, require_admin
from app.database import get_db
from app.schemas.file import FileImportResult
from app.services.file_service import MAX_FILE_BYTES, file_service

router = APIRouter(prefix="/files", tags=["files"])


def _http_error(error: AppError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message, **error.details},
    )


def _csv_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{filename}',
        },
    )


@router.post("/books/import", response_model=FileImportResult)
async def import_books_csv(
    file: UploadFile = File(...),
    _admin: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FileImportResult:
    # Reading one byte beyond the limit detects oversized uploads without
    # buffering an arbitrarily large multipart part in memory.
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "FILE_TOO_LARGE", "message": "文件大小不能超过 2 MiB"},
        )
    try:
        result = file_service.import_books(db, content)
    except AppError as error:
        raise _http_error(error) from error
    # Validation failures still return the complete import report so callers
    # can show every offending original row in one response.
    if result.errors:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=result.model_dump())
    return result


@router.get("/books/export")
def export_books_csv(
    _admin: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    return _csv_response(file_service.export_books(db), "books.csv")


@router.get("/readers/export")
def export_readers_csv(
    _admin: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    return _csv_response(file_service.export_readers(db), "readers.csv")


@router.get("/loans/export")
def export_loans_csv(
    _admin: Actor = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    return _csv_response(file_service.export_loans(db, as_of=date.today()), "loans.csv")
