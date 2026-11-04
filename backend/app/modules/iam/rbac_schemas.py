from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PermissionType = Literal["page", "action", "field"]
RiskLevel = Literal["normal", "high"]
ScopeType = Literal["source_account", "store", "owner", "sku", "product", "org_department"]


class PermissionItemRead(BaseModel):
    permission_key: str
    name: str
    description: str | None = None
    permission_type: PermissionType
    module_key: str
    page_key: str
    action_key: str | None = None
    field_key: str | None = None
    risk_level: RiskLevel
    sort_order: int


class PermissionPageRead(BaseModel):
    page_key: str
    name: str
    permission_key: str
    sort_order: int
    actions: list[PermissionItemRead] = Field(default_factory=list)
    fields: list[PermissionItemRead] = Field(default_factory=list)


class PermissionModuleRead(BaseModel):
    module_key: str
    name: str
    sort_order: int
    pages: list[PermissionPageRead] = Field(default_factory=list)


class PermissionCatalogRead(BaseModel):
    version: str = "2"
    modules: list[PermissionModuleRead] = Field(default_factory=list)


class RbacRoleRead(BaseModel):
    id: str
    role_key: str
    name: str
    description: str | None
    is_system: bool
    user_count: int
    permission_keys: list[str]
    version: int


class RbacRoleCreateRequest(BaseModel):
    role_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9:_-]+$")
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    permission_keys: list[str] = Field(default_factory=list)


class RbacRoleUpdateRequest(BaseModel):
    permission_keys: list[str]
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)


class UserRoleOptionRead(BaseModel):
    role_key: str
    name: str
    description: str | None
    is_system: bool
    assignable: bool


class UserRolesUpdateRequest(BaseModel):
    role_keys: list[str]


class DataScopeEntryRead(BaseModel):
    scope_type: ScopeType
    scope_value: str


class DataScopeEntryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_type: ScopeType
    scope_value: str = Field(min_length=1, max_length=128)


class RoleDataScopeRead(BaseModel):
    role_key: str
    items: list[DataScopeEntryRead] = Field(default_factory=list)


class RoleDataScopeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DataScopeEntryWrite] = Field(max_length=500)


class EffectiveDataScopeEntryRead(DataScopeEntryRead):
    source: Literal["user", "role"]


class UserDataScopeRead(BaseModel):
    user_id: int
    items: list[DataScopeEntryRead] = Field(default_factory=list)
    role_items: list[DataScopeEntryRead] = Field(default_factory=list)
    effective_items: list[EffectiveDataScopeEntryRead] = Field(default_factory=list)


class UserDataScopeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DataScopeEntryWrite] = Field(max_length=500)


class AuditEventRead(BaseModel):
    id: str
    actor_user_id: int | None
    event_type: str
    target_type: str
    target_key: str
    before: dict[str, object] | list[object] | None = None
    after: dict[str, object] | list[object] | None = None
    request_id: str | None
    request_ip: str | None
    user_agent: str | None
    created_at: datetime
