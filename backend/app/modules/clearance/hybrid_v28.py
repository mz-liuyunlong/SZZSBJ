"""Clearance workflow across read-only live business data and isolated local storage.

Production uses the original single-DB transactional service. Local sandbox
never updates any 15432 entity and commits ONLY to the verified 55433 session.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4
import hashlib

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.data_pages.models import ListingArchiveState

from . import service as original
from .lifecycle_v28 import publish_approved_lifecycle


def _source_listing(read: Session, account: str, store: str, item: str, accounts: frozenset[str]):
    original.scoped(account, accounts)
    listing = original.find_listing(read, account, store, item, lock=False)
    if listing is None:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
    if listing.lifecycle_status == "已归档" or read.scalar(
        select(ListingArchiveState.is_archived).where(ListingArchiveState.listing_id == listing.id)
    ):
        # CLEARANCE_EXPLICIT_REJECTION_V57: scoped read, never unarchive.
        archive_reason = read.scalar(select(ListingArchiveState.archive_reason).where(
            ListingArchiveState.listing_id == listing.id))
        raise ApiError(code="CLEARANCE_LISTING_ARCHIVED", status_code=409,
            message="该商品已归档，无法申请清货",
            details={"archive_reason": str(archive_reason)[:160]} if archive_reason else None)
    return listing


def _snapshot(read: Session, listing, version: int) -> dict:
    if not original.risk_read_model_ready(read):
        row = original.read_business_snapshot(read, listing)
    else:
        _, rules = original.rule_version(read)
        row = original._snapshot_row(read, listing, version, rules)
    return dict(row)


def submit_application(read: Session, write: Session, *, account: str, store: str, item: str,
                       accounts: frozenset[str], actor: str, qty: int, reason: str,
                       methods: list[str], note: str, due: str | None = None) -> dict:
    if read is write:
        return original.submit_application(write, account=account, store=store, item=item,
            accounts=accounts, actor=actor, qty=qty, reason=reason, methods=methods, note=note,
            planned_completion_date=due)
    if (not reason.strip() or not 1 <= len(methods) <= 2 or
        len(set(methods)) != len(methods) or any(v not in {"降价", "广告清货"} for v in methods)):
        original.invalid(422)
    listing = _source_listing(read, account, store, item, accounts)
    available = original.current_available(read, listing)
    if available is None:
        raise ApiError(code="CLEARANCE_STOCK_UNKNOWN", status_code=409,
            message="当前无法确认WFS可售库存，请刷新后重试")
    if available < 1:
        raise ApiError(code="CLEARANCE_OUT_OF_STOCK", status_code=409,
            message="当前WFS可售库存为0，无法申请")
    if qty < 1 or qty > available:
        raise ApiError(code="CLEARANCE_QUANTITY_EXCEEDED", status_code=409,
            message="清货数量超过当前WFS可售库存", details={"available": int(available)})
    existing = write.execute(text("""
        SELECT id FROM biz_clearance_applications
        WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
          AND status IN ('pending','running') LIMIT 1 FOR UPDATE
    """), {"account": account, "store": store, "item": item}).first()
    if existing:
        raise ApiError(code="CLEARANCE_DUPLICATE_APPLICATION", status_code=409,
            message="该商品已有待审批或执行中的清货申请")
    version, _ = original.rule_version(write)
    snapshot = _snapshot(read, listing, version)
    snapshot.update({"requested_qty": qty, "methods": methods, "note": note.strip(),
                     "planned_completion_date": due})
    risk = str(snapshot.get("risk") or "unknown")
    app_id, approval_id = uuid4(), uuid4()
    timestamp = datetime.now(UTC)
    snap_text = original._json(snapshot)
    write.execute(text("""
        INSERT INTO app_approval_requests
          (id,approval_type,business_ref,source_account_ref,applicant_id,title,reason,evidence,
           status,risk_level,snapshot,snapshot_hash,submitted_at,updated_at)
        VALUES (:id,'clearance_request',:business,:account,:actor,:title,:reason,:note,
           'submitted',:risk,CAST(:snapshot AS jsonb),:hash,:now,:now)
    """), {"id": approval_id, "business": str(app_id), "account": account,
          "actor": actor, "title": f"WFS清货 · {listing.title or listing.item_id}"[:255],
          "reason": reason.strip(), "note": note.strip(),
          "risk": risk if risk in {"high", "medium"} else "low",
          "snapshot": snap_text, "hash": hashlib.sha256(snap_text.encode()).hexdigest(),
          "now": timestamp})
    write.execute(text("""
        INSERT INTO biz_clearance_applications
          (id,source_account_ref,store_id,item_id,applicant_ref,reason,methods_json,note,
           requested_qty,status,rule_version,risk_at_submission,approval_id,submitted_at)
        VALUES (:id,:account,:store,:item,:actor,:reason,CAST(:methods AS jsonb),:note,
           :qty,'pending',:version,:risk,:approval,:now)
    """), {"id": app_id, "account": account, "store": store, "item": item,
          "actor": actor, "reason": reason.strip(), "methods": original._json(methods),
          "note": note.strip(), "qty": qty, "version": version,
          "risk": risk, "approval": approval_id, "now": timestamp})
    original._event(write, app_id, "submitted", actor,
        {"qty": qty, "rule_version": version, "risk": risk, "planned_completion_date": due})
    original._approval_event(write, approval_id, "submitted", actor, note,
                             {"clearance_application_id": str(app_id)})
    try:
        write.commit()
    except IntegrityError:
        write.rollback()
        original.invalid()
    return {"id": str(app_id), "approval_id": str(approval_id), "status": "pending"}


def list_applications(read: Session, write: Session, accounts: frozenset[str], actor: str,
                      *, reviewer: bool, page: int, page_size: int, status: str | None = None):
    if read is write:
        return original.list_applications(read, accounts, actor, reviewer=reviewer,
                                          page=page, page_size=page_size, status=status)
    params = {"accounts": list(accounts), "offset": (page - 1) * page_size, "limit": page_size}
    where = "source_account_ref=ANY(:accounts)"
    if status:
        if status == "approved":
            where += " AND status IN ('running','done')"
        elif status == "pending":
            where += " AND status='pending'"
        elif status == "rejected":
            where += " AND status='rejected'"
        else:
            where += " AND status=:status"
            params["status"] = status
    total = int(write.scalar(text(f"SELECT COUNT(*) FROM biz_clearance_applications WHERE {where}"), params) or 0)
    rows = write.execute(text(f"""
        SELECT * FROM biz_clearance_applications
        WHERE {where} ORDER BY submitted_at DESC,id DESC
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()
    # CLEARANCE_SNAPSHOT_FALLBACK_V46
    # Snapshots belong to the same authorized application records in 55433.
    # Current Listing facts are read only from the existing 15432 Session.
    snapshots = {}
    if rows:
        approval_ids = [r["approval_id"] for r in rows]
        saved = write.execute(text("""
            SELECT id, snapshot
            FROM app_approval_requests
            WHERE id = ANY(:ids)
              AND approval_type = 'clearance_request'
        """), {"ids": approval_ids}).mappings().all()
        snapshots = {
            str(entry["id"]): entry["snapshot"]
            for entry in saved
        }

    saved_fields = original.application_saved_metadata(write, rows, snapshots=snapshots)
    results = []
    for r in rows:
        data = dict(r)

        account = str(r["source_account_ref"])
        store = str(r["store_id"])
        raw_item = str(r["item_id"])

        parts = raw_item.split("::")
        item = raw_item

        if (
            len(parts) == 3
            and parts[0] == account
            and parts[1] == store
            and parts[2].isdigit()
        ):
            item = parts[2]

        snapshot = snapshots.get(str(r["approval_id"]))
        if not isinstance(snapshot, dict):
            snapshot = {}

        # Never attach a snapshot belonging to another Item or store.
        if (
            str(snapshot.get("source_account_ref", "")) != account
            or str(snapshot.get("store_id", "")) != store
            or str(snapshot.get("item_id", "")) != item
        ):
            snapshot = {}

        listing = original.find_listing(
            read, account, store, item, lock=False
        )

        def current(field, row=listing):
            return getattr(row, field, None) if row else None

        def first(*values):
            for value in values:
                if isinstance(value, str):
                    if value.strip():
                        return value.strip()
                elif value is not None:
                    return value
            return None

        data.update({
            **saved_fields[str(r["id"])],
            "item_id": item,
            "title": first(
                current("local_name"),
                current("product_name"),
                snapshot.get("local_name"),
                snapshot.get("product_name"),
                snapshot.get("title"),
                current("title"),
            ),
            "local_sku": first(
                current("local_sku"),
                snapshot.get("sku"),
                snapshot.get("local_sku"),
            ),
            "msku": first(
                current("msku"),
                snapshot.get("msku"),
            ),
            "store_name": first(
                current("store_name"),
                snapshot.get("store_name"),
            ),
            "owner_ref": first(
                current("owner_ref"),
                snapshot.get("owner_name"),
                snapshot.get("owner_ref"),
                snapshot.get("owner"),
            ),
            "wfs_available_quantity": current(
                "wfs_available_quantity"
            ),
            "current_risk": None,
            "can_review": bool(
                reviewer and r["status"] == "pending"
            ),
        })
        results.append(data)
    return {"items": results, "total": total, "page": page, "page_size": page_size}


def application_detail(read: Session, write: Session, app_id: UUID, accounts: frozenset[str], actor: str,
                       *, reviewer: bool) -> dict:
    if read is write:
        result = original.application_detail(read, app_id, accounts, actor, reviewer=reviewer)
    else:
        row = original._application_row(write, app_id, accounts)
        events = write.execute(text("""
            SELECT event_type,actor_ref,detail_json,created_at FROM biz_clearance_events
            WHERE application_id=:id ORDER BY created_at,id
        """), {"id": app_id}).mappings().all()
        listing = original.find_listing(read, row["source_account_ref"], row["store_id"], row["item_id"], lock=False)
        if listing is None:
            original.invalid()
        current = original.read_business_snapshot(read, listing)
        result = {"application": row, "current": current, "events": [dict(e) for e in events]}
    # Preserve the accepted form's planned completion date in the immutable
    # approval snapshot, without adding a new column to production tables.
    app = dict(result["application"])
    snapshot = write.scalar(text("SELECT snapshot FROM app_approval_requests WHERE id=:id"),
                            {"id": app["approval_id"]})
    if isinstance(snapshot, dict):
        app["planned_completion_date"] = snapshot.get("planned_completion_date")
    # CLEARANCE_APPROVAL_DISPLAY_V55: page display names are business product names,
    # never the (possibly English) Walmart Listing title. Read-only enrichment.
    if read is write:
        listing = original.find_listing(
            read, app["source_account_ref"], app["store_id"], app["item_id"], lock=False
        )
    current = dict(result.get("current") or {})
    saved = snapshot if isinstance(snapshot, dict) else {}
    if any(str(saved.get(k, "")) != str(app.get(k, ""))
           for k in ("source_account_ref", "store_id", "item_id")):
        saved = {}  # never use another store/Item's approval snapshot

    def first_text(*items):
        return next((item.strip() for item in items
                     if isinstance(item, str) and item.strip()), None)

    display_name = first_text(
        current.get("local_name"),
        getattr(listing, "local_name", None) if listing is not None else None,
        current.get("product_name"), saved.get("local_name"),
        saved.get("product_name"),
    )
    display_owner = first_text(
        current.get("owner_name"), current.get("owner"),
        getattr(listing, "owner_ref", None) if listing is not None else None,
        saved.get("owner_name"), saved.get("owner"), app.get("owner_ref"),
    )
    original_listing_title = current.get("title")
    # No fallback to English listing title: an absent product name is unknown.
    current["product_name"] = display_name
    current["title"] = display_name  # compatibility with existing detail drawer
    app["title"] = display_name
    app["product_name"] = display_name
    if original_listing_title and original_listing_title != display_name:
        current["listing_title"] = original_listing_title
    if display_owner:
        current["owner_name"] = display_owner
        current["owner"] = display_owner
        app["owner_ref"] = display_owner
        app["owner_name"] = display_owner
    if listing is not None:
        app.update({
            "local_sku": getattr(listing, "local_sku", None) or app.get("local_sku"),
            "msku": getattr(listing, "msku", None) or app.get("msku"),
            "store_name": getattr(listing, "store_name", None) or app.get("store_name"),
        })
        strike = getattr(listing, "strike_price_amount", None)
        strike_currency = getattr(listing, "strike_price_currency_code", None)
        if strike is not None and strike_currency == "USD":
            current["strike_price_amount"] = str(strike)
            app["strike_price_amount"] = str(strike)
        buybox = getattr(listing, "buybox_status", None)
        if isinstance(buybox, str) and buybox.strip():
            current["buybox_status"] = buybox.strip()
            app["buybox_status"] = buybox.strip()
    metrics = current.get("metrics") if isinstance(current.get("metrics"), dict) else {}
    # Strictly inventory cost = procurement + inbound first leg, not full sale cost.
    cost = metrics.get("inventory_unit_cost_usd")
    if cost is None:
        cost = metrics.get("unit_inventory_cost_usd")
    if cost is not None:
        current["unit_inventory_cost_usd"] = cost
        app["unit_inventory_cost_usd"] = cost
    capital = metrics.get("capital_purchase_first_leg_usd")
    if capital is None and cost is not None and current.get("available") is not None:
        try:
            from decimal import Decimal
            c, q = Decimal(str(cost)), Decimal(str(current["available"]))
            if c.is_finite() and q.is_finite() and c >= 0 and q >= 0:
                capital = float(c*q)
        except (ValueError, TypeError, ArithmeticError):
            pass
    if capital is not None:
        current["capital_purchase_first_leg_usd"] = capital
    # Full sale cost can be used for a margin only when its verified inputs exist.
    full = metrics.get("full_sale_unit_cost_usd")
    price = current.get("price_amount")
    if full is not None and price is not None:
        try:
            from decimal import Decimal
            p, c = Decimal(str(price)), Decimal(str(full))
            if p.is_finite() and c.is_finite() and p >= 0 and c >= 0:
                current["unit_gross_margin_usd"] = float(p-c)
        except (ValueError, TypeError, ArithmeticError):
            pass
    # CLEARANCE_APPROVAL_SNAPSHOT_V56: narrowly expose only verified saved
    # recommendation inputs for the exact account/store/Item. This is an
    # application-time snapshot, never reconstructed from today's rules.
    metrics_saved = saved.get("metrics") if isinstance(saved.get("metrics"), dict) else {}
    if metrics_saved:
        result["submission_suggestion"] = {
            "suggested_qty": metrics_saved.get("suggested_clearance_qty"),
            "rule_floor_price_usd": metrics_saved.get("suggested_floor_price_usd"),
            "snapshot_unit_margin_usd": metrics_saved.get("unit_margin_usd"),
            "snapshot_available_qty": saved.get("available", metrics_saved.get("wfs_available")),
        }
    result["current"] = current
    result["application"] = app
    return result


def review_application(read: Session, write: Session, app_id: UUID, accounts: frozenset[str], actor: str,
                       decision: str, note: str, expected_version: int) -> dict:
    if read is write:
        return original.review_application(read, app_id, accounts, actor,
                                           decision, note, expected_version)
    if decision not in {"approved", "rejected"} or (decision == "rejected" and not note.strip()):
        original.invalid(422)
    row = original._application_row(write, app_id, accounts, lock=True)
    if row["status"] != "pending" or row["version"] != expected_version:
        original.invalid()
    approval = write.execute(text("""
        SELECT version,status FROM app_approval_requests WHERE id=:id FOR UPDATE
    """), {"id": row["approval_id"]}).mappings().one()
    if approval["status"] != "submitted":
        original.invalid()
    listing = _source_listing(read, row["source_account_ref"], row["store_id"], row["item_id"], accounts)
    available = original.current_available(read, listing)
    if available is None:
        original.invalid()
    qty = None
    if available == 0:
        status, approval_status = "stock_closed", "withdrawn"
        write.execute(text("""
            UPDATE biz_clearance_applications
            SET status='stock_closed',finished_at=now(),
                finish_reason='库存已售罄，无须继续清货',version=version+1,updated_at=now()
            WHERE id=:id
        """), {"id": app_id})
    elif decision == "rejected":
        status, approval_status = "rejected", "rejected"
        write.execute(text("""
            UPDATE biz_clearance_applications
            SET status='rejected',version=version+1,updated_at=now() WHERE id=:id
        """), {"id": app_id})
    else:
        qty = min(int(row["requested_qty"]), available)
        status, approval_status = "running", "approved"
        now = datetime.now(UTC)
        write.execute(text("""
            UPDATE biz_clearance_applications
            SET status='running',approved_qty=:qty,approved_at=:now,
                approved_date_la=:day,version=version+1,updated_at=now()
            WHERE id=:id
        """), {"id": app_id, "qty": qty, "now": now,
              "day": now.astimezone(__import__("zoneinfo").ZoneInfo("America/Los_Angeles")).date()})
        publish_approved_lifecycle(write, listing=listing, actor=actor,
                                   application_id=app_id, read_only_source=True)
    write.execute(text("""
        UPDATE app_approval_requests
        SET status=:status,reviewed_by=:actor,review_note=:note,
            reviewed_at=now(),updated_at=now(),version=version+1
        WHERE id=:id AND status='submitted'
    """), {"id": row["approval_id"], "status": approval_status,
          "actor": actor, "note": note.strip() or None})
    if status != "stock_closed":
        write.execute(text("""
            INSERT INTO app_approval_step_decisions
              (id,approval_id,step_number,reviewer_id,decision,note)
            VALUES (:id,:approval,1,:actor,:decision,:note)
        """), {"id": uuid4(), "approval": row["approval_id"],
              "actor": actor, "decision": decision, "note": note.strip() or None})
    original._event(write, app_id, status, actor,
                     {"approved_qty": qty, "latest_available": available, "decision": decision})
    original._approval_event(write, row["approval_id"], approval_status, actor, note,
                              {"approved_qty": qty, "latest_available": available})
    write.commit()
    return {"id": str(app_id), "status": status, "approved_qty": qty,
            "latest_available": available, "lifecycle": "清货期" if status == "running" else None}


def cancel_application(read: Session, write: Session, app_id: UUID, accounts: frozenset[str], actor: str, note: str):
    if read is write:
        return original.cancel_application(read, app_id, accounts, actor, note)
    return original.cancel_application(write, app_id, accounts, actor, note)


def complete_application(read: Session, write: Session, app_id: UUID, accounts: frozenset[str], actor: str,
                         note: str, *, can_manage: bool):
    if read is write:
        return original.complete_application(read, app_id, accounts, actor, note, can_manage=can_manage)
    row = original._application_row(write, app_id, accounts, lock=True)
    if row["status"] != "running":
        original.invalid()
    listing = _source_listing(read, row["source_account_ref"], row["store_id"], row["item_id"], accounts)
    # Match actor's verified login identity, not merely display-name vs ID.
    # Keep the same permission gate as service.complete_application (single DB).
    owner = str(listing.owner_ref or "").strip()
    owner_matched = bool(owner and owner == str(actor))
    if not can_manage and not owner_matched and owner and str(actor).isdecimal():
        owner_matched = bool(read.scalar(text("""
            SELECT EXISTS (SELECT 1 FROM app_users
              WHERE id=:actor AND username=:owner)
        """), {"actor": int(actor), "owner": owner}))
    if not can_manage and not owner_matched:
        original.denied()
    write.execute(text("""
        UPDATE biz_clearance_applications SET status='done',finished_at=now(),
            finished_by=:actor,finish_reason=:reason,version=version+1,updated_at=now()
        WHERE id=:id AND status='running'
    """), {"id": app_id, "actor": actor, "reason": note.strip() or "手动完成"})
    original._event(write, app_id, "done", actor, {"reason": note.strip() or "手动完成"})
    write.commit()
    return {"id": str(app_id), "status": "done"}


def reconcile_application(read: Session, write: Session, app_id: UUID, accounts: frozenset[str]):
    if read is write:
        return original.reconcile_application(read, app_id, accounts)
    row = original._application_row(write, app_id, accounts, lock=True)
    if row["status"] not in {"running", "done"}:
        return {"id": str(app_id), "status": row["status"]}
    listing = _source_listing(read, row["source_account_ref"], row["store_id"], row["item_id"], accounts)
    available = original.current_available(read, listing)
    sold = original._sales_since_approval(read, row)
    if sold is not None and abs(float(row["sold_qty"]) - sold) > 0.0001:
        write.execute(text("""
            UPDATE biz_clearance_applications SET sold_qty=:sold,updated_at=now(),
                version=version+1 WHERE id=:id
        """), {"id": app_id, "sold": sold})
        original._event(write, app_id, "sales_reconciled", "system", {"sold": sold})
    done = row["status"] == "running" and (available == 0 or (sold is not None and sold >= int(row["approved_qty"])))
    if done:
        write.execute(text("""
            UPDATE biz_clearance_applications SET status='done',finished_at=now(),
                finished_by='system',finish_reason=:reason,version=version+1,updated_at=now()
            WHERE id=:id
        """), {"id": app_id, "reason": "库存已售罄，无须继续清货" if available == 0 else "实际销量达到审批目标"})
        original._event(write, app_id, "done", "system", {"available": available, "sold": sold})
    write.commit()
    return {"id": str(app_id), "status": "done" if done else row["status"],
            "sold_qty": sold if sold is not None else float(row["sold_qty"]),
            "approved_qty": row["approved_qty"]}


def lifecycle_overrides(read: Session, write: Session, accounts: frozenset[str]) -> list[dict]:
    if read is write:
        return []  # Single-DB production publishes real MART + manual states.
    rows = write.execute(text("""
        SELECT source_account_ref,store_id,item_id,stage,updated_at
        FROM biz_listing_lifecycle_manual_states
        WHERE source_account_ref=ANY(:accounts) AND stage='清货期'
        ORDER BY source_account_ref,store_id,item_id
    """), {"accounts": list(accounts)}).mappings().all()
    return [dict(row) for row in rows]
