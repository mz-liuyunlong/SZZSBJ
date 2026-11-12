"""New-product APIs. No direct external requests, no implicit background sync or mock fallback."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.api import SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session

from .read_source import get_new_product_read_session, require_new_product_scope
from .schemas import (
    ListingQuery,
    MarketWrite,
    PurchaseDecision,
    PurchaseWrite,
    RuleApply,
    RulePreview,
    TrackingWrite,
)
from .service import NewProductService

router = APIRouter(prefix="/api/new-products", tags=["New Product Performance"])
DB = Annotated[Session, Depends(get_db_session)]
Source = Annotated[Session, Depends(get_new_product_read_session)]
Scope = Annotated[frozenset[str], Depends(require_new_product_scope)]
Read = Annotated[Principal, Depends(require_permission("page:products:new-product-analysis:view"))]
Configure = Annotated[
    Principal, Depends(require_permission("action:products:new-product-analysis:configure"))
]
Score = Annotated[
    Principal, Depends(require_permission("action:products:new-product-analysis:score"))
]
PurchaseRequester = Annotated[
    Principal, Depends(require_permission("action:products:new-product-analysis:request"))
]
Review = Annotated[
    Principal, Depends(require_permission("action:products:new-product-analysis:review"))
]
Tracking = Annotated[
    Principal, Depends(require_permission("action:products:new-product-analysis:tracking"))
]


@router.get("/listings", response_model=SuccessEnvelope[dict, dict])
def listings(
    request: Request,
    query: Annotated[ListingQuery, Query()],
    db: DB,
    _: Read,
    accounts: Scope,
    source: Source,
):
    data = NewProductService(db, read_session=source).list(accounts, query)
    return success_response(
        request,
        data=data,
        meta={"source": "listing-management", "tag": "小批量测品", "page_size": query.page_size},
    )


@router.get("/listings/{account}/{store}/{item}", response_model=SuccessEnvelope[dict, dict])
def detail(
    request: Request,
    account: str,
    store: str,
    item: str,
    db: DB,
    _: Read,
    accounts: Scope,
    source: Source,
):
    return success_response(
        request,
        data=NewProductService(db, read_session=source).detail(accounts, account, store, item),
        meta={"source": "live"},
    )


@router.get("/listings/{account}/{store}/{item}/score", response_model=SuccessEnvelope[dict, dict])
def listing_score(
    request: Request,
    account: str,
    store: str,
    item: str,
    db: DB,
    _: Read,
    accounts: Scope,
    source: Source,
):
    return success_response(
        request,
        data=NewProductService(db, read_session=source).score(accounts, account, store, item),
        meta={"source": "live"},
    )


@router.get("/rules", response_model=SuccessEnvelope[dict, dict])
def get_rules(
    request: Request, db: DB, _: Read, kind: Literal["performance", "tracking"] = "performance"
):
    return success_response(
        request, data=NewProductService(db).rule(kind), meta={"source": "database"}
    )


@router.put("/rules/apply", response_model=SuccessEnvelope[dict, dict])
def save_apply(request: Request, payload: RuleApply, db: DB, principal: Configure):
    data = NewProductService(db).apply_rule(
        payload.kind,
        payload.expected_version,
        payload.config,
        principal.user_id,
        payload.change_reason,
    )
    return success_response(request, data=data, meta={"applied_immediately": True})


@router.get("/rules/history", response_model=SuccessEnvelope[dict, dict])
def history(
    request: Request,
    db: DB,
    _: Read,
    kind: Literal["performance", "tracking"] = "performance",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return success_response(
        request,
        data=NewProductService(db).rule_history(kind, limit, offset),
        meta={"source": "database"},
    )


@router.post("/rules/preview", response_model=SuccessEnvelope[dict, dict])
def preview(
    request: Request, payload: RulePreview, db: DB, _: Read, accounts: Scope, source: Source
):
    return success_response(
        request,
        data=NewProductService(db, read_session=source).preview(
            accounts,
            *(payload.source_account_ref, payload.store_id, payload.item_id),
            config=payload.config,
        ),
        meta={"persisted": False},
    )


@router.put("/market-score", response_model=SuccessEnvelope[dict, dict])
def market_score(
    request: Request,
    payload: MarketWrite,
    db: DB,
    principal: Score,
    accounts: Scope,
    source: Source,
):
    return success_response(
        request,
        data=NewProductService(db, read_session=source).save_market(
            accounts, payload, principal.user_id
        ),
        meta={"source": "database"},
    )


@router.put("/tracking/decision", response_model=SuccessEnvelope[dict, dict])
def tracking_decision(
    request: Request,
    payload: TrackingWrite,
    db: DB,
    principal: Tracking,
    accounts: Scope,
    source: Source,
):
    return success_response(
        request,
        data=NewProductService(db, read_session=source).save_tracking(
            accounts, payload, principal.user_id
        ),
        meta={"source": "database"},
    )


@router.post("/purchase-applications", response_model=SuccessEnvelope[dict, dict])
def apply_purchase(
    request: Request,
    payload: PurchaseWrite,
    db: DB,
    principal: PurchaseRequester,
    accounts: Scope,
    source: Source,
):
    return success_response(
        request,
        data=NewProductService(db, read_session=source).purchase(
            accounts, payload, principal.user_id
        ),
        meta={"source": "database"},
    )


@router.get("/purchase-applications", response_model=SuccessEnvelope[dict, dict])
def list_purchases(
    request: Request,
    db: DB,
    _: Read,
    accounts: Scope,
    source: Source,
    status: Literal["submitted", "approved", "rejected"] = "submitted",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return success_response(
        request,
        data=NewProductService(db, read_session=source).approvals(
            accounts, page=page, page_size=page_size, status=status
        ),
        meta={"source": "database"},
    )


@router.post(
    "/purchase-applications/{application_id}/decision", response_model=SuccessEnvelope[dict, dict]
)
def decide_purchase(
    request: Request,
    application_id: UUID,
    payload: PurchaseDecision,
    db: DB,
    principal: Review,
    accounts: Scope,
    source: Source,
):
    return success_response(
        request,
        data=NewProductService(db, read_session=source).decide_purchase(
            accounts, application_id, payload, principal.user_id
        ),
        meta={"source": "database"},
    )


@router.get("/listings-export", response_class=Response)
def export_listings(db: DB, _: Read, accounts: Scope, source: Source):
    import csv
    import io

    from .repository import NewProductRepository

    # The export never silently truncates. Bound work and reject over-limit; the
    # UI can explicitly surface this instead of returning a fake complete file.
    repo = NewProductRepository(source)
    _, count, _ = repo.page(accounts, page=1, page_size=1)
    if count > 10000:
        from .service import problem

        problem("NEW_PRODUCT_EXPORT_LIMIT", 422, "导出超过10000条，请缩小业务范围")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["账户", "店铺ID", "Item ID", "SKU", "MSKU", "品名", "负责人", "标签"])
    for page in range(1, (count + 199) // 200 + 1):
        data, _, _ = repo.page(accounts, page=page, page_size=200)
        for x in data.items:
            writer.writerow(
                [
                    x.source_account_ref,
                    x.store_id,
                    x.item_id,
                    x.local_sku,
                    x.msku,
                    x.title,
                    x.owner_name,
                    "小批量测品",
                ]
            )
    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="new-products-real.csv"'},
    )
