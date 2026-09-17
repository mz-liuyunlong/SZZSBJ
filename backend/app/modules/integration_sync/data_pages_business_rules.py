from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping
from uuid import uuid4

from sqlalchemy import text

from app.core.config import AppEnvironment, get_settings
from app.db.session import get_session_factory
from app.modules.integration_sync.catalog import IntegrationCatalogService
from app.modules.integration_sync.data_pages_real_sync import (
    AUTHORIZED_ENV,
    RUNNER_VERSION,
    WALMART_PLATFORM_CODE,
    WALMART_PLATFORM_CODE_INT,
    DataPagesRealSyncError,
    DataPagesRealSyncRunner as BaseDataPagesRealSyncRunner,
    DataPagesRealSyncSummary,
    _decimal,
    _field,
    _nested_first,
    _now,
    _row_count,
    _safe_scope,
    _timestamps,
    data_pages_client,
    parse_args,
)

FIXED_UTC_MINUS_7 = timezone(timedelta(hours=-7), name="UTC-07:00")
CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
SAMPLE_RULE_VERSION = "zero-total-uncancelled-v1"
REFUND_RULE_VERSION = "sales-x-qty-less-store-commission-v1"
DEFAULT_STORE_COMMISSION_RATE = Decimal("0.15")
BUSINESS_RULE_RUNNER_VERSION = f"{RUNNER_VERSION}+business-rules-1"


def _sample_window_china(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(0, 0, 0), tzinfo=FIXED_UTC_MINUS_7)
    end = datetime.combine(day, time(23, 59, 59), tzinfo=FIXED_UTC_MINUS_7)
    return start.astimezone(CHINA_TZ), end.astimezone(CHINA_TZ)


def _sample_window_epoch(day: date, *, end: bool) -> int:
    start_at, end_at = _sample_window_china(day)
    return int((end_at if end else start_at).timestamp())


def _is_valid_sample(order_total: Decimal | None, cancel_time_raw: str | None) -> bool:
    return order_total == Decimal("0") and not (cancel_time_raw or "").strip()


def _refund_amounts(
    unit_sales_amount: Decimal,
    quantity: Decimal,
    commission_rate: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    gross = unit_sales_amount * quantity
    commission = gross * commission_rate
    return gross, commission, gross - commission


class DataPagesRealSyncRunner(BaseDataPagesRealSyncRunner):
    """Production DATA-PAGES runner with approved SZZSBJ business rules."""

    def execute(self) -> DataPagesRealSyncSummary:
        if self.client is None:
            raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_CLIENT_REQUIRED")
        try:
            stores = self._fetch_offset_all(
                "seller_list_multi_platform",
                self._seller_body,
                minimum_page_size=20,
            )
            self.store_ids = tuple(
                value
                for value in dict.fromkeys(_field(row, "store_id", "sid") for row in stores)
                if value
            )
            if not self.store_ids:
                raise DataPagesRealSyncError("DATA_PAGES_NO_WALMART_STORES")

            advertisers = self._fetch_page_all(
                "walmart_advertiser_list",
                self._advertiser_body,
            )
            self.advertiser_ids = tuple(
                value
                for value in dict.fromkeys(
                    _field(row, "advertiserId", "advertiser_id") for row in advertisers
                )
                if value
            )
            listings = self._fetch_offset_all("walmart_listing_list", self._listing_body)

            sales_rows: list[dict[str, Any]] = []
            for result_type in (1, 2, 3):
                rows = self._fetch_page_all(
                    "sale_stat_page_list",
                    lambda page, size, result_type=result_type: self._sale_stat_body(
                        page,
                        size,
                        result_type,
                    ),
                    body_suffix=f"result_type={result_type}",
                )
                sales_rows.extend({**row, "_result_type": result_type} for row in rows)

            orders = self._fetch_offset_all(
                "order_v2_list",
                self._order_body,
                minimum_page_size=20,
            )
            sample_candidates = self._fetch_offset_all(
                "order_v2_list",
                self._sample_order_body,
                minimum_page_size=20,
            )
            refunds = self._fetch_return_all()

            ad_rows: list[dict[str, Any]] = []
            for advertiser_id in self.advertiser_ids[: self.max_advertisers]:
                ad_rows.extend(self._fetch_ads_all(advertiser_id))

            self.summary.store_rows = self._write_stores(stores)
            self.summary.advertiser_rows = self._write_advertisers(advertisers)
            self.summary.listing_rows = self._write_listings(listings)
            self.summary.sales_rows = self._write_sales(sales_rows)
            self.summary.order_rows = self._write_orders(orders)
            self._write_sample_orders(sample_candidates)
            self.summary.refund_rows = self._write_refunds(refunds)
            self.summary.ad_rows = self._write_ads(ad_rows)

            self.summary.order_unresolved_rows = self._resolve_order_items()
            self._resolve_sample_items()
            self.summary.refund_unresolved_rows = self._resolve_refund_items()
            self._reprice_refunds()
            self._resolve_ads(ad_rows)

            self.summary.mart_daily_sales_rows = self._refresh_daily_sales_mart()
            self.summary.mart_order_profit_rows = self._refresh_order_profit_mart()
            self.summary.mart_listing_rows = self._refresh_listing_mart()
            self.session.commit()
            return self.summary
        except Exception:
            self.session.rollback()
            raise

    def _sample_order_body(self, offset: int, size: int) -> dict[str, Any]:
        return {
            "date_type": "global_purchase_time",
            "start_time": _sample_window_epoch(self.business_date, end=False),
            "end_time": _sample_window_epoch(self.business_date, end=True),
            "offset": offset,
            "length": size,
            "platform_code": [WALMART_PLATFORM_CODE_INT],
            "store_id": list(self.store_ids),
        }

    def _write_sample_orders(self, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            order_total = _decimal(_nested_first(row, "transaction_info", "order_total_amount"))
            if order_total != Decimal("0"):
                continue
            cancel_time_raw = _field(row, "cancel_time") or _nested_text(
                row,
                "platform_info",
                "cancel_time",
            )
            platform_code = (
                _field(row, "platform_code")
                or _nested_text(row, "platform_info", "platform_code")
                or WALMART_PLATFORM_CODE
            )
            source_order_id = _field(row, "global_order_no", "order_id")
            store_id = _field(row, "store_id")
            store_name = _field(row, "store_name")
            currency_code = _field(row, "amount_currency") or "USD"
            item_rows = row.get("item_info") if isinstance(row.get("item_info"), list) else []

            for item in item_rows:
                if not isinstance(item, dict):
                    continue
                platform_order_no = _field(item, "platform_order_no") or _field(
                    row,
                    "platform_order_no",
                )
                source_order_line_id = _field(item, "id", "global_item_no", "order_item_no")
                if not platform_order_no or not source_order_line_id:
                    continue
                self.session.execute(
                    text(
                        "insert into fact_walmart_sample_order_items "
                        "(id,business_date_utc_minus_7,business_timezone,source_account_ref,"
                        "source_order_id,platform_order_no,store_id,store_name,platform_code,"
                        "source_order_line_id,item_id,msku,local_sku,quantity,unit_price_amount,"
                        "unit_price_currency_code,order_total_amount,order_total_currency_code,"
                        "cancel_time_raw,is_cancelled,is_valid_sample,sample_rule_version,"
                        "synced_at,created_at,updated_at) values "
                        "(:id,:business_date_utc_minus_7,'UTC-07:00',:source_account_ref,"
                        ":source_order_id,:platform_order_no,:store_id,:store_name,:platform_code,"
                        ":source_order_line_id,:item_id,:msku,:local_sku,:quantity,:unit_price_amount,"
                        ":unit_price_currency_code,:order_total_amount,:order_total_currency_code,"
                        ":cancel_time_raw,:is_cancelled,:is_valid_sample,:sample_rule_version,"
                        ":synced_at,:created_at,:updated_at) "
                        "on conflict (source_account_ref,platform_order_no,source_order_line_id) "
                        "do update set business_date_utc_minus_7=excluded.business_date_utc_minus_7,"
                        "store_id=excluded.store_id,store_name=excluded.store_name,"
                        "platform_code=excluded.platform_code,item_id=coalesce(excluded.item_id,"
                        "fact_walmart_sample_order_items.item_id),msku=excluded.msku,"
                        "local_sku=excluded.local_sku,quantity=excluded.quantity,"
                        "unit_price_amount=excluded.unit_price_amount,"
                        "unit_price_currency_code=excluded.unit_price_currency_code,"
                        "order_total_amount=excluded.order_total_amount,"
                        "order_total_currency_code=excluded.order_total_currency_code,"
                        "cancel_time_raw=excluded.cancel_time_raw,is_cancelled=excluded.is_cancelled,"
                        "is_valid_sample=excluded.is_valid_sample,"
                        "sample_rule_version=excluded.sample_rule_version,"
                        "synced_at=excluded.synced_at,updated_at=excluded.updated_at"
                    ),
                    {
                        "id": str(uuid4()),
                        "business_date_utc_minus_7": self.business_date,
                        "source_account_ref": self.source_account_ref,
                        "source_order_id": source_order_id,
                        "platform_order_no": platform_order_no,
                        "store_id": store_id,
                        "store_name": store_name,
                        "platform_code": platform_code,
                        "source_order_line_id": source_order_line_id,
                        "item_id": _field(item, "item_id", "platform_product_id"),
                        "msku": _field(item, "msku"),
                        "local_sku": _field(item, "local_sku", "sku"),
                        "quantity": _decimal(item.get("quantity")),
                        "unit_price_amount": _decimal(item.get("unit_price_amount")),
                        "unit_price_currency_code": (
                            _field(item, "unit_price_currency_code", "currency") or currency_code
                        ),
                        "order_total_amount": order_total,
                        "order_total_currency_code": currency_code,
                        "cancel_time_raw": cancel_time_raw,
                        "is_cancelled": bool((cancel_time_raw or "").strip()),
                        "is_valid_sample": _is_valid_sample(order_total, cancel_time_raw),
                        "sample_rule_version": SAMPLE_RULE_VERSION,
                        **_timestamps(),
                    },
                )
                count += 1
        return count

    def _resolve_sample_items(self) -> int:
        now = _now()
        self.session.execute(
            text(
                "with candidates as (select s.id,"
                "(select count(*) from dim_walmart_listings l "
                "where l.source_account_ref=:account and l.store_id=s.store_id "
                "and trim(l.local_sku)=trim(s.local_sku)) sku_count,"
                "(select min(l.item_id) from dim_walmart_listings l "
                "where l.source_account_ref=:account and l.store_id=s.store_id "
                "and trim(l.local_sku)=trim(s.local_sku)) sku_item,"
                "(select count(*) from dim_walmart_listings l "
                "where l.source_account_ref=:account and l.store_id=s.store_id "
                "and trim(l.local_sku)=trim(s.local_sku) and trim(l.msku)=trim(s.msku)) exact_count,"
                "(select min(l.item_id) from dim_walmart_listings l "
                "where l.source_account_ref=:account and l.store_id=s.store_id "
                "and trim(l.local_sku)=trim(s.local_sku) and trim(l.msku)=trim(s.msku)) exact_item "
                "from fact_walmart_sample_order_items s where s.source_account_ref=:account "
                "and s.business_date_utc_minus_7=:day and s.item_id is null),"
                "resolved as (select id,case when sku_count=1 then sku_item "
                "when sku_count>1 and exact_count=1 then exact_item else null end item_id "
                "from candidates) update fact_walmart_sample_order_items s set item_id=r.item_id,"
                "updated_at=:now from resolved r where s.id=r.id and r.item_id is not null"
            ),
            {"account": self.source_account_ref, "day": self.business_date, "now": now},
        )
        return int(
            self.session.execute(
                text(
                    "select count(*) from fact_walmart_sample_order_items "
                    "where source_account_ref=:account and business_date_utc_minus_7=:day "
                    "and is_valid_sample=true and item_id is null"
                ),
                {"account": self.source_account_ref, "day": self.business_date},
            ).scalar_one()
        )

    def _reprice_refunds(self) -> int:
        refunds = (
            self.session.execute(
                text(
                    "select id,store_id,item_id,msku,local_sku,customer_order_id,purchase_order_id,"
                    "quantity,refund_amount,refund_currency_code from fact_walmart_refund_items "
                    "where source_account_ref=:account and business_date_la=:day"
                ),
                {"account": self.source_account_ref, "day": self.business_date},
            )
            .mappings()
            .all()
        )
        unresolved = 0
        now = _now()
        for refund in refunds:
            quantity = _decimal(refund["quantity"])
            provider_refund = _decimal(refund["refund_amount"])
            order = self._match_refund_order_line(refund)
            unit_sales_amount = _order_unit_sales_amount(order)
            commission_rate = self._store_commission_rate(refund.get("store_id"))
            status = "calculated"
            gross: Decimal | None = None
            commission: Decimal | None = None
            net: Decimal | None = None
            if quantity is None or quantity <= 0:
                status = "quantity_missing"
            elif order is None:
                status = "order_not_matched"
            elif unit_sales_amount is None:
                status = "unit_price_missing"
            else:
                gross, commission, net = _refund_amounts(
                    unit_sales_amount,
                    quantity,
                    commission_rate,
                )
            if status != "calculated":
                unresolved += 1
            self.session.execute(
                text(
                    "insert into dws_walmart_refund_business_amounts "
                    "(id,refund_fact_id,source_account_ref,business_date_la,store_id,item_id,"
                    "local_sku,source_order_item_id,quantity,unit_sales_amount,gross_refund_sales_amount,"
                    "commission_rate,commission_amount,net_refund_amount,currency_code,"
                    "provider_refund_amount,provider_refund_currency_code,calculation_status,"
                    "rule_version,calculated_at,created_at,updated_at) values "
                    "(:id,:refund_fact_id,:source_account_ref,:business_date_la,:store_id,:item_id,"
                    ":local_sku,:source_order_item_id,:quantity,:unit_sales_amount,"
                    ":gross_refund_sales_amount,:commission_rate,:commission_amount,"
                    ":net_refund_amount,:currency_code,:provider_refund_amount,"
                    ":provider_refund_currency_code,:calculation_status,:rule_version,"
                    ":calculated_at,:created_at,:updated_at) on conflict (refund_fact_id) do update set "
                    "source_order_item_id=excluded.source_order_item_id,quantity=excluded.quantity,"
                    "unit_sales_amount=excluded.unit_sales_amount,"
                    "gross_refund_sales_amount=excluded.gross_refund_sales_amount,"
                    "commission_rate=excluded.commission_rate,commission_amount=excluded.commission_amount,"
                    "net_refund_amount=excluded.net_refund_amount,currency_code=excluded.currency_code,"
                    "provider_refund_amount=excluded.provider_refund_amount,"
                    "provider_refund_currency_code=excluded.provider_refund_currency_code,"
                    "calculation_status=excluded.calculation_status,rule_version=excluded.rule_version,"
                    "calculated_at=excluded.calculated_at,updated_at=excluded.updated_at"
                ),
                {
                    "id": str(uuid4()),
                    "refund_fact_id": str(refund["id"]),
                    "source_account_ref": self.source_account_ref,
                    "business_date_la": self.business_date,
                    "store_id": refund.get("store_id"),
                    "item_id": refund.get("item_id"),
                    "local_sku": refund.get("local_sku"),
                    "source_order_item_id": str(order["id"]) if order is not None else None,
                    "quantity": quantity,
                    "unit_sales_amount": unit_sales_amount,
                    "gross_refund_sales_amount": gross,
                    "commission_rate": commission_rate,
                    "commission_amount": commission,
                    "net_refund_amount": net,
                    "currency_code": (
                        order.get("sales_revenue_currency_code")
                        if order is not None
                        else refund.get("refund_currency_code")
                    ),
                    "provider_refund_amount": provider_refund,
                    "provider_refund_currency_code": refund.get("refund_currency_code"),
                    "calculation_status": status,
                    "rule_version": REFUND_RULE_VERSION,
                    "calculated_at": now,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return unresolved

    def _match_refund_order_line(self, refund: Mapping[str, Any]) -> Mapping[str, Any] | None:
        customer_order_id = _text_or_none(refund.get("customer_order_id"))
        purchase_order_id = _text_or_none(refund.get("purchase_order_id"))
        if not customer_order_id and not purchase_order_id:
            return None
        return (
            self.session.execute(
                text(
                    "select id,source_order_id,store_id,item_id,msku,local_sku,quantity,"
                    "sales_revenue_amount,sales_revenue_currency_code,business_date_la "
                    "from fact_walmart_order_items where source_account_ref=:account "
                    "and ((:customer_order_id is not null and source_order_id=:customer_order_id) "
                    "or (:purchase_order_id is not null and source_order_id=:purchase_order_id)) "
                    "and (:store_id is null or store_id=:store_id) and ("
                    "(:item_id is not null and item_id=:item_id) or "
                    "(:local_sku is not null and trim(local_sku)=trim(:local_sku)) or "
                    "(:msku is not null and trim(msku)=trim(:msku))) "
                    "order by case when :item_id is not null and item_id=:item_id then 0 "
                    "when :local_sku is not null and trim(local_sku)=trim(:local_sku) then 1 else 2 end,"
                    "business_date_la desc nulls last,updated_at desc limit 1"
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

    def _store_commission_rate(self, store_id: object) -> Decimal:
        if store_id is None:
            return DEFAULT_STORE_COMMISSION_RATE
        value = self.session.execute(
            text(
                "select commission_rate from ref_store_commission_rule_versions "
                "where source_account_ref=:account and platform_code='walmart' "
                "and store_id=:store_id and is_active=true and effective_from<=:day "
                "and (effective_to is null or effective_to>:day) "
                "order by effective_from desc limit 1"
            ),
            {
                "account": self.source_account_ref,
                "store_id": str(store_id),
                "day": self.business_date,
            },
        ).scalar_one_or_none()
        return _decimal(value) or DEFAULT_STORE_COMMISSION_RATE

    def _refresh_daily_sales_mart(self) -> int:
        now = _now()
        return_status = (
            "provider_permission_403" if self.summary.return_permission_403 else "loaded"
        )
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
                "coalesce(msku,'') msku,local_sku,product_name,coalesce(sales_qty,0) sales_qty,"
                "coalesce(order_count,0) order_count,coalesce(sales_amount,0) sales_amount,"
                "coalesce(sales_currency_code,'USD') currency_code from fact_walmart_sales_item_daily "
                "where source_account_ref=:account and business_date_la=:day and allocation_status='direct'),"
                "sample as (select source_account_ref,business_date_utc_minus_7 business_date_la,store_id,item_id,"
                "sum(coalesce(unit_price_amount,0)*coalesce(quantity,0)) sample_amount "
                "from fact_walmart_sample_order_items where source_account_ref=:account "
                "and business_date_utc_minus_7=:day and is_valid_sample=true and item_id is not null "
                "group by 1,2,3,4),"
                "r as (select f.source_account_ref,f.business_date_la,f.store_id,f.item_id,"
                "sum(coalesce(f.quantity,0)) return_qty,"
                "sum(coalesce(b.net_refund_amount,0)) filter (where b.calculation_status='calculated') refund_amount,"
                "coalesce(max(b.currency_code) filter (where b.calculation_status='calculated'),"
                "max(f.refund_currency_code),'USD') refund_currency_code,"
                "count(*) filter (where b.calculation_status is distinct from 'calculated') refund_unpriced_count "
                "from fact_walmart_refund_items f left join dws_walmart_refund_business_amounts b "
                "on b.refund_fact_id=f.id where f.source_account_ref=:account and f.business_date_la=:day "
                "and f.store_id is not null and f.item_id is not null group by 1,2,3,4),"
                "a as (select source_account_ref,business_date_la,store_id,item_id,msku,"
                "sum(coalesce(ad_spend_amount,0)) ad_spend from fact_walmart_ad_item_sp_daily "
                "where source_account_ref=:account and business_date_la=:day and store_id is not null "
                "and item_id is not null and msku is not null and trim(msku)<>'' group by 1,2,3,4,5),"
                "commission as (select distinct on (store_id) store_id,id rule_id,commission_rate,rule_version "
                "from ref_store_commission_rule_versions where source_account_ref=:account "
                "and platform_code='walmart' and is_active=true and effective_from<=:day "
                "and (effective_to is null or effective_to>:day) "
                "order by store_id,effective_from desc,created_at desc),"
                "sku as (select distinct on (i.source_account_ref,"
                "lower(trim(coalesce(nullif(trim(p.sku),''),nullif(trim(i.lingxing_sku_code),''))))) "
                "i.source_account_ref,"
                "lower(trim(coalesce(nullif(trim(p.sku),''),nullif(trim(i.lingxing_sku_code),'')))) sku_key,"
                "coalesce(nullif(trim(c.owner_name),''),nullif(trim(c.owner_uid),'')) owner_ref,"
                "coalesce(b.purchase_cost_cny,c.purchase_cost_cny,"
                "case when p.currency_code='CNY' then p.purchase_price end) purchase_cost_cny,"
                "pm.wfs_fulfillment_fee_usd wfs_fee_usd,"
                "coalesce(pm.first_leg_fee_cny,"
                "case when b.unit_first_leg_currency='CNY' then b.unit_first_leg_cost end,"
                "case when c.us_first_leg_currency='CNY' then c.us_first_leg_cost end) first_leg_cny,"
                "pr.usd_cny_rate,pr.fx_date,pr.fx_source from dwd_lingxing_sku_identity_index i "
                "left join products p on p.id=i.product_id and p.deleted_at is null "
                "left join dwd_lingxing_sku_product_info_current c on c.identity_id=i.id "
                "left join dws_sku_base_profile_current b on b.identity_id=i.id "
                "left join dws_product_management_pricing_current pm on pm.identity_id=i.id "
                "left join ref_product_pricing_rule_versions pr on pr.id=pm.rule_version_id "
                "where i.source_account_ref=:account and i.is_active=true "
                "and coalesce(nullif(trim(p.sku),''),nullif(trim(i.lingxing_sku_code),'')) is not null "
                "order by i.source_account_ref,"
                "lower(trim(coalesce(nullif(trim(p.sku),''),nullif(trim(i.lingxing_sku_code),'')))),"
                "case when i.mapping_status='confirmed' then 0 else 1 end,"
                "c.source_observed_at desc nulls last,i.updated_at desc),"
                "base as (select s.*,l.store_name,coalesce(nullif(trim(l.msku),''),nullif(trim(s.msku),'')) listing_msku,"
                "coalesce(nullif(trim(l.local_sku),''),nullif(trim(s.local_sku),''),s.item_id) effective_sku,"
                "l.local_name,l.title,l.picture_url,l.platform_code,l.wfs_available_quantity,"
                "coalesce(sample.sample_amount,0) sample_amount,r.return_qty,r.refund_amount,r.refund_currency_code,"
                "coalesce(r.refund_unpriced_count,0) refund_unpriced_count,coalesce(a.ad_spend,0) ad_spend,"
                "sku.owner_ref,sku.purchase_cost_cny,sku.wfs_fee_usd,sku.first_leg_cny,sku.usd_cny_rate,"
                "sku.fx_date,sku.fx_source,coalesce(commission.commission_rate,0.15) commission_rate,"
                "commission.rule_id commission_rule_id from s left join dim_walmart_listings l "
                "on l.source_account_ref=s.source_account_ref and l.store_id=s.store_id and l.item_id=s.item_id "
                "left join sample on sample.source_account_ref=s.source_account_ref "
                "and sample.business_date_la=s.business_date_la and sample.store_id=s.store_id "
                "and sample.item_id=s.item_id left join r on r.source_account_ref=s.source_account_ref "
                "and r.business_date_la=s.business_date_la and r.store_id=s.store_id and r.item_id=s.item_id "
                "left join a on a.source_account_ref=s.source_account_ref and a.business_date_la=s.business_date_la "
                "and a.store_id=s.store_id and a.item_id=s.item_id and a.msku=coalesce(nullif(trim(l.msku),''),"
                "nullif(trim(s.msku),'')) left join sku on sku.source_account_ref=s.source_account_ref "
                "and sku.sku_key=lower(trim(coalesce(nullif(trim(l.local_sku),''),nullif(trim(s.local_sku),''),s.item_id))) "
                "left join commission on commission.store_id=s.store_id) "
                "insert into mart_daily_sales_item_day "
                "(id,business_date_la,source_account_ref,platform_code,store_id,store_name,item_id,msku,local_sku,"
                "local_name,title,picture_url,owner_ref,sales_qty,order_count,sales_amount,sales_currency_code,"
                "sample_amount,sales_amount_excluding_sample,return_qty,refund_amount,refund_currency_code,"
                "ad_spend_amount,ad_spend_currency_code,ad_ratio,wfs_available_quantity,wfs_fee_unit_amount,"
                "wfs_fee_total_amount,wfs_fee_currency_code,purchase_cost_unit_cny,purchase_cost_total_usd,"
                "first_leg_cost_unit_cny,first_leg_cost_total_usd,exchange_rate,fx_date,fx_source,commission_rate,"
                "commission_rule_version_id,commission_fee_amount,commission_fee_currency_code,cost_status,"
                "missing_cost_codes_json,sales_7d_trend_json,source_lineage_json,calc_version,calculated_at,"
                "created_at,updated_at) select gen_random_uuid(),base.business_date_la,base.source_account_ref,"
                "coalesce(base.platform_code,'walmart'),base.store_id,base.store_name,base.item_id,base.listing_msku,"
                "base.effective_sku,base.local_name,base.title,base.picture_url,base.owner_ref,base.sales_qty,"
                "base.order_count,base.sales_amount,base.currency_code,base.sample_amount,base.sales_amount,"
                "base.return_qty,base.refund_amount,base.refund_currency_code,base.ad_spend,'USD',"
                "case when base.sales_amount>0 then base.ad_spend/base.sales_amount else null end,"
                "base.wfs_available_quantity,base.wfs_fee_usd,base.wfs_fee_usd*base.sales_qty,'USD',"
                "base.purchase_cost_cny,case when base.purchase_cost_cny is not null and base.usd_cny_rate>0 "
                "then base.purchase_cost_cny*base.sales_qty/base.usd_cny_rate end,base.first_leg_cny,"
                "case when base.first_leg_cny is not null and base.usd_cny_rate>0 "
                "then base.first_leg_cny*base.sales_qty/base.usd_cny_rate end,base.usd_cny_rate,base.fx_date,"
                "base.fx_source,base.commission_rate,base.commission_rule_id,base.sales_amount*base.commission_rate,"
                "base.currency_code,case when base.purchase_cost_cny is not null and base.wfs_fee_usd is not null "
                "and base.first_leg_cny is not null and base.usd_cny_rate>0 and base.refund_unpriced_count=0 "
                "then 'complete' when base.purchase_cost_cny is not null or base.wfs_fee_usd is not null "
                "or base.first_leg_cny is not null or base.refund_unpriced_count>0 then 'partial' else 'missing' end,"
                "to_jsonb(array_remove(array["
                "case when base.purchase_cost_cny is null then 'purchase_cost_missing' end,"
                "case when base.wfs_fee_usd is null then 'wfs_fee_missing' end,"
                "case when base.first_leg_cny is null then 'first_leg_cost_missing' end,"
                "case when (base.purchase_cost_cny is not null or base.first_leg_cny is not null) "
                "and (base.usd_cny_rate is null or base.usd_cny_rate<=0) then 'fx_rate_missing' end,"
                "case when base.refund_unpriced_count>0 then 'refund_business_amount_missing' end]::text[],null)),"
                "'[]'::jsonb,jsonb_build_object('runner',cast(:runner as text),'basis','fact_walmart_sales_item_daily',"
                "'sku_cost_match','daily_sales.local_sku=product_management.sku','sample_basis',"
                "'fact_walmart_sample_order_items','refund_basis','dws_walmart_refund_business_amounts',"
                "'return_status',cast(:return_status as text)),cast(:runner as text),:now,:now,:now from base"
            ),
            {
                "account": self.source_account_ref,
                "day": self.business_date,
                "runner": BUSINESS_RULE_RUNNER_VERSION,
                "return_status": return_status,
                "now": now,
            },
        )
        return _row_count(
            self.session,
            "mart_daily_sales_item_day",
            self.source_account_ref,
            self.business_date,
        )

    def _refresh_order_profit_mart(self) -> int:
        now = _now()
        self.session.execute(
            text(
                "delete from mart_order_profit_sku_day where source_account_ref=:account "
                "and business_date_la=:day"
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
                "sum(coalesce(storage_fee_total_amount,0)),null,'USD',"
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
                "runner": BUSINESS_RULE_RUNNER_VERSION,
                "now": now,
            },
        )
        return _row_count(
            self.session,
            "mart_order_profit_sku_day",
            self.source_account_ref,
            self.business_date,
        )


def _nested_text(row: dict[str, Any], list_key: str, field_name: str) -> str | None:
    value = _nested_first(row, list_key, field_name)
    return _text_or_none(value)


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _order_unit_sales_amount(order: Mapping[str, Any] | None) -> Decimal | None:
    if order is None:
        return None
    total = _decimal(order.get("sales_revenue_amount"))
    quantity = _decimal(order.get("quantity"))
    if total is None or quantity is None or quantity <= 0:
        return None
    return total / quantity


def main() -> None:
    args = parse_args()
    if os.environ.get(AUTHORIZED_ENV) != "true":
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_NOT_AUTHORIZED")
    settings = get_settings()
    if settings.app_env is not AppEnvironment.PRODUCTION:
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_REQUIRES_PRODUCTION_ENV")
    if not settings.lingxing_enable_real_calls:
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_REAL_CALLS_DISABLED")
    business_date = date.fromisoformat(args.business_date)
    source_account_ref = _safe_scope(args.source_account_ref)
    if not 1 <= args.page_size <= 200:
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_PAGE_SIZE_INVALID")

    session_factory = get_session_factory()
    with session_factory() as session:
        IntegrationCatalogService(session).bootstrap_data_pages_governance(source_account_ref)
        with data_pages_client() as client:
            summary = DataPagesRealSyncRunner(
                session=session,
                client=client,
                source_account_ref=source_account_ref,
                business_date=business_date,
                page_size=args.page_size,
                campaign_type=args.campaign_type,
                max_advertisers=args.max_advertisers,
            ).execute()
    for line in summary.safe_lines():
        print(line)
