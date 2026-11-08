"""WFS clearance transactional service; an approval is never an external repricing action."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.data_pages.models import ListingArchiveState, ListingManagementCurrentMart

from .evaluator import evaluate
from .read_only_listings import (
    read_business_snapshot,
    risk_read_model_ready,
    search_unassessed_listings,
)
from .repository import current_available, facts_for_listing, find_listing, la_today
from .rules import ClearanceRules


def denied() -> None:
    raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)


def invalid(status: int = 409) -> None:
    raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=status)


def scoped(account: str, accounts: frozenset[str]) -> None:
    if account not in accounts:
        denied()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


# CLEARANCE_APPLICATION_SAVED_FIELDS_V52
# Application-time values belong to the authorized 55433/production approval
# snapshot. They are never reconstructed from unrelated Listings or edited.
# This helper is shared by single-DB and isolated-storage read paths.
def _saved_date(value: object) -> str | None:
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        return None
    try:
        return value if date.fromisoformat(value).isoformat() == value else None
    except ValueError:
        return None


def _nonnegative_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (ValueError, InvalidOperation, TypeError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def _snapshot_saved_fields(row: Mapping[str, Any], snapshot: object) -> dict:
    result = {"planned_completion_date": None, "target_inventory_cost_usd": None}
    if not isinstance(snapshot, dict):
        return result
    account, store, raw_item = (
        str(row["source_account_ref"]),
        str(row["store_id"]),
        str(row["item_id"]),
    )
    triple = raw_item.split("::")
    item = (
        triple[2]
        if (len(triple) == 3 and triple[:2] == [account, store] and triple[2].isdigit())
        else raw_item
    )
    if (
        str(snapshot.get("source_account_ref", "")) != account
        or str(snapshot.get("store_id", "")) != store
        or str(snapshot.get("item_id", "")) != item
    ):
        return result
    result["planned_completion_date"] = _saved_date(snapshot.get("planned_completion_date"))
    metrics = snapshot.get("metrics")
    if not isinstance(metrics, dict):
        return result
    # Both evaluator and read-only business snapshots explicitly carry the
    # purchase + first-leg inventory unit cost. The similarly named
    # capital_at_cost_usd in the 0076 fallback includes selling expenses:
    # NEVER read that ambiguous value for clearance inventory capital.
    unit = _nonnegative_decimal(metrics.get("unit_inventory_cost_usd"))
    if unit is None:
        unit = _nonnegative_decimal(metrics.get("inventory_unit_cost_usd"))
    if unit is None:
        purchase = _nonnegative_decimal(metrics.get("purchase_unit_cost_usd"))
        first_leg = _nonnegative_decimal(metrics.get("first_leg_unit_cost_usd"))
        if purchase is not None and first_leg is not None:
            unit = purchase + first_leg
    qty = _nonnegative_decimal(
        row.get("approved_qty") if row.get("approved_qty") is not None else row.get("requested_qty")
    )
    if unit is not None and qty is not None and qty > 0 and qty == qty.to_integral_value():
        cost = unit * qty
        if cost.is_finite():
            try:
                result["target_inventory_cost_usd"] = float(cost.quantize(Decimal("0.01")))
            except InvalidOperation:
                pass
    return result


def application_saved_metadata(
    session: Session, rows: list[Mapping[str, Any]], snapshots: dict[str, object] | None = None
) -> dict[str, dict]:
    """Read only; scoped to application IDs already authorized by caller."""
    if not rows:
        return {}
    if snapshots is None:
        approval_ids = [row["approval_id"] for row in rows]
        records = (
            session.execute(
                text("""
            SELECT id, snapshot FROM app_approval_requests
            WHERE id=ANY(:ids) AND approval_type='clearance_request'
        """),
                {"ids": approval_ids},
            )
            .mappings()
            .all()
        )
        snapshots = {str(record["id"]): record["snapshot"] for record in records}
    result = {
        str(row["id"]): _snapshot_saved_fields(row, snapshots.get(str(row["approval_id"])))
        for row in rows
    }
    missing = [
        row["id"] for row in rows if result[str(row["id"])]["planned_completion_date"] is None
    ]
    if missing:
        events = (
            session.execute(
                text("""
            SELECT application_id, detail_json FROM biz_clearance_events
            WHERE application_id=ANY(:ids) AND event_type='submitted'
            ORDER BY created_at ASC, id ASC
        """),
                {"ids": missing},
            )
            .mappings()
            .all()
        )
        for event in events:
            app_id = str(event["application_id"])
            details = event["detail_json"]
            if (
                app_id in result
                and result[app_id]["planned_completion_date"] is None
                and isinstance(details, dict)
            ):
                result[app_id]["planned_completion_date"] = _saved_date(
                    details.get("planned_completion_date")
                )
    return result


def _event(session: Session, application_id: UUID, kind: str, actor: str, details: dict) -> None:
    session.execute(
        text("""
        INSERT INTO biz_clearance_events (id, application_id, event_type, actor_ref, detail_json)
        VALUES (:id, :application, :kind, :actor, CAST(:details AS jsonb))
    """),
        {
            "id": uuid4(),
            "application": application_id,
            "kind": kind,
            "actor": actor,
            "details": _json(details),
        },
    )


def _approval_event(
    session: Session,
    approval_id: UUID,
    kind: str,
    actor: str,
    note: str = "",
    details: dict | None = None,
) -> None:
    session.execute(
        text("""
        INSERT INTO app_approval_events (id, approval_id, event_type, actor_id, note, detail)
        VALUES (:id, :approval, :kind, :actor, :note, CAST(:detail AS jsonb))
    """),
        {
            "id": uuid4(),
            "approval": approval_id,
            "kind": kind,
            "actor": actor,
            "note": note or None,
            "detail": _json(details or {}),
        },
    )


def persisted_rule_version(session: Session) -> tuple[int, ClearanceRules] | None:
    """Return only database-saved rules; no synthetic history or persisted defaults."""
    row = (
        session.execute(
            text("""
        SELECT version, config_json FROM biz_clearance_rule_versions
        ORDER BY version DESC LIMIT 1
    """)
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return int(row["version"]), ClearanceRules.model_validate(row["config_json"])


def rule_version(
    session: Session, *, require_persisted: bool = False
) -> tuple[int, ClearanceRules]:
    saved = persisted_rule_version(session)
    if saved is not None:
        return saved
    if require_persisted:
        raise ApiError(
            code="CLEARANCE_RULES_NOT_PERSISTED",
            status_code=409,
            message="清货规则尚未保存到数据库，无法作为已生效规则读取",
        )
    # Legacy risk preview may still use in-memory fallback; GET /rules
    # exposes version 0 and persisted=false until an authorized user saves.
    return 1, ClearanceRules()


def rules_history(session: Session, offset: int, limit: int) -> list[dict]:
    rows = (
        session.execute(
            text("""
        SELECT version, config_json, changed_by, change_reason, changed_at
        FROM biz_clearance_rule_versions ORDER BY version DESC
        OFFSET :offset LIMIT :limit
    """),
            {"limit": limit, "offset": offset},
        )
        .mappings()
        .all()
    )
    result = [dict(row) for row in rows]
    return result


def save_rules(
    session: Session, config: ClearanceRules, expected_version: int, reason: str, actor: str
) -> int:
    # Serialize concurrent saves using the same transaction-scoped advisory lock.
    session.execute(text("SELECT pg_advisory_xact_lock(2406251077)"))
    saved = persisted_rule_version(session)
    if saved is None:
        # First save is expected_version=0, even when saving exact defaults.
        if expected_version != 0:
            invalid()
        new_version = 1
    else:
        current, old = saved
        if current != expected_version:
            invalid()
        if config == old:
            return current
        new_version = current + 1
    session.execute(
        text("""
        INSERT INTO biz_clearance_rule_versions (version, config_json, changed_by, change_reason)
        VALUES (:version, CAST(:config AS jsonb), :actor, :reason)
    """),
        {
            "version": new_version,
            "config": config.model_dump_json(),
            "actor": actor,
            "reason": reason.strip(),
        },
    )
    session.commit()
    return new_version


def _snapshot_row(
    session: Session, listing: ListingManagementCurrentMart, version: int, rules: ClearanceRules
) -> dict:
    facts = facts_for_listing(session, listing)
    risk = evaluate(facts, rules)
    return {
        "source_account_ref": listing.source_account_ref,
        "store_id": listing.store_id,
        "item_id": listing.item_id,
        "msku": listing.msku,
        "sku": listing.local_sku,
        "title": listing.title or listing.local_name,
        "store_name": listing.store_name,
        "owner": listing.owner_ref,
        "currency_code": "USD",
        "rule_version": version,
        "risk": risk.level,
        "reasons": risk.reasons,
        "signals": risk.signals,
        "data_gaps": risk.gaps,
        "metrics": risk.metrics,
    }


def evaluate_and_store(
    session: Session,
    listing: ListingManagementCurrentMart,
    version: int,
    rules: ClearanceRules,
    *,
    risk_session: Session | None = None,
) -> str:
    snapshot = _snapshot_row(session, listing, version, rules)
    target = risk_session if risk_session is not None else session
    target.execute(
        text("""
        INSERT INTO biz_clearance_risk_current
            (source_account_ref,store_id,item_id,level,reasons_json,signals_json,
             metrics_json,data_gaps_json,rule_version,calculated_at)
        VALUES (:account,:store,:item,:level,CAST(:reasons AS jsonb),CAST(:signals AS jsonb),
                CAST(:metrics AS jsonb),CAST(:gaps AS jsonb),:version,now())
        ON CONFLICT (source_account_ref,store_id,item_id) DO UPDATE SET
            level=excluded.level,reasons_json=excluded.reasons_json,
            signals_json=excluded.signals_json,metrics_json=excluded.metrics_json,
            data_gaps_json=excluded.data_gaps_json,rule_version=excluded.rule_version,
            calculated_at=excluded.calculated_at
        WHERE biz_clearance_risk_current.rule_version <= excluded.rule_version
    """),
        {
            "account": listing.source_account_ref,
            "store": listing.store_id,
            "item": listing.item_id,
            "level": snapshot["risk"],
            "reasons": _json(snapshot["reasons"]),
            "signals": _json(snapshot["signals"]),
            "metrics": _json(snapshot["metrics"]),
            "gaps": _json(snapshot["data_gaps"]),
            "version": version,
        },
    )
    return snapshot["risk"]


def recalculate_all(
    session: Session,
    *,
    batch_size: int = 100,
    accounts: frozenset[str] | None = None,
    risk_session: Session | None = None,
) -> dict:
    """Read legacy Listing facts from session; write clearance risks only to risk_session."""
    target = risk_session if risk_session is not None else session
    version, rules = rule_version(target, require_persisted=True)
    examined = 0
    cursor = None
    while True:
        q = (
            select(ListingManagementCurrentMart)
            .order_by(ListingManagementCurrentMart.id)
            .limit(batch_size)
        )
        if cursor is not None:
            q = q.where(ListingManagementCurrentMart.id > cursor)
        if accounts is not None:
            q = q.where(ListingManagementCurrentMart.source_account_ref.in_(accounts))
        rows = list(session.scalars(q).all())
        if not rows:
            break
        for listing in rows:
            evaluate_and_store(session, listing, version, rules, risk_session=target)
            examined += 1
        cursor = rows[-1].id
        target.commit()
        # If an admin saved newer rules mid-run, the old job stops rather than
        # replacing new-version results in later batches.
        latest, _ = rule_version(target, require_persisted=True)
        if latest != version:
            return {"examined": examined, "rule_version": version, "superseded": True}
    return {"examined": examined, "rule_version": version, "superseded": False}


def one_listing(
    session: Session, *, account: str, store: str, item: str, accounts: frozenset[str]
) -> dict:
    scoped(account, accounts)
    listing = find_listing(session, account, store, item)
    if listing is None:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    # Only the new clearance tables are optional during the read-only preview.
    # Unrelated SQL errors still propagate; no fallback on database errors.
    if not risk_read_model_ready(session):
        return read_business_snapshot(session, listing)
    version, rules = rule_version(session)
    snap = _snapshot_row(session, listing, version, rules)
    snap["available"] = current_available(session, listing)
    snap["listing_id"] = str(listing.id)
    snap["price_amount"] = (
        str(listing.sale_price_amount) if listing.sale_price_amount is not None else None
    )
    snap["picture_url"] = listing.picture_url
    return snap


def search_listings(
    session: Session,
    accounts: frozenset[str],
    keyword: str,
    page: int,
    page_size: int,
    *,
    risk_only: bool,
    exact_total: bool = False,
    store_refs: tuple[str, ...] = (),
    owner_names: tuple[str, ...] = (),
    risk_levels: tuple[str, ...] = (),
) -> dict:
    """Use the versioned risk read model for indexed server-side paging.

    Every returned row is validated against current actual WFS availability.
    The separate manual SKU search includes low/unknown eligible Listings.
    """
    # Server DB may legitimately be at 0076 while the UI is newer.
    # The fallback reads only existing MARTs and does not generate risk claims.
    if not risk_read_model_ready(session):
        return search_unassessed_listings(
            session,
            accounts,
            keyword,
            page,
            page_size,
            exact_total=exact_total,
            risk_only_requested=risk_only,
            store_refs=store_refs,
            owner_names=owner_names,
            risk_levels=risk_levels,
        )
    version, rules = rule_version(session)
    if store_refs or owner_names or risk_levels:
        from .filters_v23 import scoped_parts

        scoped_sql, scoped_params = scoped_parts(
            session, accounts, keyword, store_refs, owner_names
        )
        join_risk = """LEFT JOIN biz_clearance_risk_current AS r
          ON r.source_account_ref=l.source_account_ref AND r.store_id=l.store_id
             AND r.item_id=l.item_id"""
        prefix, separator, predicate = scoped_sql.rpartition(" WHERE ")
        if not separator:
            raise RuntimeError("Missing outer WFS filter predicate")
        scoped_sql = f"{prefix} {join_risk} WHERE {predicate}"
        if risk_levels:
            scoped_sql += (
                " AND COALESCE(CASE WHEN r.rule_version=:version THEN r.level"
                " ELSE NULL END, 'unknown') = ANY(:levels)"
            )
            scoped_params.update({"levels": list(risk_levels), "version": version})
        total = int(session.scalar(text("SELECT COUNT(*) " + scoped_sql), scoped_params) or 0)
        ids = (
            session.execute(
                text(
                    "SELECT l.id "
                    + scoped_sql
                    + (
                        " ORDER BY l.store_id, l.item_id, l.source_account_ref, l.id"
                        " LIMIT :limit OFFSET :offset"
                    )
                ),
                {**scoped_params, "limit": page_size + 1, "offset": (page - 1) * page_size},
            )
            .scalars()
            .all()
        )
        has_more = len(ids) > page_size
        selected = ids[:page_size]
        records = []
        if selected:
            found = session.scalars(
                select(ListingManagementCurrentMart).where(
                    ListingManagementCurrentMart.id.in_(selected)
                )
            ).all()
            by_id = {row.id: row for row in found}
            for row_id in selected:
                listing = by_id.get(row_id)
                if listing is None:
                    continue
                available = current_available(session, listing)
                if available is None or available <= 0:
                    continue
                snapshot = _snapshot_row(session, listing, version, rules)
                snapshot.update(
                    {
                        "available": available,
                        "listing_id": str(listing.id),
                        "picture_url": listing.picture_url,
                        "price_amount": str(listing.sale_price_amount)
                        if listing.sale_price_amount is not None
                        else None,
                    }
                )
                records.append(snapshot)
        return {
            "items": records,
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
            "total": total,
            "total_scope": "filtered_wfs_stock_eligible",
            "risk_filter_applied": bool(risk_levels),
            "rule_version": version,
        }

    params = {"accounts": list(accounts), "limit": page_size + 1, "offset": (page - 1) * page_size}
    # WFS eligibility must be checked in SQL BEFORE pagination, independent of
    # clearance risk rules or whether a risk evaluation job has been run.
    where = [
        "l.source_account_ref=ANY(:accounts)",
        "l.wfs_available_quantity > 0",
        "l.wfs_available_quantity = trunc(l.wfs_available_quantity)",
    ]
    risk_join = ""
    if risk_only:
        risk_join = """
        JOIN biz_clearance_risk_current r
          ON r.source_account_ref=l.source_account_ref AND r.store_id=l.store_id
             AND r.item_id=l.item_id
        """
        where.append("r.level IN ('medium','high') AND r.rule_version=:version")
        params["version"] = version
    if keyword.strip():
        where.append(
            "(l.item_id ILIKE :keyword OR l.msku ILIKE :keyword "
            "OR l.local_sku ILIKE :keyword OR l.title ILIKE :keyword)"
        )
        params["keyword"] = "%" + keyword.strip() + "%"
    clause = " AND ".join(where)
    from_and_where = f"FROM mart_listing_management_current l {risk_join} WHERE {clause}"
    total = None
    if exact_total and not risk_only:
        count_params = {key: value for key, value in params.items() if key not in ("limit", "offset")}
        total = int(session.scalar(text("SELECT COUNT(*) " + from_and_where), count_params) or 0)
    ordering = "CASE r.level WHEN 'high' THEN 0 ELSE 1 END," if risk_only else ""
    ids = (
        session.execute(
            text(f"""
        SELECT l.id {from_and_where}
        ORDER BY {ordering}
                 l.store_id,l.item_id,l.source_account_ref,l.id
        LIMIT :limit OFFSET :offset
    """),
            params,
        )
        .scalars()
        .all()
    )
    has_more = len(ids) > page_size
    ordered = list(ids[:page_size])
    records: list[dict] = []
    if ordered:
        found = list(
            session.scalars(
                select(ListingManagementCurrentMart).where(
                    ListingManagementCurrentMart.id.in_(ordered)
                )
            ).all()
        )
        by_id = {x.id: x for x in found}
        for row_id in ordered:
            listing = by_id.get(row_id)
            if listing is None:
                continue
            available = current_available(session, listing)
            if available is None or available <= 0:
                continue
            snapshot = _snapshot_row(session, listing, version, rules)
            if risk_only and snapshot["risk"] not in ("medium", "high"):
                continue
            snapshot.update(
                {
                    "available": available,
                    "listing_id": str(listing.id),
                    "picture_url": listing.picture_url,
                    "price_amount": str(listing.sale_price_amount)
                    if listing.sale_price_amount is not None
                    else None,
                }
            )
            records.append(snapshot)
    return {
        "items": records,
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
        "total": total,
        "total_scope": "all_wfs_stock_eligible" if total is not None else "not_calculated",
        "risk_filter_applied": bool(risk_only),
        "rule_version": version,
    }


def _application_row(
    session: Session, app_id: UUID, accounts: frozenset[str], *, lock: bool = False
) -> dict:
    q = """
        SELECT * FROM biz_clearance_applications WHERE id=:id AND source_account_ref=ANY(:accounts)
    """ + (" FOR UPDATE" if lock else "")
    row = session.execute(text(q), {"id": app_id, "accounts": list(accounts)}).mappings().first()
    if not row:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    return dict(row)


def _get_request_listing(
    session: Session, account: str, store: str, item: str, accounts: frozenset[str]
):
    scoped(account, accounts)
    listing = find_listing(session, account, store, item, lock=True)
    if listing is None:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    if listing.lifecycle_status == "已归档" or session.scalar(
        select(ListingArchiveState.is_archived).where(ListingArchiveState.listing_id == listing.id)
    ):
        # CLEARANCE_EXPLICIT_REJECTION_V57: scoped read, never unarchive.
        archive_reason = session.scalar(
            select(ListingArchiveState.archive_reason).where(
                ListingArchiveState.listing_id == listing.id
            )
        )
        raise ApiError(
            code="CLEARANCE_LISTING_ARCHIVED",
            status_code=409,
            message="该商品已归档，无法申请清货",
            details={"archive_reason": str(archive_reason)[:160]} if archive_reason else None,
        )
    return listing


def submit_application(
    session: Session,
    *,
    account: str,
    store: str,
    item: str,
    accounts: frozenset[str],
    actor: str,
    qty: int,
    reason: str,
    methods: list[str],
    note: str,
    planned_completion_date: str | None = None,
) -> dict:
    if (
        not reason.strip()
        or not 1 <= len(methods) <= 2
        or len(set(methods)) != len(methods)
        or any(m not in {"降价", "广告清货"} for m in methods)
    ):
        invalid(422)
    listing = _get_request_listing(session, account, store, item, accounts)
    available = current_available(session, listing)
    if available is None:
        raise ApiError(
            code="CLEARANCE_STOCK_UNKNOWN",
            status_code=409,
            message="当前无法确认WFS可售库存，请刷新后重试",
        )
    if available < 1:
        raise ApiError(
            code="CLEARANCE_OUT_OF_STOCK", status_code=409, message="当前WFS可售库存为0，无法申请"
        )
    if qty < 1 or qty > available:
        raise ApiError(
            code="CLEARANCE_QUANTITY_EXCEEDED",
            status_code=409,
            message="清货数量超过当前WFS可售库存",
            details={"available": int(available)},
        )
    existing = session.execute(
        text("""
        SELECT id FROM biz_clearance_applications
        WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
          AND status IN ('pending','running') LIMIT 1
    """),
        {"account": account, "store": store, "item": item},
    ).first()
    if existing:
        raise ApiError(
            code="CLEARANCE_DUPLICATE_APPLICATION",
            status_code=409,
            message="该商品已有待审批或执行中的清货申请",
        )
    version, rules = rule_version(session)
    snapshot = _snapshot_row(session, listing, version, rules)
    app_id, approval_id = uuid4(), uuid4()
    timestamp = datetime.now(UTC)
    snapshot["requested_qty"] = qty
    snapshot["methods"] = methods
    snapshot["note"] = note.strip()
    snapshot["planned_completion_date"] = planned_completion_date
    signature = hashlib.sha256(_json(snapshot).encode()).hexdigest()
    session.execute(
        text("""
        INSERT INTO app_approval_requests
          (id,approval_type,business_ref,source_account_ref,applicant_id,title,reason,evidence,
           status,risk_level,snapshot,snapshot_hash,submitted_at,updated_at)
        VALUES (:id,'clearance_request',:business,:account,:actor,:title,:reason,:note,
           'submitted',:risk,CAST(:snapshot AS jsonb),:hash,:now,:now)
    """),
        {
            "id": approval_id,
            "business": str(app_id),
            "account": account,
            "actor": actor,
            "title": f"WFS清货 · {listing.title or listing.item_id}"[:255],
            "reason": reason.strip(),
            "note": note.strip(),
            "risk": snapshot["risk"] if snapshot["risk"] in {"high", "medium"} else "low",
            "snapshot": _json(snapshot),
            "hash": signature,
            "now": timestamp,
        },
    )
    session.execute(
        text("""
        INSERT INTO biz_clearance_applications
          (id, source_account_ref,store_id,item_id,applicant_ref,reason,methods_json,note,
           requested_qty,status,rule_version,risk_at_submission,approval_id,submitted_at)
        VALUES (:id,:account,:store,:item,:actor,:reason,CAST(:methods AS jsonb),:note,
           :qty,'pending',:version,:risk,:approval,:now)
    """),
        {
            "id": app_id,
            "account": account,
            "store": store,
            "item": item,
            "actor": actor,
            "reason": reason.strip(),
            "methods": _json(methods),
            "note": note.strip(),
            "qty": qty,
            "version": version,
            "risk": snapshot["risk"],
            "approval": approval_id,
            "now": timestamp,
        },
    )
    _event(
        session,
        app_id,
        "submitted",
        actor,
        {
            "qty": qty,
            "rule_version": version,
            "risk": snapshot["risk"],
            "planned_completion_date": planned_completion_date,
        },
    )
    _approval_event(
        session, approval_id, "submitted", actor, note, {"clearance_application_id": str(app_id)}
    )
    # Partial unique index closes the concurrent request race; callers receive 409.
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        invalid()
    return {"id": str(app_id), "approval_id": str(approval_id), "status": "pending"}


def cancel_application(
    session: Session, app_id: UUID, accounts: frozenset[str], actor: str, note: str
) -> dict:
    row = _application_row(session, app_id, accounts, lock=True)
    if row["applicant_ref"] != actor:
        denied()
    if row["status"] != "pending":
        invalid()
    session.execute(
        text("""
        UPDATE biz_clearance_applications SET status='cancelled',version=version+1,updated_at=now()
        WHERE id=:id AND status='pending'
    """),
        {"id": app_id},
    )
    session.execute(
        text("""
        UPDATE app_approval_requests SET status='withdrawn',version=version+1,updated_at=now()
        WHERE id=:id AND status='submitted'
    """),
        {"id": row["approval_id"]},
    )
    _event(session, app_id, "cancelled", actor, {"note": note.strip()})
    _approval_event(session, row["approval_id"], "withdrawn", actor, note)
    session.commit()
    return {"id": str(app_id), "status": "cancelled"}


def review_application(
    session: Session,
    app_id: UUID,
    accounts: frozenset[str],
    actor: str,
    decision: str,
    note: str,
    expected_version: int,
) -> dict:
    if decision not in {"approved", "rejected"} or (decision == "rejected" and not note.strip()):
        invalid(422)
    row = _application_row(session, app_id, accounts, lock=True)
    if row["status"] != "pending" or row["version"] != expected_version:
        invalid()
    approval = (
        session.execute(
            text("""
        SELECT version,status FROM app_approval_requests WHERE id=:id FOR UPDATE
    """),
            {"id": row["approval_id"]},
        )
        .mappings()
        .one()
    )
    if approval["status"] != "submitted":
        invalid()
    listing = _get_request_listing(
        session, row["source_account_ref"], row["store_id"], row["item_id"], accounts
    )
    available = current_available(session, listing)
    if available is None:
        invalid()  # Unknown inventory blocks approval, never treated as zero.
    if available == 0:
        status = "stock_closed"
        qty = None
        end = datetime.now(UTC)
        session.execute(
            text("""
            UPDATE biz_clearance_applications
              SET status='stock_closed',finished_at=:now,finish_reason='WFS可售库存归零',
                  version=version+1,updated_at=now()
            WHERE id=:id
        """),
            {"id": app_id, "now": end},
        )
        approval_status = "withdrawn"
    elif decision == "rejected":
        status, qty, approval_status = "rejected", None, "rejected"
        session.execute(
            text("""
            UPDATE biz_clearance_applications
              SET status='rejected',version=version+1,updated_at=now() WHERE id=:id
        """),
            {"id": app_id},
        )
    else:
        approved = min(int(row["requested_qty"]), available)
        status, qty, approval_status = "running", approved, "approved"
        now = datetime.now(UTC)
        session.execute(
            text("""
            UPDATE biz_clearance_applications
              SET status='running',approved_qty=:qty,approved_at=:now,
                  approved_date_la=:day,version=version+1,updated_at=now()
            WHERE id=:id
        """),
            {
                "qty": approved,
                "now": now,
                "day": now.astimezone(
                    __import__("zoneinfo").ZoneInfo("America/Los_Angeles")
                ).date(),
                "id": app_id,
            },
        )
        from .lifecycle_v28 import publish_approved_lifecycle

        publish_approved_lifecycle(
            session, listing=listing, actor=actor, application_id=app_id, read_only_source=False
        )
    session.execute(
        text("""
        UPDATE app_approval_requests
          SET status=:status,reviewed_by=:actor,review_note=:note,
              reviewed_at=now(),updated_at=now(),version=version+1
        WHERE id=:id AND status='submitted'
    """),
        {
            "id": row["approval_id"],
            "status": approval_status,
            "actor": actor,
            "note": note.strip() or None,
        },
    )
    if decision in {"approved", "rejected"} and status != "stock_closed":
        session.execute(
            text("""
            INSERT INTO app_approval_step_decisions
                (id,approval_id,step_number,reviewer_id,decision,note)
            VALUES (:id,:approval,1,:actor,:decision,:note)
        """),
            {
                "id": uuid4(),
                "approval": row["approval_id"],
                "actor": actor,
                "decision": decision,
                "note": note.strip() or None,
            },
        )
    _event(
        session,
        app_id,
        status,
        actor,
        {"approved_qty": qty, "latest_available": available, "decision": decision},
    )
    _approval_event(
        session,
        row["approval_id"],
        approval_status,
        actor,
        note,
        {"approved_qty": qty, "latest_available": available},
    )
    session.commit()
    return {"id": str(app_id), "status": status, "approved_qty": qty, "latest_available": available}


def _sales_since_approval(session: Session, row: dict) -> float | None:
    if row["approved_date_la"] is None:
        return None
    sales_rows = (
        session.execute(
            text("""
        SELECT business_date_la,msku,sales_qty FROM mart_daily_sales_item_day
        WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
          AND business_date_la BETWEEN :start AND :end
        ORDER BY business_date_la,msku
    """),
            {
                "account": row["source_account_ref"],
                "store": row["store_id"],
                "item": row["item_id"],
                "start": row["approved_date_la"],
                "end": la_today(),
            },
        )
        .mappings()
        .all()
    )
    from collections import defaultdict
    from decimal import Decimal

    groups: dict = defaultdict(list)
    for r in sales_rows:
        groups[r["business_date_la"]].append(r)
    total = Decimal("0")
    for _day, records in groups.items():
        if len(records) > 1:
            msuks = [str(v["msku"] or "").strip() for v in records]
            if not all(msuks) or len(msuks) != len(set(msuks)):
                return None  # Ambiguous duplicate MSKU would overstate progress.
        for r in records:
            value = r["sales_qty"]
            if value is None or value < 0:
                return None
            total += value
    # Empty days are not materialized as 0; only real positive observations can
    # cause target completion. This never subtracts return/refund counts.
    return float(total)


def reconcile_application(
    session: Session, app_id: UUID, accounts: frozenset[str], actor: str = "system"
) -> dict:
    row = _application_row(session, app_id, accounts, lock=True)
    if row["status"] not in {"running", "done"}:
        return {"id": str(app_id), "status": row["status"]}
    listing = _get_request_listing(
        session, row["source_account_ref"], row["store_id"], row["item_id"], accounts
    )
    available = current_available(session, listing)
    sold = _sales_since_approval(session, row)
    changed = sold is not None and abs(float(row["sold_qty"]) - sold) > 0.0001
    if changed:
        session.execute(
            text("""
            UPDATE biz_clearance_applications SET sold_qty=:sold,updated_at=now(),version=version+1
            WHERE id=:id
        """),
            {"sold": sold, "id": app_id},
        )
        _event(
            session,
            app_id,
            "sales_reconciled",
            actor,
            {"previous": float(row["sold_qty"]), "sold": sold},
        )
    done = row["status"] == "running" and (
        available == 0 or (sold is not None and sold >= int(row["approved_qty"]))
    )
    if done:
        session.execute(
            text("""
            UPDATE biz_clearance_applications
              SET status='done',finished_at=now(),finished_by=:actor,finish_reason=:reason,
                  version=version+1,updated_at=now() WHERE id=:id AND status='running'
        """),
            {
                "id": app_id,
                "actor": actor,
                "reason": "库存已售罄，无须继续清货" if available == 0 else "实际销量达到审批目标",
            },
        )
        _event(session, app_id, "done", actor, {"available": available, "sold": sold})
    session.commit()
    return {
        "id": str(app_id),
        "status": "done" if done else row["status"],
        "sold_qty": sold if sold is not None else float(row["sold_qty"]),
        "approved_qty": row["approved_qty"],
    }


def complete_application(
    session: Session,
    app_id: UUID,
    accounts: frozenset[str],
    actor: str,
    note: str,
    *,
    can_manage: bool,
) -> dict:
    row = _application_row(session, app_id, accounts, lock=True)
    if row["status"] != "running":
        invalid()
    listing = _get_request_listing(
        session, row["source_account_ref"], row["store_id"], row["item_id"], accounts
    )
    owner_matched = str(listing.owner_ref or "") == actor
    if not owner_matched and actor.isdecimal() and listing.owner_ref:
        owner_matched = bool(
            session.scalar(
                text("""
            SELECT EXISTS (SELECT 1 FROM app_users
              WHERE id=:actor AND username=:owner)
        """),
                {"actor": int(actor), "owner": listing.owner_ref},
            )
        )
    if not can_manage and not owner_matched:
        denied()
    session.execute(
        text("""
        UPDATE biz_clearance_applications
          SET status='done',finished_at=now(),finished_by=:actor,finish_reason=:note,
              version=version+1,updated_at=now() WHERE id=:id
    """),
        {"id": app_id, "actor": actor, "note": note.strip() or "手动完成"},
    )
    _event(session, app_id, "done", actor, {"reason": note.strip() or "手动完成"})
    session.commit()
    # Lifecycle remains 清货期 until the normal lifecycle recalculation; no
    # attempt to restore a remembered previous status.
    return {"id": str(app_id), "status": "done"}


def list_applications(
    session: Session,
    accounts: frozenset[str],
    actor: str,
    *,
    reviewer: bool,
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
) -> dict:
    params = {
        "accounts": list(accounts),
        "actor": actor,
        "reviewer": reviewer,
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    # Viewers can inspect work within their authorized source accounts. Action
    # checks remain independent: only applicant may cancel; reviewer may decide.
    where = "a.source_account_ref=ANY(:accounts)"
    if status is not None:
        if status == "approved":
            where += " AND a.status IN ('running','done')"
        elif status == "pending":
            where += " AND a.status='pending'"
        elif status == "rejected":
            where += " AND a.status='rejected'"
        else:
            where += " AND a.status=:status"
            params["status"] = status
    total = session.scalar(
        text(f"SELECT COUNT(*) FROM biz_clearance_applications a WHERE {where}"), params
    )
    rows = (
        session.execute(
            text(f"""
        SELECT a.*, l.title, l.local_sku, l.msku, l.store_name, l.owner_ref,
               l.wfs_available_quantity, r.level AS current_risk
        FROM biz_clearance_applications a
        LEFT JOIN mart_listing_management_current l
          ON l.source_account_ref=a.source_account_ref AND l.store_id=a.store_id
             AND l.item_id=a.item_id
        LEFT JOIN biz_clearance_risk_current r
          ON r.source_account_ref=a.source_account_ref AND r.store_id=a.store_id
             AND r.item_id=a.item_id
        WHERE {where} ORDER BY a.submitted_at DESC, a.id DESC
        LIMIT :limit OFFSET :offset
    """),
            params,
        )
        .mappings()
        .all()
    )
    saved_fields = application_saved_metadata(session, rows)
    return {
        "items": [
            {
                **dict(row),
                **saved_fields[str(row["id"])],
                "can_review": reviewer and row["status"] == "pending",
            }
            for row in rows
        ],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
    }


def application_detail(
    session: Session, app_id: UUID, accounts: frozenset[str], actor: str, *, reviewer: bool
) -> dict:
    row = _application_row(session, app_id, accounts)
    events = (
        session.execute(
            text("""
        SELECT event_type,actor_ref,detail_json,created_at FROM biz_clearance_events
        WHERE application_id=:id ORDER BY created_at,id
    """),
            {"id": app_id},
        )
        .mappings()
        .all()
    )
    snap = one_listing(
        session,
        account=row["source_account_ref"],
        store=row["store_id"],
        item=row["item_id"],
        accounts=accounts,
    )
    return {"application": row, "current": snap, "events": [dict(v) for v in events]}


def batch_reconcile_running(session: Session, accounts: frozenset[str] | None = None) -> dict:
    params = {}
    q = (
        "SELECT id,source_account_ref FROM biz_clearance_applications "
        "WHERE status='running' ORDER BY id"
    )
    if accounts is not None:
        q = (
            "SELECT id,source_account_ref FROM biz_clearance_applications "
            "WHERE status='running' AND source_account_ref=ANY(:accounts) ORDER BY id"
        )
        params["accounts"] = list(accounts)
    rows = session.execute(text(q), params).mappings().all()
    finished = 0
    for row in rows:
        result = reconcile_application(session, row["id"], frozenset({row["source_account_ref"]}))
        if result["status"] == "done":
            finished += 1
    return {"checked": len(rows), "finished": finished}
