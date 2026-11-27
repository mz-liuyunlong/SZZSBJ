"""Authorized purchase workbench real write. Real external side effect.

Append-only attempt and receipt events are committed independently of approval.
Any post-claim error stays blocked; do not clear the claim or blindly retry.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.config import AppEnvironment, get_database_url, get_settings
from app.integrations.lingxing.new_product_purchase_plan import (
    PurchasePlanResponseError,
    build_purchase_plan_payload,
    create_purchase_plan,
    validate_transport,
)
from app.integrations.lingxing.token_manager import (
    LingxingTokenError,
    get_shared_lingxing_token_manager,
)
from app.modules.data_pages.models import LingxingStoreDimension, ListingManagementCurrentMart
from app.modules.integration_sync.models import IntegrationInterface, IntegrationSyncConfig
from app.modules.new_products.models import ActionEvent, PurchaseApplication
from app.modules.new_products.read_source import get_new_product_read_session
from app.modules.pmc_purchase.models import LingxingPurchasePlanOds

ATTEMPT = "lingxing_purchase_plan_attempt"
RECEIPT = "lingxing_purchase_plan_receipt"
UNCERTAIN = "lingxing_purchase_plan_uncertain"


def fail(code: str, message: str, status: int = 409) -> None:
    raise ApiError(code=code, status_code=status, message=message)


def _event(
    session: Session, row: PurchaseApplication, actor: str, kind: str, payload: dict
) -> None:
    session.add(
        ActionEvent(
            id=uuid4(),
            source_account_ref=row.source_account_ref,
            store_id=row.store_id,
            item_id=row.item_id,
            actor_id=actor,
            event_type=kind,
            payload_json={"application_id": str(row.id), **payload},
            created_at=datetime.now(UTC),
        )
    )


def ensure_no_attempt(session: Session, row: PurchaseApplication) -> None:
    exists = session.scalar(
        select(ActionEvent.id)
        .where(
            ActionEvent.source_account_ref == row.source_account_ref,
            ActionEvent.store_id == row.store_id,
            ActionEvent.item_id == row.item_id,
            ActionEvent.event_type.in_((ATTEMPT, RECEIPT, UNCERTAIN)),
            ActionEvent.payload_json["application_id"].astext == str(row.id),
        )
        .limit(1)
    )
    if exists is not None:
        fail(
            "NP_LX_ALREADY_ATTEMPTED",
            "\u8be5\u7533\u8bf7\u5df2\u53d1\u9001\u8fc7\u9886\u661f\uff0c\u7981\u6b62\u91cd\u590d\u63d0\u4ea4\uff1b\u8bf7\u5148\u6838\u5bf9\u9886\u661f\u91c7\u8d2d\u8ba1\u5212\u548c\u672c\u5730\u5ba1\u8ba1\u8bb0\u5f55",
        )


def _local_settings(session: Session, row: PurchaseApplication):
    """Normal workbench approval; no per-application environment configuration."""
    settings = get_settings()
    if settings.app_env is AppEnvironment.TEST:
        fail("NP_LX_TEST_ENV_DENIED", "自动化测试环境禁止真实创建采购计划", 403)
    # Optional emergency stop. Existing normal Lingxing transport gates stay mandatory.
    switch = os.getenv("SZZSBJ_NP_LINGXING_REAL_WRITE", "").strip().upper()
    if switch and switch != "YES":
        fail("NP_LX_WRITE_DISABLED", "领星采购写入已暂停，请联系管理员", 403)
    # Verify the actual bound transaction, not a hard-coded hostname or port.
    target = get_database_url(settings)
    bind = session.get_bind()
    bound = getattr(bind, "url", None)
    if bound is None:
        bound = getattr(getattr(bind, "engine", None), "url", None)
    if (
        bound is None
        or bound.get_backend_name() != "postgresql"
        or (bound.host, bound.port, bound.database, bound.username)
        != (target.host, target.port, target.database, target.username)
    ):
        fail(
            "NP_LX_WRITE_DB_UNVERIFIED",
            "Approval session does not match configured PostgreSQL write target",
            403,
        )
    if session.execute(text("SHOW transaction_read_only")).scalar_one() != "off":
        fail("NP_LX_WRITE_DB_READONLY", "Approval database transaction is read-only", 403)
    return settings


def _read_verified_payload(session: Session, row: PurchaseApplication, store_id: str, qty: int):
    # Use a separate protected source when explicitly configured. Otherwise read
    # the same authoritative server database using the already locked session.
    # Never redirect a write to the read source or invent a fallback account.
    if os.getenv("NEW_PRODUCTS_READ_DATABASE_URL", "").strip():
        with contextmanager(get_new_product_read_session)() as source:
            return _build_verified_payload(source, row, store_id, qty)
    return _build_verified_payload(session, row, store_id, qty)


def _verify_credential_account(refs: set[str], account: str) -> None:
    if not account or refs != {account}:
        fail("NP_LX_ACCOUNT_UNVERIFIED", "领星采购账号映射缺失或不唯一，禁止写入", 422)
    configured = os.getenv("SZZSBJ_NP_LINGXING_CREDENTIAL_ACCOUNT_REF", "").strip()
    if configured and configured != account:
        fail("NP_LX_CREDENTIAL_ACCOUNT_UNCONFIRMED", "领星密钥账号与采购申请账号不一致", 403)


def _build_verified_payload(source: Session, row: PurchaseApplication, store_id: str, qty: int):
    # Reuse the single configured Lingxing purchase-plan reader account context.
    # Never choose a default from several account references.
    refs = set(
        source.scalars(
            select(IntegrationSyncConfig.source_account_ref)
            .join(
                IntegrationInterface, IntegrationInterface.id == IntegrationSyncConfig.interface_id
            )
            .where(
                IntegrationInterface.provider == "lingxing",
                IntegrationInterface.interface_key == "purchasePlanList",
            )
            .distinct()
        ).all()
    )
    _verify_credential_account(refs, row.source_account_ref)
    mart = ListingManagementCurrentMart
    listing = source.scalar(
        select(mart).where(
            mart.source_account_ref == row.source_account_ref,
            mart.store_id == row.store_id,
            mart.item_id == row.item_id,
        )
    )
    if listing is None:
        fail("NP_LX_LISTING_MISSING", "Original Listing is missing; cannot resolve SKU/GTIN", 422)
    snapshot = row.score_snapshot if isinstance(row.score_snapshot, dict) else {}
    evaluation = snapshot.get("evaluation")
    if not isinstance(evaluation, dict) or evaluation.get("grade") not in ("S", "A", "B", "C"):
        fail(
            "NP_LX_GRADE_BLOCKED",
            "Only confirmed S/A/B/C purchase applications can be written",
            422,
        )
    frozen = snapshot.get("listing")
    if isinstance(frozen, dict):
        for field in ("local_sku", "gtin"):
            old = frozen.get(field)
            current = getattr(listing, field)
            if isinstance(old, str) and old.strip() and old.strip() != (current or "").strip():
                fail("NP_LX_IDENTITY_CHANGED", f"Frozen and current {field} differ", 422)
    dim = LingxingStoreDimension
    stores = source.scalars(
        select(dim).where(
            dim.source_account_ref == row.source_account_ref,
            dim.store_id == store_id,
            or_(dim.platform_code == "walmart", dim.platform_code_raw == "10008"),
            dim.is_sync.is_(True),
        )
    ).all()
    if len(stores) != 1 or not stores[0].store_name:
        fail("NP_LX_STORE_UNVERIFIED", "Selected Walmart store is missing or ambiguous", 422)
    store = stores[0]
    same_names = source.scalars(
        select(dim.id)
        .where(dim.source_account_ref == row.source_account_ref, dim.store_name == store.store_name)
        .limit(2)
    ).all()
    if len(same_names) != 1:
        fail("NP_LX_STORE_NAME_AMBIGUOUS", "Store name has multiple provider identities", 422)
    # Historical provider purchase plans are verification evidence, not live UI data.
    # A matching seller name plus a single observed nonzero SID is required.
    ods = LingxingPurchasePlanOds
    observed = set(
        source.scalars(
            select(ods.sid)
            .where(
                ods.source_account_ref == row.source_account_ref,
                ods.seller_name == store.store_name,
                ods.sid.is_not(None),
                ods.sid.notin_(("", "0")),
            )
            .distinct()
            .limit(3)
        ).all()
    )
    candidates = {
        str(v).strip() for v in (store.sid, store.store_id) if v and str(v).strip() != "0"
    }
    if len(observed) != 1 or not observed.issubset(candidates):
        fail(
            "NP_LX_SID_NOT_PROVEN",
            "Selected Walmart SID has no unambiguous historical purchase-plan evidence",
            422,
        )
    sid = next(iter(observed))
    try:
        return build_purchase_plan_payload(
            sku=listing.local_sku, gtin=listing.gtin, item_id=row.item_id, sid=sid, quantity=qty
        )
    except ValueError as exc:
        fail("NP_LX_FIELD_INVALID", str(exc), 422)


def _preflight_purchase_auth(settings) -> None:
    """Check shared token before writing durable purchase intent; no purchase POST."""
    try:
        get_shared_lingxing_token_manager(settings).get_access_token()
    except LingxingTokenError as exc:
        category = exc.category
        # These fields are internal stable codes, not credentials or provider messages.
        code = exc.provider_code if type(exc.provider_code) is int else None
        suffix = f" / {code}" if code is not None else ""
        fail(
            "NP_LX_TOKEN_PREFLIGHT_FAILED",
            f"领星认证未通过：{category}{suffix}。本次未发送采购请求，可修复认证后重新提交。",
            503,
        )
    except Exception:
        fail("NP_LX_TOKEN_PREFLIGHT_FAILED", "领星认证初始化失败。本次未发送采购请求。", 503)


def create_and_record_local_plan(
    session: Session, row: PurchaseApplication, actor: str, store_id: str, qty: int
) -> dict:
    """Caller must already hold the purchase-application row lock."""
    settings = _local_settings(session, row)
    ensure_no_attempt(session, row)
    payload = _read_verified_payload(session, row, store_id, qty)
    try:
        validate_transport(settings, payload)
    except ValueError:
        fail(
            "NP_LX_TRANSPORT_UNAVAILABLE",
            "领星真实调用配置未就绪，请核对现有 Token、签名及真实调用开关。",
            503,
        )
    _preflight_purchase_auth(settings)
    expected_version = row.version
    # Save exact intent BEFORE sending. A crash/timeout must not permit another POST.
    _event(
        session,
        row,
        actor,
        ATTEMPT,
        {
            "expected_version": expected_version,
            "purchase_store_id": store_id,
            "payload": payload,
            "mode": "authorized_real_acceptance",
        },
    )
    session.commit()
    try:
        receipt = create_purchase_plan(settings, payload)
    except Exception as exc:
        # Store only safe, stable codes; arbitrary exception texts can contain secrets.
        code = exc.code if isinstance(exc, PurchasePlanResponseError) else "LX_PURCHASE_UNKNOWN"
        request_id = exc.request_id if isinstance(exc, PurchasePlanResponseError) else None
        _event(session, row, actor, UNCERTAIN, {"error_code": code, "request_id": request_id})
        session.commit()
        fail(
            "NP_LX_RESULT_UNCERTAIN",
            f"Lingxing write not confirmed: {code}. Do not retry; reconcile in Lingxing first.",
            502,
        )
    # Persist confirmed receipt independently so a subsequent local commit error cannot cause a
    # resend.
    _event(
        session,
        row,
        actor,
        RECEIPT,
        {
            **receipt,
            "purchase_store_id": store_id,
            "approved_qty": qty,
            "expected_version": expected_version,
        },
    )
    session.commit()
    locked = session.scalar(
        select(PurchaseApplication)
        .where(
            PurchaseApplication.id == row.id,
            PurchaseApplication.source_account_ref == row.source_account_ref,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None or locked.status != "submitted" or locked.version != expected_version:
        fail(
            "NP_LX_LOCAL_FINALIZE_CONFLICT",
            "Lingxing plan exists; local approval changed. Reconcile without retrying.",
        )
    return receipt
