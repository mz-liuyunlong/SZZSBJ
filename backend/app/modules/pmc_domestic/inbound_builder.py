"""Pure IB/SKU/store projection shared by file export and database publication.

Stock is a snapshot, not proof of shipment. Parent IB quantities are never copied
as additive quantities onto multiple store rows.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from app.modules.pmc_domestic.packing_rules import available_good_stock

VERSION = "domestic.inbound.v2"


class InboundDataError(ValueError):
    """A safe code only: source payloads must not leak in exception messages."""


def source_id(value: object, *, required: bool = False) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        if required:
            raise InboundDataError("INBOUND_ID_MISSING")
        return None
    result = str(value).strip()
    if not result or len(result) > 255:
        if required:
            raise InboundDataError("INBOUND_ID_INVALID")
        return None
    return result


def quantity(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise InboundDataError("INBOUND_QUANTITY_INVALID")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and value.strip().lstrip("+-").isdigit():
        result = int(value.strip())
    else:
        raise InboundDataError("INBOUND_QUANTITY_INVALID")
    if not -(2**31) <= result < 2**31:
        raise InboundDataError("INBOUND_QUANTITY_OVERFLOW")
    return result


def id_list(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if not isinstance(value, list):
        raise InboundDataError("INBOUND_ARRAY_INVALID")
    return sorted({source_id(v, required=True) for v in value})


def unique_records(rows: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        if kind == "statement":
            key = str(source_id(row.get("statement_id"), required=True))
        else:
            key = json.dumps([row.get(k) for k in ("wid", "batch_no", "sku", "store_id")])
            source_id(row.get("batch_no"), required=True)
        if key in seen and seen[key] != row:
            raise InboundDataError("INBOUND_DUPLICATE_CONFLICT")
        seen[key] = row
    return list(seen.values())


def arrival(raw: str | None, timezone: str | None) -> tuple[str | None, str | None]:
    if not raw or not timezone:
        return None, None
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
        return parsed.astimezone(UTC).isoformat(), str(
            parsed.astimezone(ZoneInfo("Asia/Taipei")).date()
        )
    except (ValueError, KeyError):
        return None, None


def build_inbound_rows(
    statements: list[dict[str, Any]],
    batches: list[dict[str, Any]],
    *,
    account: str,
    warehouse: str,
    source_timezone: str | None = None,
) -> list[dict[str, Any]]:
    """Build procurement rows; other warehouse/type data never becomes an IB."""
    source_id(account, required=True)
    source_id(warehouse, required=True)
    parents: dict[tuple[str, str], dict[str, Any]] = {}
    for event in unique_records(statements, "statement"):
        if source_id(event.get("wid")) != warehouse or str(event.get("sub_type")) != "2202":
            continue
        ib = str(source_id(event.get("order_sn"), required=True))
        sku = str(source_id(event.get("sku"), required=True))
        p = parents.setdefault(
            (ib, sku),
            {
                "qty": 0,
                "qty_known": True,
                "dates": [],
                "purchases": set(),
                "events": [],
                "name": event.get("product_name") or "",
                "backfill": False,
            },
        )
        q = quantity(event.get("product_qc_num"))
        if q == 0:
            q = quantity(event.get("product_total"))
        if q is None:
            p["qty_known"] = False
        else:
            p["qty"] += q
        if event.get("opt_time"):
            p["dates"].append(str(event["opt_time"]))
        if event.get("ref_order_sn"):
            p["purchases"].add(str(event["ref_order_sn"]))
        p["events"].append(
            {
                k: (
                    source_id(event.get(k))
                    if k in {"statement_id", "order_sn", "sub_type", "opt_time"}
                    else quantity(event.get(k))
                )
                for k in (
                    "statement_id",
                    "order_sn",
                    "sub_type",
                    "product_total",
                    "product_qc_num",
                    "opt_time",
                )
            }
        )

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for batch in unique_records(batches, "batch"):
        if source_id(batch.get("wid")) != warehouse:
            continue
        ib = str(source_id(batch.get("order_sn"), required=True))
        sku = str(source_id(batch.get("sku"), required=True))
        key = (ib, sku)
        if key not in parents:
            # Only an explicit procurement type supports history-window backfill.
            if str(batch.get("type")) not in {"22", "2201", "2202"}:
                continue
            parents[key] = {
                "qty": None,
                "qty_known": False,
                "dates": [],
                "purchases": set(),
                "events": [],
                "name": batch.get("product_name") or "",
                "backfill": True,
            }
        parents[key]["purchases"].update(id_list(batch.get("purchase_order_sns")))
        groups[key].append(batch)

    result: list[dict[str, Any]] = []
    for (ib, sku), parent in sorted(parents.items()):
        by_store: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for batch in groups.get((ib, sku), []):
            store = source_id(batch.get("store_id"))
            by_store[None if store in {None, "0"} else store].append(batch)
        if not by_store:
            by_store[None] = []
        for store, components in sorted(by_store.items(), key=lambda v: v[0] or ""):
            values = [quantity(b.get("balance_num")) for b in components]
            balance = (
                sum(v for v in values if v is not None)
                if (values and all(v is not None for v in values))
                else None
            )
            raw = min(parent["dates"]) if parent["dates"] else None
            date_source = "inventory_statement" if raw else "unknown"
            if not raw and components:
                candidates = [b.get("purchase_in_time") or b.get("batch_time") for b in components]
                raw = min(str(v) for v in candidates if v) if any(candidates) else None
                date_source = "batch_fallback" if raw else "unknown"
            timestamp, business_date = arrival(raw, source_timezone)
            parent_qty = parent["qty"] if parent["qty_known"] else None
            good, locked, available = available_good_stock(components)
            # No direct store-level allocation evidence: even a single current store
            # may be only the remaining part of a historically split inbound order.
            identity = json.dumps([account, warehouse, ib, sku, store], ensure_ascii=False)
            result.append(
                {
                    "id": str(uuid5(NAMESPACE_URL, "szzsbj:inbound:" + identity)),
                    "source_account_ref": account,
                    "source_warehouse_id": warehouse,
                    "warehouse_name": next(
                        (b.get("wh_name") for b in components if b.get("wh_name")), None
                    ),
                    "inbound_order_sn": ib,
                    "sku": sku,
                    "product_name": parent["name"],
                    "store_id": store,
                    "store_name": next(
                        (b.get("store_name") for b in components if b.get("store_name")),
                        None,
                    ),
                    "attribution_status": "known" if store else "unknown",
                    "purchase_order_sns": sorted(parent["purchases"]),
                    "inbound_at_raw": raw,
                    "inbound_at": timestamp,
                    "arrival_business_date": business_date,
                    "arrival_source": date_source,
                    "arrival_date_status": "known" if business_date else "unknown",
                    "total_inbound_qty": None,
                    "parent_inbound_qty": parent_qty,
                    "quantity_scope": "inbound_sku" if parent_qty is not None else "unknown",
                    "balance_num": balance,
                    "good_num": good,
                    "good_locked_num": locked,
                    "available_good_num": available,
                    "inventory_status": "known" if balance is not None else "unknown",
                    "batch_nos": sorted({str(b["batch_no"]) for b in components}),
                    "batch_details": [
                        {
                            "batch_no": str(b["batch_no"]),
                            "store_id": store,
                            "balance_num": quantity(b.get("balance_num")),
                            "source_batch_nos": id_list(b.get("source_batch_no")),
                            "receipt_order_sns": id_list(b.get("delivery_order_sns")),
                        }
                        for b in components
                    ],
                    "history_complete": False,
                    "source_kind": "batch_backfill"
                    if parent["backfill"]
                    else "inventory_statement",
                    "inbound_events": parent["events"],
                    "builder_version": VERSION,
                }
            )
    return result


def with_request_days(row: dict[str, Any], today: date) -> dict[str, Any]:
    date_text = row.get("arrival_business_date")
    return {
        **row,
        "days_in_warehouse": (today - date.fromisoformat(date_text)).days if date_text else None,
    }
