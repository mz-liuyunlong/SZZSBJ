"""Reject unsafe targets before creating a connection or destroying a database."""

import pytest
from sqlalchemy.engine import make_url

from tests.db.domestic_postgresql_support import admin_url, drop_database


@pytest.mark.parametrize(
    "change",
    [
        {"APP_ENV": "production"},
        {"TEST_DATABASE_URL": "postgresql+psycopg://x:x@127.0.0.1:5432/szzsbj_app"},
        {
            "TEST_DATABASE_URL": "postgresql+psycopg://domestic_chain_ci:x@remote:5432/domestic_chain_ci"
        },
        {"TEST_DATABASE_URL": ""},
    ],
)
def test_refuses_unsafe_database_target(monkeypatch, change):
    monkeypatch.setenv("DOMESTIC_CHAIN_DB_TESTS", "1")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://domestic_chain_ci:synthetic@127.0.0.1:5432/domestic_chain_ci",
    )
    for name, value in change.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(pytest.fail.Exception):
        admin_url()


def test_cannot_drop_database_owned_by_another_process():
    url = make_url("postgresql+psycopg://domestic_chain_ci:x@127.0.0.1:5432/domestic_chain_ci")
    with pytest.raises(RuntimeError, match="not created by this test process"):
        drop_database(url, "szzsbj_chain_existing_shared")
