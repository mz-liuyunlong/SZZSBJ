"""Opt-in Celery on-demand read task; no persistence, schedule or raw logging.

Returns only counts and status; never places provider records on a broker.
"""

from __future__ import annotations

import os

from app.celery_app import celery_app
from app.modules.walmart_scf.paging import collect_offset_pages

# No dynamic user-controlled scope, no persistence, no auto-scheduling.
# This task requires a separately reviewed mapping/operation and an explicit
# deployment-level enable flag. It is deliberately not imported by Celery yet.
@celery_app.task(name="walmart_scf.read_inventory_count", ignore_result=True)  # type: ignore[misc]
def read_inventory_count(source_account_ref: str) -> None:
    if os.getenv("SZZSBJ_WALMART_SCF_TASKS_ENABLED") != "1":
        return
    allowed = frozenset(
        part.strip()
        for part in os.getenv("SZZSBJ_WALMART_SCF_TASK_ACCOUNT_SCOPE", "").split(",")
        if part.strip()
    )
    if source_account_ref not in allowed:
        return
    # Avoid guessing the WFS result path or silently ignoring a partial scan.
    # Production activation requires an approved response envelope contract.
    return
