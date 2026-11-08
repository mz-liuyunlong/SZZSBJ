"""Explicit local clearance write isolation. No effects on production wiring.

Local dev reads existing data from the authorized 15432 tunnel and writes only
clearance/approval test records to the separate local Docker database 55433.
The guard is fail closed, checks BOTH URLs, and is never a global session override.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.api import ApiError, ErrorCode
from app.core.config import get_database_url, get_settings

_LOCAL_WRITE_ROUTES = frozenset(
    {
        ("POST", "/api/clearance/applications"),
        ("PUT", "/api/clearance/rules"),
    }
)
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_REVIEW = re.compile(rf"/api/clearance/applications/{_UUID}/(review|cancel|complete|reconcile)\Z")


def _blocked():
    raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)


def is_local() -> bool:
    return str(get_settings().app_env.value).lower() == "local"


def checked_local_db_url():
    """No user-supplied arbitrary hosts, production DB, SSL options or URL logging."""
    if not is_local():
        return None
    source = get_database_url(get_settings())
    raw = os.getenv("SZZSBJ_CLEARANCE_TEST_DB_URL", "")
    if os.getenv("SZZSBJ_CLEARANCE_TEST_WRITES", "0") != "1" or not raw:
        _blocked()
    target = make_url(raw)
    if (
        not source.drivername.startswith("postgresql")
        or source.host != "127.0.0.1"
        or source.port != 15432
        or source.database != "szzsbj_app"
        or not target.drivername.startswith("postgresql")
        or target.host != "127.0.0.1"
        or target.port != 55433
        or target.database != "szzsbj_dev"
        or source.query
        or target.query
    ):
        _blocked()
    return target


def is_clearance_write_route(method: str, path: str) -> bool:
    if not is_local():
        return False
    if not (
        (method, path) in _LOCAL_WRITE_ROUTES or (method == "POST" and _REVIEW.fullmatch(path))
    ):
        return False
    try:
        return checked_local_db_url() is not None
    except ApiError:
        return False


@lru_cache(maxsize=1)
def _write_factory():
    target = checked_local_db_url()
    if target is None:
        raise RuntimeError("Local database factory cannot be used in production")
    engine = create_engine(target, pool_pre_ping=True, hide_parameters=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def storage_session(read_session: Session, *, writable: bool = False) -> Iterator[Session]:
    if not is_local():
        yield read_session
        return
    # Fail closed for BOTH read and write operations against clearance storage.
    # An unset sandbox does not cause a read of missing tables from 15432.
    checked_local_db_url()
    store = _write_factory()()
    try:
        db_name = store.scalar(text("SELECT current_database()"))
        if db_name != "szzsbj_dev":
            _blocked()
        table_names = (
            "biz_clearance_applications",
            "biz_clearance_events",
            "biz_clearance_rule_versions",
            "app_approval_requests",
            "app_approval_events",
            "app_approval_step_decisions",
            "biz_listing_lifecycle_manual_states",
            "biz_listing_lifecycle_manual_history",
        )
        missing = [
            name
            for name in table_names
            if store.scalar(
                text("SELECT to_regclass(:table_name)"), {"table_name": f"public.{name}"}
            )
            is None
        ]
        if missing:
            raise RuntimeError(
                "Local clearance test schema is incomplete; no schema modification attempted"
            )
        yield store
        if store.in_transaction():
            store.rollback()  # A read endpoint never implicitly commits.
    except Exception:
        store.rollback()
        raise
    finally:
        store.close()
