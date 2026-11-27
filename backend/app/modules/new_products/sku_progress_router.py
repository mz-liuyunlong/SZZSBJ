"""SKU progress list, facets and purchase; existing IAM source-account scope."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session

from app.core.api import ApiError, SuccessEnvelope, success_response
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal, require_principal
from app.core.permissions import has_permission, is_approval_admin
from app.db.session import get_db_session

from .read_source import get_new_product_read_session, require_new_product_scope
from .sku_progress_manual import save_progress
from .sku_progress_purchase import submit_purchase
from .sku_progress_query import (
    FACETS,
    STATIC_VALUES,
    attach_purchase_options,
    facets,
    list_page,
    summary,
)

router = APIRouter(prefix="/sku-progress", tags=["SKU Progress"])
DB = Annotated[Session, Depends(get_db_session)]
ReadDB = Annotated[Session, Depends(get_new_product_read_session)]
Auth = Annotated[Principal, Depends(require_principal)]
Scope = Annotated[frozenset[str], Depends(require_new_product_scope)]
Multi = Annotated[list[str] | None, Query(max_length=100)]


class PurchaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_account_ref: str = Field(min_length=1, max_length=128)
    sku_identity_id: UUID
    store_id: str = Field(min_length=1, max_length=128)
    item_id: str = Field(min_length=1, max_length=128)
    quantity: StrictInt | None = None


def query_filters(
    keyword: Annotated[str, Query(max_length=255)] = "",
    search_field: Literal["all", "sku", "name", "item"] = "all",
    card: Literal["all", "active", "done", "paused", "terminated"] = "all",
    start: date | None = None,
    end: date | None = None,
    store: Multi = None,
    owner: Multi = None,
    developer: Multi = None,
    listing: Multi = None,
    plan: Multi = None,
    site: Multi = None,
    strike: Multi = None,
    ad: Multi = None,
    proc: Multi = None,
    ship: Multi = None,
    progress: Multi = None,
) -> dict:
    if start and end and start > end:
        raise ApiError(
            code="SKU_PROGRESS_DATE_RANGE_INVALID",
            status_code=422,
            message="起始日期不得晚于结束日期",
        )
    result = dict(keyword=keyword, search_field=search_field, card=card, start=start, end=end)
    inputs = dict(
        store=store,
        owner=owner,
        developer=developer,
        listing=listing,
        plan=plan,
        site=site,
        strike=strike,
        ad=ad,
        proc=proc,
        ship=ship,
        progress=progress,
    )
    for key in FACETS:
        values = sorted({v.strip() for v in (inputs[key] or []) if v.strip()})
        if any(len(v) > 1200 for v in values) or (
            key in STATIC_VALUES and any(v not in STATIC_VALUES[key] for v in values)
        ):
            raise ApiError(
                code="SKU_PROGRESS_FILTER_INVALID", status_code=422, message=f"筛选条件无效：{key}"
            )
        result[key] = values
    return result


Filters = Annotated[dict, Depends(query_filters)]


def may_purchase(principal: Principal) -> bool:
    return is_approval_admin(principal) or has_permission(
        principal, "action:products:new-product-analysis:review"
    )


@router.get("/list")
def sku_progress_list(
    request: Request,
    db: ReadDB,
    principal: Auth,
    accounts: Scope,
    filters: Filters,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Literal["date", "product", "name", "dev", "progress", "listing"] = "date",
    sort_order: Literal["asc", "desc"] = "desc",
):
    data = list_page(
        db,
        accounts,
        filters,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    attach_purchase_options(db, data, may_purchase(principal))
    import os

    for row in data["items"]:
        row["can_edit_progress"] = (
            principal.user_id != PREVIEW_PRINCIPAL_ID
            and not os.getenv("NEW_PRODUCTS_READ_DATABASE_URL", "").strip()
        )
    return success_response(
        request, data=data, meta={"source": "sku_progress_current", "purchase_quantity": 20}
    )


@router.get("/summary")
def sku_progress_summary(
    request: Request, db: ReadDB, principal: Auth, accounts: Scope, filters: Filters
):
    return success_response(
        request, data=summary(db, accounts, filters), meta={"source": "sku_progress_current"}
    )


@router.get("/facets")
def sku_progress_facets(
    request: Request, db: ReadDB, principal: Auth, accounts: Scope, filters: Filters
):
    return success_response(
        request, data=facets(db, accounts, filters), meta={"source": "sku_progress_current"}
    )


@router.post("/purchase")
def sku_progress_purchase(
    request: Request, body: PurchaseInput, db: DB, principal: Auth, accounts: Scope
):
    if not may_purchase(principal):
        raise ApiError(
            code="SKU_PURCHASE_PERMISSION_DENIED", status_code=403, message="无采购审批权限"
        )
    try:
        data = submit_purchase(
            db,
            accounts,
            principal.user_id,
            account=body.source_account_ref,
            sku_id=body.sku_identity_id,
            store=body.store_id,
            item=body.item_id,
            quantity=body.quantity,
        )
    except Exception:
        db.rollback()
        raise
    return success_response(request, data=data, meta={"source": "sku_progress_purchase"})


class ManualProgressInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_account_ref: str = Field(min_length=1, max_length=128)
    sku_identity_id: UUID
    version: StrictInt = Field(ge=0)
    progress_status: Literal["in_progress", "paused", "terminated", "completed"]
    reason_type: str | None = Field(default=None, max_length=128)
    remark: str = Field(min_length=1, max_length=500)


@router.put("/manual", response_model=SuccessEnvelope[dict, dict])
def sku_progress_manual(
    request: Request, body: ManualProgressInput, db: DB, principal: Auth, accounts: Scope
):
    # Same authenticated/account scope policy as existing tracking decision; preview is read-only.
    if principal.user_id == PREVIEW_PRINCIPAL_ID:
        raise ApiError(
            code="SKU_PROGRESS_PREVIEW_DENIED", status_code=403, message="预览账号不可保存"
        )
    try:
        data = save_progress(
            db,
            accounts,
            principal.user_id,
            account=body.source_account_ref,
            sku_id=body.sku_identity_id,
            version=body.version,
            status=body.progress_status,
            reason=body.reason_type,
            remark=body.remark,
        )
    except Exception:
        db.rollback()
        raise
    return success_response(request, data=data, meta={"source": "sku_progress_manual"})
