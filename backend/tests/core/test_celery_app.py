from __future__ import annotations

import importlib

import pytest

from app.celery_app import (
    BROKER_URL_ENV,
    INTEGRATION_QUEUE,
    MEDIA_QUEUE,
    REQUIRE_BROKER_ENV,
    TASK_IMPORTS,
    TASK_ROUTES,
    create_celery_app,
    get_broker_url,
)


def test_task_routes_are_queue_isolated() -> None:
    assert TASK_ROUTES["media_assets.*"]["queue"] == MEDIA_QUEUE
    assert TASK_ROUTES["integration_sync.*"]["queue"] == INTEGRATION_QUEUE
    assert TASK_ROUTES["media_assets.*"]["queue"] != TASK_ROUTES["integration_sync.*"]["queue"]


def test_celery_app_declares_only_expected_queues() -> None:
    celery = create_celery_app(broker_url="memory://")

    assert celery.conf.task_routes == TASK_ROUTES
    assert {queue.name for queue in celery.conf.task_queues} == {
        MEDIA_QUEUE,
        INTEGRATION_QUEUE,
    }
    assert celery.conf.task_create_missing_queues is False
    assert celery.conf.task_default_queue == INTEGRATION_QUEUE
    assert celery.conf.broker_url == "memory://"


def test_task_modules_are_importable() -> None:
    for module_name in TASK_IMPORTS:
        importlib.import_module(module_name)


def test_missing_broker_fails_closed_when_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(BROKER_URL_ENV, raising=False)
    monkeypatch.setenv(REQUIRE_BROKER_ENV, "true")

    with pytest.raises(RuntimeError, match=BROKER_URL_ENV):
        get_broker_url()


def test_missing_broker_fails_closed_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(BROKER_URL_ENV, raising=False)
    monkeypatch.delenv(REQUIRE_BROKER_ENV, raising=False)
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(RuntimeError, match=BROKER_URL_ENV):
        get_broker_url()


def test_non_production_import_uses_memory_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(BROKER_URL_ENV, raising=False)
    monkeypatch.delenv(REQUIRE_BROKER_ENV, raising=False)
    monkeypatch.setenv("APP_ENV", "test")

    assert get_broker_url() == "memory://"


def test_explicit_broker_url_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(BROKER_URL_ENV, "redis://127.0.0.1:6379/0")
    monkeypatch.setenv(REQUIRE_BROKER_ENV, "true")

    assert get_broker_url() == "redis://127.0.0.1:6379/0"
