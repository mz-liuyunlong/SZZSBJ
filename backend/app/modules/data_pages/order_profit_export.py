from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Literal

from sqlalchemy import or_, select, tuple_

from app.modules.data_pages.models import DailySalesItemDayMart, ListingManagementCurrentMart
from app.modules.data_pages.service import OrderProfitService

ZERO = Decimal("0")
RATIO_SCALE = Decimal("0.000001")

OrderProfitExportPeriod = Literal["day", "month"]
OrderProfitExportDimension = Literal["item_id", "sku", "msku"]

ORDER_PROFIT_EXPORT_COLUMNS: dict[str, str] = {
    "product_id": "商品ID",
    "product_name": "品名",
    "sku": "SKU",
    "msku": "MSKU",
    "store": "店铺",
    "owner": "负责人",
    "platform": "平台",
    "sales_qty": "销量",
    "order_count": "订单量",
    "sales_amount": "销售额",
    "avg_price": "平均售价",
    "sample_qty": "送样量",
    "sample_amount": "送样金额",
    "return_qty": "退款量",
    "refund_amount": "退款金额",
    "return_rate_30d": "退货率30天",
    "total_ad_spend": "总广告费",
    "ad_ratio": "广告占比",
    "ad_spend": "广告花费",
    "sem_ad_spend": "SEM广告费",
    "wfs_fee_total": "WFS总配送费",
    "wfs_low_price_surcharge": "低价配送附加费",
    "wfs_fee_unit": "WFS配送单价",
    "commission": "佣金",
    "purchase_cost_total": "采购总成本",
    "purchase_unit_cny": "采购单价",
    "first_leg_cost_total": "头程总成本",
    "first_leg_unit_cny": "头程单价",
    "storage_fee_total": "仓储费",
    "storage_unit": "仓储单价",
    "wfs_inventory": "WFS实时库存",
    "total_cost": "总成本",
    "order_profit": "订单利润",
    "avg_profit_per_order": "平均利润/单",
    "gross_margin": "利润率",
    "roi": "ROI",
    "cost_status": "成本状态",
}

DEFAULT_EXPORT_COLUMNS = list(ORDER_PROFIT_EXPORT_COLUMNS.keys())


def _csv_values(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _coerce_decimal(value: object, default: Decimal = ZERO) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _optional_sum(rows: Iterable[object], attr: str) -> Decimal | None:
    seen_value = False
    total = ZERO
    for row in rows:
        value = getattr(row, attr, None)
        if value is None:
            continue
        seen_value = True
        total += _coerce_decimal(value)
    return total if seen_value else None


def _sum(rows: Iterable[object], attr: str) -> Decimal:
    return _optional_sum(rows, attr) or ZERO


def _first_nonblank(rows: Iterable[object], attr: str) -> str | None:
    for row in rows:
        value = getattr(row, attr, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _distinct_values(rows: Iterable[object], attr: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw_value = getattr(row, attr, None)
        if raw_value is None:
            continue
        value = str(raw_value).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def _distinct_stores(rows: Iterable[DailySalesItemDayMart]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw_value = row.store_name or row.store_id
        if raw_value is None:
            continue
        value = str(raw_value).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def _platform_label(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"10008", "walmart"}:
        return "Walmart"
    if normalized == "amazon":
        return "Amazon"
    if normalized == "temu":
        return "TEMU"
    return str(value or "").strip() or "-"


def _ratio_percent(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return (numerator / denominator * Decimal("100")).quantize(RATIO_SCALE)


def _ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return (numerator / denominator).quantize(RATIO_SCALE)


def _weighted_average(
    rows: Sequence[object],
    *,
    value_attr: str,
    weight_attr: str,
) -> Decimal | None:
    weighted_total = ZERO
    total_weight = ZERO
    fallback_values: list[Decimal] = []

    for row in rows:
        raw_value = getattr(row, value_attr, None)
        if raw_value is None:
            continue

        value = _coerce_decimal(raw_value)
        fallback_values.append(value)

        weight = _coerce_decimal(getattr(row, weight_attr, None))
        if weight > 0:
            weighted_total += value * weight
            total_weight += weight

    if total_weight > 0:
        return (weighted_total / total_weight).quantize(RATIO_SCALE)

    if fallback_values:
        return (sum(fallback_values, ZERO) / Decimal(len(fallback_values))).quantize(RATIO_SCALE)

    return None


def _format_value(value: object) -> str:
    if value is None:
        return ""

    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return str(value.quantize(Decimal("1")))
        return format(value.normalize(), "f")

    return str(value)


def _period_key(row: DailySalesItemDayMart, period: OrderProfitExportPeriod) -> str:
    if period == "month":
        return row.business_date_la.strftime("%Y-%m")
    return row.business_date_la.isoformat()


def _dimension_key(row: DailySalesItemDayMart, dimension: OrderProfitExportDimension) -> str | None:
    if dimension == "sku":
        return str(row.local_sku or row.item_id or "").strip() or None
    if dimension == "msku":
        return str(row.msku or row.local_sku or row.item_id or "").strip() or None
    return str(row.item_id or row.local_sku or "").strip() or None


def _filtered_daily_sales_rows(
    service: OrderProfitService,
    *,
    query: object,
    account_refs: frozenset[str],
) -> list[DailySalesItemDayMart]:
    statement = service.daily_sales_repository._filtered_statement(
        account_refs=account_refs,
        start_date=query.start_date,
        end_date=query.end_date,
        platform=query.platform,
        store_id=query.store_id,
        owner_ref=query.owner_ref,
        search_field=query.search_field,
        keyword=query.keyword,
        batch_values="",
    )
    return list(service.daily_sales_repository.session.scalars(statement).all())


def _current_wfs_inventory_by_item(
    service: OrderProfitService,
    rows: Sequence[DailySalesItemDayMart],
    store_id: str | None,
) -> dict[tuple[str, str], Decimal]:
    keys = {
        (
            str(row.source_account_ref or "").strip(),
            str(row.item_id or "").strip(),
        )
        for row in rows
        if row.source_account_ref and row.item_id
    }

    if not keys:
        return {}

    statement = select(
        ListingManagementCurrentMart.source_account_ref,
        ListingManagementCurrentMart.item_id,
        ListingManagementCurrentMart.wfs_available_quantity,
    ).where(
        tuple_(
            ListingManagementCurrentMart.source_account_ref,
            ListingManagementCurrentMart.item_id,
        ).in_(list(keys))
    )

    store_values = _csv_values(store_id)
    if store_values:
        statement = statement.where(
            or_(
                ListingManagementCurrentMart.store_id.in_(store_values),
                ListingManagementCurrentMart.store_name.in_(store_values),
            )
        )

    totals: dict[tuple[str, str], Decimal] = {}

    for (
        source_account_ref,
        item_id,
        wfs_available_quantity,
    ) in service.daily_sales_repository.session.execute(statement).all():
        key = (str(source_account_ref), str(item_id))
        totals[key] = totals.get(key, ZERO) + _coerce_decimal(wfs_available_quantity)

    return totals


def _group_rows(
    rows: Sequence[DailySalesItemDayMart],
    *,
    period: OrderProfitExportPeriod,
    dimension: OrderProfitExportDimension,
) -> list[tuple[str, list[DailySalesItemDayMart]]]:
    grouped: dict[tuple[str, str, str], list[DailySalesItemDayMart]] = {}

    for row in rows:
        period_value = _period_key(row, period)
        source_account_ref = str(row.source_account_ref or "").strip()
        dimension_value = _dimension_key(row, dimension)

        if not period_value or not source_account_ref or not dimension_value:
            continue

        grouped.setdefault((period_value, source_account_ref, dimension_value), []).append(row)

    return [
        (period_value, item_rows)
        for (period_value, _source_account_ref, _dimension_value), item_rows in sorted(
            grouped.items(),
            key=lambda item: (item[0][0], item[0][2]),
        )
    ]


def _wfs_inventory_total(
    rows: Sequence[DailySalesItemDayMart],
    current_inventory: dict[tuple[str, str], Decimal],
) -> Decimal:
    keys = {
        (
            str(row.source_account_ref or "").strip(),
            str(row.item_id or "").strip(),
        )
        for row in rows
        if row.source_account_ref and row.item_id
    }

    return sum((current_inventory.get(key, ZERO) for key in keys), ZERO)


def _row_value_map(
    period_value: str,
    rows: Sequence[DailySalesItemDayMart],
    current_inventory: dict[tuple[str, str], Decimal],
) -> dict[str, object]:
    sales_qty = _sum(rows, "sales_qty")
    order_count = _sum(rows, "order_count")
    sales_amount = _sum(rows, "sales_amount")
    refund_amount = _sum(rows, "refund_amount")
    ad_spend_amount = _sum(rows, "ad_spend_amount")
    sem_ad_spend_amount = _sum(rows, "sem_ad_spend_amount")
    total_ad_spend = ad_spend_amount + sem_ad_spend_amount
    gross_profit_amount = _optional_sum(rows, "gross_profit_amount")
    purchase_cost_total = _optional_sum(rows, "purchase_cost_total_usd")
    first_leg_cost_total = _optional_sum(rows, "first_leg_cost_total_usd")
    storage_fee_total = _optional_sum(rows, "storage_fee_total_amount")
    total_cost = None if gross_profit_amount is None else sales_amount - gross_profit_amount

    return_rate = _weighted_average(
        rows,
        value_attr="return_rate_30d",
        weight_attr="sales_qty",
    )

    roi_denominator = _coerce_decimal(purchase_cost_total) + _coerce_decimal(first_leg_cost_total)

    return {
        "period": period_value,
        "product_id": " / ".join(_distinct_values(rows, "item_id")),
        "product_name": (
            _first_nonblank(rows, "local_name") or _first_nonblank(rows, "title") or ""
        ),
        "sku": " / ".join(_distinct_values(rows, "local_sku")),
        "msku": " / ".join(_distinct_values(rows, "msku")),
        "store": " / ".join(_distinct_stores(rows)),
        "owner": " / ".join(_distinct_values(rows, "owner_ref")),
        "platform": " / ".join(
            dict.fromkeys(
                _platform_label(value) for value in _distinct_values(rows, "platform_code")
            )
        ),
        "sales_qty": sales_qty,
        "order_count": order_count,
        "sales_amount": sales_amount,
        "avg_price": None if sales_qty <= 0 else (sales_amount / sales_qty).quantize(RATIO_SCALE),
        "sample_qty": _sum(rows, "sample_qty"),
        "sample_amount": _optional_sum(rows, "sample_amount"),
        "return_qty": _sum(rows, "return_qty"),
        "refund_amount": refund_amount,
        "return_rate_30d": None
        if return_rate is None
        else (return_rate * Decimal("100")).quantize(RATIO_SCALE),
        "total_ad_spend": total_ad_spend,
        "ad_ratio": _ratio_percent(total_ad_spend, sales_amount),
        "ad_spend": ad_spend_amount,
        "sem_ad_spend": sem_ad_spend_amount,
        "wfs_fee_total": _optional_sum(rows, "wfs_fee_total_amount"),
        "wfs_low_price_surcharge": _sum(rows, "wfs_low_price_surcharge_amount"),
        "wfs_fee_unit": _weighted_average(
            rows,
            value_attr="wfs_fee_unit_amount",
            weight_attr="sales_qty",
        ),
        "commission": _optional_sum(rows, "commission_fee_amount"),
        "purchase_cost_total": purchase_cost_total,
        "purchase_unit_cny": _weighted_average(
            rows,
            value_attr="purchase_cost_unit_cny",
            weight_attr="cost_quantity",
        ),
        "first_leg_cost_total": first_leg_cost_total,
        "first_leg_unit_cny": _weighted_average(
            rows,
            value_attr="first_leg_cost_unit_cny",
            weight_attr="cost_quantity",
        ),
        "storage_fee_total": storage_fee_total,
        "storage_unit": _weighted_average(
            rows,
            value_attr="storage_fee_unit_amount",
            weight_attr="cost_quantity",
        ),
        "wfs_inventory": _wfs_inventory_total(rows, current_inventory),
        "total_cost": total_cost,
        "order_profit": gross_profit_amount,
        "avg_profit_per_order": (
            None
            if gross_profit_amount is None or order_count <= 0
            else (gross_profit_amount / order_count).quantize(RATIO_SCALE)
        ),
        "gross_margin": _ratio_percent(gross_profit_amount, sales_amount),
        "roi": _ratio(gross_profit_amount, roi_denominator),
        "cost_status": _cost_status_label(rows),
    }


def _cost_status_label(rows: Sequence[DailySalesItemDayMart]) -> str:
    statuses = {
        str(getattr(row, "cost_status", "missing") or "missing").strip().lower() for row in rows
    }
    if statuses == {"complete"}:
        return "已完成"
    if "complete" in statuses or "partial" in statuses:
        return "部分缺失"
    return "待补齐"


def _selected_columns(columns: str | None) -> list[str]:
    if not columns:
        return DEFAULT_EXPORT_COLUMNS

    values = [item.strip() for item in columns.split(",") if item.strip()]
    selected = [value for value in values if value in ORDER_PROFIT_EXPORT_COLUMNS]
    return selected or DEFAULT_EXPORT_COLUMNS


def export_order_profit_csv(
    service: OrderProfitService,
    *,
    query: object,
    account_refs: frozenset[str],
    period: OrderProfitExportPeriod,
    dimension: OrderProfitExportDimension,
    columns: str | None,
) -> tuple[str, str]:
    rows = _filtered_daily_sales_rows(service, query=query, account_refs=account_refs)
    current_inventory = _current_wfs_inventory_by_item(service, rows, query.store_id)
    selected_columns = _selected_columns(columns)

    output = StringIO()
    writer = csv.writer(output)

    period_header = "统计月份" if period == "month" else "统计日期"
    writer.writerow(
        [period_header, *[ORDER_PROFIT_EXPORT_COLUMNS[key] for key in selected_columns]]
    )

    for period_value, group_rows in _group_rows(rows, period=period, dimension=dimension):
        value_map = _row_value_map(period_value, group_rows, current_inventory)
        writer.writerow(
            [
                period_value,
                *[_format_value(value_map.get(key)) for key in selected_columns],
            ]
        )

    start = (
        query.start_date.isoformat().replace("-", "")
        if isinstance(query.start_date, date)
        else "start"
    )
    end = query.end_date.isoformat().replace("-", "") if isinstance(query.end_date, date) else "end"
    filename = f"order-profit-{period}-{dimension}-{start}-{end}.csv"
    return output.getvalue(), filename
