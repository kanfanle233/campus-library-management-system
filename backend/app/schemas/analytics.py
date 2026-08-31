"""Response models for the administrator analytics view."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class DailyTrend(BaseModel):
    date: date
    borrowed: int = Field(ge=0)
    returned: int = Field(ge=0)


class CategoryStat(BaseModel):
    category: str
    title_count: int = Field(ge=0)
    copy_count: int = Field(ge=0)


class PopularBook(BaseModel):
    book_id: int = Field(gt=0)
    book_code: str
    title: str
    borrow_count: int = Field(ge=0)


class OverdueBucket(BaseModel):
    label: str
    count: int = Field(ge=0)


class AnalyticsResponse(BaseModel):
    as_of: date
    start_date: date
    end_date: date
    daily_trends: list[DailyTrend]
    category_distribution: list[CategoryStat]
    popular_books: list[PopularBook]
    overdue_buckets: list[OverdueBucket]
