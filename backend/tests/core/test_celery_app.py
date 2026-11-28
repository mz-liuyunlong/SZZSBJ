from __future__ import annotations

import importlib

import pytest

from app.celery_app import (
    AI_QUEUE,
    BROKER_URL_ENV,
    INTEGRATION_QUEUE,
    MEDIA_QUEUE,
    NOTIFICATION_QUEUE,
    OPERATION_LOG_QUEUE,
    REQUIRE_BROKER_ENV,
    TASK_IMPORTS,
    TASK_ROUTES,
    create_celery_app,
    get_broker_url,
)


def test_task_routes_are_queue_isolated() -> None:
    assert TASK_ROUTES["media_assets.*"]["queue"] == MEDIA_QUEUE
    assert TASK_ROUTES["integration_sync.*"]["queue"] == INTEGRATION_QUEUE
    assert TASK_ROUTES["operation_logs.*"]["queue"] == OPERATION_LOG_QUEUE
    assert TASK_ROUTES["business_connectors.*"]["queue"] == NOTIFICATION_QUEUE
    assert TASK_ROUTES["ai_runtime.*"]["queue"] == AI_QUEUE
    assert TASK_ROUTES["media_assets.*"]["queue"] != TASK_ROUTES["integration_sync.*"]["queue"]


def test_celery_app_declares_only_expected_queues() -> None:
    celery = create_celery_app(broker_url="memory://")

    assert celery.conf.task_routes == TASK_ROUTES
    assert {queue.name for queue in celery.conf.task_queues} == {
        MEDIA_QUEUE,
        INTEGRATION_QUEUE,
        OPERATION_LOG_QUEUE,
        NOTIFICATION_QUEUE,
        AI_QUEUE,
    }
    assert celery.conf.task_create_missing_queues is False
    assert celery.conf.task_default_queue == INTEGRATION_QUEUE
    assert celery.conf.broker_url == "memory://"
    assert "app.modules.ai_runtime.tasks" in TASK_IMPORTS
    assert "app.modules.approvals.tasks" not in TASK_IMPORTS
    assert "approvals.*" not in TASK_ROUTES
    assert "approval-reminder-scheduler" not in celery.conf.beat_schedule
    assert celery.conf.beat_schedule["business-notifications-retry"] == {
        "task": "business_connectors.notification_tick",
        "schedule": 60.0,
    }
    assert (
        celery.conf.beat_schedule["ai-keyword-recovery"]["task"]
        == "ai_runtime.recover_keyword_jobs"
    )
    assert celery.conf.beat_schedule["integration-sync-scheduler"] == {
        "task": "integration_sync.scheduler_tick",
        "schedule": 60.0,
    }


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


def test_walmart_recon_payout_beat_only_in_production_with_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "walmart-bills-recon-payout-weekly"
    assert "app.modules.walmart_bills.tasks" in TASK_IMPORTS
    assert TASK_ROUTES["walmart_bills.*"]["queue"] == INTEGRATION_QUEUE
    assert "app.modules.settlement_profit.tasks" in TASK_IMPORTS
    assert TASK_ROUTES["settlement_profit.*"]["queue"] == INTEGRATION_QUEUE
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("SZZSBJ_WALMART_RECON_PAYOUT_ENABLED", "1")
    assert key not in create_celery_app(broker_url="memory://").conf.beat_schedule
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SZZSBJ_WALMART_RECON_PAYOUT_ENABLED", raising=False)
    assert key not in create_celery_app(broker_url="memory://").conf.beat_schedule
    monkeypatch.setenv("SZZSBJ_WALMART_RECON_PAYOUT_ENABLED", "1")
    entry = create_celery_app(broker_url="memory://").conf.beat_schedule[key]
    assert entry["task"] == "walmart_bills.recon_payout_sync"


@pytest.mark.parametrize(
    ("environment", "switch", "enabled"),
    [
        ("production", None, True),
        ("production", "YES", True),
        ("production", "0", False),
        ("production", "false", False),
        ("production", "", False),
        ("production", "invalid", False),
        ("local", None, False),
        ("test", "YES", False),
        ("staging", "YES", False),
    ],
)
def test_sku_progress_refresh_beat_and_worker_share_gate(
    monkeypatch: pytest.MonkeyPatch, environment: str, switch: str | None, enabled: bool
) -> None:
    from unittest.mock import MagicMock

    from app.modules.new_products import sku_progress_tasks as tasks

    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.delenv("SZZSBJ_SKU_PROGRESS_REFRESH_ENABLED", raising=False)
    if switch is not None:
        monkeypatch.setenv("SZZSBJ_SKU_PROGRESS_REFRESH_ENABLED", switch)
    schedule = create_celery_app(broker_url="memory://").conf.beat_schedule
    key = "new-products-sku-progress-refresh"
    assert (key in schedule) is enabled
    if enabled:
        assert schedule[key] == {"task": "new_products.sku_progress_refresh", "schedule": 600.0}
    factory = MagicMock()
    refresh = MagicMock(return_value={"status": "complete"})
    monkeypatch.setattr(tasks, "get_session_factory", factory)
    monkeypatch.setattr(tasks, "refresh_sources", refresh)
    assert tasks.sku_progress_refresh.run() == {"status": "complete" if enabled else "disabled"}
    if enabled:
        factory.assert_called_once_with()
        refresh.assert_called_once()
    else:
        factory.assert_not_called()
        refresh.assert_not_called()
