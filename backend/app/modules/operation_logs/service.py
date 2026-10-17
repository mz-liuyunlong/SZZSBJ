"""Copy immutable legacy history into formal logs, and store new edits locally.

Source tables are always read-only; this module never connects to old MySQL.
The only written tables have an ops_ prefix in the *new* PostgreSQL database.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode

WRITE_PERMISSION = "action:operations:log:edit"
WORK_TYPES = frozenset({
    "广告调整", "Listing优化", "销售价调整", "无需调整", "系统日志核对", "其他"
})
MAX_BATCH = 200


def account_mapping(session: Session) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """Ambiguous store or store/item ownership maps to NULL, never guesses."""
    store_rows = session.execute(text("""
        select store_id, source_account_ref
        from dim_lingxing_stores
        where platform_code_raw = '10008'
    """)).all()
    item_rows = session.execute(text("""
        select store_id, item_id, source_account_ref
        from mart_listing_management_current
    """)).all()

    def unique(rows: Any) -> dict[Any, str]:
        found: dict[Any, set[str]] = {}
        for *keys, account in rows:
            key = keys[0] if len(keys) == 1 else tuple(keys)
            found.setdefault(key, set()).add(str(account))
        return {key: next(iter(v)) for key, v in found.items() if len(v) == 1}

    return unique(store_rows), unique(item_rows)


def _account(
    mapping: tuple[dict[str, str], dict[tuple[str, str], str]],
    row: dict[str, Any],
) -> str | None:
    stores, items = mapping
    return items.get((str(row["store_id"]), str(row["item_id"]))) or stores.get(
        str(row["store_id"])
    )


def _import_batch(
    session: Session,
    *,
    kind: str,
    rows: list[dict[str, Any]],
    mapping: tuple[dict[str, str], dict[tuple[str, str], str]],
) -> int:
    if kind == "system":
        data = [{
            "id": r["id"], "account": _account(mapping, r), "day": r["event_date"],
            "store": r["store_id"], "item": r["item_id"], "msku": r["msku"],
            "action": r["action_type"], "object": r["object_name"],
            "content": r["log_content"], "highlight": bool(r["highlight"]),
            "verify": r["verify_status"], "updated": r["updated_at"],
            "detected": r["detected_at"],
        } for r in rows]
        result = session.execute(text("""
            insert into ops_system_operation_events
                (legacy_id, source_account_ref, event_date, store_id, item_id, msku,
                 action_type, object_name, log_content, highlight, verify_status,
                 source_updated_at, detected_at)
            values (:id, :account, :day, :store, :item, :msku,
                    :action, :object, :content, :highlight, :verify,
                    :updated, :detected)
            on conflict (legacy_id) do update set
                source_account_ref = excluded.source_account_ref,
                event_date = excluded.event_date,
                store_id = excluded.store_id,
                item_id = excluded.item_id,
                msku = excluded.msku,
                action_type = excluded.action_type,
                object_name = excluded.object_name,
                log_content = excluded.log_content,
                highlight = excluded.highlight,
                verify_status = excluded.verify_status,
                source_updated_at = excluded.source_updated_at,
                detected_at = excluded.detected_at
            where (
                ops_system_operation_events.source_updated_at is distinct from
                excluded.source_updated_at
                or ops_system_operation_events.source_account_ref is distinct from
                excluded.source_account_ref
                or ops_system_operation_events.log_content is distinct from
                excluded.log_content
            )
        """), data)
    else:
        data = [{
            "id": r["id"], "account": _account(mapping, r),
            "day": r["log_date"], "store": r["store_id"], "item": r["item_id"],
            "msku": r["msku"], "content": r["log_content"] or "",
            "updated": r["updated_at"],
        } for r in rows]
        result = session.execute(text("""
            insert into ops_manual_operation_logs
                (legacy_id, source_kind, source_account_ref, log_date,
                 store_id, item_id, msku, log_content, source_updated_at)
            values (:id, 'legacy', :account, :day,
                    :store, :item, :msku, :content, :updated)
            on conflict (legacy_id) do update set
                source_account_ref = excluded.source_account_ref
            where ops_manual_operation_logs.source_account_ref is null
              and excluded.source_account_ref is not null
        """), data)
    return int(result.rowcount or 0)


def import_history(
    session: Session, *, commit: bool = False, batch_size: int = 250,
    include_manual: bool = True, incremental: bool = False,
) -> dict[str, int]:
    """A dry-run by default. Full run includes both source types.

    Ten-minute sync reads new IDs + a seven-day correction window.
    Daily reconciliation re-reads the whole event mirror for late corrections.
    """
    if not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    sources = [
        ("system", "legacy_mirror.event_ops_action_log"),
    ]
    if include_manual and not incremental:
        sources.append(("manual", "legacy_mirror.biz_product_operation_log"))
    mapping = account_mapping(session)
    max_id = 0
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=7)
    if incremental:
        try:
            max_id = int(session.scalar(text(
                "select coalesce(max(legacy_id), 0) from ops_system_operation_events"
            )) or 0)
        except Exception:
            session.rollback()
            raise RuntimeError("Formal event table is missing; deploy migration first") from None

    results = {"system_scanned": 0, "manual_scanned": 0,
               "unresolved": 0, "affected": 0}
    for kind, source in sources:
        last_id = 0
        while True:
            condition = (" and (id > :max_id or updated_at >= :since)"
                         if incremental else "")
            rows = session.execute(
                text(f"select * from {source} where id > :last"
                     f"{condition} order by id limit :limit"),
                {"last": last_id, "max_id": max_id,
                 "since": since, "limit": batch_size},
            ).mappings().all()
            if not rows:
                break
            data = [dict(r) for r in rows]
            results[f"{kind}_scanned"] += len(data)
            results["unresolved"] += sum(_account(mapping, r) is None for r in data)
            if commit:
                try:
                    results["affected"] += _import_batch(
                        session, kind=kind, rows=data, mapping=mapping
                    )
                    session.commit()
                except Exception:
                    session.rollback()
                    raise
            last_id = int(data[-1]["id"])
    return results


def _identity(
    session: Session, *, accounts: frozenset[str], account: str,
    store: str, item: str, msku: str,
) -> None:
    if account not in accounts:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    found = session.scalar(text("""
        select 1 from mart_listing_management_current
        where source_account_ref = :account and store_id = :store
          and item_id = :item and coalesce(msku, '') = :msku limit 1
    """), {"account": account, "store": store, "item": item, "msku": msku})
    if not found:
        raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)


def _log_key(
    *, account: str, day: date, store: str, item: str, msku: str
) -> dict[str, object]:
    return {"account": account, "day": day, "store": store, "item": item,
            "msku": msku}


def read_detail(
    session: Session, *, accounts: frozenset[str], account: str, day: date,
    store: str, item: str, msku: str,
) -> dict[str, Any]:
    _identity(session, accounts=accounts, account=account, store=store,
              item=item, msku=msku)
    key = _log_key(account=account, day=day, store=store, item=item, msku=msku)
    events = session.execute(text("""
        select legacy_id, action_type, object_name, log_content,
               highlight, verify_status, detected_at
        from ops_system_operation_events
        where source_account_ref = :account and event_date = :day
          and store_id = :store and item_id = :item and msku = :msku
        order by legacy_id
    """), key).mappings().all()
    manuals = session.execute(text("""
        select legacy_id, source_kind, log_content, work_type, status, revision
        from ops_manual_operation_logs
        where source_account_ref = :account and log_date = :day
          and store_id = :store and item_id = :item and msku = :msku
        order by (source_kind = 'manual') desc, id desc
    """), key).mappings().all()
    current = next(iter(manuals), None)
    return {
        "system_events": [dict(r) for r in events],
        "system_operation_log": "\n".join(str(e["log_content"]) for e in events),
        "system_highlight": any(e["highlight"] for e in events),
        "operation_log": str(current["log_content"]) if current else "",
        "work_type": str(current["work_type"]) if current else "其他",
        "status": str(current["status"]) if current else "draft",
        "revision": int(current["revision"]) if current and
        current["source_kind"] == "manual" else 0,
        "legacy_history": [dict(m) for m in manuals if m["source_kind"] == "legacy"],
    }


def _save_one(
    session: Session, *, accounts: frozenset[str], account: str, day: date,
    store: str, item: str, msku: str, content: str, work_type: str,
    status: str, revision: int, actor: str,
) -> int:
    _identity(session, accounts=accounts, account=account, store=store,
              item=item, msku=msku)
    if work_type not in WORK_TYPES or status not in {"draft", "submitted"}:
        raise ApiError(code="OPERATION_LOG_INVALID_VALUES", status_code=422)
    if status == "submitted" and not content.strip():
        raise ApiError(code="OPERATION_LOG_CONTENT_REQUIRED", status_code=422)
    params = {**_log_key(account=account, day=day, store=store,
                         item=item, msku=msku),
              "content": content, "work_type": work_type,
              "status": status, "revision": revision, "actor": actor}
    if revision == 0:
        statement = """
            insert into ops_manual_operation_logs
                (source_kind, source_account_ref, log_date, store_id, item_id,
                 msku, log_content, work_type, status, actor_ref, revision)
            values ('manual', :account, :day, :store, :item, :msku,
                    :content, :work_type, :status, :actor, 1)
            on conflict (source_account_ref, log_date, store_id, item_id, msku)
            where source_kind = 'manual' do nothing
            returning revision
        """
    else:
        statement = """
            update ops_manual_operation_logs
            set log_content = :content, work_type = :work_type,
                status = :status, actor_ref = :actor,
                revision = revision + 1, updated_at = now()
            where source_kind = 'manual' and source_account_ref = :account
              and log_date = :day and store_id = :store and item_id = :item
              and msku = :msku and revision = :revision
            returning revision
        """
    result = session.scalar(text(statement), params)
    if result is None:
        raise ApiError(code="OPERATION_LOG_EDIT_CONFLICT", status_code=409)
    return int(result)


def save_batch(
    session: Session, *, accounts: frozenset[str], rows: list[dict[str, Any]],
    actor: str,
) -> list[int]:
    """All-or-nothing batch; no partial saves on stale revision or scope failure."""
    if not 1 <= len(rows) <= MAX_BATCH:
        raise ApiError(code="OPERATION_LOG_BATCH_SIZE", status_code=422)
    identities = [(r["account"], r["day"], r["store"], r["item"], r["msku"])
                  for r in rows]
    if len(set(identities)) != len(identities):
        raise ApiError(code="OPERATION_LOG_DUPLICATE_ROW", status_code=422)
    try:
        revisions = [
            _save_one(session, accounts=accounts, actor=actor, **row)
            for row in rows
        ]
        session.commit()
        return revisions
    except Exception:
        session.rollback()
        raise


def save_link(
    session: Session, *, accounts: frozenset[str], account: str, store: str,
    item: str, msku: str, entry_type: str, name: str, url: str,
    note: str, actor: str,
) -> None:
    _identity(session, accounts=accounts, account=account, store=store,
              item=item, msku=msku)
    if entry_type not in {"keyword", "ad"}:
        raise ApiError(code="OPERATION_LOG_INVALID_LINK", status_code=422)
    try:
        session.execute(text("""
            insert into ops_operation_log_links
                (source_account_ref, store_id, item_id, entry_type,
                 entry_name, entry_url, note, actor_ref)
            values (:account, :store, :item, :entry_type, :name, :url, :note, :actor)
            on conflict (source_account_ref, store_id, item_id, entry_type)
            do update set entry_name = excluded.entry_name,
                          entry_url = excluded.entry_url,
                          note = excluded.note, actor_ref = excluded.actor_ref,
                          updated_at = now()
        """), {"account": account, "store": store, "item": item,
               "entry_type": entry_type, "name": name, "url": url,
               "note": note, "actor": actor})
        session.commit()
    except Exception:
        session.rollback()
        raise
