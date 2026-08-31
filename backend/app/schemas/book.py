"""Schemas for the book inventory API."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_MONEY_QUANTUM = Decimal("0.01")


def _parse_price(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("price must be a decimal amount") from None
    if not result.is_finite() or result < 0:
        raise ValueError("price must be non-negative")
    if result != result.quantize(_MONEY_QUANTUM):
        raise ValueError("price must have at most two decimal places")
    return result.quantize(_MONEY_QUANTUM)


def normalize_isbn(value: str) -> str:
    return re.sub(r"[\s-]+", "", value)


class BookCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    author: str
    isbn: str
    publisher: str
    price: Decimal = Field(default=Decimal("0.00"), max_digits=14, decimal_places=2)
    category: str
    quantity: int | None = Field(default=None, ge=0)
    total_quantity: int | None = Field(default=None, ge=0)

    @field_validator("title", "author", mode="before")
    @classmethod
    def _required_text(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a non-empty string")
        value = value.strip()
        if not value:
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("isbn", mode="before")
    @classmethod
    def _isbn(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a non-empty string")
        value = normalize_isbn(value.strip())
        if not value:
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("publisher", "category", mode="before")
    @classmethod
    def _required_optional_text(cls, value: Any) -> str:
        if value is None:
            raise ValueError("must be a non-empty string")
        if not isinstance(value, str):
            raise ValueError("must be a non-empty string")
        value = value.strip()
        if not value:
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("price", mode="before")
    @classmethod
    def _price(cls, value: Any) -> Decimal:
        return _parse_price(value)

    @model_validator(mode="after")
    def _quantity_fields(self) -> "BookCreate":
        if self.quantity is not None and self.total_quantity is not None:
            if self.quantity != self.total_quantity:
                raise ValueError("quantity and total_quantity must match")
        if self.quantity is None and self.total_quantity is None:
            raise ValueError("quantity or total_quantity is required")
        if self.total_quantity is None:
            self.total_quantity = self.quantity
        return self


class BookUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    price: Decimal | None = None
    category: str | None = None
    quantity: int | None = Field(default=None, ge=0)
    total_quantity: int | None = Field(default=None, ge=0)

    @field_validator("title", "author", mode="before")
    @classmethod
    def _required_text_if_present(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a non-empty string")
        value = value.strip()
        if not value:
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("isbn", mode="before")
    @classmethod
    def _isbn_if_present(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a non-empty string")
        value = normalize_isbn(value.strip())
        if not value:
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("publisher", "category", mode="before")
    @classmethod
    def _optional_text_if_present(cls, value: Any) -> str | None:
        if value is None:
            raise ValueError("must be a non-empty string")
        if not isinstance(value, str):
            raise ValueError("must be a string")
        value = value.strip()
        if not value:
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("price", mode="before")
    @classmethod
    def _price_if_present(cls, value: Any) -> Decimal | None:
        return None if value is None else _parse_price(value)

    @model_validator(mode="after")
    def _quantity_fields(self) -> "BookUpdate":
        if self.quantity is not None and self.total_quantity is not None:
            if self.quantity != self.total_quantity:
                raise ValueError("quantity and total_quantity must match")
        if self.total_quantity is None and self.quantity is not None:
            self.total_quantity = self.quantity
        return self


class BookRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_code: str
    title: str
    author: str
    isbn: str
    publisher: str | None
    price: str
    category: str | None
    total_quantity: int
    available_quantity: int
    is_active: bool


class PageBookRead(BaseModel):
    items: list[BookRead]
    total: int
    page: int
    page_size: int
