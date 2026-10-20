"""Uniform approval workbench routes with WFS business permissions."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import SuccessEnvelope, success_response
from app.core.auth import Principal, require_principal
from app.core.permissions import has_any_permission, has_permission, require_permission
from app.db.session import get_db_session
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
)
from app.modules.approvals.service import ApprovalService
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
    data, total = ApprovalService(session).list_requests(
        query,
        accounts,
        principal.user_id,
        approved,
        is_admin=has_permission(principal, "*"),
    )
    return success_response(
        request,
        data=data,
        meta=ApprovalMeta(page=query.page, page_size=query.page_size, total=total),
    )


@router.get("/summary", response_model=SuccessEnvelope[ApprovalSummary, None])
def summary(
    request: Request, session: db_session, principal: view_principal, accounts: account_scope
):
    may_review = has_permission(principal, "action:warehouse:wfs-fee-alert:archive-review")
    data = ApprovalService(session).summary(
        accounts, principal.user_id, may_review, is_admin=has_permission(principal, "*")
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
        data=ApprovalService(session).legacy_detail(case_id, accounts, principal.user_id),
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
    if not has_permission(principal, "*"):
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
    data = ApprovalService(session).detail(
        approval_id,
        accounts,
        principal.user_id,
        may_review,
        is_admin=has_permission(principal, "*"),
    )
    return success_response(request, data=data, meta=None)


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
    ApprovalService(session).review_pending_case(case_id, payload, accounts, principal.user_id)
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
        if not has_permission(principal, "*"):
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
            approval_id, payload, accounts, principal.user_id, may_review
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
        allowed = has_permission(principal, "*") or (
            record["approval_type"] == "purchase_exception"
            and has_permission(principal, "action:pmc:purchase-board:override")
        )
    if not allowed:
        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    ApprovalService(session).supplement(approval_id, payload, accounts, principal.user_id)
    return success_response(request, data={"updated": True}, meta=None)
