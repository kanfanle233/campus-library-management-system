"""Reader request and response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _trim_required(value: object, field_name: str) -> object:
    if not isinstance(value, str):
        return value
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name}不能为空")
    return value


class ReaderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    student_id: str = Field(min_length=1, max_length=64)
    contact: str = Field(min_length=1, max_length=100)
    borrow_limit: int = Field(gt=0)
    password: str = Field(min_length=1, max_length=255)

    @field_validator("name", "student_id", "contact", mode="before")
    @classmethod
    def trim_text(cls, value: object, info: object) -> object:
        field_name = getattr(info, "field_name", "字段")
        return _trim_required(value, field_name)


class ReaderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    student_id: str | None = Field(default=None, min_length=1, max_length=64)
    contact: str | None = Field(default=None, min_length=1, max_length=100)
    borrow_limit: int | None = Field(default=None, gt=0)
    password: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("name", "student_id", "contact", mode="before")
    @classmethod
    def trim_optional_text(cls, value: object, info: object) -> object:
        if value is None:
            return value
        field_name = getattr(info, "field_name", "字段")
        return _trim_required(value, field_name)


class ReaderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login_name: str | None = None
    student_id: str | None = None
    name: str
    contact: str | None = None
    borrow_limit: int
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# Common aliases keep imports stable for callers that use shorter names.
ReaderOut = ReaderResponse
ReaderCreateRequest = ReaderCreate
ReaderUpdateRequest = ReaderUpdate

