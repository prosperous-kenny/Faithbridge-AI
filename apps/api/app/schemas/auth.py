"""Request and response models for the authentication endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.rbac import ROLE_VALUES


class RegisterIn(BaseModel):
    email: EmailStr
    # Policy (length bounds) is enforced here so a violation is a 422 with a
    # readable message rather than an opaque 500 from the hasher.
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    role: str = Field(default="community_member", max_length=50)
    organization_id: int | None = None

    @field_validator("role")
    @classmethod
    def role_must_be_known(cls, value: str) -> str:
        if value not in ROLE_VALUES:
            raise ValueError(f"Unknown role {value!r}. Allowed: {sorted(ROLE_VALUES)}")
        return value

    @field_validator("full_name")
    @classmethod
    def full_name_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("full_name must not be blank")
        return stripped


class LoginIn(BaseModel):
    email: EmailStr
    # Not bounded by the full policy: existing credentials must keep working,
    # and the hasher caps the work anyway.
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: str
    organization_id: int | None = None
    is_active: bool


class MessageOut(BaseModel):
    message: str
