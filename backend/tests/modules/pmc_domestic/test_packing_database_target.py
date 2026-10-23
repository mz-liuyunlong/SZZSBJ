"""Packing writes follow the process environment and never treat local as production."""

from sqlalchemy.engine import make_url

from app.modules.pmc_domestic.packing_service import (
    database_write_allowed,
    verification_record,
)

LOCAL = make_url("postgresql+psycopg://postgres@127.0.0.1:55432/szzsbj_dev")
TEST = make_url("postgresql+psycopg://postgres@127.0.0.1:55432/szzsbj_test")
PRODUCTION = make_url("postgresql+psycopg://app@10.0.0.8:5432/application")


def test_local_and_test_remain_isolated():
    assert database_write_allowed("local", LOCAL)
    assert database_write_allowed("test", TEST)
    assert not database_write_allowed("local", TEST)
    assert not database_write_allowed("local", PRODUCTION)
    assert not database_write_allowed("test", LOCAL)
    assert not database_write_allowed("production", LOCAL)
    assert not database_write_allowed("production", TEST)


def test_production_uses_its_own_database_and_formal_records():
    assert database_write_allowed("production", PRODUCTION)
    queried = make_url("postgresql+psycopg://app@10.0.0.8:5432/application?sslmode=require")
    assert not database_write_allowed("production", queried)
    assert not database_write_allowed("staging", PRODUCTION)
    assert verification_record("local")
    assert verification_record("test")
    assert not verification_record("production")
