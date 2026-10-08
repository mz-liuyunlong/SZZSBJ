from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import NAMESPACE_URL, UUID, uuid5

from app.modules.data_pages.models import DailySalesItemDayMart
from app.modules.data_pages.schemas import OrderProfitListData, OrderProfitSummaryRead
from app.modules.data_pages.service import OrderProfitService, _percent_ratio

ZERO = Decimal("0")
RATIO_SCALE = Decimal("0.000001")
DAILY_SALES_COST_INCOMPLETE = "daily_sales_cost_incomplete"
_INSTALLED = False


@dataclass(frozen=True)
class OrderProfitRangeProjection:
    """Date-range order-profit row shaped for OrderProfitService._to_read().

    Order Profit is a product range-summary page. The persisted order-profit MART
    is daily by account + SKU and cannot answer item/store/owner filtered totals
    without mixing sibling item IDs under the same local SKU. This projection is
    built from filtered Daily Sales item-day rows, so filters are applied before
    aggregation.
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


def _first_nonblank(rows: Iterable[object], attr: str, default: str | None = None) -> str | None:
    for row in rows:
        value = getattr(row, attr, None)
        if value is not None and str(value).strip():
            return str(value)
    return default


def _distinct_values(rows: Iterable[object], attr: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw_value = getattr(row, attr, None)
        if raw_value is None:
            continue
        normalized = str(raw_value).strip()
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


def _refund_loss_from_daily_rows(rows: Sequence[object]) -> Decimal:
    total = ZERO
    for row in rows:
        refund_amount = getattr(row, "refund_amount", None)
        if refund_amount is None:
            continue
        commission_rate = _coerce_decimal(getattr(row, "commission_rate", None))
        total += max(_coerce_decimal(refund_amount) * (Decimal("1") - commission_rate), ZERO)
    return total


def _range_id(
    *,
    source_account_ref: str,
    item_id: str,
    start_date: date,
    end_date: date,
) -> UUID:
    range_key = (
        f"szzsbj:order-profit-item-range:{source_account_ref}:{item_id}:{start_date}:{end_date}"
    )
    return uuid5(NAMESPACE_URL, range_key)


def _projection_for_item(
    source_account_ref: str,
    item_id: str,
    rows: Sequence[DailySalesItemDayMart],
) -> OrderProfitRangeProjection:
    latest_row = max(rows, key=lambda row: row.business_date_la)
    latest_calculated_row = max(rows, key=lambda row: row.calculated_at)
    start_date = min(row.business_date_la for row in rows)
    end_date = latest_row.business_date_la

    sales_amount = _sum(rows, "sales_amount")
    gross_profit_amount = _optional_sum(rows, "gross_profit_amount")
    purchase_cost_total_usd = _optional_sum(rows, "purchase_cost_total_usd")
    first_leg_cost_total_usd = _optional_sum(rows, "first_leg_cost_total_usd")
    roi_denominator = _coerce_decimal(purchase_cost_total_usd) + _coerce_decimal(
        first_leg_cost_total_usd
    )
    store_ids = _distinct_values(rows, "store_id")

    return OrderProfitRangeProjection(
        id=_range_id(
            source_account_ref=source_account_ref,
            item_id=item_id,
            start_date=start_date,
            end_date=end_date,
        ),
        business_date_la=end_date,
        business_timezone=_first_nonblank(rows, "business_timezone", "America/Los_Angeles")
        or "America/Los_Angeles",
        source_account_ref=source_account_ref,
        local_sku=_first_nonblank(rows, "local_sku", item_id) or item_id,
        item_ids_json=[item_id],
        store_ids_json=store_ids,
        store_count=len(store_ids),
        item_count=1,
        sales_qty=_sum(rows, "sales_qty"),
        order_count=_sum(rows, "order_count"),
        sales_amount=sales_amount,
        sales_currency_code=_first_nonblank(rows, "sales_currency_code", "USD"),
        return_qty=_sum(rows, "return_qty"),
        refund_amount=_optional_sum(rows, "refund_amount"),
        refund_loss_amount=_refund_loss_from_daily_rows(rows),
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
        calc_version=_first_nonblank(rows, "calc_version", "daily-sales-range-summary")
        or "daily-sales-range-summary",
        calculated_at=latest_calculated_row.calculated_at,
    )


def _order_profit_sort_key(row: OrderProfitRangeProjection) -> tuple[Decimal, Decimal, str]:
    return (-_coerce_decimal(row.sales_qty), -_coerce_decimal(row.sales_amount), row.local_sku)


def aggregate_order_profit_rows(
    rows: Sequence[DailySalesItemDayMart],
) -> list[OrderProfitRangeProjection]:
    """Collapse filtered item-day rows into one date-range row per account + item."""
    grouped: dict[tuple[str, str], list[DailySalesItemDayMart]] = {}
    for row in rows:
        source_account_ref = str(row.source_account_ref or "").strip()
        item_id = str(row.item_id or "").strip()
        if not source_account_ref or not item_id:
            continue
        grouped.setdefault((source_account_ref, item_id), []).append(row)

    projections = [
        _projection_for_item(source_account_ref, item_id, item_rows)
        for (source_account_ref, item_id), item_rows in grouped.items()
    ]
    projections.sort(key=_order_profit_sort_key)
    return projections


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
    return list(
        service.daily_sales_repository.session.scalars(
            statement.order_by(
                DailySalesItemDayMart.source_account_ref.asc(),
                DailySalesItemDayMart.item_id.asc(),
                DailySalesItemDayMart.business_date_la.asc(),
            )
        ).all()
    )


def _latest_calculated_at(rows: Sequence[DailySalesItemDayMart]) -> datetime | None:
    return max((row.calculated_at for row in rows if row.calculated_at), default=None)


def _summary_from_daily_rows(rows: Sequence[DailySalesItemDayMart]) -> OrderProfitSummaryRead:
    sales_amount = _sum(rows, "sales_amount")
    ad_spend_amount = _sum(rows, "ad_spend_amount")
    sem_ad_spend_amount = _sum(rows, "sem_ad_spend_amount")
    total_ad_spend_amount = ad_spend_amount + sem_ad_spend_amount
    order_profit_amount = _sum(rows, "gross_profit_amount")

    return OrderProfitSummaryRead(
        sales_qty=_sum(rows, "sales_qty"),
        order_count=_sum(rows, "order_count"),
        sales_amount=sales_amount,
        sales_currency_code=_first_nonblank(rows, "sales_currency_code", "USD") or "USD",
        return_qty=_sum(rows, "return_qty"),
        refund_amount=_sum(rows, "refund_amount"),
        refund_loss_amount=_refund_loss_from_daily_rows(rows),
        refund_currency_code=_first_nonblank(rows, "refund_currency_code", "USD") or "USD",
        order_profit_amount=order_profit_amount,
        order_profit_currency_code=_first_nonblank(rows, "gross_profit_currency_code", "USD")
        or "USD",
        ad_spend_amount=ad_spend_amount,
        sem_ad_spend_amount=sem_ad_spend_amount,
        total_ad_spend_amount=total_ad_spend_amount,
        ad_spend_currency_code=_first_nonblank(rows, "ad_spend_currency_code", "USD") or "USD",
        ad_ratio=_percent_ratio(total_ad_spend_amount, sales_amount),
    )


def _list_order_profit_from_daily_sales(
    self: OrderProfitService,
    *,
    query: object,
    account_refs: frozenset[str],
) -> tuple[OrderProfitListData, int, datetime | None]:
    raw_rows = _filtered_daily_sales_rows(self, query=query, account_refs=account_refs)
    grouped_rows = aggregate_order_profit_rows(raw_rows)
    offset = (query.page - 1) * query.page_size
    page_rows = grouped_rows[offset : offset + query.page_size]

    return (
        OrderProfitListData(
            items=[self._to_read(row) for row in page_rows],
            summary=_summary_from_daily_rows(raw_rows),
        ),
        len(grouped_rows),
        _latest_calculated_at(raw_rows),
    )


def install_order_profit_range_summary() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    OrderProfitService.list_order_profit = _list_order_profit_from_daily_sales
    _INSTALLED = True
