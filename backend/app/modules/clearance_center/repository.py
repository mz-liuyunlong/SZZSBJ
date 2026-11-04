"""Read-only Listing aggregation for WFS clearance, using existing governed MARTs."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.clearance_center.rules import DEFAULT_RULES, evaluate, number
from app.modules.product_management.daily_sales_costs import (
    load_daily_sales_costs,
    normalize_sku_key,
)

LOS_ANGELES = ZoneInfo("America/Los_Angeles")


class ClearanceReadRepository:
    def __init__(self, session: Session):
        self.session = session

    def rules(self, account: str) -> tuple[dict, int]:
        row = (
            self.session.execute(
                text("""
            select rules_json,version from ops_clearance_rule_sets where source_account_ref=:account
        """),
                {"account": account},
            )
            .mappings()
            .first()
        )
        return (
            ({**DEFAULT_RULES, **row["rules_json"]}, int(row["version"]))
            if row
            else (dict(DEFAULT_RULES), 0)
        )

    def listing(
        self, listing_id: str, accounts: frozenset[str], *, lock: bool = False
    ) -> dict | None:
        sql = """
          select l.id::text id,l.source_account_ref,l.store_id,l.store_name,l.item_id,
                 l.local_sku,l.msku,l.title,l.picture_url,l.owner_ref,l.listing_status,
                 l.fulfillment_type,l.sale_price_amount,l.sale_price_currency_code,
                 l.wfs_available_quantity,l.inbound_quantity,l.average_rating,
                 l.review_count,l.buybox_status,l.listing_start_at_utc,l.calculated_at,
                 snap.wfs_available_quantity snapshot_wfs_available,
                 snap.captured_at inventory_captured_at
            from mart_listing_management_current l
            left join lateral (
              select i.wfs_available_quantity,i.captured_at
                from fact_walmart_listing_inventory_daily i
               where i.source_account_ref=l.source_account_ref
                 and i.store_id=l.store_id and i.item_id=l.item_id
               order by i.snapshot_date_la desc, i.captured_at desc limit 1
            ) snap on true
           where l.id=cast(:id as uuid) and l.source_account_ref=any(:accounts)
        """
        if lock:
            # Locks only the request-source Listing, not the inventory snapshot.
            sql += " for update of l"
        row = (
            self.session.execute(text(sql), {"id": listing_id, "accounts": list(accounts)})
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def listings(
        self,
        accounts: frozenset[str],
        *,
        store_id: str = "",
        keyword: str = "",
        eligible_only: bool = False,
    ) -> list[dict]:
        where = ["l.source_account_ref=any(:accounts)"]
        params: dict = {"accounts": list(accounts)}
        if store_id:
            where.append("l.store_id=:store")
            params["store"] = store_id
        if keyword:
            where.append("""(l.item_id ilike :q or coalesce(l.msku,'') ilike :q
                             or coalesce(l.local_sku,'') ilike :q or coalesce(l.title,'') ilike :q)""")
            params["q"] = f"%{keyword.strip()}%"
        if eligible_only:
            where.extend(
                [
                    "l.wfs_available_quantity>0",
                    "snap.wfs_available_quantity>0",
                    "snap.captured_at >= now() - interval '72 hours'",
                ]
            )
        sql = (
            """
          select l.id::text id,l.source_account_ref,l.store_id,l.store_name,l.item_id,
                 l.local_sku,l.msku,l.title,l.picture_url,l.owner_ref,l.listing_status,
                 l.fulfillment_type,l.sale_price_amount,l.sale_price_currency_code,
                 l.wfs_available_quantity,l.inbound_quantity,l.average_rating,
                 l.review_count,l.buybox_status,l.listing_start_at_utc,l.calculated_at,
                 snap.wfs_available_quantity snapshot_wfs_available,
                 snap.captured_at inventory_captured_at
            from mart_listing_management_current l
            left join lateral (
              select i.wfs_available_quantity,i.captured_at
                from fact_walmart_listing_inventory_daily i
               where i.source_account_ref=l.source_account_ref
                 and i.store_id=l.store_id and i.item_id=l.item_id
               order by i.snapshot_date_la desc, i.captured_at desc limit 1
            ) snap on true
           where """
            + " and ".join(where)
            + " order by l.source_account_ref,l.store_id,l.item_id"
        )
        return [dict(x) for x in self.session.execute(text(sql), params).mappings().all()]

    def evidence(
        self, listings: list[dict], *, as_of: date | None = None
    ) -> dict[tuple[str, str, str], dict]:
        """Aggregate only requested Listing identities; never join by SKU alone."""
        if not listings:
            return {}
        day = as_of or datetime.now(LOS_ANGELES).date()
        accounts = sorted({str(x["source_account_ref"]) for x in listings})
        ids = sorted({str(x["item_id"]) for x in listings})
        params = {"accounts": accounts, "items": ids, "day": day}
        sales = (
            self.session.execute(
                text("""
          select source_account_ref,store_id,item_id,
            sum(sales_qty) filter(where business_date_la between :day - 29 and :day) sales30,
            sum(sales_qty) filter(where business_date_la between :day - 6 and :day) sales7,
            sum(sales_qty) filter(where business_date_la between :day - 13 and :day - 7) prev7,
            sum(sales_amount) filter(where business_date_la between :day - 29 and :day) revenue30,
            sum(sales_amount) filter(where business_date_la between :day - 6 and :day) revenue7,
            sum(sales_amount) filter(where business_date_la between :day - 13 and :day - 7) revenue_prev7,
            sum(gross_profit_amount) filter(where business_date_la between :day - 29 and :day) profit30,
            sum(gross_profit_amount) filter(where business_date_la between :day - 6 and :day) profit7,
            sum(gross_profit_amount) filter(where business_date_la between :day - 13 and :day - 7) profit_prev7,
            sum(coalesce(ad_spend_amount,0)+coalesce(sem_ad_spend_amount,0))
                filter(where business_date_la between :day - 6 and :day) ad7,
            sum(coalesce(ad_spend_amount,0)+coalesce(sem_ad_spend_amount,0))
                filter(where business_date_la between :day - 13 and :day - 7) ad_prev7,
            count(*) filter(where business_date_la between :day - 29 and :day and cost_status <> 'complete') incomplete_cost_rows,
            count(*) filter(where business_date_la between :day - 29 and :day) sales_rows,
            count(*) filter(where business_date_la between :day - 29 and :day and gross_profit_amount is null) missing_profit_rows,
            count(*) filter(where business_date_la between :day - 29 and :day and
              calculation_warnings_json ? 'sales_history_30d_incomplete') incomplete_history_rows,
            count(distinct business_date_la) filter(where business_date_la between :day - 29 and :day) recorded_days,
            string_agg(distinct calc_version,',') calc_versions
          from mart_daily_sales_item_day
          where source_account_ref=any(:accounts) and item_id=any(:items)
            and business_date_la between :day - 29 and :day
          group by source_account_ref,store_id,item_id
        """),
                params,
            )
            .mappings()
            .all()
        )
        snapshots = (
            self.session.execute(
                text("""
          select source_account_ref,store_id,item_id,
            count(distinct snapshot_date_la) filter(where wfs_available_quantity is not null) snapshot_days,
            count(distinct snapshot_date_la) filter(where wfs_available_quantity>0) positive_stock_days
          from fact_walmart_listing_inventory_daily
          where source_account_ref=any(:accounts) and item_id=any(:items)
            and snapshot_date_la between :day - 29 and :day
          group by source_account_ref,store_id,item_id
        """),
                params,
            )
            .mappings()
            .all()
        )
        refunds = (
            self.session.execute(
                text("""
          select source_account_ref,store_id,item_id,
            sum(coalesce(return_qty,0)) refund_qty,
            sum(coalesce(refund_loss_amount,0)) filter(where refund_loss_effective=true) refund_loss,
            count(distinct return_order_id) refund_orders
          from after_sales_refund_items
          where source_account_ref=any(:accounts) and item_id=any(:items)
            and platform_code='walmart' and return_order_at is not null
            and return_order_at::date between :day - 29 and :day
            and store_id is not null and item_id is not null
          group by source_account_ref,store_id,item_id
        """),
                params,
            )
            .mappings()
            .all()
        )
        costs: dict[str, dict] = {}
        for account in accounts:
            costs[account] = load_daily_sales_costs(self.session, source_account_ref=account)
        key = lambda row: (
            str(row["source_account_ref"]),
            str(row["store_id"]),
            str(row["item_id"]),
        )
        s_map = {key(r): dict(r) for r in sales}
        i_map = {key(r): dict(r) for r in snapshots}
        r_map = {key(r): dict(r) for r in refunds}
        now = datetime.now(LOS_ANGELES)
        out: dict[tuple[str, str, str], dict] = {}
        for listing in listings:
            k = key(listing)
            s = s_map.get(k, {})
            i = i_map.get(k, {})
            r = r_map.get(k, {})
            captured = listing.get("inventory_captured_at")
            inventory_fresh = bool(
                captured
                and captured.tzinfo
                and timedelta(0) <= now - captured <= timedelta(hours=72)
            )
            # A 30-day empty fact set is not proof of 30 days of zero orders.
            sales_complete = bool(s.get("sales_rows") and not s.get("incomplete_history_rows"))
            complete_costs = bool(
                s.get("sales_rows")
                and s.get("incomplete_cost_rows") == 0
                and s.get("missing_profit_rows") == 0
            )
            started = listing.get("listing_start_at_utc")
            listing_days = (
                (now.date() - started.astimezone(LOS_ANGELES).date()).days
                if started is not None and started.tzinfo
                else None
            )
            sku_key = normalize_sku_key(listing.get("local_sku"))
            cost = costs.get(k[0], {}).get(sku_key) if sku_key else None
            unit_cost_usd: Decimal | None = None
            if (
                cost is not None
                and cost.purchase_cost_unit_cny is not None
                and cost.first_leg_cost_unit_cny is not None
                and cost.exchange_rate is not None
                and cost.exchange_rate > 0
                and not cost.root_missing_codes
            ):
                unit_cost_usd = (
                    cost.purchase_cost_unit_cny + cost.first_leg_cost_unit_cny
                ) / cost.exchange_rate
            out[k] = {
                **s,
                **r,
                "positive_stock_days": int(i.get("positive_stock_days") or 0),
                "inventory_snapshot_days": int(i.get("snapshot_days") or 0),
                "inventory_fresh": inventory_fresh,
                "sales_complete": sales_complete,
                "cost_complete": complete_costs,
                "listing_days": listing_days,
                "unit_cost_usd": unit_cost_usd,
                "as_of_date": day.isoformat(),
            }
        return out

    def evaluated(self, listing: dict, metrics: dict, rules: dict) -> dict:
        day = date.fromisoformat(metrics["as_of_date"])
        # The latest captured inventory is safer than a coalesced cached MART value.
        current = dict(listing)
        current["wfs_available_quantity"] = listing.get("snapshot_wfs_available")
        value = evaluate(current, metrics, rules, as_of=day)
        qty = number(current.get("wfs_available_quantity"))
        unit_cost = metrics.get("unit_cost_usd")
        value["stock_capital_usd"] = (
            str(qty * unit_cost) if qty is not None and unit_cost is not None else None
        )
        value["current_wfs_available"] = str(qty) if qty is not None else None
        value["inventory_captured_at"] = (
            listing["inventory_captured_at"].isoformat()
            if listing.get("inventory_captured_at")
            else None
        )
        value["snapshot_coverage_days_30d"] = metrics["inventory_snapshot_days"]
        value["positive_stock_days_30d"] = metrics["positive_stock_days"]
        value["sales_complete"] = metrics["sales_complete"]
        value["cost_complete"] = metrics["cost_complete"]
        value["calc_versions"] = metrics.get("calc_versions")
        value["as_of_date"] = metrics["as_of_date"]
        value["sales_30d"] = str(metrics["sales30"]) if metrics.get("sales30") is not None else None
        value["unit_cost_usd"] = str(unit_cost) if unit_cost is not None else None
        value["profit_30d_amount"] = (
            str(metrics["profit30"])
            if metrics.get("cost_complete") and metrics.get("profit30") is not None
            else None
        )
        value["refund_loss_30d"] = (
            str(metrics["refund_loss"]) if metrics.get("refund_loss") is not None else None
        )
        return value
