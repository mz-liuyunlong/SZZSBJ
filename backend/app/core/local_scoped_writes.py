"""Local production-tunnel write allowlist; sync and all other writes blocked.

Only used by an explicitly acknowledged local run. Authentication, authorization,
data-scope checks and business validation remain active on permitted routes.
This is an HTTP entry-point restriction, not a PostgreSQL table-level permission.
"""

from __future__ import annotations

import os
import re

from fastapi import FastAPI, Request
from starlette.responses import Response

from app.core.api import error_response
from app.core.config import AppEnvironment, get_database_url, get_settings

# SZZSBJ_LOCAL_SCOPED_WRITE_GUARD_V1
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_EXACT_POST_PATHS = frozenset(("/api/auth/login", "/api/auth/logout"))

# Explicit operation-log business-write allowlist.
_EXACT_PUT_PATHS = frozenset(
    (
        "/api/operations/logs/manual/batch",
        "/api/operations/logs/links",
    )
)
_POST_PATH_PATTERNS = tuple(
    re.compile(rf"{pattern}")
    for pattern in (
        rf"/api/warehouse/wfs-fee-cases/{_UUID}/follow",
        rf"/api/approvals/wfs-cases/{_UUID}/decision",
        rf"/api/approvals/{_UUID}/decision",
        rf"/api/approvals/{_UUID}/supplement",
    )
)


def permitted_local_write(method: str, path: str) -> bool:
    """Default deny: do not allow sync, retry, backfill or broad WFS mutations."""
    # SQLite-only Decodo research is safe to run while the PostgreSQL
    # local production-tunnel write guard continues to block all other writes.
    # Access still requires the normal FastAPI authentication and permissions.
    if (
        method == "POST"
        and path in {
            "/api/keyword-planning/products/confirm",
            "/api/keyword-planning/amazon/research",
        }
        and os.getenv("APP_ENV", "").strip().lower() == "local"
        and os.getenv("DECODO_LOCAL_TEST_MODE", "").strip() == "1"
        and os.getenv("DECODO_LOCAL_TEST_ENABLE_REAL_CALLS", "").strip() == "1"
    ):
        return True
    if method == "PUT":
        return path in _EXACT_PUT_PATHS

    return method == "POST" and (
        path in _EXACT_POST_PATHS or any(pattern.fullmatch(path) for pattern in _POST_PATH_PATTERNS)
    )


def checked_scoped_mode() -> bool:
    value = os.getenv("SZZSBJ_LOCAL_SCOPED_PROD_WRITES", "").lower()
    if value not in ("", "0", "1"):
        raise RuntimeError("Local scoped write flag must be either 0 or 1")
    if value != "1":
        return False
    settings = get_settings()
    url = get_database_url(settings)
    if (
        settings.app_env is not AppEnvironment.LOCAL
        or not url.drivername.startswith("postgresql")
        or url.host != "127.0.0.1"
        or url.port != 15432
        or url.database != "szzsbj_app"
        or url.query.get("options")
        or os.getenv("PGOPTIONS")
        or os.getenv("LINGXING_ENABLE_REAL_CALLS", "false").lower() != "false"
        or os.getenv("DATA_PAGES_REAL_SYNC_AUTHORIZED", "false").lower() != "false"
        or os.getenv("PRODUCTLIST_REAL_SYNC_AUTHORIZED", "false").lower() != "false"
        or os.getenv("LINGXING_ENABLE_TOKEN_REQUESTS", "false").lower() != "false"
        or os.getenv("LINGXING_ALLOW_RAW_WRITE", "false").lower() != "false"
        or os.getenv("LINGXING_ALLOW_STRUCTURED_WRITE", "false").lower() != "false"
        or os.getenv("WALMART_CONNECT_ENABLE_REAL_CALLS", "false").lower() != "false"
        or os.getenv("CELERY_BROKER_URL") != "memory://"
        or os.getenv("SZZSBJ_CELERY_REQUIRE_BROKER", "false").lower() != "false"
        or settings.product_management_preview_auth_enabled
        or os.getenv("LINGXING_DRY_RUN", "true").lower() != "true"
    ):
        raise RuntimeError("Local scoped writes require exact safety configuration")
    return True


def install_local_scoped_write_guard(app: FastAPI) -> None:
    if not checked_scoped_mode():
        return

    @app.middleware("http")
    async def enforce_local_scoped_writes(request: Request, call_next) -> Response:
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)
        if permitted_local_write(request.method, request.url.path):
            return await call_next(request)
        return error_response(
            request,
            status_code=403,
            code="LOCAL_WRITE_DISABLED",
            message="当前本地模式禁止此操作（尤其是同步、重试、回填）",
        )
