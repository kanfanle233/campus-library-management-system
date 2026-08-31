"""Pydantic models used by the authentication API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    """Credentials accepted by both administrator and reader logins."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=255)

    @field_validator("username", mode="before")
    @classmethod
    def trim_username(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(TokenResponse):
    """Login response; user data is included for clients that need the role."""

    user: "ReaderIdentity"


class ReaderIdentity(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    name: str
    student_id: str | None = None


# Compatibility names for clients that use the conventional In/Out suffixes.
LoginIn = LoginRequest
TokenOut = TokenResponse
UserIdentity = ReaderIdentity
