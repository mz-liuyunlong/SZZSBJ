from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Mapping

from sqlalchemy import text

from app.modules.integration_sync.data_pages_business_rules_v2 import (
    DataPagesRealSyncRunner as PageCompletenessRunner,
)
from app.modules.integration_sync.data_pages_real_sync import (
    DataPagesRealSyncError,
    _decimal,
    _now,
)


def _unique_identity_pair(
    rows: Iterable[Mapping[str, object]],
) -> tuple[str, str] | None:
    """Return one historical (store_id, msku) pair only when it is unambiguous."""

    pairs = {
        (str(row["store_id"]).strip(), str(row["msku"]).strip())
        for row in rows
        if row.get("store_id") is not None
        and str(row["store_id"]).strip()
        and row.get("msku") is not None
        and str(row["msku"]).strip()
    }
    if len(pairs) != 1:
        return None
    return next(iter(pairs))


class DataPagesRealSyncRunner(PageCompletenessRunner):
    """Resolve legacy positive-spend ad rows by stable historical ad-item identity."""

    def _resolve_historical_ad_identities(self) -> int:
        rows = (
            self.session.execute(
                text(
                    "select id,advertiser_id,ad_item_id,item_id,ad_spend_amount "
                    "from fact_walmart_ad_item_sp_daily "
                    "where source_account_ref=:account and business_date_la=:day "
                    "and coalesce(ad_spend_amount,0)>0 "
                    "and (store_id is null or item_id is null)"
                ),
                {"account": self.source_account_ref, "day": self.business_date},
            )
            .mappings()
            .all()
        )
        if not rows:
            return 0

        resolved = 0
        unresolved_positive = Decimal("0")
        now = _now()

        for row in rows:
            advertiser_id = row.get("advertiser_id")
            ad_item_id = row.get("ad_item_id")
            item_id = row.get("item_id")
            pair: tuple[str, str] | None = None

            if advertiser_id and ad_item_id and item_id:
                historical = (
                    self.session.execute(
                        text(
                            "select distinct store_id,msku "
                            "from fact_walmart_ad_item_sp_daily "
                            "where source_account_ref=:account "
                            "and advertiser_id=:advertiser_id "
                            "and ad_item_id=:ad_item_id "
                            "and item_id=:item_id "
                            "and store_id is not null "
                            "and msku is not null and trim(msku)<>''"
                        ),
                        {
                            "account": self.source_account_ref,
                            "advertiser_id": advertiser_id,
                            "ad_item_id": ad_item_id,
                            "item_id": item_id,
                        },
                    )
                    .mappings()
                    .all()
                )
                pair = _unique_identity_pair(historical)

            if pair is None:
                unresolved_positive += _decimal(row.get("ad_spend_amount")) or Decimal("0")
                continue

            store_id, msku = pair
            self.session.execute(
                text(
                    "update fact_walmart_ad_item_sp_daily "
                    "set store_id=:store_id,msku=:msku,updated_at=:now "
                    "where id=:id and source_account_ref=:account and business_date_la=:day"
                ),
                {
                    "store_id": store_id,
                    "msku": msku,
                    "now": now,
                    "id": row["id"],
                    "account": self.source_account_ref,
                    "day": self.business_date,
                },
            )
            resolved += 1

        if unresolved_positive != Decimal("0"):
            raise DataPagesRealSyncError("DATA_PAGES_POSITIVE_AD_SPEND_HISTORY_UNRESOLVED")

        return resolved

    def _refresh_daily_sales_mart(self) -> int:
        self._resolve_historical_ad_identities()
        return super()._refresh_daily_sales_mart()
