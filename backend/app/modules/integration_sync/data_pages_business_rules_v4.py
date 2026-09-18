from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from app.modules.integration_sync.data_pages_business_rules_v3 import (
    DataPagesRealSyncRunner as HistoricalAdRunner,
)
from app.modules.integration_sync.data_pages_real_sync import (
    WALMART_PLATFORM_CODE_INT,
    DataPagesRealSyncError,
    _china_epoch,
    _field,
)

FIXED_UTC_MINUS_7 = timezone(timedelta(hours=-7), name="UTC-07:00")
CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")



def _refund_purchase_query_dates(rows: Iterable[Mapping[str, Any]]) -> tuple[date, ...]:
    """Return China calendar dates from provider purchaseTimeLocale values."""

    query_days: set[date] = set()
    for row in rows:
        raw = row.get("purchaseTimeLocale") or row.get("purchase_time_locale")
        if raw is None:
            continue
        value = str(raw).strip()
        if len(value) < 10:
            continue
        try:
            query_days.add(date.fromisoformat(value[:10]))
        except ValueError:
            continue
    return tuple(sorted(query_days))


def _refund_purchase_business_date(value: object) -> date | None:
    """Treat provider purchaseTimeLocale as UTC+8, then attribute sales in fixed UTC-7."""

    if value is None:
        return None
    raw = str(value).strip()
    try:
        purchase_at_china = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=CHINA_TZ
        )
    except ValueError:
        return None
    return purchase_at_china.astimezone(FIXED_UTC_MINUS_7).date()

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
            present = (
                self.session.execute(
                    text(
                        "select distinct platform_order_no from fact_walmart_order_items "
                        "where source_account_ref=:account and platform_order_no = any(:values)"
                    ),
                    {"account": self.source_account_ref, "values": list(purchase_ids)},
                )
                .scalars()
                .all()
            )
            missing_purchase.difference_update(str(value) for value in present if value)
        if customer_ids:
            present = (
                self.session.execute(
                    text(
                        "select distinct reference_no from fact_walmart_order_items "
                        "where source_account_ref=:account and reference_no = any(:values)"
                    ),
                    {"account": self.source_account_ref, "values": list(customer_ids)},
                )
                .scalars()
                .all()
            )
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

    def _refund_business_date(
        self,
        refund: Mapping[str, Any],
        order: Mapping[str, Any] | None,
    ) -> date | None:
        """Use raw refund purchaseTimeLocale converted from China time to fixed UTC-7."""

        del order
        return_id = _field(dict(refund), "source_return_order_id")
        purchase_id = _field(dict(refund), "purchase_order_id")
        msku = _field(dict(refund), "msku")
        for raw_row in getattr(self, "_refund_rows_for_hydration", ()):
            if _field(dict(raw_row), "returnOrderId", "return_order_id") != return_id:
                continue
            items = raw_row.get("items") if isinstance(raw_row.get("items"), list) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                if purchase_id and _field(item, "purchaseOrderId", "purchase_order_id") != purchase_id:
                    continue
                if msku and _field(item, "msku") != msku:
                    continue
                raw_time = item.get("purchaseTimeLocale") or raw_row.get("purchaseTimeLocale")
                return _refund_purchase_business_date(raw_time)
        return None

    def _reprice_refunds(self) -> int:
        refunds = getattr(self, "_refund_rows_for_hydration", ())
        if refunds:
            self.hydrate_refund_source_orders(refunds)
            # Item IDs for Return rows are intentionally resolved only from the
            # hydrated original order using store_id + MSKU + provider order IDs.
            self._resolve_refund_items()
        unresolved = super()._reprice_refunds()
        affected = (
            self.session.execute(
                text(
                    "select distinct b.business_date_la "
                    "from dws_walmart_refund_business_amounts b "
                    "join fact_walmart_refund_items f on f.id=b.refund_fact_id "
                    "where f.source_account_ref=:account and f.business_date_la=:refund_day "
                    "and b.calculation_status='calculated'"
                ),
                {"account": self.source_account_ref, "refund_day": self.business_date},
            )
            .scalars()
            .all()
        )
        self._refund_affected_business_dates = tuple(
            sorted(day for day in affected if day is not None)
        )
        return unresolved

    def _refresh_daily_sales_mart(self) -> int:
        """Refresh the refund event day plus every original sales day it changes."""

        current_day = self.business_date
        affected_days = tuple(
            day
            for day in getattr(self, "_refund_affected_business_dates", ())
            if day != current_day
        )
        try:
            for day in affected_days:
                self.business_date = day
                super()._refresh_daily_sales_mart()
                self._refresh_order_profit_mart()
            self.business_date = current_day
            return super()._refresh_daily_sales_mart()
        finally:
            self.business_date = current_day
