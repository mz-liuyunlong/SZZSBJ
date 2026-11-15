"""Single background entry for whole PR337 performance publication.

Daily schedule and successful performance-rule application call this same job.
This is NOT an ad-specific task. Disabled until a separate explicit rollout.
"""
from __future__ import annotations

from app.celery_app import celery_app
from .unified_publish import execute_unified_job, permission_to_write


@celery_app.task(name="new_products.performance_unified_publish", ignore_result=True)
def publish_performance(trigger: str = "daily") -> dict:
    if trigger not in {"daily", "rule_apply"}:
        return {"status": "invalid_trigger"}
    if not permission_to_write():
        return {"status": "disabled"}
    return {"status": "complete", "trigger": trigger,
            **execute_unified_job(limit=500, apply=True)}
