"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api.v1.router import router as v1_router
from .core.config import Settings, get_settings
from .core.exceptions import AppError
from .database import init_db


def _json_safe(value: Any) -> Any:
    """Convert Pydantic's exception objects into JSON-safe error details."""

    if isinstance(value, BaseException):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _database_status(settings: Settings) -> str:
    """Report configuration state without importing or duplicating DB logic."""
    if not settings.database_url:
        return "not_configured"
    try:
        __import__("app.database")
    except (ImportError, ModuleNotFoundError):
        return "unavailable"
    return "configured"


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        # The explicit scripts remain useful for demonstrations and seed data,
        # while startup initialization makes a clean checkout runnable with a
        # single uvicorn command. ``create_all`` is idempotent and never drops
        # existing rows.
        init_db()
        yield

    application = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

    @application.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": {
                    "code": exc.code,
                    "message": exc.message,
                    **exc.details,
                }
            },
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "VALIDATION_ERROR",
                    "message": "请求参数校验失败",
                    "errors": _json_safe(exc.errors()),
                }
            },
        )
    if settings.cors_origin_list:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @application.get("/health", tags=["system"])
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "database": _database_status(settings),
            "version": settings.app_version,
        }

    application.include_router(v1_router)
    return application


app = create_app()
