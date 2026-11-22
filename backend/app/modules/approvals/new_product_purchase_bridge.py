"""Adapter for real new-product purchase requests in the existing approval workbench.

NP_PURCHASE_WORKBENCH_REAL_API_V1_20261116
Source of truth: biz_new_product_purchase_applications. No mirror/double-write.
"""

from __future__ import annotations

from math import isfinite
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy import tuple_

from app.core.api import ApiError, ErrorCode
from app.modules.approvals.schemas import (
    ApprovalDetail,
    ApprovalEventRead,
    ApprovalItem,
    ApprovalListData,
    ApprovalMeta,
    ApprovalQuery,
)
from app.modules.fx_rates.reader import (
    load_usd_cny_rates, month_key, usd_cny_rate_for,
)
from app.modules.new_products.models import PurchaseApplication, NewProductRegistry
from app.modules.approvals.purchase_reference_evidence import purchase_reference_evidence


def _numeric(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _snapshot(row):
    value = row.score_snapshot
    return value if isinstance(value, dict) else {}


def _details(row, registry=None):
    source = _snapshot(row)
    listing = source.get("listing")
    listing = dict(listing) if isinstance(listing, dict) else {}
    if registry is not None:
        for key, field in (
            ("local_name", "product_name"),
            ("local_sku", "sku"),
            ("msku", "msku"),
            ("store_name", "store_name"),
            ("owner_name", "owner_name"),
        ):
            if not listing.get(key):
                listing[key] = getattr(registry, field, None)
    facts = source.get("facts")
    facts = facts if isinstance(facts, dict) else {}
    evaluation = source.get("evaluation")
    evaluation = evaluation if isinstance(evaluation, dict) else {}
    grade = evaluation.get("grade")
    if grade not in ("S", "A", "B", "C", "D", "Pass"):
        grade = None
    return {
        "purchase_kind": "initial",  # new-product module submits initial purchase only
        "application_source": "operator",  # explicit user-issued purchase request
        "product_name": listing.get("local_name") or listing.get("title"),
        "sku": listing.get("local_sku"),
        "msku": listing.get("msku"),
        "item_id": row.item_id,
        "store_name": listing.get("store_name"),
        "store_id": row.store_id,
        "owner_name": listing.get("owner_name"),
        "supplier_name": None,
        "required_delivery_date": None,
        "score_total": _numeric(evaluation.get("total")),
        "initial_grade": grade,
        "estimated_sellable_days": None,
        "sales_30d": _numeric(listing.get("sales_30d")),
        "suggested_qty": row.suggested_qty,
        "requested_qty": row.requested_qty,
        "approved_qty": row.approved_qty,
        "amount": None,  # never infer procurement spend from retail sale price
        "currency_code": None,
        "analysis": {
            "sellingPrice": _numeric(listing.get("sale_price_amount")),
            "grossMarginPct": _numeric(facts.get("gross_margin_pct")),
            "roi": _numeric(facts.get("roi")),
            "acosPct": _numeric(facts.get("acos_pct")),
            "adSpend": _numeric(facts.get("ad_spend_usd")),
            "adSales": _numeric(facts.get("ad_revenue_usd")),
            "adClicks": _numeric(facts.get("ad_clicks")),
            "validOrders14": _numeric(facts.get("valid_orders_14d")),
            "firstOrderDays": _numeric(facts.get("first_order_day")),
        },
    }


class NewProductPurchaseBridge:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _visible(accounts, actor, reviewer):
        stmt = select(PurchaseApplication).where(
            PurchaseApplication.source_account_ref.in_(list(accounts))
        )
        if not reviewer:
            stmt = stmt.where(PurchaseApplication.applicant_id == actor)
        return stmt

    def _registries(self, rows):
        keys = {(r.source_account_ref, r.store_id, r.item_id) for r in rows}
        if not keys:
            return {}
        identity = tuple_(
            NewProductRegistry.source_account_ref,
            NewProductRegistry.store_id,
            NewProductRegistry.item_id,
        )
        result = self.session.scalars(
            select(NewProductRegistry).where(identity.in_(sorted(keys)))
        ).all()
        return {
            (r.source_account_ref, r.store_id, r.item_id): r
            for r in result
        }

    @staticmethod
    def _item(row, actor, reviewer, registry=None):
        details = _details(row, registry)
        return ApprovalItem(
            id=str(row.id),
            version=row.version,
            approval_type="new_product_purchase",
            business_ref=row.item_id,
            title=details["product_name"] or row.item_id,
            source_account_ref=row.source_account_ref,
            applicant_id=row.applicant_id,
            status=row.status,
            risk_level="unknown",  # no verified risk-level snapshot; don't invent low
            amount=None,
            currency_code=None,
            submitted_at=row.created_at,
            reviewed_at=row.reviewed_at,
            reviewed_by=row.reviewed_by,
            reason=row.request_reason,
            can_review=(reviewer and row.status == "submitted" and row.applicant_id != actor),
            requires_verification=False,
            purchase_details=details,
        )

    def list(self, query: ApprovalQuery, accounts, actor, reviewer):
        stmt = self._visible(accounts, actor, reviewer)
        status = {"pending": "submitted", "approved": "approved", "rejected": "rejected"}[query.tab]
        stmt = stmt.where(PurchaseApplication.status == status)
        if query.view == "created":
            stmt = stmt.where(PurchaseApplication.applicant_id == actor)
        # Include applications created by the current user in the workbench.
        # Self-review remains disabled by _item(...).can_review.
        if query.risk_level:
            # Risk grade is unknown until a trusted snapshot is recorded.
            stmt = stmt.where(false())
        if query.keyword.strip():
            needle = "%" + query.keyword.strip() + "%"
            stmt = stmt.where(
                or_(
                    PurchaseApplication.item_id.ilike(needle),
                    PurchaseApplication.store_id.ilike(needle),
                    PurchaseApplication.request_reason.ilike(needle),
                    PurchaseApplication.score_snapshot["listing"]["local_sku"]
                    .as_string()
                    .ilike(needle),
                    PurchaseApplication.score_snapshot["listing"]["local_name"]
                    .as_string()
                    .ilike(needle),
                )
            )
        total = (
            self.session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
            or 0
        )
        rows = self.session.scalars(
            stmt.order_by(PurchaseApplication.created_at.desc(), PurchaseApplication.id.desc())
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        ).all()
        registries = self._registries(rows)
        return (
            ApprovalListData(items=[
                self._item(r, actor, reviewer,
                           registries.get((r.source_account_ref, r.store_id, r.item_id)))
                for r in rows
            ]),
            ApprovalMeta(page=query.page, page_size=query.page_size, total=total),
        )

    def detail(self, application_id: UUID, accounts, actor, reviewer):
        stmt = self._visible(accounts, actor, reviewer).where(
            PurchaseApplication.id == application_id
        )
        row = self.session.scalar(stmt)
        if row is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        registries = self._registries([row])
        item = self._item(row, actor, reviewer,
                          registries.get((row.source_account_ref, row.store_id, row.item_id)))

        # PURCHASE_PROFIT_SYSTEM_FX_V1
        # Read the Lingxing USD my_rate for the application month.
        # The existing purchase detail authorization has already
        # verified the account scope and applicant/reviewer access.
        fx_day = row.created_at.astimezone(
            ZoneInfo("Asia/Shanghai")
        ).date()
        fx_month = month_key(fx_day)
        fx_rate = usd_cny_rate_for(
            load_usd_cny_rates(self.session), fx_day
        )
        if item.purchase_details is not None:
            item.purchase_details.update({
                "profit_fx_month": fx_month,
                "profit_fx_rate": str(fx_rate) if fx_rate is not None else None,
                "profit_fx_source": "lingxing_my_rate",
            })

        # PURCHASE_APPROVAL_REFERENCE_V1: only after record-level access check.
        if item.purchase_details is not None:
            item.purchase_details["approval_evidence"] = purchase_reference_evidence(
                self.session, row
            )
        events = [
            ApprovalEventRead(
                event_type="purchase_submitted",
                actor_id=row.applicant_id,
                note=row.request_reason or None,
                created_at=row.created_at,
            )
        ]
        if row.reviewed_at is not None and row.reviewed_by:
            events.append(
                ApprovalEventRead(
                    event_type="purchase_" + row.status,
                    actor_id=row.reviewed_by,
                    note=row.review_reason,
                    created_at=row.reviewed_at,
                )
            )
        from app.modules.new_products.models import ActionEvent
        approved_store_id = None
        if row.status == "approved":
            decision_event = self.session.scalar(
                select(ActionEvent).where(
                    ActionEvent.source_account_ref == row.source_account_ref,
                    ActionEvent.store_id == row.store_id,
                    ActionEvent.item_id == row.item_id,
                    ActionEvent.event_type == "purchase_approved",
                    ActionEvent.payload_json["application_id"].as_string() == str(row.id),
                ).order_by(ActionEvent.created_at.desc()).limit(1)
            )
            if decision_event and isinstance(decision_event.payload_json, dict):
                approved_store_id = decision_event.payload_json.get("purchase_store_id")
        return ApprovalDetail(
            **item.model_dump(),
            snapshot={
                "score_snapshot": _snapshot(row),
                "item_id": row.item_id,
                "store_id": row.store_id,
                "approved_purchase_store_id": approved_store_id,
                "approved_qty": row.approved_qty,
                "requested_qty": row.requested_qty,
                "suggested_qty": row.suggested_qty,
                "score_rule_version": row.score_rule_version,
                "review_reason": row.review_reason,
            },
            evidence=None,
            current_case=None,
            data_changed=False,
            can_supplement=False,
            events=events,
        )

# SZZSBJ_PURCHASE_APPROVE_STORE_QTY_V1

# NP_APPROVAL_IDENTITY_REGISTRY_V2_20261122
