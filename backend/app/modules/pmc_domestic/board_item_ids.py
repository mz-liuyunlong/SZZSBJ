"""ItemID for one inbound row: remark digits for that store, then the store listing."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.orm import Session

from app.modules.pmc_domestic.inbound_schemas import ItemIdentity
from app.modules.pmc_purchase.remark_item_ids import (
    extract_remark_item_ids,
    validated_remark_item_ids,
)

LINE_TABLE = "ods_lingxing_purchase_order_items"
PLAN_TABLE = "ods_lingxing_purchase_plans"
LISTING_TABLE = "dim_walmart_listings"
type Listing = tuple[str, str, str | None, str | None]


class BoardItemRow(Protocol):
    source_account_ref: str
    sku: str
    store_id: str | None
    purchase_order_sns: list[str]
    item_identities: list
    identity_status: str


def resolve_store_item_ids(
    *,
    store_id: str | None,
    sku: str,
    lines: Sequence[tuple[str | None, Sequence[str | None], Sequence[str]]],
    plans: dict[str, tuple[str | None, Sequence[str | None]]],
    listings: Sequence[Listing],
) -> list[tuple[str, str | None]]:
    """ItemIDs for one inbound row.

    ``lines`` are ``(store_id, remark_texts, plan_sns)`` for this purchase order and SKU.
    ``plans`` map a plan number to ``(store_id, remark_texts)``.
    ``listings`` are ``(store_id, item_id, local_sku, gtin)`` for this SKU.
    A known store keeps only that store. An empty store is filled only when the SKU is listed
    on exactly one store.
    """

    row_store = _store(store_id)
    same_sku = [item for item in listings if (item[2] or "").strip() == sku]
    remark_ids = _remark_ids(row_store, lines, plans)
    if row_store:
        remark_ids = validated_remark_item_ids(
            [], remark_ids, _ids_for_store(same_sku, row_store)
        )
        if remark_ids:
            return [
                (
                    item_id,
                    _gtin(same_sku, row_store, item_id)
                    if _listed(same_sku, row_store, item_id)
                    else None,
                )
                for item_id in remark_ids
            ]
        chosen = _ids_for_store(same_sku, row_store)
        return [(item_id, _gtin(same_sku, row_store, item_id)) for item_id in chosen]
    remark_hits = [item for item_id in remark_ids for item in same_sku if item[1] == item_id]
    if remark_hits:
        return _single_store(remark_hits, same_sku)
    return _single_store(same_sku, same_sku)


def attach_board_item_ids(
    session: Session, rows: Sequence[BoardItemRow], accounts: frozenset[str]
) -> None:
    """Fill ItemID and GTIN for the current page. Nothing is written back to a table."""

    pairs = {
        (row.source_account_ref, sn, row.sku)
        for row in rows
        if row.source_account_ref in accounts and row.sku
        for sn in row.purchase_order_sns or []
        if sn
    }
    lines_by_key, plans_by_key = _load_remarks(session, pairs)
    listings = _load_listings(
        session,
        {account for account, _, _ in pairs},
        {sku for _, _, sku in pairs},
    )
    for row in rows:
        found: list[tuple[str, str | None]] = []
        if row.source_account_ref in accounts and row.sku:
            for sn in row.purchase_order_sns or []:
                key = (row.source_account_ref, sn, row.sku)
                for item_id, gtin in resolve_store_item_ids(
                    store_id=row.store_id,
                    sku=row.sku,
                    lines=lines_by_key.get(key, ()),
                    plans=plans_by_key.get(row.source_account_ref, {}),
                    listings=listings.get((row.source_account_ref, row.sku), ()),
                ):
                    if item_id not in {item for item, _gtin in found}:
                        found.append((item_id, gtin))
        row.item_identities = [ItemIdentity(item_id=item_id, gtin=gtin) for item_id, gtin in found]
        row.identity_status = "resolved" if len(found) == 1 else "multiple" if found else "missing"


def _remark_ids(
    row_store: str | None,
    lines: Sequence[tuple[str | None, Sequence[str | None], Sequence[str]]],
    plans: dict[str, tuple[str | None, Sequence[str | None]]],
) -> list[str]:
    seen: list[str] = []
    for line_store, texts, plan_sns in lines:
        store = _store(line_store)
        if row_store and store not in {None, row_store}:
            continue
        chosen: list[tuple[str | None, Sequence[str | None]]] = []
        for plan_sn in plan_sns:
            plan = plans.get(plan_sn)
            if plan is None:
                continue
            plan_store = _store(plan[0])
            if row_store and plan_store not in {None, row_store}:
                continue
            if not row_store and store and plan_store and plan_store != store:
                continue
            chosen.append(plan)
        if row_store and store is None and plan_sns and not chosen:
            continue
        parts: list[str | None] = []
        if row_store is None or store == row_store or chosen:
            parts.extend(texts)
        for plan in chosen:
            parts.extend(plan[1])
        for item_id in extract_remark_item_ids(parts):
            _append(seen, item_id)
    return seen


def _single_store(
    pool: Sequence[Listing], listings: Sequence[Listing]
) -> list[tuple[str, str | None]]:
    stores = {_store(item[0]) for item in pool}
    stores.discard(None)
    if len(stores) != 1:
        return []
    only = next(iter(stores))
    ordered: list[str] = []
    for item in pool:
        if _store(item[0]) == only:
            _append(ordered, item[1])
    return [(item_id, _gtin(listings, only, item_id)) for item_id in ordered]


def _load_remarks(
    session: Session, pairs: set[tuple[str, str, str]]
) -> tuple[
    dict[tuple[str, str, str], list[tuple[str | None, list[str | None], list[str]]]],
    dict[str, dict[str, tuple[str | None, list[str | None]]]],
]:
    bind = session.get_bind()
    inspector = inspect(bind)
    if not pairs or not inspector.has_table(LINE_TABLE):
        return {}, {}
    accounts = list({account for account, _, _ in pairs})
    order_sns = list({sn for _, sn, _ in pairs})
    skus = list({sku for _, _, sku in pairs})
    line_rows = session.execute(
        text(
            "select source_account_ref, order_sn, sku, item_id, plan_sn, sid, remark, "
            "payload_json, is_delete, observed_at, id "
            f"from {LINE_TABLE} "
            "where source_account_ref in :accounts and order_sn in :orders and sku in :skus"
        ).bindparams(
            bindparam("accounts", expanding=True),
            bindparam("orders", expanding=True),
            bindparam("skus", expanding=True),
        ),
        {"accounts": accounts, "orders": order_sns, "skus": skus},
    ).all()
    latest_lines: dict[tuple[str, str, str], tuple] = {}
    for row in line_rows:
        payload = _payload(row.payload_json)
        key = (row.source_account_ref, row.order_sn, str(row.item_id))
        version = _version(payload, row.observed_at, row.id)
        current = latest_lines.get(key)
        if current is None or version > current[0]:
            latest_lines[key] = (version, row, payload)
    grouped: dict[tuple[str, str, str], list[tuple[str | None, list[str | None], list[str]]]] = {}
    plan_sns: set[tuple[str, str]] = set()
    for (account, order_sn, _), (_, row, payload) in latest_lines.items():
        if _deleted(row.is_delete):
            continue
        key = (account, order_sn, row.sku)
        if key not in pairs:
            continue
        linked = _plan_sns(row.plan_sn, payload)
        grouped.setdefault(key, []).append(
            (row.sid, [row.remark, _text(payload, "item_purchase_remark")], linked)
        )
        plan_sns.update((account, plan_sn) for plan_sn in linked)
    plans = _load_plans(session, inspector, plan_sns)
    return grouped, plans


def _load_plans(
    session: Session, inspector, plan_keys: set[tuple[str, str]]
) -> dict[str, dict[str, tuple[str | None, list[str | None]]]]:
    if not plan_keys or not inspector.has_table(PLAN_TABLE):
        return {}
    accounts = list({account for account, _ in plan_keys})
    plan_sns = list({plan_sn for _, plan_sn in plan_keys})
    rows = session.execute(
        text(
            "select source_account_ref, plan_sn, sid, remark, plan_remark, "
            "payload_json, observed_at, id "
            f"from {PLAN_TABLE} "
            "where source_account_ref in :accounts and plan_sn in :plans"
        ).bindparams(bindparam("accounts", expanding=True), bindparam("plans", expanding=True)),
        {"accounts": accounts, "plans": plan_sns},
    ).all()
    latest: dict[tuple[str, str], tuple] = {}
    for row in rows:
        payload = _payload(row.payload_json)
        key = (row.source_account_ref, row.plan_sn)
        version = _version(payload, row.observed_at, row.id)
        current = latest.get(key)
        if current is None or version > current[0]:
            latest[key] = (version, row, payload)
    found: dict[str, dict[str, tuple[str | None, list[str | None]]]] = {}
    for (account, plan_sn), (_, row, payload) in latest.items():
        if (account, plan_sn) not in plan_keys:
            continue
        found.setdefault(account, {})[plan_sn] = (
            row.sid,
            [row.remark, row.plan_remark, _text(payload, "item_purchase_remark")],
        )
    return found


def _load_listings(
    session: Session, accounts: set[str], skus: set[str]
) -> dict[tuple[str, str], list[Listing]]:
    bind = session.get_bind()
    if not accounts or not skus or not inspect(bind).has_table(LISTING_TABLE):
        return {}
    rows = session.execute(
        text(
            "select source_account_ref, store_id, item_id, local_sku, gtin "
            f"from {LISTING_TABLE} "
            "where source_account_ref in :accounts and local_sku in :skus"
        ).bindparams(bindparam("accounts", expanding=True), bindparam("skus", expanding=True)),
        {"accounts": list(accounts), "skus": list(skus)},
    ).all()
    found: dict[tuple[str, str], list[Listing]] = {}
    for row in rows:
        if not row.local_sku or not row.store_id or not row.item_id:
            continue
        found.setdefault((row.source_account_ref, row.local_sku), []).append(
            (str(row.store_id), str(row.item_id), row.local_sku, row.gtin)
        )
    return found


def _plan_sns(plan_sn: object, payload: dict) -> list[str]:
    found: list[str] = []
    primary = str(plan_sn).strip() if isinstance(plan_sn, str) else ""
    if primary:
        found.append(primary)
    related = payload.get("relation_purchase_plan")
    if isinstance(related, list):
        for entry in related:
            value = entry
            if isinstance(entry, dict):
                value = entry.get("plan_sn") or entry.get("sn")
            text_value = value.strip() if isinstance(value, str) else ""
            if text_value and text_value not in found:
                found.append(text_value)
    return found


def _listed(listings: Sequence[Listing], store_id: str, item_id: str) -> bool:
    return any(_store(item[0]) == store_id and item[1] == item_id for item in listings)


def _ids_for_store(listings: Sequence[Listing], store_id: str) -> list[str]:
    seen: list[str] = []
    for store, item_id, _, _gtin in listings:
        if _store(store) == store_id:
            _append(seen, item_id)
    return seen


def _gtin(listings: Sequence[Listing], store_id: str, item_id: str) -> str | None:
    for store, listed_id, _, gtin in listings:
        if _store(store) != store_id or listed_id != item_id:
            continue
        if isinstance(gtin, str) and gtin.strip():
            return gtin.strip()
    return None


def _payload(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _text(payload: dict, key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _version(payload: dict, observed_at: object, row_id: object) -> tuple[str, str, str]:
    raw = payload.get("update_time")
    update = str(raw).strip() if isinstance(raw, str | int) and not isinstance(raw, bool) else ""
    observed = "" if observed_at is None else str(observed_at)
    identity = "" if row_id is None else str(row_id)
    return (update, observed, identity)


def _deleted(value: object) -> bool:
    return value in {1, "1"}


def _store(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text or text == "0":
        return None
    return text


def _append(seen: list[str], item_id: str) -> None:
    if item_id and item_id not in seen:
        seen.append(item_id)
