from __future__ import annotations

import os

from celery import Celery
from kombu import Exchange, Queue

APP_NAME = "szzsbj"
BROKER_URL_ENV = "CELERY_BROKER_URL"
REQUIRE_BROKER_ENV = "SZZSBJ_CELERY_REQUIRE_BROKER"
APP_ENV_ENV = "APP_ENV"

MEDIA_QUEUE = "media"
INTEGRATION_QUEUE = "integration"

TASK_IMPORTS = (
    "app.modules.media_assets.tasks",
    "app.modules.integration_sync.tasks",
)

TASK_ROUTES = {
    "media_assets.*": {"queue": MEDIA_QUEUE, "routing_key": MEDIA_QUEUE},
    "integration_sync.*": {
        "queue": INTEGRATION_QUEUE,
        "routing_key": INTEGRATION_QUEUE,
    },
}


def _env_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_production_env() -> bool:
    return (os.environ.get(APP_ENV_ENV) or "").strip().lower() == "production"


def get_broker_url(*, require: bool | None = None) -> str:
    """Return the Celery broker URL with a fail-closed production guard."""
    broker_url = (os.environ.get(BROKER_URL_ENV) or "").strip()
    if broker_url:
        return broker_url

    require_broker = (
        _env_truthy(os.environ.get(REQUIRE_BROKER_ENV)) or _is_production_env()
        if require is None
        else require
    )
    if require_broker:
        raise RuntimeError("CELERY_BROKER_URL must be configured before starting a Celery worker.")

    # Local tests need importability without a broker service. Production is guarded above.
    return "memory://"


def create_celery_app(
    *,
    broker_url: str | None = None,
    require_broker: bool | None = None,
) -> Celery:
    effective_broker_url = (broker_url or "").strip() or get_broker_url(require=require_broker)
    exchange = Exchange(APP_NAME, type="direct")
    celery = Celery(APP_NAME, broker=effective_broker_url, include=TASK_IMPORTS)

    celery.conf.update(
        task_queues=(
            Queue(MEDIA_QUEUE, exchange, routing_key=MEDIA_QUEUE),
            Queue(INTEGRATION_QUEUE, exchange, routing_key=INTEGRATION_QUEUE),
        ),
        task_routes=TASK_ROUTES,
        task_default_queue=INTEGRATION_QUEUE,
        task_default_exchange=APP_NAME,
        task_default_exchange_type="direct",
        task_default_routing_key=INTEGRATION_QUEUE,
        task_create_missing_queues=False,
        result_backend=None,
        task_ignore_result=True,
        worker_hijack_root_logger=False,
        timezone="UTC",
        enable_utc=True,
    )
    return celery


celery_app = create_celery_app()
