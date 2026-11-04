"""Opt-in Feishu organization snapshot reconciliation.

Never writes on worker startup or when disabled. Each tick reads the visible
directory, applies only a fully verified non-destructive snapshot, and leaves
unexpected identity replacement for administrator preview and approval.
"""

from __future__ import annotations

import logging
import os

from app.celery_app import celery_app
from app.db.session import get_session_factory
from app.modules.iam.organization_event_inbox import (
    acknowledge_events,
    claim_events,
    reschedule_events,
)
from app.modules.iam.organization_snapshot import apply_snapshot, canonical_snapshot
from app.modules.iam.organization_sync_router import _read_feishu

logger = logging.getLogger("app.iam.organization_sync")


@celery_app.task(name="iam.organization_sync_tick", ignore_result=True)  # type: ignore[misc]
def organization_sync_tick() -> None:
    """Scheduled read/reconcile, disabled unless explicitly opted in."""
    if os.getenv("SZZSBJ_FEISHU_ORG_AUTO_SYNC_ENABLED") != "1":
        return

    departments, users = _read_feishu()
    digest, normalized_departments, normalized_users = canonical_snapshot(departments, users)
    if not normalized_departments or not normalized_users:
        logger.warning("feishu_org_sync_empty_directory: manual review required")
        return

    with get_session_factory()() as session:
        try:
            run_id = apply_snapshot(
                session,
                expected_hash=digest,
                departments=departments,
                users=users,
                requested_by="system:feishu-org-auto",
                allow_large_reduction=False,
                allow_identity_replacement=False,
            )
        except ValueError:
            session.rollback()
            logger.warning("feishu_org_sync_identity_change: manual review required")
            return
        session.commit()
        logger.info("feishu_org_sync_reconciled run_id=%s", run_id)


@celery_app.task(name="iam.organization_event_tick", ignore_result=True)  # type: ignore[misc]
def organization_event_tick() -> None:
    """Consume authenticated callbacks in batches and reconcile a fresh directory.

    Both switches are required. No callback contents are used as authorization
    data; only a new, complete, safety-checked provider snapshot can be applied.
    """
    if (
        os.getenv("SZZSBJ_FEISHU_ORG_EVENTS_ENABLED") != "1"
        or os.getenv("SZZSBJ_FEISHU_ORG_AUTO_SYNC_ENABLED") != "1"
    ):
        return

    with get_session_factory()() as session:
        events = claim_events(session)
        session.commit()  # Durable claim; crashed workers are reclaimed by lease.
    if not events:
        return
    event_ids = [str(event["event_id"]) for event in events]
    try:
        departments, users = _read_feishu()
        digest, normalized_departments, normalized_users = canonical_snapshot(
            departments, users
        )
        if not normalized_departments or not normalized_users:
            raise ValueError("Feishu directory empty")
        with get_session_factory()() as session:
            run_id = apply_snapshot(
                session,
                expected_hash=digest,
                departments=departments,
                users=users,
                requested_by="system:feishu-org-event",
                allow_large_reduction=False,
                allow_identity_replacement=False,
            )
            acknowledge_events(session, event_ids, run_id)
            session.commit()
        logger.info("feishu_org_events_reconciled count=%d", len(events))
    except ValueError:
        with get_session_factory()() as session:
            reschedule_events(session, events, error_code="IDENTITY_REVIEW", manual_review=True)
            session.commit()
        logger.warning("feishu_org_events_need_review count=%d", len(events))
    except Exception:
        with get_session_factory()() as session:
            reschedule_events(session, events, error_code="RECONCILE_FAILURE")
            session.commit()
        logger.error("feishu_org_events_reconcile_failed count=%d", len(events))
