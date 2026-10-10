from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)


class UserCreateRequest(RegisterRequest):
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role_keys: list[str] = Field(default_factory=list)
    feishu_name: str | None = Field(default=None, max_length=128)
    feishu_open_id: str | None = Field(default=None, max_length=128)
    feishu_user_id: str | None = Field(default=None, max_length=128)
    feishu_union_id: str | None = Field(default=None, max_length=128)
    feishu_employee_id: str | None = Field(default=None, max_length=128)
    feishu_department_ids: list[str] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    role_keys: list[str] | None = None
    feishu_name: str | None = Field(default=None, max_length=128)
    feishu_open_id: str | None = Field(default=None, max_length=128)
    feishu_user_id: str | None = Field(default=None, max_length=128)
    feishu_union_id: str | None = Field(default=None, max_length=128)
    feishu_employee_id: str | None = Field(default=None, max_length=128)
    feishu_department_ids: list[str] | None = None


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class UserRoleUpdateRequest(BaseModel):
    role_keys: list[str]


class RoleCreateRequest(BaseModel):
    role_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9:_-]+$")
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    permission_keys: list[str] = Field(default_factory=list)


class RoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    permission_keys: list[str] | None = None


class FeishuDirectoryUserRead(BaseModel):
    name: str
    open_id: str
    user_id: str | None = None
    union_id: str | None = None
    employee_id: str | None = None
    department_ids: list[str] = Field(default_factory=list)


class FeishuDirectorySearchResult(BaseModel):
    query_name: str
    matched_count: int
    is_unique: bool
    users: list[FeishuDirectoryUserRead]


class PermissionRead(BaseModel):
    permission_key: str
    name: str
    group_key: str
    description: str | None = None


class RoleRead(BaseModel):
    id: str
    role_key: str
    name: str
    description: str | None
    is_system: bool
    user_count: int
    permission_keys: list[str]


class UserRead(BaseModel):
    id: int
    username: str
    display_name: str | None
    phone: str | None
    email: str | None
    is_active: bool
    is_super_admin: bool
    role_keys: list[str]
    role_names: list[str]
    feishu_name: str | None = None
    feishu_open_id: str | None = None
    feishu_user_id: str | None = None
    feishu_union_id: str | None = None
    feishu_employee_id: str | None = None
    feishu_department_ids: list[str] = Field(default_factory=list)
    feishu_last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserRead


class CurrentUserRead(UserRead):
    permissions: list[str]
