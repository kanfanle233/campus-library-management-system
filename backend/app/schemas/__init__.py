"""Pydantic request and response schemas."""

from app.schemas.book import BookCreate, BookRead, BookUpdate, PageBookRead
from app.schemas.analytics import AnalyticsResponse

__all__ = ["AnalyticsResponse", "BookCreate", "BookRead", "BookUpdate", "PageBookRead"]
