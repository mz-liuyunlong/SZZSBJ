"""Read-only access to existing production business data.

The live database is NEVER a migration or write destination.
This module does not replace the local database engine.
"""
from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, URL, create_engine, event, text
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment, get_database_url, get_settings


def _validate_environment() -> None:
    if os.getenv("SZZSBJ_DEV_LIVE_READ") != "1":
        raise RuntimeError("Live read mode is not enabled")

    if get_settings().app_env is not AppEnvironment.LOCAL:
        raise RuntimeError("Live read requires local environment")

    local = get_database_url()
    if (
        local.host != "127.0.0.1"
        or local.port != 55433
        or local.database != "szzsbj_dev"
    ):
        raise RuntimeError("Local database identity mismatch")


def _password() -> str:
    home = Path.home()
    paths = (
        home / ".szzsbj/dev/production-db.password",
        home / ".szzsbj/acceptance/production-db.password",
    )
    path = next((p for p in paths if p.is_file()), None)
    if path is None or path.is_symlink():
        raise RuntimeError("Live read credential is unavailable")

    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RuntimeError("Live read credential permissions unsafe")

    password = path.read_text().strip()
    if not password:
        raise RuntimeError("Live read credential is empty")
    return password


@lru_cache(maxsize=1)
def get_live_read_engine() -> Engine:
    _validate_environment()

    url = URL.create(
        "postgresql+psycopg",
        username="szzsbj_local_rw",
        password=_password(),
        host="127.0.0.1",
        port=15432,
        database="szzsbj_app",
    )

    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 8,
            "options": (
                "-c default_transaction_read_only=on "
                "-c statement_timeout=10000 "
                "-c idle_in_transaction_session_timeout=15000"
            ),
        },
    )

    @event.listens_for(engine, "begin")
    def enforce_read_only(connection):
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")

    return engine


@contextmanager
def live_read_session() -> Iterator[Session]:
    with Session(
        get_live_read_engine(),
        autoflush=False,
        expire_on_commit=False,
    ) as session:
        yield session


def probe_live_read() -> dict[str, object]:
    with get_live_read_engine().connect() as connection:
        row = connection.execute(text(
            "SELECT current_database(), current_user, "
            "current_setting('transaction_read_only')"
        )).one()

        if tuple(row) != (
            "szzsbj_app", "szzsbj_local_rw", "on"
        ):
            raise RuntimeError("Live database read-only check failed")

        revision = connection.scalar(text(
            "SELECT version_num FROM alembic_version"
        ))

        users = connection.scalar(text(
            "SELECT count(*) FROM app_users"
        ))

        return {
            "database": row[0],
            "read_only_transaction": True,
            "revision": revision,
            "account_count": users,
        }
