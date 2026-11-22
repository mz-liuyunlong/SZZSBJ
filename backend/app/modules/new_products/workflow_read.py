"""PR337_FLOW_WFS_REAL_STATUS_20261116: page-scoped, read-only workflow evidence.

All rows are supplied by an authorized Listing query. No writes, no inferred
approvals and no cross-store/SKU joins. At most 200 identities per call.
"""

from __future__ import annotations

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from .models import (
    NewProductRegistry,
    NewProductTrackingCurrent,
    NewProductTrackingReviewApplication,
    PurchaseApplication,
    TrackingDecision,
)


def attach_workflow_fields(session: Session, rows: list[dict]) -> None:
    keys = list(
        dict.fromkeys(
            (
                str(r.get("listing", {}).get("source_account_ref") or ""),
                str(r.get("listing", {}).get("store_id") or ""),
                str(r.get("listing", {}).get("item_id") or ""),
            )
            for r in rows
        )
    )
    if not keys:
        return
    if len(keys) > 200 or any(not all(k) for k in keys):
        raise ValueError("Invalid or excessive new-product workflow scope")

    identity = tuple_(
        PurchaseApplication.source_account_ref,
        PurchaseApplication.store_id,
        PurchaseApplication.item_id,
    )
    purchases = {}
    for item in session.scalars(
        select(PurchaseApplication)
        .where(identity.in_(keys))
        .order_by(PurchaseApplication.created_at.desc(), PurchaseApplication.id.desc())
    ):
        key = (item.source_account_ref, item.store_id, item.item_id)
        purchases.setdefault(key, item)

    registry_identity = tuple_(
        NewProductRegistry.source_account_ref,
        NewProductRegistry.store_id,
        NewProductRegistry.item_id,
    )
    registries = {
        (r.source_account_ref, r.store_id, r.item_id): r.id
        for r in session.scalars(select(NewProductRegistry).where(registry_identity.in_(keys)))
    }
    ids = list(registries.values())
    tracking = {}
    reviews = {}
    if ids:
        tracking = {
            t.registry_id: t
            for t in session.scalars(
                select(NewProductTrackingCurrent).where(
                    NewProductTrackingCurrent.registry_id.in_(ids)
                )
            )
        }
        for review in session.scalars(
            select(NewProductTrackingReviewApplication)
            .where(NewProductTrackingReviewApplication.registry_id.in_(ids))
            .order_by(NewProductTrackingReviewApplication.created_at.desc())
        ):
            reviews.setdefault(review.registry_id, review)

    decisions = {}
    decision_identity = tuple_(
        TrackingDecision.source_account_ref,
        TrackingDecision.store_id,
        TrackingDecision.item_id,
    )
    for item in session.scalars(select(TrackingDecision).where(decision_identity.in_(keys))):
        decisions[(item.source_account_ref, item.store_id, item.item_id)] = item

    for row in rows:
        listing = row["listing"]
        key = (
            str(listing["source_account_ref"]),
            str(listing["store_id"]),
            str(listing["item_id"]),
        )
        purchase = purchases.get(key)
        if purchase is not None:
            row["purchase_status"] = purchase.status
            row["purchase_id"] = str(purchase.id)
            row["purchase_version"] = purchase.version
            row["requested_qty"] = purchase.requested_qty
            row["purchase_reason"] = purchase.request_reason
            row["approved_qty"] = purchase.approved_qty
            row["purchase_review_reason"] = (
                purchase.review_reason if purchase.status == "rejected" else None
            )
            row["purchase_reviewed_by"] = (
                str(purchase.reviewed_by)
                if purchase.status == "rejected" and purchase.reviewed_by
                else None
            )
            row["purchase_reviewed_at"] = (
                purchase.reviewed_at.isoformat()
                if purchase.status == "rejected" and purchase.reviewed_at
                else None
            )
        reg_id = registries.get(key)
        track = tracking.get(reg_id)
        if track is not None:
            row["tracking_final_result"] = track.final_result
            row["tracking_status"] = track.tracking_status
            row["tracking_start_status"] = track.tracking_start_status
            row["tracking_started_date_la"] = (
                track.tracking_started_date_la.isoformat()
                if track.tracking_started_date_la
                else None
            )
        if key in decisions:
            if row.get("tracking_decision") is None:
                row["tracking_decision"] = decisions[key].decision
            row["tracking_version"] = decisions[key].version
        review = reviews.get(reg_id)
        if review is not None and review.status == "submitted":
            row["tracking_review_status"] = "submitted"
            row["tracking_review_application"] = {
                "status": review.status,
                "proposed_result": review.proposed_result,
                "reason": review.applicant_reason,
                "created_at": review.created_at.isoformat() if review.created_at else None,
            }

# NP_PURCHASE_REAPPLY_SELF_CONTAINED_V5
