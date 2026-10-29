"""On-demand read-only Celery fetch; no scheduler or database writes.

Only deployment-reviewed account scopes, operation and pagination contracts
can be dispatched. Results never enter the broker or task logs.
"""

from __future__ import annotations

import os

from app.celery_app import celery_app
from app.core.api import ApiError
from app.modules.walmart_scf.paging import collect_offset_pages
from app.modules.walmart_scf.unified import store_code_for
from app.modules.walmart_scf.store_scope import verify_store
from app.db.session import get_session_factory


@celery_app.task(name="walmart_scf.read_inventory_count", ignore_result=True)  # type: ignore[misc]
def read_inventory_count(source_account_ref: str, store_id: str) -> None:
    """Opt-in one-store WFS page scan. No side effects except approved GET calls."""
    if os.getenv("SZZSBJ_WALMART_SCF_TASKS_ENABLED") != "1":
        raise ApiError(code="WALMART_SCF_TASKS_DISABLED", status_code=503)
    if os.getenv("SZZSBJ_WALMART_SCF_TASK_OPERATION") != "wfs_inventory":
        raise ApiError(code="WALMART_SCF_TASK_UNAPPROVED", status_code=503)
    allowed = frozenset(
        part.strip()
        for part in os.getenv("SZZSBJ_WALMART_SCF_TASK_ACCOUNT_SCOPE", "").split(",")
        if part.strip()
    )
    if not allowed or source_account_ref not in allowed:
        raise ApiError(code="WALMART_SCF_TASK_SCOPE_DENIED", status_code=403)
    allowed_stores = frozenset(
        part.strip()
        for part in os.getenv("SZZSBJ_WALMART_SCF_TASK_STORE_SCOPE", "").split(",")
        if part.strip()
    )
    if store_id not in allowed_stores:
        raise ApiError(code="WALMART_SCF_TASK_STORE_SCOPE_DENIED", status_code=403)
    # Worker uses a separate operator-reviewed allowlist; never infer user RBAC.
    with get_session_factory()() as session:
        verify_store(
            session=session,
            source_account_ref=source_account_ref,
            store_id=store_id,
            store_code=store_code_for(store_id),
        )
    # Explicitly approved response path; never assume a Walmart payload shape.
    if os.getenv("SZZSBJ_WALMART_SCF_WFS_ITEMS_PATH") != "inventory":
        raise ApiError(code="WALMART_SCF_PAGE_CONTRACT_UNVERIFIED", status_code=503)
    # Bounded, all-or-nothing fetch. Never return or persist business records.
    collect_offset_pages(
        source_account_ref=source_account_ref,
        store_id=store_id,
        verified_store_scope=allowed_stores,
        verified_source_account_scope=allowed,
        operation="wfs_inventory",
        items_path=("inventory",),
        page_size=10,
        max_pages=5,
        max_items=50,
    )
