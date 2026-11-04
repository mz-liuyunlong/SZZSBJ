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
                             or coalesce(l.local_sku,'') ilike :q or coalesce(l.title,'')
                               ilike :q)""")
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

    def latest_completed_run(self) -> dict | None:
        row = self.session.execute(
            text("""select id::text id,run_date_la,as_of_date_la,status,
                           started_at,finished_at,listing_count,quality_json
                    from ops_clearance_daily_runs
                    where status='succeeded' and finished_at is not null
                    order by run_date_la desc limit 1""")
        ).mappings().first()
        return dict(row) if row else None

    def snapshot_listing(self, listing: dict, *, run: dict) -> dict | None:
        """One daily score by full account/store/item identity."""
        row = self.session.execute(
            text("""select evaluation_json,rule_config_version,quality_status
                     from ops_clearance_daily_evaluations
                    where run_id=cast(:run as uuid)
                      and source_account_ref=:account and store_id=:store
                      and item_id=:item and listing_id=cast(:listing_id as uuid)"""),
            {
                "run": run["id"], "account": listing["source_account_ref"],
                "store": listing["store_id"], "item": listing["item_id"],
                "listing_id": listing["id"],
            },
        ).mappings().first()
        if row is None:
            return None
        evaluation = dict(row["evaluation_json"])
        evaluation["quality_status"] = row["quality_status"]
        evaluation["evaluation_run_date_la"] = run["run_date_la"].isoformat()
        evaluation["as_of_date"] = run["as_of_date_la"].isoformat()
        # The daily decision remains the overnight decision; the UI/current
        # application selection always uses the independently fetched latest
        # stock snapshot so a sold-out Listing cannot be submitted later.
        latest = number(listing.get("snapshot_wfs_available"))
        evaluation["current_wfs_available"] = str(latest) if latest is not None else None
        captured = listing.get("inventory_captured_at")
        evaluation["inventory_captured_at"] = captured.isoformat() if captured else None
        if (
            latest is None or latest <= 0 or captured is None or
            captured.tzinfo is None or
            datetime.now(LOS_ANGELES) - captured > timedelta(hours=72)
        ):
            evaluation["current_inventory_not_eligible"] = True
            if "WFS_STOCK_UNAVAILABLE_OR_STALE" not in evaluation.get("warnings", []):
                evaluation["warnings"] = [
                    *evaluation.get("warnings", []),
                    "WFS_STOCK_UNAVAILABLE_OR_STALE",
                ]
        return {
            "listing": listing, "evaluation": evaluation,
            "rule_config_version": int(row["rule_config_version"]),
        }

    def snapshot_page(
        self, accounts: frozenset[str], *, run: dict, store_id: str = "",
        keyword: str = "", risk_level: str | None = None,
        candidate_status: str | None = None, page: int = 1,
        page_size: int = 50, financial_sort: bool = True,
    ) -> dict:
        """SQL-filtered count and LIMIT/OFFSET against persisted daily results."""
        where = ["e.run_id=cast(:run as uuid)", "e.source_account_ref=any(:accounts)"]
        params: dict = {
            "run": run["id"], "accounts": list(accounts), "limit": page_size,
            "offset": (page - 1) * page_size,
        }
        if store_id:
            where.append("e.store_id=:store")
            params["store"] = store_id
        if keyword:
            where.append("""(e.item_id ilike :q or coalesce(l.local_sku,'') ilike :q
                              or coalesce(l.msku,'') ilike :q or
                              coalesce(l.title,'') ilike :q)""")
            params["q"] = f"%{keyword.strip()}%"
        if risk_level:
            where.append("e.risk_level=:risk")
            params["risk"] = risk_level
        if candidate_status:
            where.append("e.candidate_status=:candidate")
            params["candidate"] = candidate_status
        conditions = " and ".join(where)
        base = """ from ops_clearance_daily_evaluations e
                  join mart_listing_management_current l
                    on l.id=e.listing_id and l.source_account_ref=e.source_account_ref
                   and l.store_id=e.store_id and l.item_id=e.item_id
                where """ + conditions
        total = int(
            self.session.execute(text("select count(*)" + base), params).scalar_one()
        )
        sort_capital = "e.stock_capital_usd desc nulls last," if financial_sort else ""
        sort_profit = (
            "e.profit_30d_amount asc nulls last, "
            "e.refund_loss_30d desc nulls last,"
            if financial_sort else ""
        )
        sql = """select l.id::text id,l.source_account_ref,l.store_id,l.store_name,
                       l.item_id,l.local_sku,l.msku,l.title,l.picture_url,l.owner_ref,
                       l.listing_status,l.fulfillment_type,l.sale_price_amount,
                       l.sale_price_currency_code,l.wfs_available_quantity,
                       l.inbound_quantity,l.average_rating,l.review_count,
                       l.buybox_status,l.listing_start_at_utc,l.calculated_at,
                       snap.wfs_available_quantity snapshot_wfs_available,
                       snap.captured_at inventory_captured_at,
                       e.evaluation_json,e.rule_config_version,e.quality_status
                  from ops_clearance_daily_evaluations e
                  join mart_listing_management_current l
                    on l.id=e.listing_id and l.source_account_ref=e.source_account_ref
                   and l.store_id=e.store_id and l.item_id=e.item_id
                  left join lateral (
                    select i.wfs_available_quantity,i.captured_at
                      from fact_walmart_listing_inventory_daily i
                     where i.source_account_ref=e.source_account_ref
                       and i.store_id=e.store_id and i.item_id=e.item_id
                     order by i.snapshot_date_la desc,i.captured_at desc limit 1
                  ) snap on true
                 where """ + conditions + """
                 order by case e.risk_level when 'high' then 0
                                            when 'medium' then 1
                                            when 'unknown' then 2 else 3 end,
                          """ + sort_capital + """
                          e.coverage_days desc nulls last,
                          """ + sort_profit + """
                          e.source_account_ref,e.store_id,e.item_id
                 limit :limit offset :offset"""
        records = self.session.execute(text(sql), params).mappings().all()
        items = []
        for row in records:
            item = dict(row)
            evaluation = item.pop("evaluation_json")
            version = item.pop("rule_config_version")
            quality = item.pop("quality_status")
            evaluation["quality_status"] = quality
            items.append({
                "listing": item, "evaluation": evaluation,
                "rule_config_version": version,
            })
        return {
            "items": items, "total": total, "page": page, "page_size": page_size,
            "evaluation_status": "ready", "run_date_la": run["run_date_la"].isoformat(),
            "as_of_date_la": run["as_of_date_la"].isoformat(),
        }

    def manual_eligible_page(
        self, accounts: frozenset[str], *, store_id: str = "", keyword: str = "",
        page: int = 1, page_size: int = 50,
    ) -> dict:
        """Live WFS-only picker with eligibility-before-pagination and no risk gate."""
        where = [
            "l.source_account_ref=any(:accounts)",
            "l.wfs_available_quantity>0",
            "snap.wfs_available_quantity>0",
            "snap.captured_at>=now()-interval '72 hours'",
        ]
        params: dict = {
            "accounts": list(accounts), "limit": page_size,
            "offset": (page - 1) * page_size,
        }
        if store_id:
            where.append("l.store_id=:store")
            params["store"] = store_id
        if keyword:
            where.append("""(l.item_id ilike :q or coalesce(l.msku,'') ilike :q
                              or coalesce(l.local_sku,'') ilike :q
                              or coalesce(l.title,'') ilike :q)""")
            params["q"] = f"%{keyword.strip()}%"
        identity = """
            from mart_listing_management_current l
            left join lateral (
                select i.wfs_available_quantity,i.captured_at
                from fact_walmart_listing_inventory_daily i
                where i.source_account_ref=l.source_account_ref
                  and i.store_id=l.store_id and i.item_id=l.item_id
                order by i.snapshot_date_la desc,i.captured_at desc limit 1
            ) snap on true
            where """ + " and ".join(where)
        count = int(self.session.execute(text("select count(*) " + identity), params).scalar_one())
        sql = """select l.id::text id,l.source_account_ref,l.store_id,l.store_name,
                        l.item_id,l.local_sku,l.msku,l.title,l.picture_url,l.owner_ref,
                        l.listing_status,l.fulfillment_type,l.sale_price_amount,
                        l.sale_price_currency_code,l.wfs_available_quantity,
                        l.inbound_quantity,l.average_rating,l.review_count,
                        l.buybox_status,l.listing_start_at_utc,l.calculated_at,
                        snap.wfs_available_quantity snapshot_wfs_available,
                        snap.captured_at inventory_captured_at """ + identity + """
                order by l.source_account_ref,l.store_id,l.item_id
                limit :limit offset :offset"""
        page_rows = [dict(x) for x in self.session.execute(text(sql), params).mappings()]
        return {"rows": page_rows, "total": count, "page": page, "page_size": page_size}

    def daily_summary(self, accounts: frozenset[str], *, run: dict, store_id: str = "") -> dict:
        where = ["run_id=cast(:run as uuid)", "source_account_ref=any(:accounts)"]
        params: dict = {"run": run["id"], "accounts": list(accounts)}
        if store_id:
            where.append("store_id=:store")
            params["store"] = store_id
        row = self.session.execute(
            text("""select count(*) total,
                     count(*) filter(where risk_level='high' and candidate_status='auto') high,
                     count(*) filter(where risk_level='medium' and candidate_status='auto') medium,
                     count(*) filter(where candidate_status='observe') observe,
                     count(*) filter(where candidate_status='review_required') review_required
                    from ops_clearance_daily_evaluations where """ + " and ".join(where)),
            params,
        ).mappings().one()
        result = {key: int(value) for key, value in row.items()}
        # Fresh manual eligibility is intentionally independent of yesterday's score.
        eligible = self.manual_eligible_page(
            accounts, store_id=store_id, page=1, page_size=1
        )
        result["eligible_manual"] = eligible["total"]
        result["run_date_la"] = run["run_date_la"].isoformat()
        result["as_of_date_la"] = run["as_of_date_la"].isoformat()
        result["evaluation_status"] = "ready"
        return result

    def readiness_report(
        self, accounts: frozenset[str], *, store_id: str = "",
    ) -> dict:
        """Live read-only evidence audit, scoped before counting any Listing."""
        params: dict = {"accounts": list(accounts)}
        store_filter = " and store_id=:store" if store_id else ""
        if store_id:
            params["store"] = store_id
        available = int(self.session.execute(
            text("""select count(*) from mart_listing_management_current
                     where source_account_ref=any(:accounts)""" + store_filter),
            params,
        ).scalar_one())
        run = self.latest_completed_run()
        if run is None:
            return {
                "evaluation_status": "not_ready", "run_date_la": None,
                "as_of_date_la": None, "total_listings": available,
                "evaluated_listings": 0, "not_evaluated_listings": available,
                "missing_sales_window": None, "missing_wfs_stock": None,
                "missing_profit_cost": None, "missing_listing_start": None,
                "history_21day_eligible": None,
                "refund_period_data_complete": False,
            }
        params["run"] = run["id"]
        rows = self.session.execute(
            text("""select count(*) total,
                      count(*) filter(where quality_status='complete') complete,
                      count(*) filter(where quality_status='partial') partial,
                      count(*) filter(where quality_status='stale') stale,
                      count(*) filter(where evaluation_json->'warnings'
                               ? 'SALES_WINDOW_UNVERIFIED') missing_sales_window,
                      count(*) filter(where evaluation_json->'warnings'
                               ? 'WFS_STOCK_UNAVAILABLE_OR_STALE') missing_wfs_stock,
                      count(*) filter(where evaluation_json->'warnings'
                               ? 'PROFIT_COST_INCOMPLETE') missing_profit_cost,
                      count(*) filter(where evaluation_json->'warnings'
                               ? 'LISTING_START_UNKNOWN') missing_listing_start,
                      count(*) filter(where
                         (evaluation_json->>'positive_stock_days_30d')::integer >= 21)
                         history_21day_eligible,
                      count(*) filter(where
                         (evaluation_json->>'source_sales_coverage_days_30d')::integer >= 30)
                         sales_source_30day_covered
                   from ops_clearance_daily_evaluations
                   where run_id=cast(:run as uuid)
                     and source_account_ref=any(:accounts)""" + store_filter),
            params,
        ).mappings().one()
        report = {key: int(value) for key, value in rows.items()}
        report.update({
            "evaluation_status": "ready",
            "run_date_la": run["run_date_la"].isoformat(),
            "as_of_date_la": run["as_of_date_la"].isoformat(),
            "total_listings": available,
            "evaluated_listings": report.pop("total"),
            "not_evaluated_listings": max(available - int(rows["total"]), 0),
            "refund_period_data_complete": False,
            "refund_coverage_note": (
                "Refund events are event-date based; no verified per-day refund "
                "sync watermark is available. Absence is not treated as zero."
            ),
        })
        return report

    def evidence(
        self, listings: list[dict], *, as_of: date | None = None,
        cost_cache: dict[str, dict] | None = None,
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
            sum(gross_sales_qty) filter(where business_date_la between :day - 29 and :day)
              gross_sales30,
            sum(sales_qty) filter(where business_date_la between :day - 6 and :day) sales7,
            sum(sales_qty) filter(where business_date_la between :day - 13 and :day - 7) prev7,
            sum(sales_amount) filter(where business_date_la between :day - 29 and :day) revenue30,
            sum(sales_amount) filter(where business_date_la between :day - 6 and :day) revenue7,
            sum(sales_amount) filter(where business_date_la between :day - 13 and :day - 7)
              revenue_prev7,
            sum(gross_profit_amount) filter(where business_date_la between :day - 29 and :day)
              profit30,
            sum(gross_profit_amount) filter(where business_date_la between :day - 6 and :day)
              profit7,
            sum(gross_profit_amount) filter(where business_date_la between :day - 13 and :day
              - 7) profit_prev7,
            sum(coalesce(ad_spend_amount,0)+coalesce(sem_ad_spend_amount,0))
                filter(where business_date_la between :day - 6 and :day) ad7,
            sum(coalesce(ad_spend_amount,0)+coalesce(sem_ad_spend_amount,0))
                filter(where business_date_la between :day - 13 and :day - 7) ad_prev7,
            count(*) filter(where business_date_la between :day - 29 and :day and cost_status
              <> 'complete') incomplete_cost_rows,
            count(*) filter(where business_date_la between :day - 29 and :day) sales_rows,
            count(*) filter(where business_date_la between :day - 29 and :day and
              gross_profit_amount is null) missing_profit_rows,
            count(*) filter(where business_date_la between :day - 29 and :day and
              calculation_warnings_json ? 'sales_history_30d_incomplete') incomplete_history_rows,
            count(distinct business_date_la) filter(where business_date_la between :day - 29
              and :day) recorded_days,
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
        # A missing per-Listing daily MART row is not zero sales.
        # Verify all 30 source dates for the exact store and no unresolved allocations.
        store_history = (
            self.session.execute(
                text("""
          select source_account_ref,store_id,
            count(distinct business_date_la)
              filter(where allocation_status='direct') covered_days,
            count(distinct business_date_la)
              filter(where allocation_status='direct'
                and business_date_la between :day - 6 and :day) last7_days,
            count(distinct business_date_la)
              filter(where allocation_status='direct'
                and business_date_la between :day - 13 and :day - 7) prev7_days,
            count(*) filter(where allocation_status<>'direct') unresolved_rows,
            count(*) filter(where allocation_status<>'direct'
                and business_date_la between :day - 6 and :day) last7_unresolved,
            count(*) filter(where allocation_status<>'direct'
                and business_date_la between :day - 13 and :day - 7) prev7_unresolved
          from fact_walmart_sales_item_daily
          where source_account_ref=any(:accounts)
            and business_date_la between :day - 29 and :day
          group by source_account_ref,store_id
        """),
                params,
            )
            .mappings()
            .all()
        )
        source_item_sales = (
            self.session.execute(
                text("""
          select source_account_ref,store_id,item_id,
            sum(coalesce(sales_qty,0))
              filter(where allocation_status='direct') source_sales_qty,
            sum(coalesce(sales_qty,0))
              filter(where allocation_status='direct'
                and business_date_la between :day - 6 and :day) last7_source_qty,
            sum(coalesce(sales_qty,0))
              filter(where allocation_status='direct'
                and business_date_la between :day - 13 and :day - 7) prev7_source_qty,
            count(*) filter(where allocation_status<>'direct') unresolved_rows,
            count(*) filter(where sales_qty is null) missing_qty_rows
          from fact_walmart_sales_item_daily
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
            count(distinct snapshot_date_la) filter(
              where wfs_available_quantity is not null
                and (captured_at at time zone 'America/Los_Angeles')::date=snapshot_date_la
            ) snapshot_days,
            count(distinct snapshot_date_la) filter(
              where wfs_available_quantity>0
                and (captured_at at time zone 'America/Los_Angeles')::date=snapshot_date_la
            ) positive_stock_days
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
            sum(coalesce(return_qty,0)) filter(where refund_effective=true)
              refund_qty,
            sum(coalesce(refund_loss_amount,0)) filter(where refund_loss_effective=true)
              refund_loss,
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
        costs: dict[str, dict] = cost_cache if cost_cache is not None else {}
        for account in accounts:
            if account not in costs:
                costs[account] = load_daily_sales_costs(
                    self.session, source_account_ref=account
                )

        def key(row: dict) -> tuple[str, str, str]:
            return (
                str(row["source_account_ref"]),
                str(row["store_id"]),
                str(row["item_id"]),
            )

        s_map = {key(r): dict(r) for r in sales}
        i_map = {key(r): dict(r) for r in snapshots}
        r_map = {key(r): dict(r) for r in refunds}
        source_map = {key(r): dict(r) for r in source_item_sales}
        store_history_map = {
            (str(r["source_account_ref"]), str(r["store_id"])): dict(r) for r in store_history
        }
        now = datetime.now(LOS_ANGELES)
        out: dict[tuple[str, str, str], dict] = {}
        for listing in listings:
            k = key(listing)
            s = s_map.get(k, {})
            i = i_map.get(k, {})
            r = r_map.get(k, {})
            source = source_map.get(k, {})
            history = store_history_map.get(k[:2], {})
            source_qty = number(source.get("source_sales_qty"))
            # Store-wide evidence may prove a day is represented but does not
            # by itself prove that every Walmart page was captured. Be
            # conservative: incomplete source dates or unresolved allocations
            # invalidate the affected sales window, never manufacture zero.
            gross30 = number(s.get("gross_sales30"))
            mart_matches_source = bool(
                (source_qty is None and gross30 is None)
                or (source_qty is not None and gross30 is not None
                    and source_qty == gross30)
            )
            verified_30 = bool(
                history.get("covered_days", 0) >= 30
                and not history.get("unresolved_rows")
                and not source.get("unresolved_rows")
                and not source.get("missing_qty_rows")
                and mart_matches_source
            )
            verified_7 = bool(
                history.get("last7_days", 0) >= 7
                and not history.get("last7_unresolved")
                and not source.get("unresolved_rows")
                and not source.get("missing_qty_rows")
            )
            verified_prev7 = bool(
                history.get("prev7_days", 0) >= 7
                and not history.get("prev7_unresolved")
                and not source.get("unresolved_rows")
                and not source.get("missing_qty_rows")
            )
            zero_sales_verified = bool(
                verified_30 and (source_qty is None or source_qty == 0)
                and (number(s.get("sales30")) in (None, Decimal(0)))
            )
            if zero_sales_verified and s.get("sales30") is None:
                s = {**s, "sales30": Decimal(0)}
            if verified_7 and s.get("sales7") is None and number(
                source.get("last7_source_qty")
            ) in (None, Decimal(0)):
                s = {**s, "sales7": Decimal(0), "revenue7": Decimal(0)}
            if verified_prev7 and s.get("prev7") is None and number(
                source.get("prev7_source_qty")
            ) in (None, Decimal(0)):
                s = {**s, "prev7": Decimal(0), "revenue_prev7": Decimal(0)}
            captured = listing.get("inventory_captured_at")
            inventory_fresh = bool(
                captured
                and captured.tzinfo
                and timedelta(0) <= now - captured <= timedelta(hours=72)
            )
            # A 30-day empty fact set is not proof of 30 days of zero orders.
            sales_complete = bool(
                verified_30
                and not s.get("incomplete_history_rows")
                and (s.get("sales_rows") or zero_sales_verified)
            )
            sales_7d_complete = bool(verified_7 and s.get("sales7") is not None)
            sales_prev_7d_complete = bool(
                verified_prev7 and s.get("prev7") is not None
            )
            complete_costs = bool(
                sales_complete
                and s.get("sales_rows")
                and s.get("incomplete_cost_rows") == 0
                and s.get("missing_profit_rows") == 0
            )
            started = listing.get("listing_start_at_utc")
            listing_days = (
                (day - started.astimezone(LOS_ANGELES).date()).days
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
                "sales_7d_complete": sales_7d_complete,
                "sales_prev_7d_complete": sales_prev_7d_complete,
                "zero_sales_verified": zero_sales_verified,
                "source_sales_coverage_days_30d": int(history.get("covered_days") or 0),
                "source_sales_coverage_days_7d": int(history.get("last7_days") or 0),
                "source_sales_coverage_days_prev7": int(history.get("prev7_days") or 0),
                "source_mart_qty_match": mart_matches_source,
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
        value["high_stock_capital"] = bool(
            qty is not None
            and unit_cost is not None
            and qty * unit_cost >= Decimal(str(rules["high_stock_capital_usd"]))
        )
        alerts: list[str] = []
        inbound = number(listing.get("inbound_quantity"))
        if inbound is not None and inbound > 0:
            alerts.append("INBOUND_STOCK_PRESENT")
        if listing.get("buybox_status") in ("未拥有", "LOST", "NOT_OWNED", "secondary", "other"):
            alerts.append("BUYBOX_ISSUE")
        value["conflict_alerts"] = alerts
        value["current_wfs_available"] = str(qty) if qty is not None else None
        value["inventory_captured_at"] = (
            listing["inventory_captured_at"].isoformat()
            if listing.get("inventory_captured_at")
            else None
        )
        value["snapshot_coverage_days_30d"] = metrics["inventory_snapshot_days"]
        value["positive_stock_days_30d"] = metrics["positive_stock_days"]
        value["sales_complete"] = metrics["sales_complete"]
        value["source_sales_coverage_days_30d"] = metrics["source_sales_coverage_days_30d"]
        value["source_sales_coverage_days_7d"] = metrics["source_sales_coverage_days_7d"]
        value["source_sales_coverage_days_prev7"] = metrics["source_sales_coverage_days_prev7"]
        value["source_mart_qty_match"] = metrics["source_mart_qty_match"]
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
