"""Single page read of the approval workbench; decisions stay in existing routes."""

from __future__ import annotations

import logging
from contextlib import ExitStack
from time import perf_counter
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.api import ApiError, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import has_permission, is_approval_admin, require_permission
from app.db.session import get_db_session
from app.modules.approvals.applicant_names import attach_approval_names, attach_clearance_names
from app.modules.approvals.new_product_purchase_bridge import NewProductPurchaseBridge
from app.modules.approvals.schemas import (
    ApprovalItem,
    ApprovalListData,
    ApprovalMeta,
    ApprovalQuery,
)
from app.modules.approvals.service import ApprovalService
from app.modules.approvals.workbench_purchase_read import enrich_purchase_page
from app.modules.clearance import hybrid_v28
from app.modules.clearance import service as clearance_service
from app.modules.clearance.batch_read import enrich_application_rows
from app.modules.clearance.local_store_v28 import storage_session
from app.modules.clearance.rules import ClearanceRules
from app.modules.integration_sync.dependencies import (
    SourceAccountScopeProvider,
    get_source_account_scope_provider,
    require_source_account_scope,
)

# This router is included below the existing /api/approvals prefix.
workbench_read_router = APIRouter()
_LOGGER = logging.getLogger(__name__)


class PurchasePageRead(BaseModel):
    application_id: str
    version: int
    source_account_ref: str
    store_id: str
    item_id: str
    listing: dict[str, Any] | None
    daily: dict[str, Any] | None
    unit_purchase_cost_cny: str | None


class WorkbenchRow(ApprovalItem):
    risk_level: Literal["low", "medium", "high", "unknown", "none"]
    clearance_details: dict[str, Any] | None = None
    purchase_read: PurchasePageRead | None = None


class WorkbenchReadData(BaseModel):
    items: list[WorkbenchRow]
    business_counts: dict[str, int] = Field(default_factory=dict)


def _merge_page(query, groups):
    """Retain source ordering and exact global offsets; count each source once.

    A normal first page reads the needed rows on its count query, not a probe
    followed by a duplicate fetch. Other categories only need a bounded head.
    """
    selected = {
        "purchase_exception": {"np_purchase", "purchase"},
        "new_product_purchase": {"np_purchase"},
        "clearance_request": {"clearance"},
        "new_product_evaluation_review": {"newProduct"},
        "wfs_case_abandon": {"wfs"},
        "finance_exception": {"finance"},
    }
    active = (
        set(k for k, _, _ in groups if k != "finance")
        if not query.approval_type
        else selected.get(query.approval_type, set())
    )
    offset = (query.page - 1) * query.page_size
    result = []
    total = 0
    counts = {}
    for name, cap, fetch in groups:
        skip = max(0, offset - total) if name in active else 0
        remaining = query.page_size - len(result)
        first_size = min(cap, max(1, remaining)) if name in active and skip == 0 else 1
        first, n = fetch(1, first_size)
        if n < 0 or len(first) > first_size or len(first) > n:
            raise ApiError(code="WORKBENCH_SOURCE_INVALID", status_code=409)
        counts[name] = n
        if name not in active:
            continue
        take = min(remaining, max(0, n - skip))
        if take > 0:
            if skip == 0 and take <= len(first):
                result.extend(first[:take])
            else:
                cursor = skip
                stop = skip + take
                if cursor == 0 and first:
                    result.extend(first[:take])
                    cursor += min(len(first), take)
                while cursor < stop:
                    page = cursor // cap + 1
                    index = cursor % cap
                    needed = min(stop - cursor, cap - index)
                    chunk, new_total = fetch(page, cap)
                    if new_total != n or len(chunk[index : index + needed]) != needed:
                        raise ApiError(
                            code="WORKBENCH_SOURCE_CHANGED",
                            status_code=409,
                            message="审批列表已变化，请刷新",
                        )
                    result.extend(chunk[index : index + needed])
                    cursor += needed
        total += n
    return (
        result,
        total,
        {
            "all": sum(n for k, n in counts.items() if k != "finance"),
            "purchase": counts.get("np_purchase", 0) + counts.get("purchase", 0),
            "newProduct": counts.get("newProduct", 0),
            "wfs": counts.get("wfs", 0),
            "clearance": counts.get("clearance", 0),
            "finance": counts.get("finance", 0),
        },
    )


def _clearance_match(row, query):
    if query.risk_level and row.get("risk_at_submission") != query.risk_level:
        return False
    needle = query.keyword.strip().lower()
    return (
        not needle
        or needle
        in " ".join(
            str(row.get(k) or "") for k in ("item_id", "local_sku", "msku", "title", "reason")
        ).lower()
    )


def _clearance_row(row):
    return WorkbenchRow(
        id=str(row["id"]),
        version=row["version"],
        approval_type="clearance_request",
        business_ref=f"{row['store_id']}/{row['item_id']}",
        title=row.get("display_product_name") or row.get("title") or row["item_id"],
        source_account_ref=row["source_account_ref"],
        applicant_id=row["applicant_ref"],
        applicant_name=row.get("applicant_name"),
        status={
            "pending": "submitted",
            "rejected": "rejected",
            "running": "approved",
            "done": "approved",
        }.get(row["status"], "withdrawn"),
        risk_level=row["risk_at_submission"],
        amount=None,
        currency_code=None,
        submitted_at=row["submitted_at"],
        reviewed_at=row.get("approved_at"),
        reviewed_by=None,
        reason=row["reason"],
        can_review=bool(row.get("can_review")),
        clearance_details={
            "sku": row.get("local_sku"),
            "msku": row.get("msku"),
            "item_id": row["item_id"],
            "store_id": row["store_id"],
            "store_name": row.get("store_name"),
            "owner_ref": row.get("display_owner_name") or row.get("owner_ref"),
            "requested_qty": row["requested_qty"],
            "methods": row["methods_json"],
            "wfs_available_quantity": row.get("wfs_available_quantity"),
            "listing_days": row.get("listing_days"),
            "inventory_cost_usd": row.get("inventory_cost_usd"),
        },
    )


def read_workbench(session, principal, accounts, provider, query, *, timings=None):
    started = perf_counter()
    timings = {} if timings is None else timings
    admin = is_approval_admin(principal)
    reviewer = admin or has_permission(principal, "action:products:new-product-analysis:review")
    wfs_reviewer = has_permission(principal, "action:warehouse:wfs-fee-alert:archive-review")
    clearance_reviewer = has_permission(principal, "action:products:clearance-center:review")
    bridge = NewProductPurchaseBridge(session)
    formal = ApprovalService(session)
    with ExitStack() as stack:
        clearance_store = None
        clearance_filtered = None
        clearance_rows = {}

        def clearance_fetch(page, size):
            nonlocal clearance_store, clearance_filtered
            if clearance_store is None:
                clearance_store = stack.enter_context(storage_session(session))

            def read(p, s):
                return hybrid_v28.list_applications(
                    session,
                    clearance_store,
                    accounts,
                    principal.user_id,
                    reviewer=clearance_reviewer,
                    page=p,
                    page_size=s,
                    status=query.tab,
                )

            if query.risk_level or query.keyword.strip():
                # The existing clearance API filters after pagination. Apply its
                # same predicates before merged pagination, only on filtered
                # requests; page scans are bounded chunks, no per-item calls.
                if clearance_filtered is None:
                    head = read(1, 100)
                    raw = list(head["items"])
                    n = head["total"]
                    for p in range(2, (n + 99) // 100 + 1):
                        chunk = read(p, 100)
                        if chunk["total"] != n:
                            raise ApiError(code="WORKBENCH_SOURCE_CHANGED", status_code=409)
                        raw.extend(chunk["items"])
                    clearance_filtered = [r for r in raw if _clearance_match(r, query)]
                total = len(clearance_filtered)
                rows = clearance_filtered[(page - 1) * size : page * size]
            else:
                data = read(page, size)
                total = data["total"]
                rows = data["items"]
            for row in rows:
                clearance_rows[str(row["id"])] = row
            return [_clearance_row(r) for r in rows], total

        def purchase_fetch(page, size):
            q = query.model_copy(
                update={
                    "approval_type": None,
                    "page": page,
                    "page_size": size,
                    "view": "all" if admin and query.view == "mine" else query.view,
                }
            )
            data, meta = bridge.list(q, accounts, principal.user_id, reviewer)
            if admin:
                for row in data.items:
                    row.can_review = row.status == "submitted"
            return data.items, meta.total

        def generic_fetch(kind):
            def fetch(page, size):
                q = query.model_copy(
                    update={"approval_type": kind, "page": page, "page_size": size}
                )
                data, total = formal.list_requests(
                    q,
                    accounts,
                    principal.user_id,
                    True,
                    is_admin=admin,
                    np_may_review=True,
                    wfs_may_review=wfs_reviewer,
                )
                if not wfs_reviewer and not admin:
                    for row in data.items:
                        if row.approval_type != "new_product_evaluation_review":
                            row.can_review = False
                return data.items, total

            return fetch

        groups = [
            ("clearance", 100, clearance_fetch),
            ("np_purchase", 200, purchase_fetch),
            ("purchase", 200, generic_fetch("purchase_exception")),
            ("newProduct", 200, generic_fetch("new_product_evaluation_review")),
            ("wfs", 200, generic_fetch("wfs_case_abandon")),
        ]
        if query.approval_type == "finance_exception":
            groups.append(("finance", 200, generic_fetch("finance_exception")))
        items, total, counts = _merge_page(query, groups)
        timings["list_counts"] = (perf_counter() - started) * 1000
        stage = perf_counter()
        # Only page-visible clearance records need live display enrichment.
        selected_clearance = [
            clearance_rows[r.id] for r in items if r.approval_type == "clearance_request"
        ]
        if selected_clearance:
            version, rules = clearance_service.persisted_rule_version(clearance_store) or (
                0,
                ClearanceRules(),
            )
            selected_clearance = enrich_application_rows(
                session, selected_clearance, accounts, rules, version
            )
            named = attach_clearance_names(session, {"items": selected_clearance})["items"]
            mapped = {str(r["id"]): _clearance_row(r) for r in named}
            items = [mapped[r.id] if r.approval_type == "clearance_request" else r for r in items]
        # Do not call attach_approval_names on clearance rows; their adapter
        # already resolved the same authorized IAM names.
        attach_approval_names(
            session,
            ApprovalListData(items=[r for r in items if r.approval_type != "clearance_request"]),
        )
        timings["clearance_names"] = (perf_counter() - stage) * 1000
        stage = perf_counter()
        reads = enrich_purchase_page(session, principal, accounts, provider, items, timings=timings)
        timings["purchase_total"] = (perf_counter() - stage) * 1000
        stage = perf_counter()
        result = [
            WorkbenchRow.model_validate({**r.model_dump(), "purchase_read": reads.get(r.id)})
            for r in items
        ]
        data = WorkbenchReadData(items=result, business_counts=counts)
        timings["assemble"] = (perf_counter() - stage) * 1000
        return data, ApprovalMeta(page=query.page, page_size=query.page_size, total=total)


@workbench_read_router.get(
    "/workbench/read", response_model=SuccessEnvelope[WorkbenchReadData, ApprovalMeta]
)
def workbench_read(
    request: Request,
    response: Response,
    query: Annotated[ApprovalQuery, Query()],
    session: Annotated[Session, Depends(get_db_session)],
    principal: Annotated[
        Principal, Depends(require_permission("page:data-center:approval-workspace:view"))
    ],
    accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    provider: Annotated[
        SourceAccountScopeProvider | None, Depends(get_source_account_scope_provider)
    ],
):
    timings = {}
    started = perf_counter()
    data, meta = read_workbench(session, principal, accounts, provider, query, timings=timings)
    timings["total"] = (perf_counter() - started) * 1000
    # Only fixed stage names and durations; never log product data or credentials.
    response.headers["Server-Timing"] = ", ".join(
        f"{name};dur={ms:.1f}" for name, ms in timings.items()
    )
    _LOGGER.info("approval_workbench_timing %s", response.headers["Server-Timing"])
    return success_response(request, data=data, meta=meta)
