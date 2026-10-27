"""Fail-closed notification retry worker.

Beat may enqueue this tick every minute. Nothing is sent unless the operator
sets BUSINESS_NOTIFICATIONS_OUTBOUND_ENABLED=true in the authorized runtime.
"""

from __future__ import annotations

import logging

from celery import shared_task

from app.modules.business_connectors.router import dispatch_pending

logger = logging.getLogger(__name__)


@shared_task(name="business_connectors.notification_tick", ignore_result=True)  # type: ignore[untyped-decorator]
def notification_tick() -> None:
    try:
        dispatch_pending(limit=10, actor="system:notification_worker")
    except Exception as exc:
        # Never log provider payloads, credentials or exception strings.
        logger.error("business_notification_dispatch_error type=%s", type(exc).__name__)
