"""Version 1 route registration for the complete course feature set."""

from fastapi import APIRouter

from . import auth, books, dashboard, files, loans, readers

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(books.router)
router.include_router(readers.router)
router.include_router(loans.router)
router.include_router(files.router)
router.include_router(dashboard.router)
