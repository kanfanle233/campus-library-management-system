"""Request and response models for borrowing and returning books."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import FineStatus, LoanStatus
from app.schemas.book import normalize_isbn


class BorrowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The UI may submit the internal id, the generated book code, or ISBN.
    # Exactly one identifier is required; keeping all three in the contract
    # makes the endpoint usable by both an admin table and a scan/search form.
    book_id: int | None = Field(default=None, gt=0)
    isbn: str | None = Field(default=None, min_length=1, max_length=32)
    book_code: str | None = Field(default=None, min_length=1, max_length=64)
    reader_id: int | None = Field(default=None, gt=0)

    @field_validator("isbn", mode="before")
    @classmethod
    def normalize_isbn_value(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("isbn must be a string")
        normalized = normalize_isbn(value.strip())
        if not normalized:
            raise ValueError("isbn must be non-empty")
        return normalized

    @field_validator("book_code", mode="before")
    @classmethod
    def trim_book_code(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("book_code must be a string")
        value = value.strip()
        if not value:
            raise ValueError("book_code must be non-empty")
        return value

    @model_validator(mode="after")
    def require_one_book_identifier(self) -> "BorrowRequest":
        identifiers = [self.book_id is not None, self.isbn is not None, self.book_code is not None]
        if sum(identifiers) != 1:
            raise ValueError("exactly one of book_id, isbn or book_code is required")
        return self


class LoanQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoanOut(BaseModel):
    id: int
    loan_no: str
    reader_id: int
    student_id: str | None
    reader_name: str
    book_id: int
    book_code: str
    book_title: str
    isbn: str
    borrow_date: date
    due_date: date
    return_date: date | None
    status: LoanStatus
    overdue_days: int
    fine_amount: str
    fine_status: FineStatus


class LoanListResponse(BaseModel):
    items: list[LoanOut]
    total: int
    page: int
    page_size: int


class ReturnPreview(BaseModel):
    loan_no: str
    book_title: str
    due_date: date
    return_date: date
    overdue_days: int
    fine_amount: str
    fine_status: FineStatus
