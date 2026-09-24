from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.modules.after_sales.repository import AfterSalesRefundRepository
from app.modules.after_sales.schemas import (
    FilterOption,
    RefundBaseQuery,
    RefundComparison,
    RefundFacets,
    RefundHeatRow,
    RefundItemListData,
    RefundItemQuery,
    RefundItemRead,
    RefundLagAnalysis,
    RefundLagBucket,
    RefundOverviewData,
    RefundProductAnalysisData,
    RefundProductAnalysisQuery,
    RefundProductDetail,
    RefundProductRead,
    RefundProductTrendPoint,
    RefundReasonRead,
    RefundReasonTag,
    RefundResponsibilityRead,
    RefundResponsibilityTag,
    RefundSummary,
    RefundTrendPoint,
)

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_SOURCE_OBJECTS = [
    "after_sales_refund_items",
    "mart_daily_sales_item_day",
    "dim_lingxing_stores",
    "products",
    "dwd_lingxing_sku_identity_index",
    "dwd_lingxing_sku_product_info_current",
    "after_sales_reason_dict",
    "after_sales_responsibility_dict",
    "after_sales_reason_rules",
]
_LAG_KEYS = ("0_3", "4_7", "8_14", "15_30", "31_plus")


def _decimal(value: Any) -> Decimal:
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _rate(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator <= 0:
        return None
    return (numerator / denominator * _HUNDRED).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _change_rate(current: Decimal, previous: Decimal) -> Decimal | None:
    if previous == 0:
        return None
    return ((current - previous) / previous * _HUNDRED).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


def _date_axis(start_date: date, end_date: date) -> list[date]:
    days = (end_date - start_date).days
    return [start_date + timedelta(days=offset) for offset in range(days + 1)]


class AfterSalesRefundService:
    """Build UI-ready refund metrics from governed refund and daily-sales facts."""

    def __init__(self, session: Session) -> None:
        self.repository = AfterSalesRefundRepository(session)

    @property
    def source_objects(self) -> list[str]:
        return list(_SOURCE_OBJECTS)

    def overview(
        self,
        query: RefundBaseQuery,
        account_refs: frozenset[str],
    ) -> RefundOverviewData:
        current = self.repository.refund_stats(query, account_refs)
        current_sales = self.repository.sales_qty(query, account_refs)
        summary = self._summary(current, current_sales)

        period_days = (query.end_date - query.start_date).days + 1
        previous_end = query.start_date - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)
        previous = self.repository.refund_stats(
            query,
            account_refs,
            start_date=previous_start,
            end_date=previous_end,
        )
        previous_sales = self.repository.sales_qty(
            query,
            account_refs,
            start_date=previous_start,
            end_date=previous_end,
        )
        previous_summary = self._summary(previous, previous_sales)

        comparison = RefundComparison(
            previous_start_date=previous_start,
            previous_end_date=previous_end,
            refund_orders_change_rate=_change_rate(
                Decimal(summary.refund_orders), Decimal(previous_summary.refund_orders)
            ),
            refund_qty_change_rate=_change_rate(summary.refund_qty, previous_summary.refund_qty),
            refund_loss_change_rate=_change_rate(
                summary.refund_loss_amount, previous_summary.refund_loss_amount
            ),
            refund_rate_change_pp=(
                summary.refund_rate - previous_summary.refund_rate
                if summary.refund_rate is not None and previous_summary.refund_rate is not None
                else None
            ),
        )

        trend = self._trend(query, account_refs)
        reasons = [
            RefundReasonRead(**row)
            for row in self.repository.reason_breakdown(query, account_refs, limit=20)
        ]
        responsibilities = [
            RefundResponsibilityRead(**row)
            for row in self.repository.responsibility_breakdown(query, account_refs, limit=20)
        ]
        raw_facets = self.repository.facets(query, account_refs)
        facets = RefundFacets(
            stores=[FilterOption(**item) for item in raw_facets["stores"]],
            owners=[FilterOption(**item) for item in raw_facets["owners"]],
            reasons=[FilterOption(**item) for item in raw_facets["reasons"]],
            responsibilities=[FilterOption(**item) for item in raw_facets["responsibilities"]],
        )
        return RefundOverviewData(
            summary=summary,
            comparison=comparison,
            trend=trend,
            reasons=reasons,
            responsibilities=responsibilities,
            facets=facets,
        )

    def product_analysis(
        self,
        query: RefundProductAnalysisQuery,
        account_refs: frozenset[str],
    ) -> RefundProductAnalysisData:
        summary_rows = self.repository.product_summary(
            query,
            account_refs,
            limit=query.limit,
        )
        items = [self._product_read(row) for row in summary_rows]
        dates = _date_axis(query.start_date, query.end_date)
        product_keys = [item.product_key for item in items]
        heat_raw = self.repository.heat_rows(query, account_refs, product_keys)
        heat_map: dict[str, dict[date, Decimal]] = {key: {} for key in product_keys}
        for row in heat_raw:
            heat_map.setdefault(str(row["product_key"]), {})[row["day"]] = _decimal(
                row["refund_qty"]
            )
        heat = [
            RefundHeatRow(
                product_key=key,
                values=[heat_map.get(key, {}).get(day, _ZERO) for day in dates],
            )
            for key in product_keys
        ]

        overall_lag = self._lag(query, account_refs)

        selected_key = query.selected_product_key.strip()
        if selected_key and selected_key not in product_keys:
            selected_key = ""
        if not selected_key and product_keys:
            selected_key = product_keys[0]

        selected = None
        if selected_key:
            base = next(item for item in items if item.product_key == selected_key)
            trend = self._product_trend(query, account_refs, selected_key)
            reasons = [
                RefundReasonRead(**row)
                for row in self.repository.reason_breakdown(
                    query,
                    account_refs,
                    product_key=selected_key,
                    limit=10,
                )
            ]
            product_lag = self._lag(query, account_refs, selected_key)
            selected = RefundProductDetail(
                **base.model_dump(),
                trend=trend,
                reasons=reasons,
                lag=product_lag,
            )

        return RefundProductAnalysisData(
            dates=dates,
            items=items,
            heat=heat,
            lag=overall_lag,
            selected=selected,
        )

    def list_items(
        self,
        query: RefundItemQuery,
        account_refs: frozenset[str],
    ) -> tuple[RefundItemListData, int, Any]:
        rows, total, latest = self.repository.list_items(query, account_refs)
        return (
            RefundItemListData(items=[self._item_read(row) for row in rows]),
            total,
            latest,
        )

    def latest_updated_at(
        self,
        query: RefundBaseQuery | RefundItemQuery,
        account_refs: frozenset[str],
    ) -> Any:
        return self.repository.latest_updated_at(query, account_refs)

    def _summary(self, row: dict[str, Any], sales_qty: Decimal) -> RefundSummary:
        refund_qty = _decimal(row["refund_qty"])
        refund_amount = _decimal(row["refund_amount"])
        refund_loss = _decimal(row["refund_loss_amount"])
        return RefundSummary(
            refund_orders=int(row["refund_orders"] or 0),
            refund_item_rows=int(row["refund_item_rows"] or 0),
            refund_qty=refund_qty,
            refund_amount=refund_amount,
            refund_currency_code=row["refund_currency_code"],
            refund_loss_amount=refund_loss,
            sales_qty=sales_qty,
            refund_rate=_rate(refund_qty, sales_qty),
            avg_refund_amount_per_unit=(refund_amount / refund_qty if refund_qty > 0 else None),
            avg_refund_loss_per_unit=(refund_loss / refund_qty if refund_qty > 0 else None),
        )

    def _trend(
        self,
        query: RefundBaseQuery,
        account_refs: frozenset[str],
    ) -> list[RefundTrendPoint]:
        refund_rows = {row["day"]: row for row in self.repository.refund_trend(query, account_refs)}
        sales_rows = {
            row["day"]: _decimal(row["sales_qty"])
            for row in self.repository.sales_trend(query, account_refs)
        }
        result = []
        for day in _date_axis(query.start_date, query.end_date):
            refund = refund_rows.get(day, {})
            refund_qty = _decimal(refund.get("refund_qty"))
            sales_qty = sales_rows.get(day, _ZERO)
            result.append(
                RefundTrendPoint(
                    date=day,
                    refund_orders=int(refund.get("refund_orders") or 0),
                    refund_qty=refund_qty,
                    refund_amount=_decimal(refund.get("refund_amount")),
                    refund_loss_amount=_decimal(refund.get("refund_loss_amount")),
                    sales_qty=sales_qty,
                    refund_rate=_rate(refund_qty, sales_qty),
                )
            )
        return result

    def _product_read(self, row: dict[str, Any]) -> RefundProductRead:
        return RefundProductRead(
            product_key=str(row["product_key"]),
            store_id=str(row["store_id"]),
            store_name=row["store_name"],
            local_sku=row["local_sku"],
            msku=row["msku"],
            item_id=row["item_id"],
            product_name=row["product_name"],
            owner_ref=row["owner_ref"],
            refund_orders=int(row["refund_orders"] or 0),
            refund_qty=_decimal(row["refund_qty"]),
            refund_amount=_decimal(row["refund_amount"]),
            refund_loss_amount=_decimal(row["refund_loss_amount"]),
            sales_qty=_decimal(row["sales_qty"]),
            refund_rate=(_decimal(row["refund_rate"]) if row["refund_rate"] is not None else None),
            top_reason=(
                RefundReasonTag(
                    code=str(row["top_reason_code"]),
                    name=row["top_reason_name"] or "未分类",
                    category_code=row["top_reason_category_code"] or "PENDING",
                    category_name=row["top_reason_category_name"] or "待判定",
                    color=row["top_reason_color"] or "#8C8C8C",
                )
                if row.get("top_reason_code")
                else None
            ),
            top_responsibility=(
                RefundResponsibilityTag(
                    code=str(row["top_responsibility_code"]),
                    name=row["top_responsibility_name"] or "待判定",
                    color=row["top_responsibility_color"] or "#8C8C8C",
                    source="AGGREGATED",
                    confidence="N/A",
                )
                if row.get("top_responsibility_code")
                else None
            ),
            risk_level="pending",
        )

    def _item_read(self, row: dict[str, Any]) -> RefundItemRead:
        return RefundItemRead(
            id=str(row["id"]),
            store_id=str(row["store_id"]),
            store_name=row["store_name"],
            owner_ref=row["owner_ref"],
            item_id=row["item_id"],
            product_name=row["product_name"],
            local_sku=row["local_sku"],
            msku=row["msku"],
            return_order_id=str(row["return_order_id"]),
            customer_order_id=row["customer_order_id"],
            purchase_order_id=row["purchase_order_id"],
            platform_order_id=str(row["platform_order_id"]),
            purchase_time_at=row["purchase_time_at"],
            refund_time_at=row["refund_time_at"],
            refund_lag_days=(
                _decimal(row["refund_lag_days"]) if row["refund_lag_days"] is not None else None
            ),
            return_qty=_decimal(row["return_qty"]),
            refund_amount=(
                _decimal(row["refund_amount"]) if row["refund_amount"] is not None else None
            ),
            refund_currency_code=row["refund_currency_code"],
            refund_loss_amount=(
                _decimal(row["refund_loss_amount"])
                if row["refund_loss_amount"] is not None
                else None
            ),
            return_reason_code=row["return_reason_code"],
            return_description=row["return_description"],
            reason=RefundReasonTag(
                code=str(row["reason_code"]),
                name=str(row["reason_name"]),
                category_code=str(row["reason_category_code"]),
                category_name=str(row["reason_category_name"]),
                color=str(row["reason_color"]),
            ),
            responsibility=RefundResponsibilityTag(
                code=str(row["responsibility_code"]),
                name=str(row["responsibility_name"]),
                color=str(row["responsibility_color"]),
                source=str(row["responsibility_source"]),
                confidence=str(row["responsibility_confidence"]),
            ),
            current_refund_status=row["current_refund_status"],
            refund_completed=bool(row["refund_completed"]),
        )

    def _product_trend(
        self,
        query: RefundProductAnalysisQuery,
        account_refs: frozenset[str],
        product_key: str,
    ) -> list[RefundProductTrendPoint]:
        refund_rows = {
            row["day"]: row
            for row in self.repository.refund_trend(
                query,
                account_refs,
                product_key=product_key,
            )
        }
        sales_rows = {
            row["day"]: _decimal(row["sales_qty"])
            for row in self.repository.sales_trend(
                query,
                account_refs,
                product_key=product_key,
            )
        }
        result = []
        for day in _date_axis(query.start_date, query.end_date):
            refund = refund_rows.get(day, {})
            refund_qty = _decimal(refund.get("refund_qty"))
            sales_qty = sales_rows.get(day, _ZERO)
            result.append(
                RefundProductTrendPoint(
                    date=day,
                    refund_qty=refund_qty,
                    refund_orders=int(refund.get("refund_orders") or 0),
                    refund_amount=_decimal(refund.get("refund_amount")),
                    refund_loss_amount=_decimal(refund.get("refund_loss_amount")),
                    sales_qty=sales_qty,
                    refund_rate=_rate(refund_qty, sales_qty),
                )
            )
        return result

    def _lag(
        self,
        query: RefundProductAnalysisQuery,
        account_refs: frozenset[str],
        product_key: str | None = None,
    ) -> RefundLagAnalysis:
        summary, rows = self.repository.lag_analysis(query, account_refs, product_key)
        by_key = {str(row["bucket_key"]): row for row in rows}
        total_qty = sum((_decimal(row["refund_qty"]) for row in rows), _ZERO)
        buckets = []
        for key in _LAG_KEYS:
            row = by_key.get(key, {})
            qty = _decimal(row.get("refund_qty"))
            buckets.append(
                RefundLagBucket(
                    key=key,  # type: ignore[arg-type]
                    refund_orders=int(row.get("refund_orders") or 0),
                    refund_qty=qty,
                    ratio=_rate(qty, total_qty),
                    refund_amount=_decimal(row.get("refund_amount")),
                    refund_loss_amount=_decimal(row.get("refund_loss_amount")),
                )
            )
        main = max(buckets, key=lambda item: item.refund_qty, default=None)
        main_key = main.key if main and main.refund_qty > 0 else None
        return RefundLagAnalysis(
            average_days=(
                _decimal(summary["average_days"]).quantize(Decimal("0.01"))
                if summary["average_days"] is not None
                else None
            ),
            median_days=(
                _decimal(summary["median_days"]).quantize(Decimal("0.01"))
                if summary["median_days"] is not None
                else None
            ),
            main_bucket=main_key,
            main_bucket_ratio=main.ratio if main_key and main is not None else None,
            eligible_item_rows=int(summary["eligible_item_rows"] or 0),
            missing_time_rows=int(summary["missing_time_rows"] or 0),
            buckets=buckets,
        )
