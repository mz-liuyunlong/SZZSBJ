from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.db import session as db_session
from app.main import create_app

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"


@pytest.fixture
def isolated_postgresql_session() -> Iterator[Session]:
    try:
        settings = Settings()  # type: ignore[call-arg]  # Values come from environment sources.
        url = get_test_database_url(settings)
    except (SettingsError, ValidationError):
        pytest.skip("isolated PostgreSQL test database is not configured")

    engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(
                    bind=connection,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session
            finally:
                if transaction.is_active:
                    transaction.rollback()
    finally:
        engine.dispose()


def test_engine_is_lazy_cached_and_disposable(monkeypatch: pytest.MonkeyPatch) -> None:
    db_session.dispose_engine()
    engine = MagicMock(spec=Engine)
    create_engine_mock = MagicMock(return_value=engine)
    monkeypatch.setattr(db_session, "create_engine", create_engine_mock)
    monkeypatch.setattr(
        db_session,
        "get_database_url",
        lambda: SYNTHETIC_DATABASE_URL,
    )

    assert not create_engine_mock.called
    assert db_session.get_engine() is engine
    assert db_session.get_engine() is engine
    create_engine_mock.assert_called_once_with(
        SYNTHETIC_DATABASE_URL,
        pool_pre_ping=True,
        hide_parameters=True,
    )

    db_session.dispose_engine()
    engine.dispose.assert_called_once_with()


def test_session_dependency_does_not_commit_and_always_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(db_session, "get_session_factory", lambda: factory)

    dependency = db_session.get_db_session()
    assert next(dependency) is session
    with pytest.raises(StopIteration):
        next(dependency)

    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_called_once_with()


def test_session_dependency_rolls_back_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(db_session, "get_session_factory", lambda: factory)

    dependency = db_session.get_db_session()
    assert next(dependency) is session
    with pytest.raises(RuntimeError, match="synthetic failure"):
        dependency.throw(RuntimeError("synthetic failure"))

    session.commit.assert_not_called()
    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()


def test_health_does_not_create_a_database_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_session.dispose_engine()
    create_engine_mock = MagicMock(side_effect=AssertionError("engine created"))
    monkeypatch.setattr(db_session, "create_engine", create_engine_mock)

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    create_engine_mock.assert_not_called()


def test_isolated_postgresql_fixture(
    isolated_postgresql_session: Session,
) -> None:
    assert isolated_postgresql_session.get_bind() is not None
