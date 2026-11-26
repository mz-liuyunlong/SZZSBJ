"""Uniform approval workbench routes with WFS business permissions."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import SuccessEnvelope, success_response
from app.core.auth import Principal, require_principal
from app.core.permissions import (
    has_any_permission,
    has_permission,
    is_approval_admin,
    require_permission,
)
from app.db.session import get_db_session
from app.modules.approvals.applicant_names import attach_approval_names
from app.modules.approvals.generic import GenericApprovalService
from app.modules.approvals.schemas import (
    ApprovalDecisionWrite,
    ApprovalDetail,
    ApprovalListData,
    ApprovalMeta,
    ApprovalQuery,
    ApprovalSubmitResult,
    ApprovalSummary,
    ApprovalSupplementWrite,
    BulkDecisionWrite,
    LegacyReattestationWrite,
    NewProductPurchaseDecisionWrite,
)
from app.modules.approvals.service import ApprovalService
from app.modules.approvals.workbench_read import workbench_read_router
from app.modules.approvals.workflow import ApprovalWorkflow
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.warehouse_wfs.schemas import WfsFeeArchiveRequestWrite

router = APIRouter(prefix="/api/approvals", tags=["Approval Workbench"])
db_session = Annotated[Session, Depends(get_db_session)]
account_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
view_principal = Annotated[
    Principal,
    Depends(require_permission("page:data-center:approval-workspace:view")),
]
archive_request_principal = Annotated[
    Principal,
    Depends(require_permission("action:warehouse:wfs-fee-alert:archive-request")),
]
archive_review_principal = Annotated[
    Principal,
    Depends(require_permission("action:warehouse:wfs-fee-alert:archive-review")),
]


@router.get("", response_model=SuccessEnvelope[ApprovalListData, ApprovalMeta])
def list_approvals(
    request: Request,
    query: Annotated[ApprovalQuery, Query()],
    session: db_session,
    principal: view_principal,
    accounts: account_scope,
):
    approved = has_permission(principal, "action:warehouse:wfs-fee-alert:archive-review")
    np_reviewer = True
    data, total = ApprovalService(session).list_requests(
        query,
        accounts,
        principal.user_id,
        approved or np_reviewer,
        is_admin=is_approval_admin(principal),
        np_may_review=np_reviewer,
        wfs_may_review=approved,
    )
    if np_reviewer and not approved and not is_approval_admin(principal):
        for item in data.items:
            if item.approval_type != "new_product_evaluation_review":
                item.can_review = False
    return success_response(
        request,
        data=attach_approval_names(session, data),
        meta=ApprovalMeta(page=query.page, page_size=query.page_size, total=total),
    )


@router.get("/summary", response_model=SuccessEnvelope[ApprovalSummary, None])
def summary(
    request: Request, session: db_session, principal: view_principal, accounts: account_scope
):
    may_review = has_permission(principal, "action:warehouse:wfs-fee-alert:archive-review")
    data = ApprovalService(session).summary(
        accounts, principal.user_id, may_review, is_admin=is_approval_admin(principal)
    )
    return success_response(request, data=data, meta=None)


@router.get("/wfs-cases/{case_id}/detail", response_model=SuccessEnvelope[ApprovalDetail, None])
@router.get("/legacy/{case_id}", response_model=SuccessEnvelope[ApprovalDetail, None])
def legacy_detail(
    request: Request,
    case_id: UUID,
    session: db_session,
    principal: view_principal,
    accounts: account_scope,
):
    if not has_permission(principal, "action:warehouse:wfs-fee-alert:archive-review"):
        from app.core.api import ApiError, ErrorCode

        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    return success_response(
        request,
        data=attach_approval_names(
            session,
            ApprovalService(session).legacy_detail(
                case_id, accounts, principal.user_id, allow_self=is_approval_admin(principal)
            ),
        ),
        meta=None,
    )


@router.post("/legacy/{case_id}/reattest", response_model=SuccessEnvelope[dict[str, str], None])
def reattest_legacy(
    request: Request,
    case_id: UUID,
    payload: LegacyReattestationWrite,
    session: db_session,
    principal: archive_request_principal,
    accounts: account_scope,
):
    approval_id = ApprovalWorkflow(session).reattest_wfs(
        case_id,
        accounts,
        principal.user_id,
        payload.reason_type,
        payload.reason,
        payload.evidence,
    )
    return success_response(request, data={"approval_id": approval_id}, meta=None)


@router.post("/workflow/bulk-approve", response_model=SuccessEnvelope[dict[str, int], None])
def approve_bulk(
    request: Request,
    payload: BulkDecisionWrite,
    session: db_session,
    principal: view_principal,
    accounts: account_scope,
):
    if not is_approval_admin(principal):
        from app.core.api import ApiError, ErrorCode

        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    ids = [UUID(x) for x in payload.approval_ids]
    count = GenericApprovalService(session).approve_bulk(
        ids,
        payload.expected_versions,
        accounts,
        principal.user_id,
        payload.note,
    )
    return success_response(request, data={"approved": count}, meta=None)


@router.get("/{approval_id}", response_model=SuccessEnvelope[ApprovalDetail, None])
def get_approval(
    request: Request,
    approval_id: UUID,
    session: db_session,
    principal: view_principal,
    accounts: account_scope,
):
    may_review = has_permission(principal, "action:warehouse:wfs-fee-alert:archive-review")
    np_may_review = True
    data = ApprovalService(session).detail(
        approval_id,
        accounts,
        principal.user_id,
        may_review,
        is_admin=is_approval_admin(principal),
        np_may_review=np_may_review,
    )
    return success_response(request, data=attach_approval_names(session, data), meta=None)


@router.post(
    "/wfs-cases/{case_id}/decision",
    response_model=SuccessEnvelope[dict[str, bool], None],
)
def review_current_wfs_case(
    request: Request,
    case_id: UUID,
    payload: ApprovalDecisionWrite,
    session: db_session,
    principal: archive_review_principal,
    accounts: account_scope,
):
    ApprovalService(session).review_pending_case(
        case_id, payload, accounts, principal.user_id, allow_self=is_approval_admin(principal)
    )
    return success_response(request, data={"updated": True}, meta=None)


@router.post("/wfs-cases/{case_id}", response_model=SuccessEnvelope[ApprovalSubmitResult, None])
def submit_wfs(
    request: Request,
    case_id: UUID,
    payload: WfsFeeArchiveRequestWrite,
    session: db_session,
    principal: archive_request_principal,
    accounts: account_scope,
):
    result = ApprovalService(session).submit_wfs(
        case_id,
        reason_type=payload.archive_reason_type,
        reason=payload.archive_reason,
        evidence=payload.archive_evidence,
        account_refs=accounts,
        actor=principal.user_id,
    )
    return success_response(request, data=result, meta=None)


@router.post("/{approval_id}/decision", response_model=SuccessEnvelope[dict[str, bool], None])
def decide(
    request: Request,
    approval_id: UUID,
    payload: ApprovalDecisionWrite,
    session: db_session,
    principal: archive_review_principal,
    accounts: account_scope,
):
    may_review = has_permission(principal, "action:warehouse:wfs-fee-alert:archive-review")
    record = ApprovalService(session)._record(approval_id, accounts)
    if record["approval_type"] != "wfs_case_abandon":
        if not is_approval_admin(principal):
            from app.core.api import ApiError, ErrorCode

            raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
        GenericApprovalService(session).decide(
            approval_id,
            accounts,
            principal.user_id,
            payload.decision,
            payload.note,
            payload.expected_version,
        )
    else:
        ApprovalService(session).decide(
            approval_id,
            payload,
            accounts,
            principal.user_id,
            may_review,
            allow_self=is_approval_admin(principal),
        )
    return success_response(request, data={"updated": True}, meta=None)


@router.post("/{approval_id}/supplement", response_model=SuccessEnvelope[dict[str, bool], None])
def supplement(
    request: Request,
    approval_id: UUID,
    payload: ApprovalSupplementWrite,
    session: db_session,
    principal: Annotated[Principal, Depends(require_principal)],
    accounts: account_scope,
):
    from app.core.api import ApiError, ErrorCode

    # Reject callers with no supplement-capable permission *before* reading
    # approval data. The record-specific check below further narrows access.
    if not has_any_permission(
        principal,
        (
            "action:warehouse:wfs-fee-alert:archive-request",
            "action:pmc:purchase-board:override",
        ),
    ):
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)

    # WFS and purchase requests have different business permissions.
    record = ApprovalService(session)._record(approval_id, accounts)
    if record["approval_type"] == "wfs_case_abandon":
        allowed = has_permission(principal, "action:warehouse:wfs-fee-alert:archive-request")
    else:
        allowed = is_approval_admin(principal) or (
            record["approval_type"] == "purchase_exception"
            and has_permission(principal, "action:pmc:purchase-board:override")
        )
    if not allowed:
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    ApprovalService(session).supplement(approval_id, payload, accounts, principal.user_id)
    return success_response(request, data={"updated": True}, meta=None)


# NP_PURCHASE_WORKBENCH_REAL_API_V1_20261116
# New-product purchase lives in its own source table, not purchase_exception.
# Reuse the existing approval workbench UI with independently scoped endpoints.
@router.get(
    "/new-products/purchases", response_model=SuccessEnvelope[ApprovalListData, ApprovalMeta]
)
def new_product_purchase_workbench_list(
    request: Request,
    query: Annotated[ApprovalQuery, Query()],
    session: db_session,
    principal: view_principal,
    accounts: account_scope,
):
    from app.modules.approvals.new_product_purchase_bridge import NewProductPurchaseBridge

    can_review = is_approval_admin(principal) or has_permission(
        principal, "action:products:new-product-analysis:review"
    )
    # An approval administrator sees all scoped pending purchase requests,
    # including their own. Keep all other business/list filters unchanged.
    purchase_query = (
        query.model_copy(update={"view": "all"})
        if is_approval_admin(principal) and query.view == "mine"
        else query
    )
    data, meta = NewProductPurchaseBridge(session).list(
        purchase_query, accounts, principal.user_id, can_review
    )
    if is_approval_admin(principal):
        for item in data.items:
            item.can_review = item.status == "submitted"
    return success_response(request, data=attach_approval_names(session, data), meta=meta)


@router.get(
    "/new-products/purchases/{application_id}", response_model=SuccessEnvelope[ApprovalDetail, None]
)
def new_product_purchase_workbench_detail(
    request: Request,
    application_id: UUID,
    session: db_session,
    principal: view_principal,
    accounts: account_scope,
):
    from app.modules.approvals.new_product_purchase_bridge import NewProductPurchaseBridge

    can_review = is_approval_admin(principal) or has_permission(
        principal, "action:products:new-product-analysis:review"
    )
    result = NewProductPurchaseBridge(session).detail(
        application_id, accounts, principal.user_id, can_review
    )
    if is_approval_admin(principal):
        result.can_review = result.status == "submitted"
    return success_response(request, data=attach_approval_names(session, result), meta=None)


@router.get(
    "/new-products/purchases/{application_id}/stores",
    response_model=SuccessEnvelope[dict, None],
)
def new_product_purchase_store_options(
    request: Request,
    application_id: UUID,
    session: db_session,
    principal: view_principal,
    accounts: account_scope,
):
    from sqlalchemy import or_, select

    from app.core.api import ApiError, ErrorCode
    from app.modules.data_pages.models import LingxingStoreDimension
    from app.modules.new_products.models import PurchaseApplication

    if not (
        is_approval_admin(principal)
        or has_permission(principal, "action:products:new-product-analysis:review")
    ):
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)

    application = session.scalar(
        select(PurchaseApplication).where(
            PurchaseApplication.id == application_id,
            PurchaseApplication.source_account_ref.in_(accounts),
        )
    )
    if application is None:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    if application.applicant_id == principal.user_id and not is_approval_admin(principal):
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    if application.status != "submitted":
        raise ApiError(code="NP_PURCHASE_ALREADY_REVIEWED", status_code=409)

    records = session.scalars(
        select(LingxingStoreDimension)
        .where(
            LingxingStoreDimension.source_account_ref == application.source_account_ref,
            or_(
                LingxingStoreDimension.platform_code == "walmart",
                LingxingStoreDimension.platform_code_raw == "10008",
            ),
            LingxingStoreDimension.is_sync.is_(True),
        )
        .order_by(LingxingStoreDimension.store_id)
    ).all()
    seen = set()
    stores = []
    for store in records:
        if not store.store_id or store.store_id in seen:
            continue
        seen.add(store.store_id)
        stores.append(
            {"store_id": store.store_id, "store_name": store.store_name or store.store_id}
        )
    return success_response(
        request,
        data={
            "source_store_id": application.store_id,
            "stores": stores,
        },
        meta=None,
    )


@router.post(
    "/new-products/purchases/{application_id}/decision",
    response_model=SuccessEnvelope[dict, None],
)
def new_product_purchase_workbench_decision(
    request: Request,
    application_id: UUID,
    payload: NewProductPurchaseDecisionWrite,
    session: db_session,
    principal: Annotated[Principal, Depends(require_principal)],
    accounts: account_scope,
):
    from app.core.api import ApiError, ErrorCode
    from app.modules.new_products.schemas import PurchaseDecision
    from app.modules.new_products.service import NewProductService

    if not (
        is_approval_admin(principal)
        or has_permission(principal, "action:products:new-product-analysis:review")
    ):
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)

    if payload.decision not in ("approved", "rejected"):
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
    # Source service owns locking, version check, self-review guard and audit.
    result = NewProductService(session).decide_purchase(
        accounts,
        application_id,
        PurchaseDecision(
            decision=payload.decision,
            reason=payload.note,
            expected_version=payload.expected_version,
            purchase_store_id=payload.purchase_store_id,
            approved_qty=payload.approved_qty,
        ),
        principal.user_id,
        allow_self=is_approval_admin(principal),
        real_purchase_test=True,
    )
    return success_response(
        request,
        data={"updated": True, "lingxing_receipt": result.get("lingxing_receipt")},
        meta=None,
    )


# SZZSBJ_NP_PERMISSIONS_V3

# SZZSBJ_PURCHASE_APPROVE_STORE_QTY_V1

# Unified read-only workbench; all existing decision routes are unchanged.
router.include_router(workbench_read_router)
