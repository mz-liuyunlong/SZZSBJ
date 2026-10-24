"""Scoped source bridge: stored Decodo evidence, never a client-claimed API result."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.products.models import Product

from .analysis_routes import _account_allowed, _require_opted_in_writes
from .models import (
    AiKwProductFactSnapshot,
    BizSkuAsinReference,
    RawKwUploadFile,
    RawKwUploadRow,
)
from .rule_gates import REQUIRED_PRODUCT_FIELDS
from .source_bridge import (
    ConfirmedFieldInput,
    SourceBridgeBlocked,
    confirm_stored_walmart_product,
    import_stored_asin,
)

router = APIRouter(tags=["Keyword Planning"])


class ConfirmField(BaseModel):
    value: str = Field(min_length=1, max_length=1000)
    source: Literal["walmart", "operator", "product_management"]


class SemanticPhraseInput(BaseModel):
    phrase: str = Field(min_length=1, max_length=200)
    keyword_type: str = Field(min_length=1, max_length=64)
    evidence_ref: str = Field(min_length=1, max_length=255)
    hard_risk_proven: bool = False
    page_phrase: str | None = Field(default=None, max_length=200)


class ConfirmWalmartBody(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)
    product_id: UUID
    item_id: str = Field(pattern=r"^[0-9]{1,20}$")
    decodo_snapshot_id: UUID
    fields: dict[str, ConfirmField]
    risk_boundary_mode: Literal["provided", "none"]
    risk_boundary_acknowledged: bool
    semantic_phrases: list[SemanticPhraseInput] = Field(default_factory=list, max_length=500)


class ConfirmWalmartRead(BaseModel):
    product_fact_snapshot_id: UUID
    walmart_page_snapshot_id: UUID
    status: Literal["confirmed"] = "confirmed"


class ImportAsinBody(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)
    product_id: UUID
    asin: str = Field(pattern=r"^[A-Za-z0-9]{10}$")
    decodo_snapshot_id: UUID


class ImportAsinRead(BaseModel):
    asin_snapshot_id: UUID
    image_count: int
    status: Literal["stored"] = "stored"


class KeywordSourceStateRead(BaseModel):
    product_id: UUID
    latest_confirmed_fact_id: UUID | None
    latest_upload_id: UUID | None
    latest_upload_filename: str | None
    latest_upload_rows: int
    item_id: str | None
    confirmed_fields: dict[str, str]
    asin_reference_count: int
    asin_references: list[str]
    source_status: Literal["ready_for_import", "fact_confirmed"]


def _invalid(exc: SourceBridgeBlocked) -> ApiError:
    return ApiError(
        code=ErrorCode.INVALID_REQUEST, status_code=409, details={"reason_code": str(exc)}
    )


@router.get(
    "/products/{product_id}/source-state",
    response_model=SuccessEnvelope[KeywordSourceStateRead, None],
)
def get_source_state(
    request: Request,
    product_id: UUID,
    source_account_ref: Annotated[str, Query(min_length=1, max_length=128)],
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("products:read"))],
) -> SuccessEnvelope[KeywordSourceStateRead, None]:
    _account_allowed(source_account_ref, allowed_accounts, principal)
    product = session.get(Product, product_id)
    if (
        product is None
        or product.deleted_at is not None
        or not session.scalar(
            select(
                ListingManagementCurrentMart.id,
            )
            .where(
                ListingManagementCurrentMart.source_account_ref == source_account_ref,
                ListingManagementCurrentMart.local_sku == product.sku,
            )
            .limit(1)
        )
    ):
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    fact = session.scalar(
        select(AiKwProductFactSnapshot)
        .where(
            AiKwProductFactSnapshot.source_account_ref == source_account_ref,
            AiKwProductFactSnapshot.product_id == product_id,
            AiKwProductFactSnapshot.status == "confirmed",
        )
        .order_by(AiKwProductFactSnapshot.created_at.desc())
        .limit(1)
    )
    upload = session.scalar(
        select(RawKwUploadFile)
        .where(
            RawKwUploadFile.source_account_ref == source_account_ref,
            RawKwUploadFile.product_id == product_id,
            RawKwUploadFile.status == "parsed",
        )
        .order_by(RawKwUploadFile.created_at.desc())
        .limit(1)
    )
    upload_rows = (
        session.scalar(
            select(func.count())
            .select_from(RawKwUploadRow)
            .where(
                RawKwUploadRow.source_account_ref == source_account_ref,
                RawKwUploadRow.upload_id == upload.id,
            )
        )
        if upload
        else 0
    )
    asin_references = list(
        session.scalars(
            select(BizSkuAsinReference.asin)
            .where(
                BizSkuAsinReference.source_account_ref == source_account_ref,
                BizSkuAsinReference.product_id == product_id,
                BizSkuAsinReference.is_active.is_(True),
                BizSkuAsinReference.latest_snapshot_id.is_not(None),
            )
            .order_by(BizSkuAsinReference.asin.asc())
        )
    )
    return success_response(
        request,
        data=KeywordSourceStateRead(
            product_id=product_id,
            latest_confirmed_fact_id=fact.id if fact else None,
            latest_upload_id=upload.id if upload else None,
            latest_upload_filename=upload.original_filename if upload else None,
            latest_upload_rows=int(upload_rows or 0),
            item_id=fact.item_id if fact else None,
            confirmed_fields={
                key: str(value["value"])
                for key, value in (fact.facts_with_sources_json or {}).items()
                if key in REQUIRED_PRODUCT_FIELDS
                and isinstance(value, dict)
                and isinstance(value.get("value"), str)
            }
            if fact
            else {},
            asin_reference_count=len(asin_references),
            asin_references=asin_references,
            source_status="fact_confirmed" if fact else "ready_for_import",
        ),
        meta=None,
    )


@router.post("/sources/walmart/confirm", response_model=SuccessEnvelope[ConfirmWalmartRead, None])
def confirm_walmart_source(
    request: Request,
    body: ConfirmWalmartBody,
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("products:write"))],
) -> SuccessEnvelope[ConfirmWalmartRead, None]:
    _account_allowed(body.source_account_ref, allowed_accounts, principal)
    _require_opted_in_writes()
    if set(body.fields) != set(REQUIRED_PRODUCT_FIELDS):
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=422,
            details={"reason_code": "PRODUCT_REQUIRED_FIELDS_MISMATCH"},
        )
    if session.new or session.dirty or session.deleted:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
    session.rollback()
    try:
        fact_id, page_id = confirm_stored_walmart_product(
            session,
            account=body.source_account_ref,
            product_id=body.product_id,
            item_id=body.item_id,
            decodo_snapshot_id=body.decodo_snapshot_id,
            fields={
                key: ConfirmedFieldInput(value=value.value, source=value.source)
                for key, value in body.fields.items()
            },
            risk_mode=body.risk_boundary_mode,
            risk_acknowledged=body.risk_boundary_acknowledged,
            semantic_phrases=[item.model_dump() for item in body.semantic_phrases],
            actor=principal.user_id,
        )
    except SourceBridgeBlocked as exc:
        raise _invalid(exc) from exc
    return success_response(
        request,
        data=ConfirmWalmartRead(
            product_fact_snapshot_id=fact_id,
            walmart_page_snapshot_id=page_id,
        ),
        meta=None,
    )


@router.post("/sources/amazon/asin", response_model=SuccessEnvelope[ImportAsinRead, None])
def import_asin_source(
    request: Request,
    body: ImportAsinBody,
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("products:write"))],
) -> SuccessEnvelope[ImportAsinRead, None]:
    _account_allowed(body.source_account_ref, allowed_accounts, principal)
    _require_opted_in_writes()
    if session.new or session.dirty or session.deleted:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
    session.rollback()
    try:
        snapshot_id, image_count = import_stored_asin(
            session,
            account=body.source_account_ref,
            product_id=body.product_id,
            asin=body.asin,
            decodo_snapshot_id=body.decodo_snapshot_id,
            actor=principal.user_id,
        )
    except SourceBridgeBlocked as exc:
        raise _invalid(exc) from exc
    return success_response(
        request,
        data=ImportAsinRead(
            asin_snapshot_id=snapshot_id,
            image_count=image_count,
        ),
        meta=None,
    )
