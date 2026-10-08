from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import NAMESPACE_URL, UUID, uuid5

from app.modules.data_pages.models import OrderProfitSkuDayMart
from app.modules.data_pages.repository import OrderProfitRepository

ZERO = Decimal("0")
RATIO_SCALE = Decimal("0.000001")
DAILY_SALES_COST_INCOMPLETE = "daily_sales_cost_incomplete"


@dataclass(frozen=True)
class OrderProfitRangeProjection:
    """Date-range order-profit row shaped like OrderProfitSkuDayMart.

    Order Profit is a range summary page, not a daily-detail page. The persisted
    MART table is daily by account + SKU, so this projection collapses the
    filtered date range into one row per account + local SKU while preserving the
    attributes consumed by OrderProfitService._to_read().
    """

    id: UUID
    business_date_la: date
    business_timezone: str
    source_account_ref: str
    local_sku: str
    item_ids_json: list[str]
    store_ids_json: list[str]
    store_count: int
    item_count: int
    sales_qty: Decimal
    order_count: Decimal
    sales_amount: Decimal
    sales_currency_code: str | None
    return_qty: Decimal
    refund_amount: Decimal | None
    refund_loss_amount: Decimal
    ad_spend_amount: Decimal | None
    sem_ad_spend_amount: Decimal
    commission_fee_amount: Decimal | None
    wfs_fee_total_amount: Decimal | None
    purchase_cost_total_usd: Decimal | None
    first_leg_cost_total_usd: Decimal | None
    storage_fee_total_amount: Decimal | None
    gross_profit_amount: Decimal | None
    gross_profit_currency_code: str | None
    gross_margin: Decimal | None
    roi: Decimal | None
    cost_status: str
    missing_cost_codes_json: list[str]
    calc_version: str
    calculated_at: datetime


def _decimal(value: object, default: Decimal = ZERO) -> Decimal:
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
        total += _decimal(value)
    return total if seen_value else None


def _sum(rows: Iterable[object], attr: str) -> Decimal:
    return _optional_sum(rows, attr) or ZERO


def _first_nonblank(rows: Iterable[object], attr: str, default: str | None = None) -> str | None:
    for row in rows:
        value = getattr(row, attr, None)
        if value is not None and str(value).strip():
            return str(value)
    return default


def _distinct_json_values(rows: Iterable[object], attr: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw_values = getattr(row, attr, None)
        if not isinstance(raw_values, list):
            continue
        for value in raw_values:
            normalized = str(value).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            values.append(normalized)
    return values


def _ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return (numerator / denominator).quantize(RATIO_SCALE)


def _normalized_status(value: object) -> str:
    status = str(value or "missing").strip().lower()
    if status in {"complete", "partial", "missing"}:
        return status
    return "partial"


def _cost_status(rows: Sequence[object]) -> str:
    """Aggregate range status using the persisted MART rollup semantics."""
    statuses = [_normalized_status(getattr(row, "cost_status", "missing")) for row in rows]
    if statuses and all(status == "complete" for status in statuses):
        return "complete"
    if any(status != "missing" for status in statuses):
        return "partial"
    return "missing"


def _missing_cost_codes(rows: Sequence[object]) -> list[str]:
    if _cost_status(rows) == "complete":
        return []

    codes: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw_codes = getattr(row, "missing_cost_codes_json", None)
        if not isinstance(raw_codes, list):
            continue
        for code in raw_codes:
            normalized = str(code).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            codes.append(normalized)

    if not codes:
        return [DAILY_SALES_COST_INCOMPLETE]
    return codes


def _range_id(
    *,
    source_account_ref: str,
    local_sku: str,
    start_date: date,
    end_date: date,
) -> UUID:
    range_key = f"szzsbj:order-profit-range:{source_account_ref}:{local_sku}:{start_date}:{end_date}"
    return uuid5(NAMESPACE_URL, range_key)


def _projection_for_sku(
    source_account_ref: str,
    local_sku: str,
    rows: Sequence[object],
) -> OrderProfitRangeProjection:
    latest_row = max(rows, key=lambda row: getattr(row, "business_date_la"))
    latest_calculated_row = max(rows, key=lambda row: getattr(row, "calculated_at"))
    start_date = min(getattr(row, "business_date_la") for row in rows)
    end_date = getattr(latest_row, "business_date_la")

    sales_amount = _sum(rows, "sales_amount")
    gross_profit_amount = _optional_sum(rows, "gross_profit_amount")
    purchase_cost_total_usd = _optional_sum(rows, "purchase_cost_total_usd")
    first_leg_cost_total_usd = _optional_sum(rows, "first_leg_cost_total_usd")
    roi_denominator = _decimal(purchase_cost_total_usd) + _decimal(first_leg_cost_total_usd)

    return OrderProfitRangeProjection(
        id=_range_id(
            source_account_ref=source_account_ref,
            local_sku=local_sku,
            start_date=start_date,
            end_date=end_date,
        ),
        business_date_la=end_date,
        business_timezone=_first_nonblank(
            rows,
            "business_timezone",
            "America/Los_Angeles",
        )
        or "America/Los_Angeles",
        source_account_ref=source_account_ref,
        local_sku=local_sku,
        item_ids_json=_distinct_json_values(rows, "item_ids_json"),
        store_ids_json=_distinct_json_values(rows, "store_ids_json"),
        store_count=len(_distinct_json_values(rows, "store_ids_json")),
        item_count=len(_distinct_json_values(rows, "item_ids_json")),
        sales_qty=_sum(rows, "sales_qty"),
        order_count=_sum(rows, "order_count"),
        sales_amount=sales_amount,
        sales_currency_code=_first_nonblank(rows, "sales_currency_code", "USD"),
        return_qty=_sum(rows, "return_qty"),
        refund_amount=_optional_sum(rows, "refund_amount"),
        refund_loss_amount=_sum(rows, "refund_loss_amount"),
        ad_spend_amount=_optional_sum(rows, "ad_spend_amount"),
        sem_ad_spend_amount=_sum(rows, "sem_ad_spend_amount"),
        commission_fee_amount=_optional_sum(rows, "commission_fee_amount"),
        wfs_fee_total_amount=_optional_sum(rows, "wfs_fee_total_amount"),
        purchase_cost_total_usd=purchase_cost_total_usd,
        first_leg_cost_total_usd=first_leg_cost_total_usd,
        storage_fee_total_amount=_optional_sum(rows, "storage_fee_total_amount"),
        gross_profit_amount=gross_profit_amount,
        gross_profit_currency_code=_first_nonblank(rows, "gross_profit_currency_code", "USD"),
        gross_margin=_ratio(gross_profit_amount, sales_amount),
        roi=_ratio(gross_profit_amount, roi_denominator),
        cost_status=_cost_status(rows),
        missing_cost_codes_json=_missing_cost_codes(rows),
        calc_version=_first_nonblank(rows, "calc_version", "range-summary") or "range-summary",
        calculated_at=getattr(latest_calculated_row, "calculated_at"),
    )


def _order_profit_sort_key(row: OrderProfitRangeProjection) -> tuple[Decimal, Decimal, str]:
    return (-_decimal(row.sales_qty), -_decimal(row.sales_amount), row.local_sku)


def aggregate_order_profit_rows(rows: Sequence[object]) -> list[OrderProfitRangeProjection]:
    """Collapse daily SKU MART rows into one date-range row per account + SKU."""
    grouped: dict[tuple[str, str], list[object]] = {}
    for row in rows:
        source_account_ref = str(getattr(row, "source_account_ref", "")).strip()
        local_sku = str(getattr(row, "local_sku", "")).strip()
        if not source_account_ref or not local_sku:
            continue
        grouped.setdefault((source_account_ref, local_sku), []).append(row)

    projections = [
        _projection_for_sku(source_account_ref, local_sku, sku_rows)
        for (source_account_ref, local_sku), sku_rows in grouped.items()
    ]
    projections.sort(key=_order_profit_sort_key)
    return projections


def _list_order_profit_range_summary(
    self: OrderProfitRepository,
    *,
    account_refs: frozenset[str],
    start_date: date | None,
    end_date: date | None,
    store_id: str | None,
    search_field: str,
    keyword: str,
    page: int,
    page_size: int,
) -> tuple[Sequence[OrderProfitRangeProjection], int, datetime | None]:
    statement = self._filtered_statement(
        account_refs=account_refs,
        start_date=start_date,
        end_date=end_date,
        store_id=store_id,
        search_field=search_field,
        keyword=keyword,
    )

    raw_rows = list(
        self.session.scalars(
            statement.order_by(
                OrderProfitSkuDayMart.source_account_ref.asc(),
                OrderProfitSkuDayMart.local_sku.asc(),
                OrderProfitSkuDayMart.business_date_la.asc(),
            )
        ).all()
    )
    grouped_rows = aggregate_order_profit_rows(raw_rows)
    offset = (page - 1) * page_size
    latest_calculated_at = max(
        (getattr(row, "calculated_at") for row in raw_rows if getattr(row, "calculated_at", None)),
        default=None,
    )
    return grouped_rows[offset : offset + page_size], len(grouped_rows), latest_calculated_at


def install_order_profit_range_summary() -> None:
    current = OrderProfitRepository.list_order_profit
    if getattr(current, "_order_profit_range_summary", False):
        return
    setattr(_list_order_profit_range_summary, "_order_profit_range_summary", True)
    setattr(
        OrderProfitRepository,
        "list_order_profit",
        _list_order_profit_range_summary,
    )
