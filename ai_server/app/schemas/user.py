from __future__ import annotations

from pydantic import BaseModel, Field


class UserCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    role: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    preferred_language: str = Field(default='ko', max_length=20)
    report_style: str = Field(default='standard', max_length=80)


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    preferred_language: str | None = Field(default=None, max_length=20)
    report_style: str | None = Field(default=None, max_length=80)


class UserResponse(BaseModel):
    user_id: str
    display_name: str
    role: str | None = None
    department: str | None = None
    preferred_language: str = 'ko'
    report_style: str = 'standard'
    created_at: str
    updated_at: str
    deleted_at: str | None = None
