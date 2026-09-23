"""Import Walmart return-order snapshot into after_sales_refund_items.

This script only persists after-sales refund facts. It does not refresh Daily Sales MART.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from app.core.config import get_database_url, get_settings

REFUND_COMPLETED = "REFUND_COMPLETED"
EXCLUDED_REFUND_STATUSES = frozenset({"NOT_REFUNDED", "CANCELLED"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", default=[], help="One response JSON/TXT file.")
    parser.add_argument("--input-dir", help="Directory containing response JSON/TXT page files.")
    parser.add_argument("--source-account-ref", default="primary")
    parser.add_argument("--allow-partial", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def response_body(doc: dict[str, Any]) -> dict[str, Any]:
    body = doc.get("body") or doc.get("compactBody") or doc
    if not isinstance(body, dict):
        raise ValueError("response body is not an object")
    return body


def response_data(doc: dict[str, Any]) -> dict[str, Any]:
    body = response_body(doc)
    data = body.get("data")
    if not isinstance(data, dict):
        raise ValueError("response data is not an object")
    return data


def parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text_value = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text_value, fmt)
        except ValueError:
            continue
    return None


def parse_qty(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")


def stable_hash(*values: Any) -> str:
    raw = "|".join("" if value is None else str(value) for value in values)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def table_exists(conn, table_name: str) -> bool:
    return (
        conn.execute(text("select to_regclass(:name)"), {"name": f"public.{table_name}"}).scalar()
        is not None
    )


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(
        text(
            """
            select column_name
            from information_schema.columns
            where table_schema='public' and table_name=:table_name
            """
        ),
        {"table_name": table_name},
    ).scalars()
    return set(rows)


def find_table(conn, *, required: set[str], hints: tuple[str, ...]) -> tuple[str | None, set[str]]:
    rows = (
        conn.execute(
            text(
                """
            select table_name
            from information_schema.tables
            where table_schema='public' and table_type='BASE TABLE'
            """
            )
        )
        .scalars()
        .all()
    )

    scored: list[tuple[int, str, set[str]]] = []
    for table_name in rows:
        cols = table_columns(conn, table_name)
        if not required.issubset(cols):
            continue
        score = sum(1 for hint in hints if hint in table_name)
        scored.append((score, table_name, cols))

    if not scored:
        return None, set()

    scored.sort(reverse=True)
    _, table_name, cols = scored[0]
    return table_name, cols


def first_existing(cols: set[str], names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in cols:
            return name
    return None


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def load_store_names(conn, source_account_ref: str) -> dict[str, str]:
    if not table_exists(conn, "dim_lingxing_stores"):
        return {}

    rows = conn.execute(
        text(
            """
            select store_id::text as store_id, max(store_name) as store_name
            from dim_lingxing_stores
            where source_account_ref = :source_account_ref
              and store_id is not null
            group by store_id::text
            """
        ),
        {"source_account_ref": source_account_ref},
    ).mappings()
    return {row["store_id"]: row["store_name"] for row in rows if row["store_name"]}


def lookup_listing(
    conn, table_name: str | None, cols: set[str], store_id: str, msku: str | None
) -> dict[str, Any]:
    if not table_name or not msku:
        return {"item_id": None, "listing_image_url": None, "listing_match_status": "pending"}

    image_col = first_existing(
        cols, ("picture_url", "product_image_url", "image_url", "main_image_url")
    )
    select_image = qident(image_col) if image_col else "null"
    sql = f"""
        select item_id::text as item_id, {select_image} as listing_image_url
        from {qident(table_name)}
        where store_id::text = :store_id and msku = :msku
        limit 2
    """
    rows = conn.execute(text(sql), {"store_id": store_id, "msku": msku}).mappings().all()
    if len(rows) == 1:
        return {
            "item_id": rows[0]["item_id"],
            "listing_image_url": rows[0]["listing_image_url"],
            "listing_match_status": "matched",
        }
    if len(rows) > 1:
        return {"item_id": None, "listing_image_url": None, "listing_match_status": "conflict"}
    return {"item_id": None, "listing_image_url": None, "listing_match_status": "unmatched"}


def lookup_product(
    conn, table_name: str | None, cols: set[str], local_sku: str | None
) -> dict[str, Any]:
    empty = {
        "product_name": None,
        "product_match_status": "pending",
        "purchase_cost": None,
        "first_leg_cost": None,
        "wfs_fee": None,
        "daily_storage_fee": None,
        "unit_total_cost": None,
        "cost_match_status": "pending",
    }
    if not table_name or not local_sku:
        return empty

    sku_col = first_existing(cols, ("local_sku", "sku"))
    if not sku_col:
        return empty

    name_col = first_existing(cols, ("product_name", "local_name", "pname", "name"))
    purchase_col = first_existing(
        cols, ("purchase_cost", "purchase_cost_usd", "purchase_cost_amount")
    )
    first_leg_col = first_existing(
        cols, ("first_leg_cost", "unit_first_leg_cost", "first_leg_cost_usd")
    )
    wfs_col = first_existing(cols, ("wfs_fee", "wfs_fulfillment_fee", "wfs_unit"))
    storage_col = first_existing(
        cols, ("daily_storage_fee", "wfs_daily_storage_fee", "storage_fee")
    )

    select_parts = [
        f"{qident(sku_col)} as sku_value",
        f"{qident(name_col)} as product_name" if name_col else "null as product_name",
        f"{qident(purchase_col)} as purchase_cost" if purchase_col else "null as purchase_cost",
        f"{qident(first_leg_col)} as first_leg_cost" if first_leg_col else "null as first_leg_cost",
        f"{qident(wfs_col)} as wfs_fee" if wfs_col else "null as wfs_fee",
        f"{qident(storage_col)} as daily_storage_fee"
        if storage_col
        else "null as daily_storage_fee",
    ]

    sql = f"""
        select {", ".join(select_parts)}
        from {qident(table_name)}
        where {qident(sku_col)} = :local_sku
        limit 2
    """
    rows = conn.execute(text(sql), {"local_sku": local_sku}).mappings().all()
    if len(rows) > 1:
        return {**empty, "product_match_status": "conflict", "cost_match_status": "pending"}
    if not rows:
        return {**empty, "product_match_status": "unmatched", "cost_match_status": "unmatched"}

    row = rows[0]
    purchase_cost = decimal_or_none(row["purchase_cost"])
    first_leg_cost = decimal_or_none(row["first_leg_cost"])
    wfs_fee = decimal_or_none(row["wfs_fee"])
    daily_storage_fee = decimal_or_none(row["daily_storage_fee"])

    costs = [purchase_cost, first_leg_cost, wfs_fee, daily_storage_fee]
    unit_total_cost = (
        sum(costs, Decimal("0")) if all(value is not None for value in costs) else None
    )

    return {
        "product_name": row["product_name"],
        "product_match_status": "matched",
        "purchase_cost": purchase_cost,
        "first_leg_cost": first_leg_cost,
        "wfs_fee": wfs_fee,
        "daily_storage_fee": daily_storage_fee,
        "unit_total_cost": unit_total_cost,
        "cost_match_status": "matched" if unit_total_cost is not None else "incomplete",
    }


def collect_input_files(args: argparse.Namespace) -> list[Path]:
    files = [Path(value) for value in args.input]
    if args.input_dir:
        folder = Path(args.input_dir)
        files.extend(
            sorted(path for path in folder.iterdir() if path.suffix.lower() in {".json", ".txt"})
        )
    if not files:
        raise SystemExit("必须传 --input 或 --input-dir")
    return files


def main() -> int:
    args = parse_args()
    input_files = collect_input_files(args)
    docs = [load_json(path) for path in input_files]

    page_numbers: set[int] = set()
    expected_pages = 1
    expected_total = None
    for doc in docs:
        data = response_data(doc)
        page_numbers.add(int(data.get("current") or 1))
        expected_pages = max(expected_pages, int(data.get("pages") or 1))
        expected_total = data.get("total", expected_total)

    if expected_pages > len(page_numbers) and not args.allow_partial:
        raise SystemExit(
            f"当前只加载 {len(page_numbers)} 页，但接口返回 "
            f"pages={expected_pages}, total={expected_total}。"
            "请把全部页面保存到目录后重跑，或加 --allow-partial 只导入已加载页面。"
        )

    engine = create_engine(get_database_url(get_settings()), pool_pre_ping=True)

    with engine.begin() as conn:
        if not table_exists(conn, "after_sales_refund_items"):
            raise SystemExit("after_sales_refund_items 不存在，请先执行 alembic upgrade head")

        store_names = load_store_names(conn, args.source_account_ref)
        listing_table, listing_cols = find_table(
            conn,
            required={"store_id", "msku", "item_id"},
            hints=("listing", "mart"),
        )
        product_table, product_cols = find_table(
            conn,
            required=set(),
            hints=("product_management", "pricing", "sku_base", "product"),
        )

        parsed_rows = 0
        completed_rows = 0

        for doc in docs:
            body = response_body(doc)
            data = response_data(doc)
            source_request_id = body.get("request_id")

            for order in data.get("list") or []:
                return_order_id = str(order.get("returnOrderId") or "").strip()
                store_id = str(order.get("storeId") or "").strip()
                raw_store_name = order.get("storeName")
                standard_store_name = store_names.get(store_id)
                store_name = standard_store_name or raw_store_name
                store_match_status = (
                    "matched"
                    if standard_store_name
                    else "raw_only"
                    if raw_store_name
                    else "unmatched"
                )

                return_order_at = parse_dt(order.get("returnOrderDate"))
                purchase_time_at = parse_dt(order.get("purchaseTimeLocale"))

                for item_index, item in enumerate(order.get("items") or []):
                    local_sku = (item.get("localSku") or "").strip() or None
                    msku = (item.get("msku") or "").strip() or None
                    return_qty = parse_qty(item.get("quantityDisplay"))
                    current_refund_status = str(
                        item.get("currentRefundStatus") or ""
                    ).strip()
                    if current_refund_status in EXCLUDED_REFUND_STATUSES:
                        conn.execute(
                            text(
                                """
                                delete from after_sales_refund_items
                                where source_account_ref = :source_account_ref
                                  and platform_code = :platform_code
                                  and return_order_id = :return_order_id
                                  and item_index = :item_index
                                """
                            ),
                            {
                                "source_account_ref": args.source_account_ref,
                                "platform_code": "walmart",
                                "return_order_id": return_order_id,
                                "item_index": item_index,
                            },
                        )
                        continue

                    refund_completed = current_refund_status == REFUND_COMPLETED
                    refund_effective = True
                    status_time = parse_dt(item.get("statusTime"))
                    refund_effective_date = (
                        return_order_at.date()
                        if return_order_at
                        else None
                    )
                    listing = lookup_listing(conn, listing_table, listing_cols, store_id, msku)
                    product = lookup_product(conn, product_table, product_cols, local_sku)

                    unit_total_cost = product["unit_total_cost"]
                    refund_loss_amount = (
                        return_qty * unit_total_cost
                        if unit_total_cost is not None
                        else None
                    )

                    refund_amount = decimal_or_none(item.get("lineTotalAmount"))
                    refund_currency_code = (
                        str(item.get("lineTotalCurrency") or "").strip() or None
                    )

                    purchase_order_id = item.get("purchaseOrderId")
                    source_item_hash = stable_hash(order, item)
                    row_id = stable_hash(
                        args.source_account_ref,
                        return_order_id,
                        item_index,
                        purchase_order_id,
                        msku,
                        item.get("statusTime"),
                    )

                    params = {
                        "id": row_id,
                        "source_account_ref": args.source_account_ref,
                        "platform_code": "walmart",
                        "source_request_id": source_request_id,
                        "return_order_id": return_order_id,
                        "item_index": item_index,
                        "customer_order_id": order.get("customerOrderId"),
                        "purchase_order_id": purchase_order_id,
                        "store_id": store_id,
                        "raw_store_name": raw_store_name,
                        "store_name": store_name,
                        "store_match_status": store_match_status,
                        "site_code": order.get("siteCode"),
                        "return_type": order.get("returnType"),
                        "return_order_at": return_order_at,
                        "purchase_time_at": purchase_time_at,
                        "local_sku": local_sku,
                        "msku": msku,
                        "return_qty": return_qty,
                        "quantity_display_raw": item.get("quantityDisplay"),
                        "return_reason_code": item.get("returnReason"),
                        "return_description": item.get("returnDescription"),
                        "status_time": status_time,
                        "current_refund_status": current_refund_status,
                        "refund_completed": refund_completed,
                        "refund_effective": refund_effective,
                        "refund_effective_date": refund_effective_date,
                        "refund_loss_effective": True,
                        "refund_loss_date": refund_effective_date,
                        "refund_amount": refund_amount,
                        "refund_currency_code": refund_currency_code,
                        "item_id": listing["item_id"],
                        "listing_image_url": listing["listing_image_url"],
                        "listing_match_status": listing["listing_match_status"],
                        "product_name": product["product_name"],
                        "product_match_status": product["product_match_status"],
                        "purchase_cost": product["purchase_cost"],
                        "first_leg_cost": product["first_leg_cost"],
                        "wfs_fee": product["wfs_fee"],
                        "daily_storage_fee": product["daily_storage_fee"],
                        "unit_total_cost": unit_total_cost,
                        "cost_match_status": product["cost_match_status"],
                        "refund_loss_amount": refund_loss_amount,
                        "source_item_hash": source_item_hash,
                        "synced_at": datetime.now(UTC),
                    }

                    conn.execute(
                        text(
                            """
                            insert into after_sales_refund_items (
                                id, source_account_ref, platform_code, source_request_id,
                                return_order_id, item_index, customer_order_id, purchase_order_id,
                                store_id, raw_store_name, store_name, store_match_status, site_code,
                                return_type, return_order_at, purchase_time_at, local_sku, msku,
                                return_qty, quantity_display_raw, return_reason_code,
                                return_description,
                                status_time, current_refund_status, refund_completed,
                                refund_effective,
                                refund_effective_date,
                                refund_loss_effective,
                                refund_loss_date,
                                refund_amount, refund_currency_code,
                                item_id, listing_image_url, listing_match_status,
                                product_name, product_match_status, purchase_cost, first_leg_cost,
                                wfs_fee, daily_storage_fee, unit_total_cost, cost_match_status,
                                refund_loss_amount, source_item_hash, synced_at
                            ) values (
                                :id, :source_account_ref, :platform_code, :source_request_id,
                                :return_order_id, :item_index, :customer_order_id,
                                :purchase_order_id,
                                :store_id, :raw_store_name, :store_name,
                                :store_match_status, :site_code,
                                :return_type, :return_order_at, :purchase_time_at,
                                :local_sku, :msku,
                                :return_qty, :quantity_display_raw, :return_reason_code,
                                :return_description,
                                :status_time, :current_refund_status, :refund_completed,
                                :refund_effective,
                                :refund_effective_date,
                                :refund_loss_effective,
                                :refund_loss_date,
                                :refund_amount, :refund_currency_code,
                                :item_id, :listing_image_url, :listing_match_status,
                                :product_name, :product_match_status, :purchase_cost,
                                :first_leg_cost,
                                :wfs_fee, :daily_storage_fee, :unit_total_cost, :cost_match_status,
                                :refund_loss_amount, :source_item_hash, :synced_at
                            )
                            on conflict (
                                source_account_ref, return_order_id, item_index
                            ) do update set
                                source_request_id = excluded.source_request_id,
                                customer_order_id = excluded.customer_order_id,
                                purchase_order_id = excluded.purchase_order_id,
                                store_id = excluded.store_id,
                                raw_store_name = excluded.raw_store_name,
                                store_name = excluded.store_name,
                                store_match_status = excluded.store_match_status,
                                site_code = excluded.site_code,
                                return_type = excluded.return_type,
                                return_order_at = excluded.return_order_at,
                                purchase_time_at = excluded.purchase_time_at,
                                local_sku = excluded.local_sku,
                                msku = excluded.msku,
                                return_qty = excluded.return_qty,
                                quantity_display_raw = excluded.quantity_display_raw,
                                return_reason_code = excluded.return_reason_code,
                                return_description = excluded.return_description,
                                status_time = excluded.status_time,
                                current_refund_status = excluded.current_refund_status,
                                refund_completed = excluded.refund_completed,
                                refund_effective = excluded.refund_effective,
                                refund_effective_date = excluded.refund_effective_date,
                                refund_loss_effective = excluded.refund_loss_effective,
                                refund_loss_date = excluded.refund_loss_date,
                                refund_amount = excluded.refund_amount,
                                refund_currency_code = excluded.refund_currency_code,
                                item_id = excluded.item_id,
                                listing_image_url = excluded.listing_image_url,
                                listing_match_status = excluded.listing_match_status,
                                product_name = excluded.product_name,
                                product_match_status = excluded.product_match_status,
                                purchase_cost = excluded.purchase_cost,
                                first_leg_cost = excluded.first_leg_cost,
                                wfs_fee = excluded.wfs_fee,
                                daily_storage_fee = excluded.daily_storage_fee,
                                unit_total_cost = excluded.unit_total_cost,
                                cost_match_status = excluded.cost_match_status,
                                refund_loss_amount = excluded.refund_loss_amount,
                                source_item_hash = excluded.source_item_hash,
                                synced_at = excluded.synced_at,
                                updated_at = now()
                            """
                        ),
                        params,
                    )

                    parsed_rows += 1
                    if refund_completed:
                        completed_rows += 1

    print(
        "IMPORTED",
        {
            "files": len(input_files),
            "pages_loaded": sorted(page_numbers),
            "expected_pages": expected_pages,
            "expected_total": expected_total,
            "rows": parsed_rows,
            "refund_completed_rows": completed_rows,
        },
    )
    print(f"listing_table={listing_table or 'NOT_FOUND'}")
    print(f"product_table={product_table or 'NOT_FOUND'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
