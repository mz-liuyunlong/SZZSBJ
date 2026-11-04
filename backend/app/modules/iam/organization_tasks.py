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
