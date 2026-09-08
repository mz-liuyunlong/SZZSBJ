import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_LOGGER = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    DATA_SCOPE_DENIED = "DATA_SCOPE_DENIED"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_SAFE_MESSAGES = {
    ErrorCode.INVALID_REQUEST: "请求无效",
    ErrorCode.VALIDATION_ERROR: "请求参数无效",
    ErrorCode.UNAUTHORIZED: "需要认证",
    ErrorCode.FORBIDDEN: "没有访问权限",
    ErrorCode.DATA_SCOPE_DENIED: "数据范围不允许",
    ErrorCode.NOT_FOUND: "资源不存在",
    ErrorCode.METHOD_NOT_ALLOWED: "请求方法不允许",
    ErrorCode.INTERNAL_ERROR: "服务器内部错误",
}


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class SuccessEnvelope[DataT, MetaT](BaseModel):
    success: Literal[True] = True
    data: DataT
    error: None = None
    meta: MetaT | None = None
    request_id: str


class ErrorEnvelope(BaseModel):
    success: Literal[False] = False
    data: None = None
    error: ErrorBody
    meta: None = None
    request_id: str


class ApiError(Exception):
    def __init__(
        self,
        *,
        code: str | ErrorCode,
        status_code: int,
        message: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        if not 400 <= status_code <= 599:
            raise ValueError("API errors require a 4xx or 5xx status")
        self.code = _validated_error_code(code)
        self.status_code = status_code
        self.message = message or _message_for(self.code)
        self.details = dict(details or {})
        super().__init__(self.code)


def get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id
    request_id = str(uuid4())
    request.state.request_id = request_id
    return request_id


def success_response[DataT, MetaT](
    request: Request,
    *,
    data: DataT,
    meta: MetaT | None = None,
) -> SuccessEnvelope[DataT, MetaT]:
    return SuccessEnvelope[DataT, MetaT](
        data=data,
        meta=meta,
        request_id=get_request_id(request),
    )


def error_response(
    request: Request,
    *,
    code: str | ErrorCode,
    status_code: int,
    message: str | None = None,
    details: Mapping[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    if not 400 <= status_code <= 599:
        raise ValueError("API errors require a 4xx or 5xx status")
    code_value = _validated_error_code(code)
    request_id = get_request_id(request)
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=code_value,
            message=message or _message_for(code_value),
            details=dict(details or {}),
        ),
        request_id=request_id,
    )
    response_headers = dict(headers or {})
    response_headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers=response_headers,
    )


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request.state.request_id = _safe_request_id(request.headers.get(REQUEST_ID_HEADER))
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = get_request_id(request)
    return response


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ApiError):
        return _internal_error_response(request, exc)
    return error_response(
        request,
        code=exc.code,
        status_code=exc.status_code,
        message=exc.message,
        details=exc.details,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        return _internal_error_response(request, exc)
    code = _http_error_code(exc.status_code)
    return error_response(
        request,
        code=code,
        status_code=exc.status_code,
        headers=_safe_http_headers(exc.headers) if exc.status_code == 405 else None,
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        return _internal_error_response(request, exc)
    errors: list[dict[str, object]] = []
    for error in exc.errors():
        errors.append(
            {
                "location": [str(part) for part in error.get("loc", ())],
                "reason": str(error.get("type", "invalid")),
            }
        )
    return error_response(
        request,
        code=ErrorCode.VALIDATION_ERROR,
        status_code=422,
        details={"errors": errors},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return _internal_error_response(request, exc)


def install_api_foundation(app: FastAPI) -> None:
    app.middleware("http")(request_id_middleware)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


def _safe_request_id(candidate: str | None) -> str:
    if candidate is not None:
        candidate = candidate.strip()
        if _REQUEST_ID_PATTERN.fullmatch(candidate):
            return candidate
    return str(uuid4())


def _message_for(code: str) -> str:
    try:
        return _SAFE_MESSAGES[ErrorCode(code)]
    except ValueError:
        return "请求失败"


def _validated_error_code(code: str | ErrorCode) -> str:
    value = str(code)
    if not value or value != value.strip():
        raise ValueError("error code must be a non-empty canonical value")
    return value


def _http_error_code(status_code: int) -> ErrorCode:
    return {
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        405: ErrorCode.METHOD_NOT_ALLOWED,
    }.get(
        status_code,
        ErrorCode.INVALID_REQUEST if 400 <= status_code < 500 else ErrorCode.INTERNAL_ERROR,
    )


def _safe_http_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    for name, value in headers.items():
        if name.lower() == "allow":
            return {"Allow": value}
    return {}


def _internal_error_response(request: Request, exc: Exception) -> JSONResponse:
    _LOGGER.error(
        "api_error request_id=%s method=%s route=%s status=500 error_code=%s exception_type=%s",
        get_request_id(request),
        request.method,
        _route_template(request),
        ErrorCode.INTERNAL_ERROR,
        type(exc).__name__,
    )
    return error_response(
        request,
        code=ErrorCode.INTERNAL_ERROR,
        status_code=500,
    )


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"
