from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import text

from app.modules.after_sales.classification import AfterSalesReasonClassifier
from app.modules.integration_sync.data_pages_business_rules_v2 import (
    DAILY_SALES_V2_VERSION,
    _low_price_delivery_surcharge,
)
from app.modules.integration_sync.data_pages_business_rules_v3 import (
    DataPagesRealSyncRunner as HistoricalAdRunner,
)
from app.modules.integration_sync.data_pages_mart_invariants import (
    snapshot_automatic_marts,
    validate_automatic_mart_replay,
)
from scripts.import_after_sales_refund_items import (
    build_cost_map,
    build_listing_map,
    build_rows,
    collect_excluded_item_keys,
    delete_excluded_rows,
    find_listing_source_table,
    upsert_rows,
)


class DataPagesRealSyncRunner(HistoricalAdRunner):
    """Use Refund Management as the only refund truth for Daily Sales.

    Return API rows are written into after_sales_refund_items with the same governed
    rules used by Refund Management. Refund Management keeps the raw refund event date,
    while Daily Sales attributes refund quantity/loss to purchase_time_at::date directly
    (purchase_time_at is already the Walmart/US order time and is not timezone-shifted).
    Purchase days without SaleStat are deferred until sales facts exist. The legacy
    refund fact/DWS chain remains retired.
    """

    def _write_refunds(self, rows: Iterable[dict[str, Any]]) -> int:
        """Persist current Return rows into the governed Refund Management fact."""

        payload = {
            "data": {
                "list": [dict(row) for row in rows],
            }
        }
        conn = self.session.connection()
        listing_source_table = find_listing_source_table(conn)
        listing_map = build_listing_map(conn, listing_source_table)
        cost_map = build_cost_map(conn, self.business_date)
        facts = build_rows(
            payload,
            source_account_ref=self.source_account_ref,
            target_date=self.business_date,
            listing_map=listing_map,
            cost_map=cost_map,
        )

        classifier = AfterSalesReasonClassifier.from_executor(conn)
        for fact in facts:
            classified = classifier.classify(
                fact["return_reason_code"],
                fact["return_description"],
            )
            fact.update(classified.as_storage_values())

        excluded_keys = collect_excluded_item_keys(payload)
        delete_excluded_rows(
            conn,
            source_account_ref=self.source_account_ref,
            keys=excluded_keys,
        )
        upsert_rows(conn, facts)
        return len(facts)

    def _resolve_refund_items(self) -> int:
        """Report Refund Management rows that still lack strict Daily Sales identity."""

        return int(
            self.session.execute(
                text(
                    "select count(*) from after_sales_refund_items "
                    "where source_account_ref=:account and platform_code='walmart' "
                    "and refund_effective=true and return_order_at::date=:day "
                    "and (store_id is null or item_id is null or msku is null or trim(msku)='')"
                ),
                {
                    "account": self.source_account_ref,
                    "day": self.business_date,
                },
            ).scalar_one()
            or 0
        )

    def _reprice_refunds(self) -> int:
        """Collect purchase dates changed by the current refund-event-day sync."""

        affected = (
            self.session.execute(
                text(
                    "select distinct r.purchase_time_at::date "
                    "from after_sales_refund_items r "
                    "where r.source_account_ref=:account and r.platform_code='walmart' "
                    "and r.refund_effective=true and r.return_order_at::date=:refund_day "
                    "and r.purchase_time_at is not null "
                    "and exists (select 1 from fact_walmart_sales_item_daily s "
                    "where s.source_account_ref=r.source_account_ref "
                    "and s.business_date_la=r.purchase_time_at::date "
                    "and s.allocation_status='direct')"
                ),
                {
                    "account": self.source_account_ref,
                    "refund_day": self.business_date,
                },
            )
            .scalars()
            .all()
        )
        self._refund_affected_business_dates = tuple(
            sorted(day for day in affected if day is not None)
        )
        return 0

    def _refresh_daily_sales_mart(self) -> int:
        """Refresh and replay-validate current and refund-affected purchase days."""

        current_day = self.business_date
        affected_days = tuple(
            day
            for day in getattr(self, "_refund_affected_business_dates", ())
            if day != current_day
        )
        current_daily_rows = 0
        current_order_rows = 0
        try:
            for day in (*affected_days, current_day):
                self.business_date = day
                super()._refresh_daily_sales_mart()
                super()._refresh_order_profit_mart()
                first = snapshot_automatic_marts(
                    self.session,
                    self.source_account_ref,
                    day,
                )
                if self.heartbeat is not None:
                    self.heartbeat()

                daily_rows = super()._refresh_daily_sales_mart()
                order_rows = super()._refresh_order_profit_mart()
                replay = snapshot_automatic_marts(
                    self.session,
                    self.source_account_ref,
                    day,
                )
                validate_automatic_mart_replay(
                    first,
                    replay,
                    expected_calc_version=DAILY_SALES_V2_VERSION,
                    surcharge_for=_low_price_delivery_surcharge,
                )
                if day == current_day:
                    current_daily_rows = daily_rows
                    current_order_rows = order_rows

            self._guarded_order_profit_result = (current_day, current_order_rows)
            return current_daily_rows
        finally:
            self.business_date = current_day

    def _refresh_order_profit_mart(self) -> int:
        """Return the already validated current-day rollup to legacy callers."""

        guarded = getattr(self, "_guarded_order_profit_result", None)
        if guarded is not None and guarded[0] == self.business_date:
            del self._guarded_order_profit_result
            return int(guarded[1])
        return super()._refresh_order_profit_mart()
