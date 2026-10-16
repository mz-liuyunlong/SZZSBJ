"""Uniform approval workbench routes with WFS business permissions."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.api import SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.approvals.schemas import (
    ApprovalDecisionWrite,
    ApprovalDetail,
    ApprovalListData,
    ApprovalMeta,
    ApprovalQuery,
    ApprovalSubmitResult,
    ApprovalSummary,
    ApprovalSupplementWrite,
)
from app.modules.approvals.service import ApprovalService
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.warehouse_wfs.schemas import WfsFeeArchiveRequestWrite

router = APIRouter(prefix="/api/approvals", tags=["Approval Workbench"])
db_session = Annotated[Session, Depends(get_db_session)]
account_scope = Annotated[frozenset[str], Depends(require_source_account_scope)]
view_principal = Annotated[Principal, Depends(require_permission("approvals:workbench:read"))]
wfs_writer = Annotated[Principal, Depends(require_permission("warehouse:wfs-fee-alert:write"))]


@router.get("", response_model=SuccessEnvelope[ApprovalListData, ApprovalMeta])
def list_approvals(
    request: Request,
    query: Annotated[ApprovalQuery, Query()],
    session: db_session,
    principal: view_principal,
    accounts: account_scope,
):
    approved = "warehouse:wfs-fee-alert:review" in principal.permissions
    data, total = ApprovalService(session).list_requests(
        query, accounts, principal.user_id, approved
    )
    return success_response(
        request,
        data=data,
        meta=ApprovalMeta(page=query.page, page_size=query.page_size, total=total),
    )


@router.get("/summary", response_model=SuccessEnvelope[ApprovalSummary, None])
def summary(request: Request, session: db_session, principal: view_principal, accounts: account_scope):
    may_review = "warehouse:wfs-fee-alert:review" in principal.permissions
    data = ApprovalService(session).summary(accounts, principal.user_id, may_review)
    return success_response(request, data=data, meta=None)


@router.get("/{approval_id}", response_model=SuccessEnvelope[ApprovalDetail, None])
def get_approval(
    request: Request,
    approval_id: UUID,
    session: db_session,
    principal: view_principal,
    accounts: account_scope,
):
    may_review = "warehouse:wfs-fee-alert:review" in principal.permissions
    data = ApprovalService(session).detail(approval_id, accounts, principal.user_id, may_review)
    return success_response(request, data=data, meta=None)


@router.post("/wfs-cases/{case_id}", response_model=SuccessEnvelope[ApprovalSubmitResult, None])
def submit_wfs(
    request: Request,
    case_id: UUID,
    payload: WfsFeeArchiveRequestWrite,
    session: db_session,
    principal: wfs_writer,
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
    principal: view_principal,
    accounts: account_scope,
):
    may_review = "warehouse:wfs-fee-alert:review" in principal.permissions
    ApprovalService(session).decide(approval_id, payload, accounts, principal.user_id, may_review)
    return success_response(request, data={"updated": True}, meta=None)


@router.post("/{approval_id}/supplement", response_model=SuccessEnvelope[dict[str, bool], None])
def supplement(
    request: Request,
    approval_id: UUID,
    payload: ApprovalSupplementWrite,
    session: db_session,
    principal: view_principal,
    accounts: account_scope,
):
    ApprovalService(session).supplement(approval_id, payload, accounts, principal.user_id)
    return success_response(request, data={"updated": True}, meta=None)
