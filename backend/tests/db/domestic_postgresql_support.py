"""Disposable databases on an explicitly selected, dedicated local CI cluster."""

import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import URL, make_url

_OWNED: set[tuple[str, str]] = set()


def admin_url() -> URL:
    if os.environ.get("DOMESTIC_CHAIN_DB_TESTS") != "1":
        pytest.skip("domestic PostgreSQL tests require explicit opt-in")
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw or os.environ.get("APP_ENV") != "test":
        pytest.fail("APP_ENV=test and TEST_DATABASE_URL are required")
    url = make_url(raw)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or not url.port
        or url.username != "domestic_chain_ci"
        or url.database != "domestic_chain_ci"
        or not url.password
        or url.query
    ):
        pytest.fail("refusing PostgreSQL target outside the dedicated domestic_chain_ci cluster")
    return url


def connect(url: URL, database: str) -> psycopg.Connection:
    return psycopg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        dbname=database,
        autocommit=True,
    )


def create_database(url: URL, label: str) -> str:
    database = "szzsbj_chain_" + label[:15] + "_" + uuid4().hex[:20]
    # CREATE (never DROP IF EXISTS) makes a collision fail without touching it.
    with connect(url, "domestic_chain_ci") as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    _OWNED.add((url.render_as_string(), database))
    return database


def drop_database(url: URL, database: str) -> None:
    key = (url.render_as_string(), database)
    if key not in _OWNED:
        raise RuntimeError("refusing to drop a database not created by this test process")
    with connect(url, "domestic_chain_ci") as admin:
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
    _OWNED.remove(key)
