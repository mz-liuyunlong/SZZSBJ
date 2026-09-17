from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text

from app.modules.integration_sync.data_pages_business_rules_v3 import (
    DataPagesRealSyncRunner as HistoricalAdRunner,
)
from app.modules.integration_sync.data_pages_real_sync import (
    DataPagesRealSyncError,
    WALMART_PLATFORM_CODE_INT,
    _china_epoch,
    _field,
    _row_count,
)


def _refund_purchase_query_dates(rows: Iterable[Mapping[str, Any]]) -> tuple[date, ...]:
    """Return China-date Order V2 windows that can contain refund source orders.

    Return purchaseTimeLocale is marketplace-local. Existing Order V2 requests are
    China-day based, so each marketplace-local purchase date is covered by that date
    plus the following China date. This avoids a blind broad historical backfill while
    preserving the existing Order V2 request contract.
    """

    query_days: set[date] = set()
    for row in rows:
        raw = row.get("purchaseTimeLocale") or row.get("purchase_time_locale")
        if raw is None:
            continue
        value = str(raw).strip()
        if len(value) < 10:
            continue
        try:
            purchase_day = date.fromisoformat(value[:10])
        except ValueError:
            continue
        query_days.add(purchase_day)
        query_days.add(purchase_day + timedelta(days=1))
    return tuple(sorted(query_days))


def _refund_identifiers(rows: Iterable[Mapping[str, Any]]) -> tuple[set[str], set[str]]:
    purchase_ids: set[str] = set()
    customer_ids: set[str] = set()
    for row in rows:
        customer = _field(dict(row), "customerOrderId", "customer_order_id")
        if customer:
            customer_ids.add(customer)
        items = row.get("items") if isinstance(row.get("items"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            purchase = _field(item, "purchaseOrderId", "purchase_order_id")
            if purchase:
                purchase_ids.add(purchase)
    return purchase_ids, customer_ids


def _order_matches_refund_identifiers(
    row: Mapping[str, Any],
    purchase_ids: set[str],
    customer_ids: set[str],
) -> bool:
    reference_no = _field(dict(row), "reference_no", "referenceNo")
    if reference_no and reference_no in customer_ids:
        return True
    items = row.get("item_info") if isinstance(row.get("item_info"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        platform_order_no = _field(item, "platform_order_no")
        if platform_order_no and platform_order_no in purchase_ids:
            return True
    return False


class DataPagesRealSyncRunner(HistoricalAdRunner):
    """Finalize Daily Sales row scope and hydrate historical refund source orders."""

    def _fetch_return_all(self) -> list[dict[str, Any]]:
        rows = super()._fetch_return_all()
        self._refund_rows_for_hydration = tuple(dict(row) for row in rows)
        return rows

    def _order_body_for_day(self, day: date, offset: int, size: int) -> dict[str, Any]:
        return {
            "date_type": "global_purchase_time",
            "start_time": _china_epoch(day, end=False),
            "end_time": _china_epoch(day, end=True),
            "offset": offset,
            "length": size,
            "platform_code": [WALMART_PLATFORM_CODE_INT],
            "store_id": list(self.store_ids),
        }

    def _missing_refund_identifiers(
        self,
        purchase_ids: set[str],
        customer_ids: set[str],
    ) -> tuple[set[str], set[str]]:
        missing_purchase = set(purchase_ids)
        missing_customer = set(customer_ids)
        if purchase_ids:
            present = self.session.execute(
                text(
                    "select distinct platform_order_no from fact_walmart_order_items "
                    "where source_account_ref=:account and platform_order_no = any(:values)"
                ),
                {"account": self.source_account_ref, "values": list(purchase_ids)},
            ).scalars().all()
            missing_purchase.difference_update(str(value) for value in present if value)
        if customer_ids:
            present = self.session.execute(
                text(
                    "select distinct reference_no from fact_walmart_order_items "
                    "where source_account_ref=:account and reference_no = any(:values)"
                ),
                {"account": self.source_account_ref, "values": list(customer_ids)},
            ).scalars().all()
            missing_customer.difference_update(str(value) for value in present if value)
        return missing_purchase, missing_customer

    def hydrate_refund_source_orders(self, refunds: Iterable[Mapping[str, Any]]) -> int:
        """Persist only historical Order V2 rows referenced by current refund data."""

        if self.client is None:
            raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_CLIENT_REQUIRED")
        refund_rows = [dict(row) for row in refunds]
        purchase_ids, customer_ids = _refund_identifiers(refund_rows)
        missing_purchase, missing_customer = self._missing_refund_identifiers(
            purchase_ids,
            customer_ids,
        )
        if not missing_purchase and not missing_customer:
            return 0

        written = 0
        for query_day in _refund_purchase_query_dates(refund_rows):
            rows = self._fetch_offset_all(
                "order_v2_list",
                lambda offset, size, query_day=query_day: self._order_body_for_day(
                    query_day,
                    offset,
                    size,
                ),
                minimum_page_size=20,
            )
            matched = [
                row
                for row in rows
                if _order_matches_refund_identifiers(
                    row,
                    missing_purchase,
                    missing_customer,
                )
            ]
            if not matched:
                continue
            original_day = self.business_date
            try:
                self.business_date = query_day
                written += self._write_orders(matched)
                self._resolve_order_items()
            finally:
                self.business_date = original_day
            missing_purchase, missing_customer = self._missing_refund_identifiers(
                missing_purchase,
                missing_customer,
            )
            if not missing_purchase and not missing_customer:
                break
        return written

    def _reprice_refunds(self) -> int:
        refunds = getattr(self, "_refund_rows_for_hydration", ())
        if refunds:
            self.hydrate_refund_source_orders(refunds)
        return super()._reprice_refunds()

    def _refresh_daily_sales_mart(self) -> int:
        super()._refresh_daily_sales_mart()
        self.session.execute(
            text(
                "delete from mart_daily_sales_item_day m "
                "where m.source_account_ref=:account and m.business_date_la=:day "
                "and coalesce(m.ad_spend_amount,0)=0 and not exists ("
                "select 1 from fact_walmart_sales_item_daily s "
                "where s.source_account_ref=m.source_account_ref "
                "and s.business_date_la=m.business_date_la "
                "and s.store_id=m.store_id and s.item_id=m.item_id "
                "and s.allocation_status='direct')"
            ),
            {"account": self.source_account_ref, "day": self.business_date},
        )
        return _row_count(
            self.session,
            "mart_daily_sales_item_day",
            self.source_account_ref,
            self.business_date,
        )
