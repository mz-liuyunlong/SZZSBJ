"""New-product operational source, isolated from PR337 decision persistence.

No hardcoded endpoints or local startup entrypoints. Dedicated source sessions are
transaction READ ONLY, including when production uses the application's normal DB.
Local independent-database development must supply NEW_PRODUCTS_READ_DATABASE_URL
from trusted runtime configuration; missing configuration fails closed.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.auth import Principal, require_principal
from app.core.config import get_database_url
from app.db.session import get_engine
from app.modules.integration_sync.dependencies import (
    SourceAccountScopeProvider,
    get_source_account_scope_provider,
    require_source_account_scope,
)


def source_url():
    raw = os.getenv("NEW_PRODUCTS_READ_DATABASE_URL", "").strip()
    if not raw:
        # Existing deployment uses the same business database and does not
        # require a second connection. Local development may not silently read
        # the independent write-test database as if it were real sales data.
        if os.getenv("APP_ENV", "").strip().lower() in ("local", "dev", "test"):
            raise ApiError(
                code="NEW_PRODUCT_READ_SOURCE_MISSING",
                status_code=503,
                message="真实商品只读数据源未配置",
            )
        return None
    try:
        url = make_url(raw)
    except Exception:
        raise ApiError(
            code="NEW_PRODUCT_READ_SOURCE_INVALID",
            status_code=503,
            message="真实商品数据源配置无效",
        ) from None
    if url.drivername != "postgresql+psycopg" or not url.host or not url.database:
        raise ApiError(
            code="NEW_PRODUCT_READ_SOURCE_INVALID",
            status_code=503,
            message="真实商品数据源必须为 PostgreSQL psycopg",
        )
    write_url = get_database_url()
    if (url.host, url.port, url.database) == (write_url.host, write_url.port, write_url.database):
        # Separate operational and decision sources are mandatory when an
        # explicit read URL is provided; prevents bypassing the write boundary.
        raise ApiError(
            code="NEW_PRODUCT_SOURCE_COLLISION",
            status_code=503,
            message="经营只读库与业务写库不得指向同一个目标",
        )
    return url


@lru_cache(maxsize=1)
def _source_engine(url_repr: str) -> Engine:
    return create_engine(
        url_repr,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"options": "-c default_transaction_read_only=on", "connect_timeout": 8},
    )


def get_new_product_read_session() -> Generator[Session]:
    configured = source_url()
    engine = (
        _source_engine(configured.render_as_string(hide_password=False))
        if configured
        else get_engine()
    )
    with Session(engine, autoflush=False, expire_on_commit=False) as session:
        # Read-only transaction also protects the production same-DB path.
        session.execute(text("SET TRANSACTION READ ONLY"))
        # Transaction-local upper bound for stuck analytical SELECTs; no global GUC writes.
        session.execute(text("SELECT set_config('statement_timeout', '20000', true)"))
        try:
            yield session
        finally:
            session.rollback()


def require_new_product_scope(
    principal: Annotated[Principal, Depends(require_principal)],
    provider: Annotated[
        SourceAccountScopeProvider | None, Depends(get_source_account_scope_provider)
    ],
    source: Annotated[Session, Depends(get_new_product_read_session)],
) -> frozenset[str]:
    # Reuse the established real IAM source-account scope policy, but resolve
    # registry permissions from the same operational database being queried.
    return require_source_account_scope(principal, provider, source)
