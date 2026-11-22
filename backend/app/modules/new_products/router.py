"""New-product APIs. No direct external requests, no implicit background sync or mock fallback."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.api import SuccessEnvelope, success_response
from app.core.auth import Principal, require_principal
from app.core.permissions import is_approval_admin
from app.db.session import get_db_session

from .evaluation_schemas import (
    EvaluationCalculate,
    EvaluationReviewDecision,
    EvaluationReviewRequest,
)
from .read_source import get_new_product_read_session, require_new_product_scope
from .schemas import (
    AssessmentPurchaseWrite,
    AssessmentWrite,
    ListingQuery,
    MarketWrite,
    PurchaseDecision,
    PurchaseWrite,
    RuleApply,
    RulePreview,
    ScoreCorrectionWrite,
    TrackingWrite,
)
from .service import NewProductService

router = APIRouter(prefix="/api/new-products", tags=["New Product Performance"])
DB = Annotated[Session, Depends(get_db_session)]
Source = Annotated[Session, Depends(get_new_product_read_session)]
Scope = Annotated[frozenset[str], Depends(require_new_product_scope)]
Authenticated = Annotated[Principal, Depends(require_principal)]
Read = Authenticated
Configure = Authenticated
Score = Authenticated
PurchaseRequester = Authenticated
Review = Authenticated
Tracking = Authenticated


@router.get("/summary", response_model=SuccessEnvelope[dict, dict])
def performance_summary(request: Request, db: DB, _: Read, accounts: Scope, source: Source):
    from .performance_list_scope import summary

    return success_response(
        request, data=summary(source, db, accounts), meta={"source": "saved_projection"}
    )


@router.get("/board/summary", response_model=SuccessEnvelope[dict, dict])
def new_product_board_summary(
    request: Request,
    start_date: date,
    end_date: date,
    db: DB,
    _: Read,
    accounts: Scope,
    source: Source,
):
    from app.core.api import ApiError

    from .performance_list_scope import board_summary

    if start_date > end_date:
        raise ApiError(
            code="NP_BOARD_DATE_RANGE_INVALID", status_code=422, message="开始日期不得晚于结束日期"
        )
    cfg, _ = NewProductService(db, read_session=source)._config()
    remind_days = int(cfg.get("remindDays", 30))
    data = board_summary(
        source,
        db,
        accounts,
        start_date=start_date,
        end_date=end_date,
        remind_days=remind_days,
    )
    return success_response(request, data=data, meta={"source": "saved_board_projection"})



# Tracking is intentionally split into two independent, read-only requests.
# No shared full-Listing page loop is used for either view.
@router.get("/tracking/board/summary", response_model=SuccessEnvelope[dict, dict])
def tracking_board_summary(
    request: Request,
    start_date: date,
    end_date: date,
    db: DB,
    _: Read,
    accounts: Scope,
    source: Source,
):
    from .tracking_read import board_summary

    result = board_summary(source, db, accounts, start_date, end_date)
    return success_response(request, data=result, meta={"source": "saved_tracking_projection"})


@router.get("/tracking/listings", response_model=SuccessEnvelope[dict, dict])
def tracking_listings(
    request: Request,
    db: DB,
    _: Read,
    accounts: Scope,
    source: Source,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=20, le=50)] = 50,
    keyword: str = "",
    owners: str = "",
    grades: str = "",
    outcome: str = "all",
    period: Annotated[int, Query()] = 30,
    drill_kind: str = "",
    drill_value: str = "",
    parent_category: str = "",
    start_date: Annotated[date | None, Query(alias="from")] = None,
    end_date: Annotated[date | None, Query(alias="to")] = None,
):
    from app.core.api import ApiError

    from .tracking_read import detail_list

    if period not in (30, 60, 180):
        raise ApiError(
            code="NP_TRACKING_PERIOD_INVALID",
            status_code=422,
            message="数据周期仅支持30、60、180天",
        )

    data = detail_list(
        source,
        db,
        accounts,
        page=page,
        page_size=page_size,
        keyword=keyword,
        owners=owners,
        grades=grades,
        outcome=outcome,
        drill_kind=drill_kind,
        drill_value=drill_value,
        parent_category=parent_category,
        start_date=start_date,
        end_date=end_date,
    )
    return success_response(
        request,
        data=data,
        meta={"source": "saved_tracking_page", "period": period},
    )


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
    # PR337_EVALUATION_FULL_WORKFLOW_20261116:
    # One page-sized snapshot lookup, no per-item source scan.
    from .evaluation_workflow import decorate_page

    data = decorate_page(db, data)
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
        data=NewProductService(db, read_session=source).persisted_score(
            accounts, account, store, item
        ),  # PR337_PERSISTED_DISPLAY_V1
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
    # Same guarded publisher is used by the daily tick and rule apply.
    queued = False
    recalc_status = "disabled"
    if payload.kind == "performance" and not data.get("unchanged"):
        import os

        from .unified_publish import permission_to_write

        if permission_to_write():
            if not (os.getenv("CELERY_BROKER_URL") or "").strip():
                recalc_status = "manual_execution_required"
            else:
                from app.celery_app import celery_app

                try:
                    celery_app.send_task(
                        "new_products.performance_unified_publish",
                        args=["rule_apply"],
                        queue="integration",
                    )
                except Exception:
                    recalc_status = "enqueue_failed"
                else:
                    recalc_status = "queued"
                    queued = True
    elif data.get("unchanged"):
        recalc_status = "unchanged"
    return success_response(
        request,
        data=data,
        meta={
            **{"applied_immediately": True},
            "unified_recalculation_queued": queued,
            "unified_recalculation_status": recalc_status,
        },
    )


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


@router.post("/evaluations/manual-decision", response_model=SuccessEnvelope[dict, dict])
def save_manual_evaluation_decision(
    request: Request,
    payload: AssessmentWrite,
    db: DB,
    principal: Score,
    accounts: Scope,
    source: Source,
):
    return success_response(
        request,
        data=NewProductService(db, read_session=source).save_manual_assessment(
            accounts, payload, principal.user_id
        ),
        meta={"source": "database"},
    )


@router.post("/evaluations/confirm-and-purchase", response_model=SuccessEnvelope[dict, dict])
def confirm_evaluation_and_request_purchase(
    request: Request,
    payload: AssessmentPurchaseWrite,
    db: DB,
    principal: Score,
    purchase_authority: PurchaseRequester,
    accounts: Scope,
    source: Source,
):
    # Both Score and PurchaseRequester permissions are checked by FastAPI.
    del purchase_authority
    return success_response(
        request,
        data=NewProductService(db, read_session=source).save_assessment_and_purchase(
            accounts, payload, principal.user_id
        ),
        meta={"source": "database"},
    )


# NP_OPERATOR_SCORE_CORRECTION_V1_20261119: same score permission, separate from approval.
@router.put("/score-corrections", response_model=SuccessEnvelope[dict, dict])
def save_operator_score_correction(
    request: Request,
    payload: ScoreCorrectionWrite,
    db: DB,
    principal: Score,
    accounts: Scope,
    source: Source,
):
    return success_response(
        request,
        data=NewProductService(db, read_session=source).save_score_correction(
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


@router.get("/purchase-applications/{application_id}", response_model=SuccessEnvelope[dict, dict])
def purchase_application_snapshot(
    request: Request,
    application_id: UUID,
    db: DB,
    principal: Review,
    accounts: Scope,
    source: Source,
):
    return success_response(
        request,
        data=NewProductService(db, read_session=source).purchase_application_snapshot(
            accounts, application_id
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
            accounts,
            application_id,
            payload,
            principal.user_id,
            allow_self=is_approval_admin(principal),
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


# PR337_EVALUATION_FULL_WORKFLOW_20261116:
# Single-item and evaluation-review endpoints, independent of purchase/tracking.
@router.post("/evaluations/calculate", response_model=SuccessEnvelope[dict, dict])
def evaluate_manually(
    request: Request,
    payload: EvaluationCalculate,
    db: DB,
    principal: Score,
    accounts: Scope,
    source: Source,
):
    from .evaluation_workflow import calculate_once
    from .unified_publish import authenticated_manual_publish

    a, s, i = payload.source_account_ref, payload.store_id, payload.item_id
    listing = NewProductService(db, read_session=source)._listing(accounts, a, s, i)
    with authenticated_manual_publish((a, s, i)):
        result = calculate_once(db, a, s, i, principal.user_id, listing)
    return success_response(
        request,
        data=result,
        meta={"source": "database"},
    )


@router.get(
    "/evaluations/status/{account}/{store}/{item}", response_model=SuccessEnvelope[dict, dict]
)
def get_evaluation_job(
    request: Request,
    account: str,
    store: str,
    item: str,
    db: DB,
    _: Read,
    accounts: Scope,
    source: Source,
):
    from .evaluation_workflow import calculation_status

    NewProductService(db, read_session=source)._listing(accounts, account, store, item)
    return success_response(
        request,
        data=calculation_status(db, accounts, account, store, item),
        meta={"source": "database"},
    )


@router.post("/evaluation-reviews", response_model=SuccessEnvelope[dict, dict])
def apply_evaluation_review(
    request: Request,
    payload: EvaluationReviewRequest,
    db: DB,
    principal: Score,
    accounts: Scope,
    source: Source,
):
    from .evaluation_workflow import submit_review

    a, s, i = payload.source_account_ref, payload.store_id, payload.item_id
    NewProductService(db, read_session=source)._listing(accounts, a, s, i)
    return success_response(
        request,
        data=submit_review(
            db,
            accounts,
            a,
            s,
            i,
            principal.user_id,
            payload.reason_type,
            payload.reason,
            payload.evidence,
            payload.new_decision,
        ),
        meta={"source": "database"},
    )


@router.post(
    "/evaluation-reviews/{application_id}/decision", response_model=SuccessEnvelope[dict, dict]
)
def decide_evaluation_review(
    request: Request,
    application_id: UUID,
    payload: EvaluationReviewDecision,
    db: DB,
    principal: Review,
    accounts: Scope,
):
    from .evaluation_workflow import decide_review

    return success_response(
        request,
        data=decide_review(
            db,
            accounts,
            application_id,
            principal.user_id,
            payload.decision,
            payload.reason,
            payload.expected_version,
            allow_self=is_approval_admin(principal),
        ),
        meta={"source": "database"},
    )


@router.post(
    "/evaluation-reviews/{application_id}/recheck", response_model=SuccessEnvelope[dict, dict]
)
def recheck_evaluation_review(
    request: Request, application_id: UUID, db: DB, principal: Score, accounts: Scope
):
    from .evaluation_workflow import recheck_once

    return success_response(
        request,
        data=recheck_once(db, accounts, application_id, principal.user_id),
        meta={"source": "database"},
    )

# SZZSBJ_NP_PERMISSIONS_V3
