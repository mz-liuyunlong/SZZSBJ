from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import text

from app.modules.after_sales.classification import AfterSalesReasonClassifier
from app.modules.integration_sync.data_pages_business_rules_v3 import (
    DataPagesRealSyncRunner as HistoricalAdRunner,
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
    rules used by Refund Management. Daily Sales never converts refund logs back to
    purchase dates and never reads the legacy refund fact/DWS chain.
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
                    "and refund_effective=true and refund_effective_date=:day "
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
        """Legacy original-sales-day refund repricing is intentionally disabled."""

        return 0

    def _refresh_daily_sales_mart(self) -> int:
        """Refresh only the requested business day from current refund facts."""

        return super()._refresh_daily_sales_mart()
