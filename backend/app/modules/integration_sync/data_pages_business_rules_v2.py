from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping
from uuid import uuid4

from sqlalchemy import text

from app.modules.integration_sync.data_pages_business_rules import (
    BUSINESS_RULE_RUNNER_VERSION,
    DataPagesRealSyncRunner as BusinessRulesRunner,
)
from app.modules.integration_sync.data_pages_real_sync import (
    WALMART_PLATFORM_CODE,
    _decimal,
    _field,
    _nested_first,
    _now,
    _row_count,
    _stable_hash,
    _timestamps,
)
from app.modules.product_management.daily_sales_costs import (
    DailySalesCostResolution,
    load_daily_sales_costs,
    normalize_sku_key,
)

DAILY_SALES_V2_VERSION = f"{BUSINESS_RULE_RUNNER_VERSION}+page-completeness-113"


def _money_decimal(value: object) -> Decimal | None:
    """Parse provider money strings while keeping the original numeric semantics."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    cleaned = str(value).strip().replace(",", "")
    for token in ("$", "¥", "￥", "USD", "CNY"):
        cleaned = cleaned.replace(token, "")
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _cost_totals(
    cost: DailySalesCostResolution,
    quantity: Decimal,
) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    fx = cost.exchange_rate
    purchase = (
        cost.purchase_cost_unit_cny * quantity / fx
        if cost.purchase_cost_unit_cny is not None and fx is not None and fx > 0
        else None
    )
    first_leg = (
        cost.first_leg_cost_unit_cny * quantity / fx
        if cost.first_leg_cost_unit_cny is not None and fx is not None and fx > 0
        else None
    )
    wfs = (
        cost.wfs_fee_unit_usd * quantity
        if cost.wfs_fee_unit_usd is not None
        else None
    )
    storage = (
        cost.storage_fee_unit_usd * quantity
        if cost.storage_fee_unit_usd is not None
        else None
    )
    return purchase, first_leg, wfs, storage


class DataPagesRealSyncRunner(BusinessRulesRunner):
    """#113 runner: one Daily Sales truth with Product Management cost semantics."""

    def _write_sample_orders(self, rows: Iterable[dict[str, Any]]) -> int:
        normalized: list[dict[str, Any]] = []
        for row in rows:
            copied = dict(row)
            transaction_info = row.get("transaction_info")
            if isinstance(transaction_info, list):
                normalized_transactions: list[object] = []
                for transaction in transaction_info:
                    if not isinstance(transaction, dict):
                        normalized_transactions.append(transaction)
                        continue
                    transaction_copy = dict(transaction)
                    parsed_total = _money_decimal(transaction.get("order_total_amount"))
                    if parsed_total is not None:
                        transaction_copy["order_total_amount"] = parsed_total
                    normalized_transactions.append(transaction_copy)
                copied["transaction_info"] = normalized_transactions
            normalized.append(copied)
        return super()._write_sample_orders(normalized)

    def _write_orders(self, rows: Iterable[dict[str, Any]]) -> int:
        """Persist provider order identifiers required for exact refund matching."""
        count = 0
        for row in rows:
            order_id = _field(row, "global_order_no", "order_id", "platform_order_no")
            item_rows = row.get("item_info") if isinstance(row.get("item_info"), list) else [row]
            if not order_id:
                continue
            for ordinal, item in enumerate(item_rows):
                if not isinstance(item, dict):
                    continue
                line_hash = _stable_hash({"order": order_id, "line": item, "ordinal": ordinal})
                self.session.execute(
                    text(
                        "insert into fact_walmart_order_items "
                        "(id,source_account_ref,store_id,source_order_id,source_order_line_id,"
                        "platform_order_no,reference_no,source_line_hash,source_line_ordinal,item_id,msku,local_sku,"
                        "quantity,source_purchase_at_raw,business_date_la,order_status_raw,order_sub_status_raw,"
                        "flow_node_raw,sales_revenue_amount,sales_revenue_currency_code,order_total_amount,"
                        "order_total_currency_code,discount_amount,discount_currency_code,is_sample_order,"
                        "synced_at,created_at,updated_at) values "
                        "(:id,:source_account_ref,:store_id,:source_order_id,:source_order_line_id,"
                        ":platform_order_no,:reference_no,:source_line_hash,:source_line_ordinal,:item_id,:msku,"
                        ":local_sku,:quantity,:source_purchase_at_raw,:business_date_la,:order_status_raw,"
                        ":order_sub_status_raw,:flow_node_raw,:sales_revenue_amount,:sales_revenue_currency_code,"
                        ":order_total_amount,:order_total_currency_code,:discount_amount,:discount_currency_code,"
                        ":is_sample_order,:synced_at,:created_at,:updated_at) "
                        "on conflict (source_account_ref,source_order_id,source_line_hash) do update set "
                        "store_id=excluded.store_id,source_order_line_id=excluded.source_order_line_id,"
                        "platform_order_no=excluded.platform_order_no,reference_no=excluded.reference_no,"
                        "item_id=coalesce(excluded.item_id,fact_walmart_order_items.item_id),"
                        "msku=excluded.msku,local_sku=excluded.local_sku,quantity=excluded.quantity,"
                        "sales_revenue_amount=excluded.sales_revenue_amount,order_total_amount=excluded.order_total_amount,"
                        "updated_at=excluded.updated_at"
                    ),
                    {
                        "id": str(uuid4()),
                        "source_account_ref": self.source_account_ref,
                        "store_id": _field(row, "store_id"),
                        "source_order_id": order_id,
                        "source_order_line_id": _field(item, "global_item_no", "order_item_no", "id"),
                        "platform_order_no": _field(item, "platform_order_no") or _field(row, "platform_order_no"),
                        "reference_no": _field(row, "reference_no", "referenceNo"),
                        "source_line_hash": line_hash,
                        "source_line_ordinal": ordinal,
                        "item_id": _field(item, "item_id", "platform_product_id"),
                        "msku": _field(item, "msku"),
                        "local_sku": _field(item, "local_sku", "sku"),
                        "quantity": _decimal(item.get("quantity")),
                        "source_purchase_at_raw": _field(row, "global_purchase_time"),
                        "business_date_la": self.business_date,
                        "order_status_raw": _field(row, "status"),
                        "order_sub_status_raw": _field(row, "status_sub"),
                        "flow_node_raw": _field(row, "flow_node"),
                        "sales_revenue_amount": _money_decimal(item.get("sales_revenue_amount")),
                        "sales_revenue_currency_code": _field(row, "amount_currency") or "USD",
                        "order_total_amount": _money_decimal(
                            _nested_first(row, "transaction_info", "order_total_amount")
                        ),
                        "order_total_currency_code": _field(row, "amount_currency") or "USD",
                        "discount_amount": _money_decimal(item.get("discount_amount")),
                        "discount_currency_code": _field(row, "amount_currency") or "USD",
                        "is_sample_order": False,
                        **_timestamps(),
                    },
                )
                count += 1
        return count

    def _match_refund_order_line(self, refund: Mapping[str, Any]) -> Mapping[str, Any] | None:
        customer_order_id = _text_or_none(refund.get("customer_order_id"))
        purchase_order_id = _text_or_none(refund.get("purchase_order_id"))
        if not customer_order_id and not purchase_order_id:
            return None
        return (
            self.session.execute(
                text(
                    "select id,source_order_id,platform_order_no,reference_no,store_id,item_id,msku,local_sku,"
                    "quantity,sales_revenue_amount,sales_revenue_currency_code,business_date_la "
                    "from fact_walmart_order_items where source_account_ref=:account and ("
                    "(cast(:customer_order_id as text) is not null and ("
                    "source_order_id=cast(:customer_order_id as text) or reference_no=cast(:customer_order_id as text))) or "
                    "(cast(:purchase_order_id as text) is not null and ("
                    "source_order_id=cast(:purchase_order_id as text) or platform_order_no=cast(:purchase_order_id as text)))) "
                    "and (cast(:store_id as text) is null or store_id=cast(:store_id as text)) and ("
                    "(cast(:item_id as text) is not null and item_id=cast(:item_id as text)) or "
                    "(cast(:local_sku as text) is not null and lower(trim(local_sku))=lower(trim(cast(:local_sku as text)))) or "
                    "(cast(:msku as text) is not null and lower(trim(msku))=lower(trim(cast(:msku as text))))) "
                    "order by case "
                    "when cast(:purchase_order_id as text) is not null and platform_order_no=cast(:purchase_order_id as text) then 0 "
                    "when cast(:customer_order_id as text) is not null and reference_no=cast(:customer_order_id as text) then 1 "
                    "when cast(:item_id as text) is not null and item_id=cast(:item_id as text) then 2 "
                    "when cast(:local_sku as text) is not null and lower(trim(local_sku))=lower(trim(cast(:local_sku as text))) then 3 "
                    "else 4 end,business_date_la desc nulls last,updated_at desc limit 1"
                ),
                {
                    "account": self.source_account_ref,
                    "customer_order_id": customer_order_id,
                    "purchase_order_id": purchase_order_id,
                    "store_id": refund.get("store_id"),
                    "item_id": refund.get("item_id"),
                    "local_sku": refund.get("local_sku"),
                    "msku": refund.get("msku"),
                },
            )
            .mappings()
            .first()
        )

    def _refresh_daily_sales_mart(self) -> int:
        now = _now()
        self.session.execute(
            text(
                "delete from mart_daily_sales_item_day where source_account_ref=:account "
                "and business_date_la=:day"
            ),
            {"account": self.source_account_ref, "day": self.business_date},
        )
        self.session.execute(
            text(
                "with s as (select business_date_la,source_account_ref,store_id,item_id,"
                "max(msku) msku,max(local_sku) local_sku,max(product_name) product_name,"
                "sum(coalesce(sales_qty,0)) sales_qty,sum(coalesce(order_count,0)) order_count,"
                "sum(coalesce(sales_amount,0)) sales_amount,coalesce(max(sales_currency_code),'USD') currency_code "
                "from fact_walmart_sales_item_daily where source_account_ref=:account and business_date_la=:day "
                "and allocation_status='direct' group by 1,2,3,4),"
                "a as (select business_date_la,source_account_ref,store_id,item_id,max(msku) msku,"
                "sum(coalesce(ad_spend_amount,0)) ad_spend from fact_walmart_ad_item_sp_daily "
                "where source_account_ref=:account and business_date_la=:day and store_id is not null "
                "and item_id is not null group by 1,2,3,4),"
                "k as (select business_date_la,source_account_ref,store_id,item_id from s union "
                "select business_date_la,source_account_ref,store_id,item_id from a),"
                "sample as (select source_account_ref,business_date_utc_minus_7 business_date_la,store_id,item_id,"
                "sum(coalesce(unit_price_amount,0)*coalesce(quantity,0)) sample_amount "
                "from fact_walmart_sample_order_items where source_account_ref=:account "
                "and business_date_utc_minus_7=:day and is_valid_sample=true and item_id is not null group by 1,2,3,4),"
                "r as (select f.source_account_ref,f.business_date_la,f.store_id,f.item_id,"
                "sum(coalesce(f.quantity,0)) return_qty,"
                "sum(coalesce(b.net_refund_amount,0)) filter (where b.calculation_status='calculated') refund_amount,"
                "coalesce(max(b.currency_code) filter (where b.calculation_status='calculated'),max(f.refund_currency_code),'USD') refund_currency_code,"
                "count(*) filter (where b.calculation_status is distinct from 'calculated') refund_unpriced_count "
                "from fact_walmart_refund_items f left join dws_walmart_refund_business_amounts b on b.refund_fact_id=f.id "
                "where f.source_account_ref=:account and f.business_date_la=:day and f.store_id is not null "
                "and f.item_id is not null group by 1,2,3,4),"
                "commission as (select distinct on (store_id) store_id,id rule_id,commission_rate,rule_version "
                "from ref_store_commission_rule_versions where source_account_ref=:account and platform_code='walmart' "
                "and is_active=true and effective_from<=:day and (effective_to is null or effective_to>:day) "
                "order by store_id,effective_from desc,created_at desc) "
                "insert into mart_daily_sales_item_day "
                "(id,business_date_la,source_account_ref,platform_code,store_id,store_name,item_id,msku,local_sku,"
                "local_name,title,picture_url,owner_ref,sales_qty,order_count,sales_amount,sales_currency_code,"
                "sample_amount,sales_amount_excluding_sample,return_qty,refund_amount,refund_currency_code,"
                "ad_spend_amount,ad_spend_currency_code,ad_ratio,wfs_available_quantity,commission_rate,"
                "commission_rule_version_id,commission_fee_amount,commission_fee_currency_code,cost_status,"
                "missing_cost_codes_json,sales_7d_trend_json,source_lineage_json,calc_version,calculated_at,created_at,updated_at) "
                "select gen_random_uuid(),k.business_date_la,k.source_account_ref,coalesce(l.platform_code,'walmart'),"
                "k.store_id,l.store_name,k.item_id,coalesce(nullif(trim(l.msku),''),nullif(trim(s.msku),''),nullif(trim(a.msku),'')),"
                "coalesce(nullif(trim(l.local_sku),''),nullif(trim(s.local_sku),''),k.item_id),"
                "coalesce(l.local_name,s.product_name),l.title,l.picture_url,null,coalesce(s.sales_qty,0),"
                "coalesce(s.order_count,0),coalesce(s.sales_amount,0),coalesce(s.currency_code,'USD'),"
                "coalesce(sample.sample_amount,0),greatest(coalesce(s.sales_amount,0)-coalesce(sample.sample_amount,0),0),"
                "r.return_qty,r.refund_amount,r.refund_currency_code,coalesce(a.ad_spend,0),'USD',"
                "case when coalesce(s.sales_amount,0)>0 then coalesce(a.ad_spend,0)/s.sales_amount else null end,"
                "l.wfs_available_quantity,coalesce(commission.commission_rate,0.15),commission.rule_id,"
                "coalesce(s.sales_amount,0)*coalesce(commission.commission_rate,0.15),coalesce(s.currency_code,'USD'),"
                "'missing','[\"product_management_cost_pending\"]'::jsonb,'[]'::jsonb,"
                "jsonb_build_object('runner',cast(:runner as text),'basis','sale_stat_union_ad_spend',"
                "'ads_match_key','store_id+item_id','refund_unpriced_count',coalesce(r.refund_unpriced_count,0)),"
                "cast(:runner as text),:now,:now,:now from k "
                "left join s on s.source_account_ref=k.source_account_ref and s.business_date_la=k.business_date_la "
                "and s.store_id=k.store_id and s.item_id=k.item_id "
                "left join a on a.source_account_ref=k.source_account_ref and a.business_date_la=k.business_date_la "
                "and a.store_id=k.store_id and a.item_id=k.item_id "
                "left join dim_walmart_listings l on l.source_account_ref=k.source_account_ref and l.store_id=k.store_id and l.item_id=k.item_id "
                "left join sample on sample.source_account_ref=k.source_account_ref and sample.business_date_la=k.business_date_la "
                "and sample.store_id=k.store_id and sample.item_id=k.item_id "
                "left join r on r.source_account_ref=k.source_account_ref and r.business_date_la=k.business_date_la "
                "and r.store_id=k.store_id and r.item_id=k.item_id "
                "left join commission on commission.store_id=k.store_id"
            ),
            {
                "account": self.source_account_ref,
                "day": self.business_date,
                "runner": DAILY_SALES_V2_VERSION,
                "now": now,
            },
        )

        costs = load_daily_sales_costs(
            self.session,
            source_account_ref=self.source_account_ref,
            at=now,
        )
        trend_rows = self.session.execute(
            text(
                "select business_date_la,store_id,item_id,coalesce(sales_qty,0) sales_qty "
                "from fact_walmart_sales_item_daily where source_account_ref=:account "
                "and business_date_la between :start_day and :end_day and allocation_status='direct'"
            ),
            {
                "account": self.source_account_ref,
                "start_day": self.business_date - timedelta(days=7),
                "end_day": self.business_date - timedelta(days=1),
            },
        ).mappings().all()
        trend_map: dict[tuple[str, str, object], Decimal] = {}
        for trend in trend_rows:
            trend_map[(str(trend["store_id"]), str(trend["item_id"]), trend["business_date_la"])] = (
                _decimal(trend["sales_qty"]) or Decimal("0")
            )

        mart_rows = self.session.execute(
            text(
                "select m.id,m.store_id,m.item_id,m.local_sku,m.sales_qty,m.sales_amount,m.refund_amount,"
                "m.ad_spend_amount,m.commission_fee_amount,coalesce((m.source_lineage_json->>'refund_unpriced_count')::int,0) refund_unpriced_count "
                "from mart_daily_sales_item_day m where m.source_account_ref=:account and m.business_date_la=:day"
            ),
            {"account": self.source_account_ref, "day": self.business_date},
        ).mappings().all()

        for row in mart_rows:
            quantity = _decimal(row["sales_qty"]) or Decimal("0")
            sales = _decimal(row["sales_amount"]) or Decimal("0")
            refund = _decimal(row["refund_amount"]) or Decimal("0")
            ad_spend = _decimal(row["ad_spend_amount"]) or Decimal("0")
            commission = _decimal(row["commission_fee_amount"]) or Decimal("0")
            sku_key = normalize_sku_key(row["local_sku"])
            cost = costs.get(sku_key) if sku_key is not None else None
            missing: list[str] = []
            purchase_total = first_leg_total = wfs_total = storage_total = None
            if cost is None:
                missing.append("product_management_sku_unmatched")
            else:
                purchase_total, first_leg_total, wfs_total, storage_total = _cost_totals(cost, quantity)
                if cost.purchase_cost_unit_cny is None:
                    missing.append("purchase_cost_missing")
                if cost.wfs_fee_unit_usd is None:
                    missing.append("wfs_fee_missing")
                if cost.first_leg_cost_unit_cny is None:
                    missing.append("first_leg_cost_missing")
                if cost.storage_fee_unit_usd is None:
                    missing.append("storage_fee_missing")
                if (
                    (cost.purchase_cost_unit_cny is not None or cost.first_leg_cost_unit_cny is not None)
                    and (cost.exchange_rate is None or cost.exchange_rate <= 0)
                ):
                    missing.append("fx_rate_missing")
            if int(row["refund_unpriced_count"] or 0) > 0:
                missing.append("refund_business_amount_missing")

            complete_costs = all(
                value is not None
                for value in (purchase_total, first_leg_total, wfs_total, storage_total)
            )
            if not missing and complete_costs:
                cost_status = "complete"
            elif cost is not None or int(row["refund_unpriced_count"] or 0) > 0:
                cost_status = "partial"
            else:
                cost_status = "missing"

            known_costs = [refund, ad_spend, commission]
            optional_costs = (purchase_total, first_leg_total, wfs_total, storage_total)
            gross_profit = (
                sales - sum(known_costs, Decimal("0")) - sum(
                    (value for value in optional_costs if value is not None),
                    Decimal("0"),
                )
                if complete_costs and int(row["refund_unpriced_count"] or 0) == 0
                else None
            )
            gross_margin = gross_profit / sales if gross_profit is not None and sales > 0 else None
            trend = [
                {
                    "date": (self.business_date - timedelta(days=offset)).isoformat(),
                    "sales_qty": str(
                        trend_map.get(
                            (
                                str(row["store_id"]),
                                str(row["item_id"]),
                                self.business_date - timedelta(days=offset),
                            ),
                            Decimal("0"),
                        )
                    ),
                }
                for offset in range(7, 0, -1)
            ]
            self.session.execute(
                text(
                    "update mart_daily_sales_item_day set owner_ref=:owner_ref,"
                    "wfs_fee_unit_amount=:wfs_unit,wfs_fee_total_amount=:wfs_total,wfs_fee_currency_code='USD',"
                    "purchase_cost_unit_cny=:purchase_unit,purchase_cost_total_usd=:purchase_total,"
                    "first_leg_cost_unit_cny=:first_leg_unit,first_leg_cost_total_usd=:first_leg_total,"
                    "storage_fee_unit_amount=:storage_unit,storage_fee_total_amount=:storage_total,"
                    "storage_fee_currency_code='USD',exchange_rate=:exchange_rate,fx_date=:fx_date,fx_source=:fx_source,"
                    "gross_profit_amount=:gross_profit,gross_profit_currency_code='USD',gross_margin=:gross_margin,"
                    "cost_status=:cost_status,missing_cost_codes_json=cast(:missing_codes as jsonb),"
                    "sales_7d_trend_json=cast(:trend as jsonb),calc_version=:runner,updated_at=:now where id=:id"
                ),
                {
                    "id": str(row["id"]),
                    "owner_ref": cost.owner_ref if cost is not None else None,
                    "wfs_unit": cost.wfs_fee_unit_usd if cost is not None else None,
                    "wfs_total": wfs_total,
                    "purchase_unit": cost.purchase_cost_unit_cny if cost is not None else None,
                    "purchase_total": purchase_total,
                    "first_leg_unit": cost.first_leg_cost_unit_cny if cost is not None else None,
                    "first_leg_total": first_leg_total,
                    "storage_unit": cost.storage_fee_unit_usd if cost is not None else None,
                    "storage_total": storage_total,
                    "exchange_rate": cost.exchange_rate if cost is not None else None,
                    "fx_date": cost.fx_date if cost is not None else None,
                    "fx_source": cost.fx_source if cost is not None else None,
                    "gross_profit": gross_profit,
                    "gross_margin": gross_margin,
                    "cost_status": cost_status,
                    "missing_codes": _json(missing),
                    "trend": _json(trend),
                    "runner": DAILY_SALES_V2_VERSION,
                    "now": now,
                },
            )

        provider_spend = _decimal(
            self.session.execute(
                text(
                    "select coalesce(sum(ad_spend_amount),0) from fact_walmart_ad_item_sp_daily "
                    "where source_account_ref=:account and business_date_la=:day"
                ),
                {"account": self.source_account_ref, "day": self.business_date},
            ).scalar_one()
        ) or Decimal("0")
        mart_spend = _decimal(
            self.session.execute(
                text(
                    "select coalesce(sum(ad_spend_amount),0) from mart_daily_sales_item_day "
                    "where source_account_ref=:account and business_date_la=:day"
                ),
                {"account": self.source_account_ref, "day": self.business_date},
            ).scalar_one()
        ) or Decimal("0")
        if provider_spend != mart_spend:
            raise RuntimeError("DATA_PAGES_DAILY_SALES_AD_SPEND_MISMATCH")
        return _row_count(
            self.session,
            "mart_daily_sales_item_day",
            self.source_account_ref,
            self.business_date,
        )

    def _refresh_order_profit_mart(self) -> int:
        """Keep the persisted SKU-day rollup aligned with the Daily Sales truth."""
        now = _now()
        self.session.execute(
            text(
                "delete from mart_order_profit_sku_day where source_account_ref=:account and business_date_la=:day"
            ),
            {"account": self.source_account_ref, "day": self.business_date},
        )
        self.session.execute(
            text(
                "insert into mart_order_profit_sku_day "
                "(id,business_date_la,source_account_ref,local_sku,item_ids_json,store_ids_json,store_count,item_count,"
                "sales_qty,order_count,sales_amount,sales_currency_code,refund_amount,ad_spend_amount,"
                "commission_fee_amount,wfs_fee_total_amount,purchase_cost_total_usd,first_leg_cost_total_usd,"
                "storage_fee_total_amount,gross_profit_amount,gross_profit_currency_code,cost_status,"
                "missing_cost_codes_json,source_lineage_json,calc_version,calculated_at,created_at,updated_at) "
                "select gen_random_uuid(),business_date_la,source_account_ref,coalesce(nullif(local_sku,''),item_id),"
                "jsonb_agg(distinct item_id),jsonb_agg(distinct store_id),count(distinct store_id),count(distinct item_id),"
                "sum(coalesce(sales_qty,0)),sum(coalesce(order_count,0)),sum(coalesce(sales_amount,0)),"
                "coalesce(max(sales_currency_code),'USD'),sum(coalesce(refund_amount,0)),sum(coalesce(ad_spend_amount,0)),"
                "sum(coalesce(commission_fee_amount,0)),sum(coalesce(wfs_fee_total_amount,0)),"
                "sum(coalesce(purchase_cost_total_usd,0)),sum(coalesce(first_leg_cost_total_usd,0)),"
                "sum(coalesce(storage_fee_total_amount,0)),"
                "case when bool_and(gross_profit_amount is not null) then sum(gross_profit_amount) end,'USD',"
                "case when bool_and(cost_status='complete') then 'complete' "
                "when bool_or(cost_status<>'missing') then 'partial' else 'missing' end,"
                "case when bool_and(cost_status='complete') then '[]'::jsonb "
                "else '[\"daily_sales_cost_incomplete\"]'::jsonb end,"
                "jsonb_build_object('runner',cast(:runner as text),'basis','mart_daily_sales_item_day'),"
                "cast(:runner as text),:now,:now,:now from mart_daily_sales_item_day "
                "where source_account_ref=:account and business_date_la=:day "
                "group by business_date_la,source_account_ref,coalesce(nullif(local_sku,''),item_id)"
            ),
            {
                "account": self.source_account_ref,
                "day": self.business_date,
                "runner": DAILY_SALES_V2_VERSION,
                "now": now,
            },
        )
        return _row_count(
            self.session,
            "mart_order_profit_sku_day",
            self.source_account_ref,
            self.business_date,
        )


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _json(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
