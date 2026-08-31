"""Schemas used by CSV import and export endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileImportError(BaseModel):
    """One data row that prevented an import from being committed."""

    row: int = Field(ge=1, description="Original CSV row number, including the header")
    reason: str


class FileImportResult(BaseModel):
    """Outcome of a books CSV import."""

    total: int = Field(ge=0)
    success: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: list[FileImportError] = Field(default_factory=list)


# Compatibility aliases for clients that used conventional schema names.
ImportErrorItem = FileImportError
ImportResult = FileImportResult
FileImportResponse = FileImportResult
