"""Read-only single-column report ordering; never changes financial calculations."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String, case, cast, func, literal, select

# Keys match the existing export field dictionary, not raw SQL identifiers.
COMMON = (
    "platform",
    "sales_qty",
    "order_count",
    "sales_amount",
    "avg_price",
    "sample_qty",
    "sample_amount",
    "return_qty",
    "refund_amount",
    "return_rate_30d",
    "ad_spend",
    "sem_ad_spend",
    "total_ad_spend",
    "ad_ratio",
    "wfs_fee_total",
    "wfs_low_price_surcharge",
    "wfs_fee_unit",
    "commission",
    "purchase_cost_total",
    "purchase_unit_cny",
    "first_leg_cost_total",
    "first_leg_unit_cny",
    "storage_fee_total",
    "storage_unit",
    "wfs_inventory",
    "order_profit",
    "gross_margin",
    "roi",
    "cost_status",
)
DAILY_FIELDS = frozenset((*COMMON, "period"))
PROFIT_FIELDS = frozenset((*COMMON, "total_cost", "avg_profit_per_order"))
ATTR = {
    "sales_qty": "sales_qty",
    "order_count": "order_count",
    "sales_amount": "sales_amount",
    "sample_qty": "sample_qty",
    "sample_amount": "sample_amount",
    "return_qty": "return_qty",
    "refund_amount": "refund_amount",
    "return_rate_30d": "return_rate_30d",
    "ad_spend": "ad_spend_amount",
    "sem_ad_spend": "sem_ad_spend_amount",
    "wfs_fee_total": "wfs_fee_total_amount",
    "wfs_low_price_surcharge": "wfs_low_price_surcharge_amount",
    "wfs_fee_unit": "wfs_fee_unit_amount",
    "commission": "commission_fee_amount",
    "purchase_cost_total": "purchase_cost_total_usd",
    "purchase_unit_cny": "purchase_cost_unit_cny",
    "first_leg_cost_total": "first_leg_cost_total_usd",
    "first_leg_unit_cny": "first_leg_cost_unit_cny",
    "storage_fee_total": "storage_fee_total_amount",
    "storage_unit": "storage_fee_unit_amount",
    "wfs_inventory": "wfs_available_quantity",
    "order_profit": "gross_profit_amount",
    "gross_margin": "gross_margin",
    "roi": "roi",
    "total_cost": "total_cost_amount",
    "avg_profit_per_order": "average_profit_per_order",
}
USD_FIELDS = frozenset(
    (
        "sales_amount",
        "avg_price",
        "sample_amount",
        "refund_amount",
        "ad_spend",
        "sem_ad_spend",
        "total_ad_spend",
        "wfs_fee_total",
        "wfs_low_price_surcharge",
        "wfs_fee_unit",
        "commission",
        "purchase_cost_total",
        "first_leg_cost_total",
        "storage_fee_total",
        "storage_unit",
        "order_profit",
        "total_cost",
        "avg_profit_per_order",
    )
)
CNY_FIELDS = frozenset(("purchase_unit_cny", "first_leg_unit_cny"))
ZERO_FIELDS = frozenset(
    (
        "sales_qty",
        "order_count",
        "sales_amount",
        "sample_qty",
        "return_qty",
        "sem_ad_spend",
        "wfs_low_price_surcharge",
    )
)
COST_RANK = {
    "missing": 0,
    "待补齐": 0,
    "异常": 0,
    "partial": 1,
    "部分缺失": 1,
    "complete": 2,
    "已完成": 2,
}


def _missing_numeric():
    return cast(literal(None), Numeric())


def _text(value):
    return func.nullif(func.btrim(value), "")


def _first_json(model, field):
    value = getattr(model, field, None)
    return _text(value[0].astext) if value is not None else cast(literal(None), String())


def sql_sort_expression(model, field, currency="USD", *, daily, inventory=None):
    """Use the current DTO/UI sources; unavailable legacy fields stay NULL."""
    allowed = DAILY_FIELDS if daily else PROFIT_FIELDS
    if field not in allowed:
        raise ValueError("Unsupported report sort field")

    def get(name):
        return getattr(model, name, _missing_numeric())

    qty = func.coalesce(model.sales_qty, 0)
    amount = func.coalesce(model.sales_amount, 0)
    ad = func.coalesce(model.ad_spend_amount, 0) + func.coalesce(model.sem_ad_spend_amount, 0)
    if field == "period":
        expr = model.business_date_la
    elif field == "sku":
        expr = _text(model.local_sku)
    elif field == "msku":
        expr = (
            _text(model.msku)
            if daily
            else func.coalesce(
                _first_json(model, "mskus_json"), _first_json(model, "item_ids_json")
            )
        )
    elif field == "product_id":
        expr = func.coalesce(_first_json(model, "item_ids_json"), _text(model.local_sku))
    elif field == "store":
        expr = (
            func.coalesce(_text(model.store_name), _text(model.store_id))
            if daily
            else func.coalesce(
                _first_json(model, "store_names_json"), _first_json(model, "store_ids_json")
            )
        )
    elif field == "owner":
        expr = _text(model.owner_ref) if daily else _first_json(model, "owner_refs_json")
    elif field == "platform":
        # Both existing DTO adapters display Walmart, regardless of source code.
        expr = cast(literal("Walmart"), String())
    elif field == "avg_price":
        expr = amount / func.nullif(qty, 0)
    elif field == "total_ad_spend":
        expr = ad
    elif field == "ad_ratio":
        expr = model.ad_ratio if daily else ad / func.nullif(amount, 0)
    elif field == "cost_status":
        expr = case(
            (func.jsonb_array_length(model.missing_cost_codes_json) > 0, 1),
            (model.cost_status == "complete", 2),
            (model.cost_status == "partial", 1),
            (model.cost_status == "missing", 0),
            else_=None,
        )
    elif field == "wfs_inventory" and daily:
        if inventory is None:
            expr = _missing_numeric()
        else:
            expr = (
                select(inventory.wfs_available_quantity)
                .where(
                    inventory.snapshot_date_la == model.business_date_la,
                    inventory.source_account_ref == model.source_account_ref,
                    inventory.store_id == model.store_id,
                    inventory.item_id == model.item_id,
                )
                .correlate(model)
                .scalar_subquery()
            )
    else:
        expr = get(ATTR[field])
        if field in ZERO_FIELDS:
            expr = func.coalesce(expr, 0)
    # The existing Daily Sales renderers use row exchange rate (6.6 fallback).
    # Order Profit uses a fixed 6.6 conversion so ordering is monotonic.
    if daily:
        fx = func.coalesce(model.exchange_rate, Decimal("6.6"))
        fx = case((fx > 0, fx), else_=1)
        if field in USD_FIELDS and currency == "CNY":
            expr = expr * fx
            if field == "purchase_cost_total":
                expr = func.coalesce(
                    model.purchase_cost_unit_cny * func.coalesce(model.cost_quantity, 0),
                    expr,
                )
            if field == "first_leg_cost_total":
                expr = func.coalesce(
                    model.first_leg_cost_unit_cny * func.coalesce(model.cost_quantity, 0),
                    expr,
                )
        elif field in CNY_FIELDS and currency == "USD":
            expr = expr / fx
    return expr


def sql_order(model, field, direction, currency, *, daily, inventory=None):
    if direction not in ("asc", "desc"):
        raise ValueError("Unsupported sort direction")
    expr = sql_sort_expression(model, field, currency, daily=daily, inventory=inventory)
    return (expr.asc() if direction == "asc" else expr.desc()).nulls_last()


def _first(values):
    return next((str(x).strip() for x in (values or []) if str(x).strip()), None)


def profit_value(row, field):
    """Value of an already aggregated Order Profit DTO, before paging."""
    if field == "product_id":
        return _first(row.item_ids) or row.local_sku
    if field == "sku":
        return row.local_sku
    if field == "msku":
        return _first(row.mskus) or _first(row.item_ids)
    if field == "store":
        return _first(row.store_names) or _first(row.store_ids)
    if field == "owner":
        return _first(row.owner_refs)
    if field == "platform":
        return "Walmart"
    if field == "avg_price":
        return row.sales_amount / row.sales_qty if row.sales_qty else None
    if field == "total_ad_spend":
        return row.total_ad_spend_amount
    if field == "ad_ratio":
        return row.ad_ratio
    if field == "cost_status":
        return 1 if row.missing_cost_codes else COST_RANK.get(row.cost_status)
    return getattr(row, ATTR[field], None)


def sort_values(rows, value, direction, tie):
    """Stable, NULL-last, single-field sort (also used by grouped exports)."""
    if direction not in ("asc", "desc"):
        raise ValueError("Unsupported sort direction")
    present, missing = [], []
    for row in sorted(rows, key=tie):
        key = value(row)
        if key is None or key == "":
            missing.append(row)
        else:
            present.append((key, row))
    present.sort(key=lambda pair: pair[0], reverse=direction == "desc")
    return [row for _, row in present] + missing


def sort_export_rows(rows, field, direction):
    """Order the actual CSV group values in their existing native currency units."""
    if not field:
        return rows

    def value(row):
        v = row[1].get(field)
        return COST_RANK.get(v) if field == "cost_status" else v

    return sort_values(
        rows,
        value,
        direction,
        lambda row: (
            row[0],
            str(row[1].get("product_id") or ""),
            str(row[1].get("sku") or ""),
            str(row[1].get("msku") or ""),
            str(row[1].get("store") or ""),
        ),
    )
