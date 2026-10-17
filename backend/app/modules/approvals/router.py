"""Uniform approval workbench routes with WFS business permissions."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import has_permission, require_permission
from app.db.session import get_db_session
from app.modules.approvals.generic import GenericApprovalService
from app.modules.approvals.schemas import (
    ApprovalDecisionWrite,
    ApprovalDetail,
    ApprovalListData,
    ApprovalMeta,
    ApprovalQuery,
    ApprovalRuleWrite,
    ApprovalSubmitResult,
    ApprovalSummary,
    ApprovalSupplementWrite,
    BulkDecisionWrite,
    GenericApprovalWrite,
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
    if query.tab == "legacy" and not approved:
        from app.core.api import ApiError, ErrorCode

        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    data, total = ApprovalService(session).list_requests(
        query,
        accounts,
        principal.user_id,
        approved,
        is_admin="*" in principal.permissions,
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
        accounts, principal.user_id, may_review, is_admin="*" in principal.permissions
    )
    return success_response(request, data=data, meta=None)


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
        request, data=ApprovalService(session).legacy_detail(case_id, accounts), meta=None
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


@router.get("/workflow/rules", response_model=SuccessEnvelope[list[dict], None])
def approval_rules(request: Request, session: db_session, _: view_principal):
    return success_response(request, data=ApprovalWorkflow(session).available_rules(), meta=None)


@router.put(
    "/workflow/rules/{approval_type}", response_model=SuccessEnvelope[dict[str, bool], None]
)
def update_approval_rule(
    request: Request,
    approval_type: str,
    payload: ApprovalRuleWrite,
    session: db_session,
    principal: Annotated[
        Principal,
        Depends(require_permission("action:settings:role-management:configure-permissions")),
    ],
):
    ApprovalWorkflow(session).update_rule(
        approval_type,
        principal.user_id,
        payload.expected_version,
        payload.required_steps,
        payload.due_hours,
        payload.allows_bulk,
    )
    return success_response(request, data={"updated": True}, meta=None)


@router.get("/workflow/notifications", response_model=SuccessEnvelope[list[dict], None])
def approval_notifications(request: Request, session: db_session, principal: view_principal):
    return success_response(
        request, data=ApprovalWorkflow(session).inbox(principal.user_id), meta=None
    )


@router.post(
    "/workflow/notifications/{notification_id}/read",
    response_model=SuccessEnvelope[dict[str, bool], None],
)
def mark_approval_notification_read(
    request: Request,
    notification_id: UUID,
    session: db_session,
    principal: view_principal,
):
    return success_response(
        request,
        data={"updated": ApprovalWorkflow(session).mark_read(notification_id, principal.user_id)},
        meta=None,
    )


@router.post("/workflow/requests", response_model=SuccessEnvelope[dict[str, str], None])
def submit_generic_approval(
    request: Request,
    payload: GenericApprovalWrite,
    session: db_session,
    principal: view_principal,
    accounts: account_scope,
):
    # High-impact general requests require explicit super-admin authority.
    # Purchase requests may also be initiated by a PMC override authorized user.
    allowed = "*" in principal.permissions or (
        payload.approval_type == "purchase_exception"
        and has_permission(principal, "action:pmc:purchase-board:override")
    )
    if not allowed:
        from app.core.api import ApiError, ErrorCode

        raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
    approval_id = GenericApprovalService(session).submit(
        payload.approval_type,
        payload.source_ref,
        payload.source_account_ref,
        accounts,
        principal.user_id,
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
    if "*" not in principal.permissions:
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
        is_admin="*" in principal.permissions,
    )
    return success_response(request, data=data, meta=None)


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
        if "*" not in principal.permissions:
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
    principal: archive_request_principal,
    accounts: account_scope,
):
    ApprovalService(session).supplement(approval_id, payload, accounts, principal.user_id)
    return success_response(request, data={"updated": True}, meta=None)
