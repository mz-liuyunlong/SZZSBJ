"""Import Walmart after-sales return/refund items from saved returnOrder/list JSON.

Current rules:
- one counted return order item = one row in after_sales_refund_items
- items[].currentRefundStatus NOT_REFUNDED / CANCELLED are excluded from refund
- provider refund amount comes directly from items[].lineTotalAmount (no quantity multiply)
- every status except NOT_REFUNDED / CANCELLED is an effective refund;
  REFUND_COMPLETED is descriptive only and does not gate refund-loss accounting
- store_id + msku matches listing item_id when a listing-like table is available
- local_sku matches cost from mart_daily_sales_item_day as the current cost snapshot source
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_database_url, get_settings  # noqa: E402

PLATFORM_CODE = "walmart"
REFUND_COMPLETED = "REFUND_COMPLETED"
EXCLUDED_REFUND_STATUSES = frozenset({"NOT_REFUNDED", "CANCELLED"})

RETURN_RAW_POLICY_KEY = (
    "lingxing-data-pages-walmart-return-order-list-v1"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    source_group = parser.add_mutually_exclusive_group(
        required=True
    )
    source_group.add_argument(
        "--input-json",
        help="Saved returnOrder/list response JSON file",
    )
    source_group.add_argument(
        "--from-ods",
        action="store_true",
        help=(
            "Read Walmart returnOrder/list RAW directly "
            "from ods_api_raw_blobs."
        ),
    )

    parser.add_argument(
        "--source-account-ref",
        default="primary",
    )
    parser.add_argument(
        "--target-date",
        default="2026-09-01",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    return parser.parse_args()


def as_json(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def unwrap_response(payload: Any) -> dict[str, Any]:
    """Accept direct API response or wrapper with body / compactBody / response_json."""

    payload = as_json(payload)

    if not isinstance(payload, dict):
        raise ValueError("input JSON root is not an object")

    for key in ("body", "compactBody", "compact_body", "response_json", "responseJson", "data"):
        value = payload.get(key)
        parsed = as_json(value)
        if isinstance(parsed, dict) and find_return_list(parsed) is not None:
            return parsed

    if find_return_list(payload) is not None:
        return payload

    raise ValueError("could not locate returnOrder/list response body")


def find_return_list(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Find body.data.list or similar list payload."""

    data = payload.get("data")
    if isinstance(data, dict):
        rows = data.get("list") or data.get("records") or data.get("items")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]

    rows = payload.get("list") or payload.get("records") or payload.get("items")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]

    return None


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def filter_payload_for_target_date(
    payload: dict[str, Any],
    target_date: date,
) -> dict[str, Any]:
    """Keep return orders whose returnOrderDate is target_date."""

    return_orders = find_return_list(payload)

    if return_orders is None:
        raise ValueError("return list not found")

    selected: list[dict[str, Any]] = []

    for order in return_orders:
        return_order_at = parse_datetime(
            order.get("returnOrderDate")
        )

        if return_order_at is None:
            continue

        if return_order_at.date() != target_date:
            continue

        selected.append(order)

    return {
        "data": {
            "list": selected,
        }
    }


def load_payload_from_ods(
    conn: Connection,
    target_date: date,
) -> dict[str, Any]:
    """Load latest Walmart returnOrder rows from DATA-PAGES ODS."""

    orders = conn.execute(
        text(
            """
            with raw_orders as (
                select
                    b.received_at,
                    x.order_json,
                    nullif(
                        trim(
                            x.order_json ->> 'returnOrderId'
                        ),
                        ''
                    ) as return_id
                from ods_api_raw_blobs b
                join gov_raw_retention_policies p
                  on p.id = b.retention_policy_id
                cross join lateral jsonb_array_elements(
                    case
                        when jsonb_typeof(
                            b.payload_json #> '{data,list}'
                        ) = 'array'
                        then
                            b.payload_json #> '{data,list}'
                        else
                            '[]'::jsonb
                    end
                ) as x(order_json)
                where p.policy_key = :policy_key
            ),
            latest_orders as (
                select distinct on (return_id)
                    return_id,
                    received_at,
                    order_json
                from raw_orders
                where return_id is not null
                order by
                    return_id,
                    received_at desc
            )
            select order_json
            from latest_orders
            order by return_id
            """
        ),
        {
            "policy_key": RETURN_RAW_POLICY_KEY,
        },
    ).scalars().all()

    payload = {
        "data": {
            "list": [
                order
                for order in orders
                if isinstance(order, dict)
            ]
        }
    }

    return filter_payload_for_target_date(
        payload,
        target_date,
    )


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def decimal_or_zero(value: Any) -> Decimal:
    return decimal_or_none(value) or Decimal("0")


def quantity_from_display(value: Any) -> Decimal:
    """Parse quantityDisplay. Keep first numeric token only."""

    if value is None:
        return Decimal("0")
    raw = str(value).strip()
    if not raw:
        return Decimal("0")

    number = []
    started = False
    for char in raw:
        if char.isdigit() or char == ".":
            number.append(char)
            started = True
        elif started:
            break

    if not number:
        return Decimal("0")
    return decimal_or_zero("".join(number))


def normalize_store_id(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    return raw or None


def item_hash(order: dict[str, Any], item: dict[str, Any]) -> str:
    payload = {
        "return_order_id": order.get("returnOrderId"),
        "store_id": order.get("storeId"),
        "item": item,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def find_listing_source_table(conn: Connection) -> str | None:
    """Auto-pick a listing-like table with store_id, msku, item_id."""

    rows = (
        conn.execute(
            text(
                """
            select table_name
            from information_schema.columns
            where table_schema = 'public'
              and column_name in ('store_id', 'msku', 'item_id')
            group by table_name
            having count(distinct column_name) = 3
            order by
              case when table_name ilike '%listing%' then 0 else 1 end,
              table_name
            """
            )
        )
        .scalars()
        .all()
    )

    for table_name in rows:
        if table_name == "after_sales_refund_items":
            continue
        return str(table_name)

    return None


def build_listing_map(
    conn: Connection, table_name: str | None
) -> dict[tuple[str, str], dict[str, Any]]:
    if not table_name:
        return {}

    rows = (
        conn.execute(
            text(
                f"""
            select
                cast(store_id as text) as store_id,
                cast(msku as text) as msku,
                max(cast(item_id as text)) as item_id,
                count(distinct cast(item_id as text)) as item_id_count
            from {table_name}
            where store_id is not null
              and msku is not null
              and item_id is not null
            group by cast(store_id as text), cast(msku as text)
            """
            )
        )
        .mappings()
        .all()
    )

    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        result[(row["store_id"], row["msku"])] = {
            "item_id": row["item_id"],
            "status": "matched" if int(row["item_id_count"]) == 1 else "conflict",
        }

    return result


def build_cost_map(conn: Connection, target_date: date) -> dict[str, dict[str, Any]]:
    """Use Daily Sales MART cost fields as the first import cost snapshot source."""

    rows = (
        conn.execute(
            text(
                """
            select distinct on (local_sku)
                local_sku,
                purchase_cost_unit_cny,
                first_leg_cost_unit_cny,
                wfs_fee_unit_amount,
                storage_fee_unit_amount,
                exchange_rate,
                business_date_la
            from mart_daily_sales_item_day
            where local_sku is not null
              and business_date_la <= :target_date
            order by local_sku, business_date_la desc
            """
            ),
            {"target_date": target_date},
        )
        .mappings()
        .all()
    )

    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        local_sku = str(row["local_sku"])

        purchase_cost = decimal_or_none(row["purchase_cost_unit_cny"])
        first_leg_cost = decimal_or_none(row["first_leg_cost_unit_cny"])
        wfs_fee = decimal_or_none(row["wfs_fee_unit_amount"])
        storage_fee = decimal_or_none(row["storage_fee_unit_amount"])
        exchange_rate = decimal_or_none(row["exchange_rate"])

        missing: list[str] = []
        if purchase_cost is None:
            missing.append("purchase_cost")
        if first_leg_cost is None:
            missing.append("first_leg_cost")
        if wfs_fee is None:
            missing.append("wfs_fee")
        if storage_fee is None:
            missing.append("daily_storage_fee")
        if exchange_rate is None or exchange_rate <= 0:
            missing.append("exchange_rate")

        unit_total_cost = None
        if not missing:
            assert purchase_cost is not None
            assert first_leg_cost is not None
            assert wfs_fee is not None
            assert storage_fee is not None
            assert exchange_rate is not None
            unit_total_cost = (
                purchase_cost / exchange_rate
                + first_leg_cost / exchange_rate
                + wfs_fee
                + storage_fee
            )

        result[local_sku] = {
            "purchase_cost": purchase_cost,
            "first_leg_cost": first_leg_cost,
            "wfs_fee": wfs_fee,
            "daily_storage_fee": storage_fee,
            "unit_total_cost": unit_total_cost,
            "cost_match_status": "matched" if unit_total_cost is not None else "incomplete",
            "missing_cost_codes": missing,
        }

    return result


def summarize_refund_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize raw item statuses before the exclusion rule is applied."""

    return_orders = find_return_list(payload)
    if return_orders is None:
        raise ValueError("return list not found")

    raw_item_rows = 0
    status_counts: dict[str, int] = {}
    counted_order_ids: set[str] = set()

    for order in return_orders:
        items = order.get("items")
        if not isinstance(items, list):
            continue

        return_order_id = str(order.get("returnOrderId") or "").strip()

        for item in items:
            if not isinstance(item, dict):
                continue

            raw_item_rows += 1
            status = str(
                item.get("currentRefundStatus")
                or order.get("currentRefundStatus")
                or ""
            ).strip()
            status_counts[status or "<BLANK>"] = status_counts.get(
                status or "<BLANK>", 0
            ) + 1

            if status not in EXCLUDED_REFUND_STATUSES and return_order_id:
                counted_order_ids.add(return_order_id)

    excluded_rows = sum(
        status_counts.get(status, 0)
        for status in EXCLUDED_REFUND_STATUSES
    )

    return {
        "raw_item_rows": raw_item_rows,
        "excluded_rows": excluded_rows,
        "counted_rows": raw_item_rows - excluded_rows,
        "counted_order_rows": len(counted_order_ids),
        "status_counts": status_counts,
    }



def collect_excluded_item_keys(
    payload: dict[str, Any],
) -> list[tuple[str, int]]:
    """Return exact RAW identities whose current status must not count as refunds."""

    return_orders = find_return_list(payload)
    if return_orders is None:
        raise ValueError("return list not found")

    keys: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()

    for order in return_orders:
        items = order.get("items")
        if not isinstance(items, list):
            continue

        return_order_id = str(
            order.get("returnOrderId") or ""
        ).strip()

        if not return_order_id:
            continue

        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            current_refund_status = str(
                item.get("currentRefundStatus")
                or order.get("currentRefundStatus")
                or ""
            ).strip()

            if current_refund_status not in EXCLUDED_REFUND_STATUSES:
                continue

            key = (
                return_order_id,
                item_index,
            )

            if key in seen:
                continue

            seen.add(key)
            keys.append(key)

    return keys


def delete_excluded_rows(
    conn: Connection,
    *,
    source_account_ref: str,
    keys: list[tuple[str, int]],
) -> None:
    """Remove rows that RAW now explicitly marks as excluded refund statuses."""

    if not keys:
        return

    statement = text(
        """
        delete from after_sales_refund_items
        where source_account_ref = :source_account_ref
          and platform_code = :platform_code
          and return_order_id = :return_order_id
          and item_index = :item_index
        """
    )

    params = [
        {
            "source_account_ref": source_account_ref,
            "platform_code": PLATFORM_CODE,
            "return_order_id": return_order_id,
            "item_index": item_index,
        }
        for return_order_id, item_index in keys
    ]

    conn.execute(
        statement,
        params,
    )


def build_rows(
    payload: dict[str, Any],
    *,
    source_account_ref: str,
    target_date: date,
    listing_map: dict[tuple[str, str], dict[str, Any]],
    cost_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return_orders = find_return_list(payload)
    if return_orders is None:
        raise ValueError("return list not found")

    rows: list[dict[str, Any]] = []

    for order in return_orders:
        items = order.get("items")
        if not isinstance(items, list):
            continue

        store_id = normalize_store_id(order.get("storeId"))
        raw_store_name = order.get("storeName")
        raw_site_code = order.get("siteCode")

        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            msku = str(item.get("msku") or "").strip() or None
            local_sku = str(item.get("localSku") or "").strip() or None

            current_refund_status = str(
                item.get("currentRefundStatus") or order.get("currentRefundStatus") or ""
            ).strip()

            # Confirmed Walmart refund-counting rule:
            # NOT_REFUNDED and CANCELLED do not count as refunds.
            # Previously persisted rows for those exact RAW identities are
            # reconciled before retained refund rows are upserted.
            if current_refund_status in EXCLUDED_REFUND_STATUSES:
                continue

            refund_completed = (
                current_refund_status == REFUND_COMPLETED
            )
            refund_effective = True

            return_order_at = parse_datetime(
                order.get("returnOrderDate")
            )

            purchase_time_at = parse_datetime(
                item.get("purchaseTimeLocale")
                or order.get("purchaseTimeLocale")
            )

            status_time = parse_datetime(
                item.get("statusTime")
                or order.get("statusTime")
            )

            refund_effective_date = (
                return_order_at.date()
                if refund_effective and return_order_at
                else None
            )

            refund_loss_date = refund_effective_date

            refund_amount = decimal_or_none(
                item.get("lineTotalAmount")
            )
            refund_currency_code = (
                str(item.get("lineTotalCurrency") or "").strip()
                or None
            )

            return_qty = quantity_from_display(
                item.get("quantityDisplay")
            )

            listing = listing_map.get((store_id or "", msku or ""), {})
            item_id = listing.get("item_id")
            listing_match_status = listing.get("status") or "unmatched"

            cost = cost_map.get(local_sku or "")
            if cost is None:
                cost = {
                    "purchase_cost": None,
                    "first_leg_cost": None,
                    "wfs_fee": None,
                    "daily_storage_fee": None,
                    "unit_total_cost": None,
                    "cost_match_status": "unmatched",
                    "missing_cost_codes": ["local_sku_cost"],
                }

            unit_total_cost = cost["unit_total_cost"]
            refund_loss_amount = (
                return_qty * unit_total_cost
                if unit_total_cost is not None
                else None
            )

            rows.append(
                {
                    "id": str(uuid4()),
                    "source_account_ref": source_account_ref,
                    "platform_code": PLATFORM_CODE,
                    "return_order_id": str(order.get("returnOrderId") or ""),
                    "item_index": index,
                    "source_item_hash": item_hash(order, item),
                    "customer_order_id": order.get("customerOrderId"),
                    "purchase_order_id": item.get("purchaseOrderId"),
                    "store_id": store_id,
                    "store_name": None,
                    "raw_store_name": raw_store_name,
                    "store_match_status": "raw_fallback" if raw_store_name else "unmatched",
                    "site_code": None,
                    "raw_site_code": raw_site_code,
                    "return_type": order.get("returnType"),

                    "return_order_at": return_order_at,
                    "purchase_time_at": purchase_time_at,

                    # Temporary dual-write while duplicate
                    # after-sales columns are consolidated later.
                    "return_order_date": return_order_at,

                    "status_time": status_time,
                    "current_refund_status": (
                        current_refund_status or None
                    ),

                    "refund_completed": refund_completed,

                    "refund_effective": True,
                    "refund_effective_date": (
                        refund_effective_date
                    ),

                    "refund_loss_effective": True,
                    "refund_loss_date": refund_loss_date,
                    "refund_amount": refund_amount,
                    "refund_currency_code": refund_currency_code,
                    "local_sku": local_sku,
                    "msku": msku,
                    "item_id": item_id,
                    "listing_image_url": item.get("productImageUrl"),
                    "listing_match_status": listing_match_status,
                    "product_name": item.get("productName") or item.get("pname"),
                    "product_match_status": "matched" if local_sku in cost_map else "unmatched",
                    "quantity_display_raw": item.get("quantityDisplay"),
                    "return_qty": return_qty,
                    "return_reason_code": item.get("returnReason"),
                    "return_description": item.get("returnDescription"),
                    "return_reason_category": None,
                    "purchase_cost": cost["purchase_cost"],
                    "first_leg_cost": cost["first_leg_cost"],
                    "wfs_fee": cost["wfs_fee"],
                    "daily_storage_fee": cost["daily_storage_fee"],
                    "unit_total_cost": unit_total_cost,
                    "cost_match_status": cost["cost_match_status"],
                    "missing_cost_codes": json.dumps(
                        cost["missing_cost_codes"], ensure_ascii=False
                    ),
                    "refund_loss_amount": refund_loss_amount,
                }
            )

    return rows


def upsert_rows(conn: Connection, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    statement = text(
        """
        insert into after_sales_refund_items (
            id,
            source_account_ref,
            platform_code,
            return_order_id,
            item_index,
            source_item_hash,
            customer_order_id,
            purchase_order_id,
            store_id,
            store_name,
            raw_store_name,
            store_match_status,
            site_code,
            raw_site_code,
            return_type,
            return_order_at,
            purchase_time_at,
            return_order_date,
            status_time,
            current_refund_status,
            refund_completed,
            refund_effective,
            refund_effective_date,
            refund_loss_effective,
            refund_loss_date,
            refund_amount,
            refund_currency_code,
            local_sku,
            msku,
            item_id,
            listing_image_url,
            listing_match_status,
            product_name,
            product_match_status,
            quantity_display_raw,
            return_qty,
            return_reason_code,
            return_description,
            return_reason_category,
            purchase_cost,
            first_leg_cost,
            wfs_fee,
            daily_storage_fee,
            unit_total_cost,
            cost_match_status,
            missing_cost_codes,
            refund_loss_amount
        )
        values (
            :id,
            :source_account_ref,
            :platform_code,
            :return_order_id,
            :item_index,
            :source_item_hash,
            :customer_order_id,
            :purchase_order_id,
            :store_id,
            :store_name,
            :raw_store_name,
            :store_match_status,
            :site_code,
            :raw_site_code,
            :return_type,
            :return_order_at,
            :purchase_time_at,
            :return_order_date,
            :status_time,
            :current_refund_status,
            :refund_completed,
            :refund_effective,
            :refund_effective_date,
            :refund_loss_effective,
            :refund_loss_date,
            :refund_amount,
            :refund_currency_code,
            :local_sku,
            :msku,
            :item_id,
            :listing_image_url,
            :listing_match_status,
            :product_name,
            :product_match_status,
            :quantity_display_raw,
            :return_qty,
            :return_reason_code,
            :return_description,
            :return_reason_category,
            :purchase_cost,
            :first_leg_cost,
            :wfs_fee,
            :daily_storage_fee,
            :unit_total_cost,
            :cost_match_status,
            cast(:missing_cost_codes as jsonb),
            :refund_loss_amount
        )
        on conflict (source_account_ref, platform_code, return_order_id, item_index)
        do update set
            source_item_hash = excluded.source_item_hash,
            customer_order_id = excluded.customer_order_id,
            purchase_order_id = excluded.purchase_order_id,
            store_id = excluded.store_id,
            store_name = excluded.store_name,
            raw_store_name = excluded.raw_store_name,
            store_match_status = excluded.store_match_status,
            site_code = excluded.site_code,
            raw_site_code = excluded.raw_site_code,
            return_type = excluded.return_type,
            return_order_at = excluded.return_order_at,
            purchase_time_at = excluded.purchase_time_at,
            return_order_date = excluded.return_order_date,
            status_time = excluded.status_time,
            current_refund_status = excluded.current_refund_status,
            refund_completed = excluded.refund_completed,
            refund_effective = excluded.refund_effective,
            refund_effective_date = excluded.refund_effective_date,
            refund_loss_effective = excluded.refund_loss_effective,
            refund_loss_date = excluded.refund_loss_date,
            refund_amount = excluded.refund_amount,
            refund_currency_code = excluded.refund_currency_code,
            local_sku = excluded.local_sku,
            msku = excluded.msku,
            item_id = excluded.item_id,
            listing_image_url = excluded.listing_image_url,
            listing_match_status = excluded.listing_match_status,
            product_name = excluded.product_name,
            product_match_status = excluded.product_match_status,
            quantity_display_raw = excluded.quantity_display_raw,
            return_qty = excluded.return_qty,
            return_reason_code = excluded.return_reason_code,
            return_description = excluded.return_description,
            return_reason_category = excluded.return_reason_category,
            purchase_cost = excluded.purchase_cost,
            first_leg_cost = excluded.first_leg_cost,
            wfs_fee = excluded.wfs_fee,
            daily_storage_fee = excluded.daily_storage_fee,
            unit_total_cost = excluded.unit_total_cost,
            cost_match_status = excluded.cost_match_status,
            missing_cost_codes = excluded.missing_cost_codes,
            refund_loss_amount = excluded.refund_loss_amount,
            updated_at = now()
        """
    )

    conn.execute(statement, rows)


def main() -> None:
    args = parse_args()

    target_date = date.fromisoformat(
        args.target_date
    )

    engine = create_engine(
        get_database_url(get_settings()),
        pool_pre_ping=True,
    )

    with engine.begin() as conn:
        if args.from_ods:
            payload = load_payload_from_ods(
                conn,
                target_date,
            )
            source_mode = "ods"

        else:
            if not args.input_json:
                raise ValueError(
                    "--input-json is required"
                )

            source_payload = unwrap_response(
                json.loads(
                    Path(
                        args.input_json
                    ).read_text(
                        encoding="utf-8"
                    )
                )
            )

            payload = filter_payload_for_target_date(
                source_payload,
                target_date,
            )

            source_mode = "file"

        listing_source_table = (
            find_listing_source_table(conn)
        )

        listing_map = build_listing_map(
            conn,
            listing_source_table,
        )

        cost_map = build_cost_map(
            conn,
            target_date,
        )

        raw_summary = summarize_refund_payload(payload)

        rows = build_rows(
            payload,
            source_account_ref=args.source_account_ref,
            target_date=target_date,
            listing_map=listing_map,
            cost_map=cost_map,
        )

        completed = sum(
            1
            for row in rows
            if row["refund_completed"]
        )

        refund_effective = sum(
            1
            for row in rows
            if row["refund_effective"]
        )

        loss_effective = sum(
            1
            for row in rows
            if row["refund_loss_effective"]
        )

        refund_order_count = len(
            {
                row["return_order_id"]
                for row in rows
                if row["return_order_id"]
            }
        )

        refund_amount_total = sum(
            (
                row["refund_amount"]
                for row in rows
                if row["refund_amount"] is not None
            ),
            Decimal("0"),
        )

        refund_amount_missing = sum(
            1
            for row in rows
            if row["refund_amount"] is None
        )

        refund_currency_codes = sorted(
            {
                row["refund_currency_code"]
                for row in rows
                if row["refund_currency_code"]
            }
        )

        matched_cost = sum(
            1
            for row in rows
            if row["cost_match_status"] == "matched"
        )

        matched_listing = sum(
            1
            for row in rows
            if row["listing_match_status"] == "matched"
        )

        blank_return_order_id = sum(
            1
            for row in rows
            if not row["return_order_id"]
        )

        blank_store_id = sum(
            1
            for row in rows
            if not row["store_id"]
        )

        print(
            "source_mode=",
            source_mode,
        )
        print(
            "target_date=",
            target_date.isoformat(),
        )
        print(
            "listing_source_table=",
            listing_source_table,
        )
        print(
            "raw_item_rows=",
            raw_summary["raw_item_rows"],
        )
        print(
            "excluded_not_refunded_rows=",
            raw_summary["status_counts"].get("NOT_REFUNDED", 0),
        )
        print(
            "excluded_cancelled_rows=",
            raw_summary["status_counts"].get("CANCELLED", 0),
        )
        print(
            "excluded_rows=",
            raw_summary["excluded_rows"],
        )
        print(
            "parsed_rows=",
            len(rows),
        )
        print(
            "refund_order_count=",
            refund_order_count,
        )
        print(
            "refund_completed_rows=",
            completed,
        )
        print(
            "refund_effective_rows=",
            refund_effective,
        )
        print(
            "refund_loss_effective_rows=",
            loss_effective,
        )
        print(
            "refund_amount_total=",
            refund_amount_total,
        )
        print(
            "refund_amount_missing_rows=",
            refund_amount_missing,
        )
        print(
            "refund_currency_codes=",
            ",".join(refund_currency_codes),
        )
        print(
            "refund_status_counts=",
            json.dumps(
                raw_summary["status_counts"],
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        print(
            "cost_matched_rows=",
            matched_cost,
        )
        print(
            "listing_matched_rows=",
            matched_listing,
        )
        print(
            "blank_return_order_id_rows=",
            blank_return_order_id,
        )
        print(
            "blank_store_id_rows=",
            blank_store_id,
        )

        if args.dry_run:
            print(
                "dry_run=true, skip upsert"
            )
            return

        if blank_return_order_id:
            raise ValueError(
                "return_order_id is missing"
            )

        if blank_store_id:
            raise ValueError(
                "store_id is missing"
            )

        excluded_item_keys = collect_excluded_item_keys(payload)
        delete_excluded_rows(
            conn,
            source_account_ref=args.source_account_ref,
            keys=excluded_item_keys,
        )

        upsert_rows(
            conn,
            rows,
        )

        print(
            "upserted_rows=",
            len(rows),
        )


if __name__ == "__main__":
    main()
