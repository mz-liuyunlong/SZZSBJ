"""SKU first purchase: same signed transport/identity gates as workbench.

No existing application is created or mutated. A durable per-Listing claim
is committed before the provider POST; ambiguous results are never retried.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError

from .sku_progress_projection import ELIGIBLE

FIXED_QTY = 20


# SKU_PURCHASE_READ_COMPAT_20261128
# Check the actual purchase table, not the application's migration version.
# A deployment may serve reads from a separate schema. Only permit real new
# Listing claims after the column and both protective unique indexes exist.
LISTING_PURCHASE_SCHEMA_READY_SQL = """EXISTS (
    SELECT 1 FROM pg_catalog.pg_attribute a
    WHERE a.attrelid=to_regclass('biz_new_product_sku_purchase_plans')
      AND a.attname='item_id' AND a.attnum>0 AND NOT a.attisdropped
) AND (
    SELECT count(*)=2 FROM pg_catalog.pg_index i
    JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid
    WHERE i.indrelid=to_regclass('biz_new_product_sku_purchase_plans')
      AND i.indisunique AND i.indisvalid AND i.indisready
      AND c.relname IN ('uq_sku_purchase_active_listing','uq_sku_purchase_active_legacy_store')
) AND EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint c
    WHERE c.conrelid=to_regclass('biz_new_product_sku_purchase_plans')
      AND c.conname='ck_sku_purchase_listing_identity' AND c.contype='c'
)"""


def fail(code: str, message: str, status: int = 409):
    raise ApiError(code=code, message=message, status_code=status)


def enforce_qty(qty: int | None) -> int:
    if qty is not None and (type(qty) is not int or qty != FIXED_QTY):
        fail("SKU_PURCHASE_FIXED_QUANTITY", "首批采购数量固定20件，禁止修改", 422)
    return FIXED_QTY


def confirmed_grade(grade, coverage) -> str:
    """Use saved evidence, not a client-supplied or inferred grade."""
    coverage = coverage if isinstance(coverage, dict) else {}
    confirmed = coverage.get("evaluation_grade_confirmation_v1")
    manual = coverage.get("operator_assessment_v1")
    final = coverage.get("evaluation_final_snapshot")
    if not isinstance(confirmed, dict) or confirmed.get("status") != "confirmed":
        fail("SKU_PURCHASE_GRADE_UNCONFIRMED", "等级未确认，禁止采购", 422)
    if grade not in ("S", "A", "B", "C") or confirmed.get("effective_grade") != grade:
        fail("SKU_PURCHASE_GRADE_BLOCKED", "仅允许已确认S/A/B/C等级采购", 422)
    if not isinstance(manual, dict) or manual.get("decision") != "passed":
        fail("SKU_PURCHASE_MANUAL_PASS_REQUIRED", "须先确认人工测评通过", 422)
    risk = final.get("risk_evaluation") if isinstance(final, dict) else None
    if not isinstance(risk, dict) or risk.get("recommend_not_pass") is not False:
        fail("SKU_PURCHASE_RISK_BLOCKED", "风险证据不足或高风险，禁止采购", 422)
    if final.get("grade") != grade or final.get("rule_version") != confirmed.get("rule_version"):
        fail("SKU_PURCHASE_GRADE_CONFLICT", "等级快照与确认记录不一致", 422)
    return grade


def store_lock_key(account: str, sku_id: UUID, store: str) -> str:
    return (
        "sku-first-v1:" + hashlib.sha256(f"{account}\x1f{sku_id}\x1f{store}".encode()).hexdigest()
    )


# Keep the old store-wide transaction lock for unresolved historical claims.
# The durable idempotency key is now per Listing, not per store.
def claim_key(account: str, sku_id: UUID, store: str, item: str) -> str:
    identity = f"{account}\x1f{sku_id}\x1f{store}\x1f{item}"
    return "sku-first-v2:" + hashlib.sha256(identity.encode()).hexdigest()


ELIGIBILITY = text(f"""SELECT e.* FROM ({ELIGIBLE}) e
WHERE e.source_account_ref=:account AND e.sku_identity_id=:sku_id""")
LISTING = text("""SELECT l.item_id,l.local_sku,l.gtin FROM mart_listing_management_current l
WHERE l.source_account_ref=:account AND l.store_id=:store AND l.item_id=:item
AND l.local_sku=:sku AND EXISTS(SELECT 1 FROM dim_walmart_listings d
WHERE d.source_account_ref=l.source_account_ref AND d.store_id=l.store_id AND d.item_id=l.item_id
AND d.local_sku=l.local_sku)""")
GRADE = text("""SELECT f.grade,f.data_coverage_json FROM biz_new_product_registry r
JOIN biz_new_product_performance_current f ON f.registry_id=r.id
WHERE r.source_account_ref=:account AND r.store_id=:store AND r.item_id=:item
FOR UPDATE OF f""")


def submit_purchase(
    db: Session,
    accounts: frozenset[str],
    actor: str,
    *,
    account: str,
    sku_id: UUID,
    store: str,
    item: str,
    quantity: int | None = None,
) -> dict:
    qty = enforce_qty(quantity)
    if account not in accounts:
        fail("SKU_PURCHASE_SCOPE_DENIED", "无该账号的数据权限", 403)
    if os.getenv("NEW_PRODUCTS_READ_DATABASE_URL", "").strip():
        fail("SKU_PURCHASE_SPLIT_SOURCE_DENIED", "首批采购仅允许同一权威业务数据库", 403)
    if os.getenv("SZZSBJ_SKU_PROGRESS_PURCHASE_ENABLED", "").strip().upper() != "YES":
        fail("SKU_PURCHASE_DISABLED", "SKU首批采购尚未启用", 403)
    # Fail closed before credentials, token preflight, claim writes or provider calls.
    if not db.scalar(text("SELECT " + LISTING_PURCHASE_SCHEMA_READY_SQL)):
        fail("SKU_PURCHASE_SCHEMA_NOT_READY", "Listing独立采购数据结构未就绪，禁止提交", 409)
    # Import the actual existing implementation, not a copied transport.
    from app.integrations.lingxing.new_product_purchase_plan import (
        PurchasePlanResponseError,
        create_purchase_plan,
        validate_transport,
    )

    from .purchase_plan_service import (
        _build_verified_payload,
        _local_settings,
        _preflight_purchase_auth,
    )

    params = {"account": account, "sku_id": sku_id, "store": store, "item": item}
    context = SimpleNamespace(source_account_ref=account, store_id=store, item_id=item)
    settings = _local_settings(db, context)
    db.execute(text("SET LOCAL lock_timeout='3s'"))
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": store_lock_key(account, sku_id, store)},
    )
    e = db.execute(ELIGIBILITY, params).mappings().one_or_none()
    if e is None:
        fail("SKU_PURCHASE_NOT_ELIGIBLE", "SKU未纳入小批量测品", 422)
    params["sku"] = e["sku"]
    if (
        db.scalar(
            text(
                "SELECT count(*) FROM dwd_lingxing_sku_identity_index\n"
                "      WHERE source_account_ref=:account AND provider='lingxing' AND "
                "is_active AND lingxing_sku_code=:sku"
            ),
            params,
        )
        != 1
    ):
        fail("SKU_PURCHASE_IDENTITY_AMBIGUOUS", "SKU归属不唯一", 422)
    listing = db.execute(LISTING, params).mappings().one_or_none()
    if listing is None:
        fail("SKU_PURCHASE_LISTING_REQUIRED", "必须已上架且匹配所选店铺Listing", 422)
    saved = db.execute(GRADE, params).mappings().one_or_none()
    if saved is None:
        fail("SKU_PURCHASE_GRADE_UNCONFIRMED", "未找到已确认等级的测评记录", 422)
    grade = confirmed_grade(saved["grade"], saved["data_coverage_json"])
    context.score_snapshot = {
        "evaluation": {"grade": grade},
        "listing": {"local_sku": listing["local_sku"], "gtin": listing["gtin"]},
    }
    # Reuse workbench store/SID/credential-account/GTIN/Item ID validation.
    payload = _build_verified_payload(db, context, store, qty)
    if payload["data"][0]["quantity_plan"] != FIXED_QTY:
        fail("SKU_PURCHASE_FIXED_QUANTITY", "采购请求数量不符合固定20件", 422)
    try:
        validate_transport(settings, payload)
    except ValueError:
        fail("SKU_PURCHASE_TRANSPORT_UNAVAILABLE", "领星真实调用配置未就绪", 503)
    # Create progress record only if not already present; never reset manual data.
    db.execute(
        text("""INSERT INTO biz_new_product_sku_progress
    (id,source_account_ref,sku_identity_id,entered_at) VALUES(:pid,:account,:sku_id,now())
    ON CONFLICT(source_account_ref,sku_identity_id) DO NOTHING"""),
        {**params, "pid": uuid4()},
    )
    p = (
        db.execute(
            text("""SELECT id,progress_status,exited_at FROM biz_new_product_sku_progress
    WHERE source_account_ref=:account AND sku_identity_id=:sku_id FOR UPDATE"""),
            params,
        )
        .mappings()
        .one()
    )
    if p["progress_status"] != "in_progress" or p["exited_at"] is not None:
        fail("SKU_PURCHASE_PROGRESS_BLOCKED", "当前推进状态不允许采购", 422)
    key = claim_key(account, sku_id, store, item)
    existing = (
        db.execute(
            text(
                "SELECT id,submission_status,lingxing_plan_sn,quantity,item_id,"
                """cancellation_status
    FROM biz_new_product_sku_purchase_plans WHERE sku_progress_id=:pid AND store_id=:store
    AND (item_id=:item OR item_id IS NULL)
    ORDER BY (item_id IS NULL) DESC,created_at DESC,id DESC LIMIT 1"""
            ),
            {"pid": p["id"], "store": store, "item": item},
        )
        .mappings()
        .one_or_none()
    )
    if existing is not None:
        if existing["item_id"] is None:
            fail("SKU_PURCHASE_LEGACY_UNRESOLVED", "历史采购归属未确认，禁止重复采购")
        if existing["submission_status"] == "submitted" and existing["cancellation_status"] in (
            None,
            "failed",
        ):
            return {
                "id": existing["id"],
                "submission_status": "submitted",
                "quantity": existing["quantity"],
                "lingxing_plan_sn": existing["lingxing_plan_sn"],
                "duplicate": True,
            }
        fail("SKU_PURCHASE_ALREADY_ATTEMPTED", "已有采购记录，必须人工核对后处理，禁止重复提交")
    if db.scalar(
        text("""SELECT EXISTS(SELECT 1 FROM biz_new_product_purchase_applications
      WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
        AND status IN ('submitted','approved'))"""),
        params,
    ):
        fail(
            "SKU_PURCHASE_EXISTING_APPROVAL", "该Listing存在待审批或已批准的采购申请，禁止重复采购"
        )
    _preflight_purchase_auth(settings)
    plan_id = uuid4()
    db.execute(
        text("""INSERT INTO biz_new_product_sku_purchase_plans
    (id,sku_progress_id,store_id,item_id,quantity,submission_status,idempotency_key,
     submitted_by,last_attempt_at)
    VALUES(:id,:pid,:store,:item,20,'submitting',:key,:actor,now())"""),
        {
            "id": plan_id,
            "pid": p["id"],
            "store": store,
            "item": item,
            "key": key,
            "actor": actor,
        },
    )
    _event(
        db, p["id"], actor, plan_id, "attempt", {"store_id": store, "item_id": item, "quantity": 20}
    )
    db.commit()  # durable claim; do not POST if this commit raises
    try:
        receipt = create_purchase_plan(settings, payload)
    except Exception as exc:
        code = exc.code if isinstance(exc, PurchasePlanResponseError) else "LX_PURCHASE_UNKNOWN"
        request_ref = exc.request_id if isinstance(exc, PurchasePlanResponseError) else None
        db.execute(
            text(
                "UPDATE biz_new_product_sku_purchase_plans SET "
                "submission_status='unknown',\n"
                "         error_code=:code,request_ref=:request_ref,updated_at=now() "
                "WHERE id=:id AND submission_status='submitting'"
            ),
            {"id": plan_id, "code": code, "request_ref": request_ref},
        )
        _event(
            db, p["id"], actor, plan_id, "unknown", {"error_code": code, "request_ref": request_ref}
        )
        db.commit()
        fail("SKU_PURCHASE_RESULT_UNCERTAIN", "领星采购结果未确认，请核对领星，禁止重复提交", 502)
    try:
        updated = db.execute(
            text("""UPDATE biz_new_product_sku_purchase_plans SET submission_status='submitted',
          lingxing_plan_sn=:sn,request_ref=:request_ref,response_status='confirmed',submitted_at=now(),updated_at=now()
          WHERE id=:id AND submission_status='submitting'"""),
            {"id": plan_id, "sn": receipt["plan_sn"], "request_ref": receipt["request_id"]},
        )
        if updated.rowcount != 1:
            raise RuntimeError("SKU_PURCHASE_RECEIPT_CONFLICT")
        _event(
            db,
            p["id"],
            actor,
            plan_id,
            "receipt",
            {
                "plan_sn": receipt["plan_sn"],
                "ppg_sn": receipt["ppg_sn"],
                "request_id": receipt["request_id"],
                "quantity": 20,
            },
        )
        db.commit()
    except Exception:
        db.rollback()  # prior claim remains durable
        fail(
            "SKU_PURCHASE_LOCAL_FINALIZE_FAILED",
            "领星已返回采购回执，本地保存未确认，禁止重复提交",
            502,
        )
    return {
        "id": plan_id,
        "submission_status": "submitted",
        "quantity": 20,
        "lingxing_plan_sn": receipt["plan_sn"],
    }


def _event(db: Session, pid: UUID, actor: str, plan_id: UUID, event: str, data: dict):
    import json

    db.execute(
        text("""INSERT INTO biz_new_product_sku_progress_events
    (id,sku_progress_id,event_type,actor_type,actor_ref,event_key,after_json,occurred_at)
    VALUES(:id,:pid,:kind,'manual',:actor,:key,CAST(:data AS jsonb),:now)"""),
        {
            "id": uuid4(),
            "pid": pid,
            "kind": "purchase_" + event,
            "actor": actor,
            "key": f"{plan_id}:{event}",
            "data": json.dumps(data, ensure_ascii=False),
            "now": datetime.now(UTC),
        },
    )
