from __future__ import annotations

from typing import Generic, TypeVar, Any
from uuid import uuid4

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApiMeta(BaseModel):
    pagination: dict[str, Any] | None = None
    source: str | None = None
    source_tables: list[str] = Field(default_factory=list)
    freshness: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: ApiError | None = None
    meta: ApiMeta | None = None
    request_id: str


def ok(data: T, *, meta: ApiMeta | None = None, request_id: str | None = None) -> ApiResponse[T]:
    return ApiResponse(success=True, data=data, error=None, meta=meta, request_id=request_id or f"req_{uuid4().hex}")


def fail(code: str, message: str, *, details: dict[str, Any] | None = None, request_id: str | None = None) -> ApiResponse[None]:
    return ApiResponse(
        success=False,
        data=None,
        error=ApiError(code=code, message=message, details=details or {}),
        meta=None,
        request_id=request_id or f"req_{uuid4().hex}",
    )
