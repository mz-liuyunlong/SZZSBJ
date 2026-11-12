"""Read scoped Listing Management facts and require the upstream product tag."""

from __future__ import annotations

from collections.abc import Collection
from datetime import date
from typing import Any

from sqlalchemy import func, or_, select, text, tuple_
from sqlalchemy.orm import Session

from app.modules.data_pages.models import (
    DailySalesItemDayMart,
    ListingManagementCurrentMart,
    WalmartListingInventoryDailyFact,
)
from app.modules.data_pages.repository import (
    LISTING_WFS_LA_LOCKED,
    PRODUCT_INFO_CURRENT,
    ListingManagementRepository,
)
from app.modules.data_pages.schemas import ListingManagementListData
from app.modules.data_pages.service import ListingManagementService

from .models import ActionEvent, MarketScore, PurchaseApplication, RuleVersion, TrackingDecision

SAMPLE_TAG = "小批量测品"


class _NewProductListingRepository(ListingManagementRepository):
    """Reuse all Listing Management filters while matching provider *product_tags*.

    The public Listing 'tag' filter targets user-defined tags_json; it does not
    represent product_tags_json. A JSONB containment predicate avoids substring
    matches and is applied before COUNT, ORDER BY, LIMIT and OFFSET.
    """

    def _filtered_listing_statement(self, **filters):
        filters["tag"] = ""  # Never confuse custom tags with provider product tags.
        statement = super()._filtered_listing_statement(**filters)
        return statement.where(
            ListingManagementCurrentMart.product_tags_json.contains([{"label": SAMPLE_TAG}])
        )


class NewProductRepository:
    def __init__(self, session: Session):
        self.session = session
        self.listings = ListingManagementService(session)
        self.listings.repository = _NewProductListingRepository(session)

    def page(
        self,
        accounts: frozenset[str],
        *,
        page: int = 1,
        page_size: int = 50,
        store_id: str = "",
        owner: str = "",
        keyword: str = "",
        search_field: str = "item_id",
        status: str = "",
        item_ids: Collection[str] | None = None,
    ):
        # Stage 1 must only read existing Listing MART rows. Reusing the full
        # Listing Management page would COUNT/MAX/ORDER a six-table joined
        # projection three times, before the first product can be displayed.
        # Business evaluation and enrichment are separate background stages.
        mart = ListingManagementCurrentMart
        stmt = select(mart).where(
            mart.source_account_ref.in_(accounts),
            mart.product_tags_json.contains([{"label": SAMPLE_TAG}]),
        )
        # Explicit local preview only: filter at the source before count and page.
        if item_ids is not None:
            stmt = stmt.where(mart.item_id.in_(sorted(item_ids)))
        stores = [v.strip() for v in store_id.split(",") if v.strip()]
        if stores:
            stmt = stmt.where(or_(mart.store_id.in_(stores), mart.store_name.in_(stores)))
        owners = [v.strip() for v in owner.split(",") if v.strip()]
        if owners:
            stmt = stmt.where(mart.owner_ref.in_(owners))
        value = keyword.strip()
        if value:
            pattern = f"%{value}%"
            column = {
                "sku": mart.local_sku,
                "msku": mart.msku,
                "item_id": mart.item_id,
                "title": mart.title,
            }[search_field]
            stmt = stmt.where(
                or_(mart.local_name.ilike(pattern), column.ilike(pattern))
                if search_field == "title"
                else column.ilike(pattern)
            )
        # Preserve current Listing-management status semantics on the MART
        # fields available in this stage (monitor enrichment is deferred).
        conditions = []
        for item in (s.strip() for s in status.split(",") if s.strip()):
            if item == "启用":
                conditions.append(mart.disabled_reason.is_(None))
            elif item == "停用":
                conditions.append(mart.disabled_reason.is_not(None))
            elif item == "在线":
                conditions.append(
                    mart.listing_status.in_(
                        ["在线", "在售", "ONLINE", "PUBLISHED", "PUBLISH", "published"]
                    )
                )
            elif item == "离线":
                conditions.append(
                    mart.listing_status.in_(
                        ["离线", "UNPUBLISHED", "OFFLINE", "unpublished", "offline"]
                    )
                )
            elif item == "拥有":
                conditions.append(
                    mart.buybox_status.in_(["拥有", "PRIMARY", "primary", "WON", "WINNING"])
                )
            elif item == "未拥有":
                conditions.append(
                    mart.buybox_status.in_(["未拥有", "LOST", "NOT_OWNED", "secondary", "other"])
                )
        if conditions:
            stmt = stmt.where(or_(*conditions))
        total = int(
            self.session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
            or 0
        )
        listing_rows = self.session.scalars(
            stmt.order_by(
                func.coalesce(mart.wfs_available_quantity, 0).desc(),
                mart.store_name.asc(),
                mart.local_sku.asc(),
                mart.item_id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        # Enrich only the already-paged identities. Never join these tables into
        # the full-tag COUNT or scan sales/ads/evaluation during a page GET.
        items = [self.listings._to_read(row) for row in listing_rows]
        if not items:
            return ListingManagementListData(items=[]), total, None

        owner_by_sku = {}
        sku_keys = sorted(
            {(item.source_account_ref, item.local_sku) for item in items if item.local_sku}
        )
        if sku_keys:
            owner_rows = self.session.execute(
                select(
                    PRODUCT_INFO_CURRENT.c.source_account_ref,
                    PRODUCT_INFO_CURRENT.c.lingxing_sku_code,
                    func.max(PRODUCT_INFO_CURRENT.c.owner_uid).label("owner_uid"),
                    func.max(PRODUCT_INFO_CURRENT.c.owner_name).label("owner_name"),
                )
                .where(
                    tuple_(
                        PRODUCT_INFO_CURRENT.c.source_account_ref,
                        PRODUCT_INFO_CURRENT.c.lingxing_sku_code,
                    ).in_(sku_keys)
                )
                .group_by(
                    PRODUCT_INFO_CURRENT.c.source_account_ref,
                    PRODUCT_INFO_CURRENT.c.lingxing_sku_code,
                )
            ).mappings()
            owner_by_sku = {
                (r["source_account_ref"], r["lingxing_sku_code"]): r for r in owner_rows
            }

        identity_keys = [(item.source_account_ref, item.store_id, item.item_id) for item in items]
        first_by_item = {}
        locked_available = (
            self.session.scalar(
                text("SELECT to_regclass('public.listing_wfs_first_stock_la_locked')")
            )
            is not None
        )
        if locked_available:
            first_rows = self.session.execute(
                select(
                    LISTING_WFS_LA_LOCKED.c.source_account_ref,
                    LISTING_WFS_LA_LOCKED.c.store_id,
                    LISTING_WFS_LA_LOCKED.c.item_id,
                    LISTING_WFS_LA_LOCKED.c.first_wfs_available_date_la,
                ).where(
                    tuple_(
                        LISTING_WFS_LA_LOCKED.c.source_account_ref,
                        LISTING_WFS_LA_LOCKED.c.store_id,
                        LISTING_WFS_LA_LOCKED.c.item_id,
                    ).in_(identity_keys)
                )
            ).mappings()
        else:
            # Same historical first-positive-WFS fallback as Listing Management
            # when the locked table is unavailable. Only these page identities.
            inv = WalmartListingInventoryDailyFact
            first_rows = self.session.execute(
                select(
                    inv.source_account_ref,
                    inv.store_id,
                    inv.item_id,
                    func.min(inv.snapshot_date_la).label("first_wfs_available_date_la"),
                )
                .where(
                    tuple_(inv.source_account_ref, inv.store_id, inv.item_id).in_(identity_keys),
                    inv.wfs_available_quantity >= 1,
                )
                .group_by(inv.source_account_ref, inv.store_id, inv.item_id)
            ).mappings()
        first_by_item = {
            (r["source_account_ref"], r["store_id"], r["item_id"]): r["first_wfs_available_date_la"]
            for r in first_rows
        }

        enriched = []
        for item in items:
            owner = owner_by_sku.get((item.source_account_ref, item.local_sku))
            first_date = first_by_item.get((item.source_account_ref, item.store_id, item.item_id))
            enriched.append(
                item.model_copy(
                    update={
                        "owner_uid": owner["owner_uid"] if owner else None,
                        "owner_name": owner["owner_name"] if owner else None,
                        "first_wfs_available_date_la": first_date,
                    }
                )
            )
        return ListingManagementListData(items=enriched), total, None

    def first_order_dates(self, items):
        """Read the earliest positive-order LA day for only the current page.

        This reads the existing daily-sales MART; it does not run a product
        evaluation, refresh a source, or persist any data.
        """
        keys = sorted({(item.source_account_ref, item.store_id, item.item_id) for item in items})
        if not keys:
            return {}
        daily = DailySalesItemDayMart
        stmt = (
            select(
                daily.source_account_ref,
                daily.store_id,
                daily.item_id,
                func.min(daily.business_date_la).label("first_order_date"),
            )
            .where(
                tuple_(daily.source_account_ref, daily.store_id, daily.item_id).in_(keys),
                daily.order_count > 0,
            )
            .group_by(daily.source_account_ref, daily.store_id, daily.item_id)
        )
        return {
            (row["source_account_ref"], row["store_id"], row["item_id"]): row["first_order_date"]
            for row in self.session.execute(stmt).mappings()
        }

    def exact_listing(self, accounts: frozenset[str], account: str, store: str, item: str):
        if account not in accounts:
            return None
        data, _, _ = self.page(
            frozenset({account}),
            store_id=store,
            keyword=item,
            search_field="item_id",
            page=1,
            page_size=500,
        )
        return next(
            (
                row
                for row in data.items
                if row.source_account_ref == account
                and row.store_id == store
                and row.item_id == item
            ),
            None,
        )

    @staticmethod
    def params(account: str, store: str, item: str) -> dict:
        return {"account": account, "store": store, "item": item}

    def first_wfs_date(self, account: str, store: str, item: str):
        return (
            self.session.execute(
                text("""
          SELECT first_wfs_available_date_la AS day, date_source
          FROM listing_wfs_first_stock_la_locked
          WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
        """),
                self.params(account, store, item),
            )
            .mappings()
            .first()
        )

    def order_summary(
        self, account: str, store: str, item: str, start: date, end: date
    ) -> dict[str, Any]:
        params = {**self.params(account, store, item), "start": start, "end": end}
        # A single row can have multiple order lines. Group by true source order id.
        # No SKU/MSKU fallback; unknown identity rows do not count as a product order.
        result = (
            self.session.execute(
                text("""
         WITH orders AS (
          SELECT source_order_id AS order_ref,
                 min(business_date_la) AS first_date,
                 sum(quantity) AS units,
                 count(*) FILTER (WHERE quantity IS NULL OR business_date_la IS NULL) AS
                     unknown_lines
          FROM fact_walmart_order_items
          WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
            AND is_identity_current IS TRUE
            AND is_sample_order IS FALSE
            AND business_date_la BETWEEN :start AND :end
            AND UPPER(COALESCE(order_status_raw,'')) NOT IN ('CANCELED','CANCELLED','CANCEL','VOID')
          GROUP BY source_order_id
         )
         SELECT COUNT(*) AS order_count,
                SUM(units) AS units,
                COUNT(*) FILTER (WHERE units = 1) AS single_orders,
                MIN(first_date) AS first_order_date,
                COALESCE(SUM(unknown_lines),0) AS unknown_lines
         FROM orders
        """),
                params,
            )
            .mappings()
            .one()
        )
        return dict(result)

    def daily_series(self, account: str, store: str, item: str, start: date, end: date):
        return [
            dict(row)
            for row in self.session.execute(
                text("""
          SELECT business_date_la AS day, sales_qty,order_count,sales_amount,
                 gross_profit_amount,cost_status,roi,gross_margin,ad_spend_amount,
                 sales_currency_code,gross_profit_currency_code,
                 purchase_cost_total_usd,first_leg_cost_total_usd,
                 missing_cost_codes_json,calculated_at
          FROM mart_daily_sales_item_day
          WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
            AND business_date_la BETWEEN :start AND :end
          ORDER BY business_date_la
        """),
                {**self.params(account, store, item), "start": start, "end": end},
            )
            .mappings()
            .all()
        ]

    def ads(self, account: str, store: str, item: str, start: date, end: date) -> dict:
        x = (
            self.session.execute(
                text("""
          SELECT COUNT(*) AS n,
              COUNT(*) FILTER (WHERE ad_spend_amount IS NULL OR num_ads_clicks IS NULL
                 OR attributed_orders IS NULL OR attributed_sales_amount IS NULL
                 OR ad_spend_currency_code IS DISTINCT FROM 'USD'
                 OR attributed_sales_currency_code IS DISTINCT FROM 'USD') AS incomplete,
              sum(ad_spend_amount) AS spend, sum(num_ads_clicks) AS clicks,
              sum(attributed_orders) AS orders, sum(attributed_sales_amount) AS revenue,
              max(synced_at) AS latest_sync
          FROM fact_walmart_ad_item_sp_daily
          WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
            AND business_date_la BETWEEN :start AND :end
        """),
                {**self.params(account, store, item), "start": start, "end": end},
            )
            .mappings()
            .one()
        )
        return dict(x)

    def market(self, account: str, store: str, item: str):
        return self.session.scalar(
            select(MarketScore).where(
                MarketScore.source_account_ref == account,
                MarketScore.store_id == store,
                MarketScore.item_id == item,
            )
        )

    def tracking(self, account: str, store: str, item: str):
        return self.session.scalar(
            select(TrackingDecision).where(
                TrackingDecision.source_account_ref == account,
                TrackingDecision.store_id == store,
                TrackingDecision.item_id == item,
            )
        )

    def active_purchase(self, account: str, store: str, item: str, *, lock=False):
        stmt = select(PurchaseApplication).where(
            PurchaseApplication.source_account_ref == account,
            PurchaseApplication.store_id == store,
            PurchaseApplication.item_id == item,
            PurchaseApplication.status == "submitted",
        )
        return self.session.scalar(stmt.with_for_update() if lock else stmt)

    def rule_version(self, kind: str, *, lock=False):
        stmt = (
            select(RuleVersion)
            .where(RuleVersion.kind == kind)
            .order_by(RuleVersion.version.desc())
            .limit(1)
        )
        return self.session.scalar(stmt.with_for_update() if lock else stmt)

    def rule_history(self, kind: str, limit: int, offset: int):
        stmt = select(RuleVersion).where(RuleVersion.kind == kind)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = self.session.scalars(
            stmt.order_by(RuleVersion.version.desc()).offset(offset).limit(limit)
        ).all()
        return rows, int(total or 0)

    def events(self, account: str, store: str, item: str, limit: int = 100):
        return self.session.scalars(
            select(ActionEvent)
            .where(
                ActionEvent.source_account_ref == account,
                ActionEvent.store_id == store,
                ActionEvent.item_id == item,
            )
            .order_by(ActionEvent.created_at.desc())
            .limit(limit)
        ).all()
