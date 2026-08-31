"""Response models for the administrator dashboard."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DashboardStats(BaseModel):
    """Small, database-backed summary used by the frontend home page."""

    total_books: int = Field(ge=0, description="Active book titles")
    total_copies: int = Field(ge=0)
    available_copies: int = Field(ge=0)
    total_readers: int = Field(ge=0, description="Active reader accounts")
    active_loans: int = Field(ge=0)
    overdue_loans: int = Field(ge=0)
    unpaid_fines: str = Field(description="Yuan, formatted to two decimals")
