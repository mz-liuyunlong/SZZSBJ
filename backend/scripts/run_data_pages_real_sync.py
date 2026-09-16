from __future__ import annotations

import argparse
import hashlib
import os
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from uuid import uuid4

import httpx
from pydantic import JsonValue
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment, get_settings
from app.db.session import get_session_factory
from app.integrations.lingxing.client import (
    LingxingCaptureRequest,
    LingxingEndpoint,
    LingxingPageRequest,
    LingxingRawEnvelope,
    LingxingReadonlyClient,
)
from app.integrations.lingxing.security import canonical_json, redact_json
from app.integrations.lingxing.token_manager import LingxingTokenClient, LingxingTokenManager
from app.modules.integration_sync.catalog import IntegrationCatalogService
from app.modules.integration_sync.data_pages_catalog import DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY
from app.modules.integration_sync.parsers.lingxing_data_pages import DataPagesParserKey

AUTHORIZED_ENV = "DATA_PAGES_REAL_SYNC_AUTHORIZED"
RUNNER_VERSION = "real-data-1.0"
DEFAULT_DATE = date(2026, 9, 1)
WALMART_PLATFORM_CODE = "10008"


class DataPagesRealSyncError(RuntimeError):
    """Safe one-time DATA-PAGES sync error without credentials or payload details."""


@dataclass(slots=True)
class DataPagesRealSyncSummary:
    source_account_ref: str
    business_date: date
    raw_blobs: int = 0
    store_rows: int = 0
    listing_rows: int = 0
    advertiser_rows: int = 0
    sales_rows: int = 0
    order_rows: int = 0
    refund_rows: int = 0
    ad_rows: int = 0
    mart_daily_sales_rows: int = 0
    mart_order_profit_rows: int = 0
    mart_listing_rows: int = 0
    requested_interfaces: list[str] = field(default_factory=list)
    skipped_interfaces: list[str] = field(default_factory=list)

    def safe_lines(self) -> list[str]:
        return [
            f"source_account_ref={self.source_account_ref}",
            f"business_date={self.business_date.isoformat()}",
            f"requested_interfaces={len(self.requested_interfaces)}",
            f"skipped_interfaces={len(self.skipped_interfaces)}",
            f"raw_blobs={self.raw_blobs}",
            f"store_rows={self.store_rows}",
            f"listing_rows={self.listing_rows}",
            f"advertiser_rows={self.advertiser_rows}",
            f"sales_rows={self.sales_rows}",
            f"order_rows={self.order_rows}",
            f"refund_rows={self.refund_rows}",
            f"ad_rows={self.ad_rows}",
            f"mart_daily_sales_rows={self.mart_daily_sales_rows}",
            f"mart_order_profit_rows={self.mart_order_profit_rows}",
            f"mart_listing_rows={self.mart_listing_rows}",
        ]


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    parser_key: DataPagesParserKey
    envelope: LingxingRawEnvelope
    raw_blob_id: str | None
    rows: tuple[dict[str, Any], ...]


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
    page_size = min(args.page_size, settings.lingxing_sample_page_size)
    if page_size < 1:
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
                page_size=page_size,
                campaign_type=args.campaign_type,
                max_advertisers=args.max_advertisers,
            ).execute()
    for line in summary.safe_lines():
        print(line)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one authorized DATA-PAGES real sync for a single business date."
    )
    parser.add_argument("--business-date", default=DEFAULT_DATE.isoformat())
    parser.add_argument("--source-account-ref", required=True)
    parser.add_argument("--page-size", type=int, default=3)
    parser.add_argument("--campaign-type", default="SP")
    parser.add_argument("--max-advertisers", type=int, default=20)
    return parser.parse_args()


@contextmanager
def data_pages_client() -> Iterable[LingxingReadonlyClient]:
    settings = get_settings()
    token_client = LingxingTokenClient(settings)
    token_manager = LingxingTokenManager(token_client, settings)
    client = LingxingReadonlyClient(
        settings,
        token_provider=token_manager,
        success_evaluator=data_pages_response_succeeded,
    )
    try:
        yield client
    finally:
        client.close()
        token_client.close()


def data_pages_response_succeeded(
    endpoint: LingxingEndpoint,
    response: httpx.Response,
    payload: JsonValue,
) -> bool:
    del endpoint
    if not response.is_success:
        return False
    if not isinstance(payload, dict):
        return True
    code = payload.get("code")
    if code is None:
        return True
    normalized = str(code).strip().lower()
    return normalized in {"0", "200", "success"}


class DataPagesRealSyncRunner:
    def __init__(
        self,
        *,
        session: Session,
        client: LingxingReadonlyClient,
        source_account_ref: str,
        business_date: date,
        page_size: int,
        campaign_type: str,
        max_advertisers: int,
    ) -> None:
        self.session = session
        self.client = client
        self.source_account_ref = source_account_ref
        self.business_date = business_date
        self.page_size = page_size
        self.campaign_type = campaign_type
        self.max_advertisers = max(1, max_advertisers)
        self.summary = DataPagesRealSyncSummary(source_account_ref, business_date)
        self.store_ids: tuple[str, ...] = (source_account_ref,)
        self.advertiser_ids: tuple[str, ...] = ()

    def execute(self) -> DataPagesRealSyncSummary:
        stores = self._request("seller_list_multi_platform", self._seller_body())
        self.store_ids = tuple(_unique(_field(row, "store_id") for row in stores.rows)) or (
            self.source_account_ref,
        )
        self.summary.store_rows = self._write_stores(stores.rows)

        advertisers = self._request("walmart_advertiser_list", self._advertiser_body())
        self.advertiser_ids = tuple(
            _unique(_field(row, "advertiserId", "advertiser_id") for row in advertisers.rows)
        )
        self.summary.advertiser_rows = self._write_advertisers(advertisers.rows)

        listings = self._request("walmart_listing_list", self._listing_body())
        self.summary.listing_rows = self._write_listings(listings.rows)

        sales_rows: list[dict[str, Any]] = []
        for result_type in (1, 2, 3):
            response = self._request(
                "sale_stat_page_list",
                self._sale_stat_body(result_type),
                body_suffix=f"result_type={result_type}",
            )
            sales_rows.extend({**row, "_result_type": result_type} for row in response.rows)
        self.summary.sales_rows = self._write_sales(sales_rows)

        orders = self._request("order_v2_list", self._order_body())
        self.summary.order_rows = self._write_orders(orders.rows)

        refunds = self._request("walmart_return_order_list", self._return_body())
        self.summary.refund_rows = self._write_refunds(refunds.rows)

        ad_rows: list[dict[str, Any]] = []
        if not self.advertiser_ids:
            self.summary.skipped_interfaces.append("walmartAdItemSpList:no_advertiser_id")
        for advertiser_id in self.advertiser_ids[: self.max_advertisers]:
            ads = self._request(
                "walmart_ad_item_sp_list",
                self._ad_item_body(advertiser_id),
                body_suffix="advertiserId",
            )
            ad_rows.extend(ads.rows)
        self.summary.ad_rows = self._write_ads(ad_rows)

        self.summary.mart_listing_rows = self._refresh_listing_mart()
        self.summary.mart_daily_sales_rows = self._refresh_daily_sales_mart()
        self.summary.mart_order_profit_rows = self._refresh_order_profit_mart()
        self.session.commit()
        return self.summary

    def _request(
        self,
        parser_key: DataPagesParserKey,
        body: dict[str, Any],
        *,
        body_suffix: str | None = None,
    ) -> ProviderResponse:
        spec = DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY[parser_key]
        capture = LingxingCaptureRequest(
            api_path=spec.endpoint_path,
            pages=(
                LingxingPageRequest(
                    page_no=1,
                    page_size=self.page_size,
                    params=None,
                    body=cast(JsonValue, body),
                ),
            ),
            store_ids=self.store_ids,
            object_type=f"data_pages_{parser_key}",
            trace_id=f"data-pages-{self.business_date.isoformat()}",
            run_id=f"data-pages-{self.business_date.isoformat()}",
            batch_id=f"{parser_key}:{body_suffix or 'page1'}",
            data_date=self.business_date,
            extra={"runner_version": RUNNER_VERSION, "parser_key": parser_key},
        )
        envelope = self.client.fetch_pages(capture)[0]
        self.summary.requested_interfaces.append(spec.interface_key)
        raw_blob_id = self._persist_raw_blob(parser_key, envelope)
        if not envelope.is_success or envelope.response_json is None:
            raise DataPagesRealSyncError(f"DATA_PAGES_PROVIDER_FAILED:{spec.interface_key}")
        return ProviderResponse(
            parser_key=parser_key,
            envelope=envelope,
            raw_blob_id=raw_blob_id,
            rows=tuple(_rows_for(parser_key, envelope.response_json)),
        )

    def _persist_raw_blob(
        self,
        parser_key: DataPagesParserKey,
        envelope: LingxingRawEnvelope,
    ) -> str | None:
        if envelope.response_json is None:
            return None
        spec = DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY[parser_key]
        policy_id = self.session.execute(
            text(
                "select id from gov_raw_retention_policies "
                "where policy_key = :policy_key and is_active = true"
            ),
            {"policy_key": spec.retention_policy_key},
        ).scalar_one()
        payload = redact_json(envelope.response_json)
        encoded = canonical_json(payload).encode("utf-8")
        response_hash = hashlib.sha256(encoded).hexdigest()
        row = self.session.execute(
            text(
                "insert into ods_api_raw_blobs "
                "(id, response_hash, payload_json, payload_bytes, content_type, storage_mode, "
                "retention_policy_id, received_at, created_at) "
                "values (:id, :response_hash, cast(:payload_json as jsonb), :payload_bytes, "
                ":content_type, 'database', :retention_policy_id, :received_at, :created_at) "
                "on conflict (response_hash) do update set received_at = excluded.received_at "
                "returning id"
            ),
            {
                "id": str(uuid4()),
                "response_hash": response_hash,
                "payload_json": canonical_json(payload),
                "payload_bytes": len(encoded),
                "content_type": "application/json",
                "retention_policy_id": str(policy_id),
                "received_at": envelope.pulled_at,
                "created_at": _now(),
            },
        ).scalar_one()
        self.summary.raw_blobs += 1
        return str(row)

    def _seller_body(self) -> dict[str, Any]:
        return {"offset": 0, "length": self.page_size, "platform_code": WALMART_PLATFORM_CODE}

    def _advertiser_body(self) -> dict[str, Any]:
        return {"paging": True, "page": 1, "limit": self.page_size}

    def _listing_body(self) -> dict[str, Any]:
        return {"offset": 0, "length": self.page_size}

    def _sale_stat_body(self, result_type: int) -> dict[str, Any]:
        return {
            "data_type": 1,
            "date_unit": "day",
            "start_date": self.business_date.isoformat(),
            "end_date": self.business_date.isoformat(),
            "page": 1,
            "length": self.page_size,
            "result_type": result_type,
            "sids": list(self.store_ids),
        }

    def _order_body(self) -> dict[str, Any]:
        return {
            "date_type": "global_purchase_time",
            "start_time": f"{self.business_date.isoformat()} 00:00:00",
            "end_time": f"{self.business_date.isoformat()} 23:59:59",
            "offset": 0,
            "length": self.page_size,
            "platform_code": WALMART_PLATFORM_CODE,
        }

    def _return_body(self) -> dict[str, Any]:
        return {
            "dateType": "1",
            "startDate": self.business_date.isoformat(),
            "endDate": self.business_date.isoformat(),
            "pageNum": 1,
            "pageSize": self.page_size,
            "returnTypeList": ["REFUND"],
            "storeIdList": list(self.store_ids),
        }

    def _ad_item_body(self, advertiser_id: str) -> dict[str, Any]:
        return {
            "advertiserIds": [advertiser_id],
            "campaignType": self.campaign_type,
            "startDate": self.business_date.isoformat(),
            "endDate": self.business_date.isoformat(),
            "pageNum": 1,
            "pageSize": self.page_size,
            "paging": True,
        }

    def _write_stores(self, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            store_id = _field(row, "store_id", "sid")
            platform_code = _field(row, "platform_code") or WALMART_PLATFORM_CODE
            if not store_id:
                continue
            self.session.execute(
                text(
                    "insert into dim_lingxing_stores "
                    "(id, source_account_ref, platform_name_raw, platform_code_raw, "
                    "platform_code, store_id, store_name, sid, currency_code, raw_status, "
                    "is_sync, synced_at, created_at, updated_at) "
                    "values (:id, :source_account_ref, :platform_name_raw, :platform_code_raw, "
                    ":platform_code, :store_id, :store_name, :sid, :currency_code, :raw_status, "
                    ":is_sync, :synced_at, :created_at, :updated_at) "
                    "on conflict (source_account_ref, platform_code_raw, store_id) do update set "
                    "store_name = excluded.store_name, sid = excluded.sid, raw_status = "
                    "excluded.raw_status, is_sync = excluded.is_sync, synced_at = excluded.synced_at, "
                    "updated_at = excluded.updated_at"
                ),
                {
                    "id": str(uuid4()),
                    "source_account_ref": self.source_account_ref,
                    "platform_name_raw": _field(row, "platform_name"),
                    "platform_code_raw": platform_code,
                    "platform_code": _platform_code(platform_code),
                    "store_id": store_id,
                    "store_name": _field(row, "store_name", "name"),
                    "sid": _field(row, "sid"),
                    "currency_code": _field(row, "currency"),
                    "raw_status": _field(row, "status"),
                    "is_sync": _bool(row.get("is_sync")),
                    **_timestamps(),
                },
            )
            count += 1
        self.session.commit()
        return count

    def _write_advertisers(self, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            advertiser_id = _field(row, "advertiserId", "advertiser_id")
            if not advertiser_id:
                continue
            self.session.execute(
                text(
                    "insert into dim_walmart_advertisers "
                    "(id, source_account_ref, advertiser_id, advertiser_name, store_id, "
                    "platform_code, raw_status, standard_status, synced_at, created_at, updated_at) "
                    "values (:id, :source_account_ref, :advertiser_id, :advertiser_name, :store_id, "
                    ":platform_code, :raw_status, :standard_status, :synced_at, :created_at, "
                    ":updated_at) "
                    "on conflict (source_account_ref, advertiser_id) do update set "
                    "advertiser_name = excluded.advertiser_name, raw_status = excluded.raw_status, "
                    "synced_at = excluded.synced_at, updated_at = excluded.updated_at"
                ),
                {
                    "id": str(uuid4()),
                    "source_account_ref": self.source_account_ref,
                    "advertiser_id": advertiser_id,
                    "advertiser_name": _field(row, "advertiserName", "advertiser_name"),
                    "store_id": _field(row, "storeId", "store_id"),
                    "platform_code": WALMART_PLATFORM_CODE,
                    "raw_status": _field(row, "status"),
                    "standard_status": _field(row, "status"),
                    **_timestamps(),
                },
            )
            count += 1
        self.session.commit()
        return count

    def _write_listings(self, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            item_id = _field(row, "item_id", "itemId")
            store_id = _field(row, "store_id", "sid")
            if not item_id or not store_id:
                continue
            self.session.execute(
                text(
                    "insert into dim_walmart_listings "
                    "(id, source_account_ref, platform_code, platform_code_raw, store_id, store_name, "
                    "item_id, msku, local_sku, local_name, title, picture_url, item_url, "
                    "price_amount, price_currency_code, listing_start_source_raw, "
                    "available_quantity, wfs_available_quantity, average_rating, review_count, "
                    "gtin, upc, brand, raw_status, standard_status, fulfillment_type, "
                    "fulfillment_type_name, variant_unique_id, synced_at, created_at, updated_at) "
                    "values (:id, :source_account_ref, :platform_code, :platform_code_raw, "
                    ":store_id, :store_name, :item_id, :msku, :local_sku, :local_name, :title, "
                    ":picture_url, :item_url, :price_amount, :price_currency_code, "
                    ":listing_start_source_raw, :available_quantity, :wfs_available_quantity, "
                    ":average_rating, :review_count, :gtin, :upc, :brand, :raw_status, "
                    ":standard_status, :fulfillment_type, :fulfillment_type_name, "
                    ":variant_unique_id, :synced_at, :created_at, :updated_at) "
                    "on conflict (source_account_ref, store_id, item_id) do update set "
                    "msku = excluded.msku, local_sku = excluded.local_sku, title = excluded.title, "
                    "picture_url = excluded.picture_url, price_amount = excluded.price_amount, "
                    "wfs_available_quantity = excluded.wfs_available_quantity, "
                    "available_quantity = excluded.available_quantity, review_count = excluded.review_count, "
                    "average_rating = excluded.average_rating, synced_at = excluded.synced_at, "
                    "updated_at = excluded.updated_at"
                ),
                {
                    "id": str(uuid4()),
                    "source_account_ref": self.source_account_ref,
                    "platform_code": WALMART_PLATFORM_CODE,
                    "platform_code_raw": _field(row, "platform_code") or WALMART_PLATFORM_CODE,
                    "store_id": store_id,
                    "store_name": _field(row, "store_name"),
                    "item_id": item_id,
                    "msku": _field(row, "msku"),
                    "local_sku": _field(row, "local_sku", "sku"),
                    "local_name": _field(row, "local_name"),
                    "title": _field(row, "title"),
                    "picture_url": _field(row, "picture_url", "image"),
                    "item_url": _field(row, "item_url"),
                    "price_amount": _decimal(row.get("price")),
                    "price_currency_code": _field(row, "currency", "currency_code") or "USD",
                    "listing_start_source_raw": _field(row, "listing_start_time"),
                    "available_quantity": _decimal(row.get("available_quantity")),
                    "wfs_available_quantity": _decimal(row.get("wfs_available_quantity")),
                    "average_rating": _decimal(row.get("average_rating")),
                    "review_count": _int(row.get("review_count")),
                    "gtin": _field(row, "gtin"),
                    "upc": _field(row, "upc"),
                    "brand": _field(row, "brand"),
                    "raw_status": _field(row, "status", "status_name"),
                    "standard_status": _field(row, "status_name", "status"),
                    "fulfillment_type": _field(row, "fulfillment_type"),
                    "fulfillment_type_name": _field(row, "fulfillment_type_name"),
                    "variant_unique_id": _field(row, "variant_unique_id"),
                    **_timestamps(),
                },
            )
            count += 1
        self.session.commit()
        return count

    def _write_sales(self, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            item_id = _first_value(row.get("platform_product_id"))
            store_id = _field(row, "sid", "store_id")
            if not item_id or not store_id:
                continue
            result_type = _int(row.get("_result_type")) or 0
            amount_fields = _sales_amount_fields(result_type, row.get("volumeTotal"))
            self.session.execute(
                text(
                    "insert into fact_walmart_sales_item_daily "
                    "(id, business_date_la, source_account_ref, platform_code, platform_code_raw, "
                    "store_id, sid, store_name, item_id, msku, local_sku, product_name, "
                    "sales_qty, order_count, sales_amount, sales_currency_code, source_date_raw, "
                    "source_group_key, allocation_status, date_collect_json, synced_at, created_at, "
                    "updated_at) values (:id, :business_date_la, :source_account_ref, "
                    ":platform_code, :platform_code_raw, :store_id, :sid, :store_name, :item_id, "
                    ":msku, :local_sku, :product_name, :sales_qty, :order_count, :sales_amount, "
                    ":sales_currency_code, :source_date_raw, :source_group_key, :allocation_status, "
                    "cast(:date_collect_json as jsonb), :synced_at, :created_at, :updated_at) "
                    "on conflict (business_date_la, source_account_ref, store_id, item_id) "
                    "do update set sales_qty = coalesce(excluded.sales_qty, "
                    "fact_walmart_sales_item_daily.sales_qty), order_count = coalesce("
                    "excluded.order_count, fact_walmart_sales_item_daily.order_count), "
                    "sales_amount = coalesce(excluded.sales_amount, "
                    "fact_walmart_sales_item_daily.sales_amount), updated_at = excluded.updated_at"
                ),
                {
                    "id": str(uuid4()),
                    "business_date_la": self.business_date,
                    "source_account_ref": self.source_account_ref,
                    "platform_code": WALMART_PLATFORM_CODE,
                    "platform_code_raw": _field(row, "platform_code") or WALMART_PLATFORM_CODE,
                    "store_id": store_id,
                    "sid": store_id,
                    "store_name": _field(row, "store_name"),
                    "item_id": item_id,
                    "msku": _field(row, "msku"),
                    "local_sku": _field(row, "sku", "local_sku"),
                    "product_name": _field(row, "product_name", "platform_product_title"),
                    "sales_currency_code": _field(row, "currency_code") or "USD",
                    "source_date_raw": _field(row, "date_collect") or self.business_date.isoformat(),
                    "source_group_key": _stable_hash(row),
                    "allocation_status": "direct",
                    "date_collect_json": canonical_json(row.get("date_collect")),
                    **amount_fields,
                    **_timestamps(),
                },
            )
            count += 1
        self.session.commit()
        return count

    def _write_orders(self, rows: Iterable[dict[str, Any]]) -> int:
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
                        "(id, source_account_ref, store_id, source_order_id, source_order_line_id, "
                        "source_line_hash, source_line_ordinal, item_id, msku, local_sku, quantity, "
                        "source_purchase_at_raw, business_date_la, order_status_raw, "
                        "order_sub_status_raw, flow_node_raw, sales_revenue_amount, "
                        "sales_revenue_currency_code, order_total_amount, order_total_currency_code, "
                        "discount_amount, discount_currency_code, is_sample_order, synced_at, "
                        "created_at, updated_at) values (:id, :source_account_ref, :store_id, "
                        ":source_order_id, :source_order_line_id, :source_line_hash, "
                        ":source_line_ordinal, :item_id, :msku, :local_sku, :quantity, "
                        ":source_purchase_at_raw, :business_date_la, :order_status_raw, "
                        ":order_sub_status_raw, :flow_node_raw, :sales_revenue_amount, "
                        ":sales_revenue_currency_code, :order_total_amount, :order_total_currency_code, "
                        ":discount_amount, :discount_currency_code, :is_sample_order, :synced_at, "
                        ":created_at, :updated_at) on conflict (source_account_ref, "
                        "source_order_id, source_line_hash) do update set quantity = excluded.quantity, "
                        "sales_revenue_amount = excluded.sales_revenue_amount, updated_at = excluded.updated_at"
                    ),
                    {
                        "id": str(uuid4()),
                        "source_account_ref": self.source_account_ref,
                        "store_id": _field(row, "store_id"),
                        "source_order_id": order_id,
                        "source_order_line_id": _field(item, "global_item_no", "order_item_no", "id"),
                        "source_line_hash": line_hash,
                        "source_line_ordinal": ordinal,
                        "item_id": _field(item, "item_id", "platform_product_id", "product_no"),
                        "msku": _field(item, "msku"),
                        "local_sku": _field(item, "local_sku", "sku"),
                        "quantity": _decimal(item.get("quantity")),
                        "source_purchase_at_raw": _field(row, "global_purchase_time"),
                        "business_date_la": self.business_date,
                        "order_status_raw": _field(row, "status"),
                        "order_sub_status_raw": _field(row, "status_sub"),
                        "flow_node_raw": _field(row, "flow_node"),
                        "sales_revenue_amount": _decimal(item.get("sales_revenue_amount")),
                        "sales_revenue_currency_code": _field(row, "amount_currency") or "USD",
                        "order_total_amount": _decimal(_nested_first(row, "transaction_info", "order_total_amount")),
                        "order_total_currency_code": _field(row, "amount_currency") or "USD",
                        "discount_amount": _decimal(item.get("discount_amount")),
                        "discount_currency_code": _field(row, "amount_currency") or "USD",
                        "is_sample_order": False,
                        **_timestamps(),
                    },
                )
                count += 1
        self.session.commit()
        return count

    def _write_refunds(self, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            return_type = _field(row, "returnType", "return_type")
            if return_type != "REFUND":
                continue
            return_id = _field(row, "returnOrderId", "return_order_id")
            items = row.get("items") if isinstance(row.get("items"), list) else [row]
            if not return_id:
                continue
            for ordinal, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                line_hash = _stable_hash({"return": return_id, "line": item, "ordinal": ordinal})
                self.session.execute(
                    text(
                        "insert into fact_walmart_refund_items "
                        "(id, source_account_ref, store_id, source_return_order_id, "
                        "source_return_line_id, source_line_hash, source_line_ordinal, "
                        "customer_order_id, purchase_order_id, item_id, msku, local_sku, "
                        "return_type_raw, return_type_name, refund_status_raw, return_order_date_raw, "
                        "business_date_la, status_time_raw, quantity, refund_amount, "
                        "refund_currency_code, tracking_no, synced_at, created_at, updated_at) "
                        "values (:id, :source_account_ref, :store_id, :source_return_order_id, "
                        ":source_return_line_id, :source_line_hash, :source_line_ordinal, "
                        ":customer_order_id, :purchase_order_id, :item_id, :msku, :local_sku, "
                        ":return_type_raw, :return_type_name, :refund_status_raw, "
                        ":return_order_date_raw, :business_date_la, :status_time_raw, :quantity, "
                        ":refund_amount, :refund_currency_code, :tracking_no, :synced_at, "
                        ":created_at, :updated_at) on conflict (source_account_ref, "
                        "source_return_order_id, source_line_hash) do update set "
                        "refund_amount = excluded.refund_amount, updated_at = excluded.updated_at"
                    ),
                    {
                        "id": str(uuid4()),
                        "source_account_ref": self.source_account_ref,
                        "store_id": _field(row, "storeId", "store_id"),
                        "source_return_order_id": return_id,
                        "source_return_line_id": _field(item, "returnLineId", "id"),
                        "source_line_hash": line_hash,
                        "source_line_ordinal": ordinal,
                        "customer_order_id": _field(row, "customerOrderId"),
                        "purchase_order_id": _field(item, "purchaseOrderId"),
                        "item_id": _field(item, "itemId"),
                        "msku": _field(item, "msku"),
                        "local_sku": _field(item, "localSku", "local_sku"),
                        "return_type_raw": "REFUND",
                        "return_type_name": _field(row, "returnTypeName"),
                        "refund_status_raw": _field(item, "currentRefundStatus", "status"),
                        "return_order_date_raw": _field(row, "returnOrderDate"),
                        "business_date_la": self.business_date,
                        "status_time_raw": _field(item, "statusTime"),
                        "quantity": _decimal(item.get("quantityDisplay")),
                        "refund_amount": _decimal(item.get("lineTotalAmount")),
                        "refund_currency_code": _field(item, "lineTotalCurrency") or "USD",
                        "tracking_no": _field(item, "trackingNo"),
                        **_timestamps(),
                    },
                )
                count += 1
        self.session.commit()
        return count

    def _write_ads(self, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            advertiser_id = _field(row, "advertiserId", "advertiser_id")
            if not advertiser_id:
                continue
            line_hash = _stable_hash(row)
            self.session.execute(
                text(
                    "insert into fact_walmart_ad_item_sp_daily "
                    "(id, business_date_la, source_account_ref, advertiser_id, store_id, item_id, "
                    "msku, campaign_id, ad_group_id, ad_item_id, source_line_hash, source_key, "
                    "ad_spend_amount, ad_spend_currency_code, attributed_sales_amount, "
                    "attributed_orders, attributed_units, advertised_sku_sales_amount, "
                    "advertised_sku_units, num_ads_clicks, num_ads_shown, acos, roas, cpc, ctr, "
                    "cvr, synced_at, created_at, updated_at) values (:id, :business_date_la, "
                    ":source_account_ref, :advertiser_id, :store_id, :item_id, :msku, "
                    ":campaign_id, :ad_group_id, :ad_item_id, :source_line_hash, :source_key, "
                    ":ad_spend_amount, :ad_spend_currency_code, :attributed_sales_amount, "
                    ":attributed_orders, :attributed_units, :advertised_sku_sales_amount, "
                    ":advertised_sku_units, :num_ads_clicks, :num_ads_shown, :acos, :roas, :cpc, "
                    ":ctr, :cvr, :synced_at, :created_at, :updated_at) on conflict "
                    "(business_date_la, source_account_ref, advertiser_id, source_line_hash) "
                    "do update set ad_spend_amount = excluded.ad_spend_amount, "
                    "num_ads_clicks = excluded.num_ads_clicks, updated_at = excluded.updated_at"
                ),
                {
                    "id": str(uuid4()),
                    "business_date_la": self.business_date,
                    "source_account_ref": self.source_account_ref,
                    "advertiser_id": advertiser_id,
                    "store_id": _field(row, "storeId", "store_id"),
                    "item_id": _field(row, "itemId", "item_id"),
                    "msku": _field(row, "msku"),
                    "campaign_id": _field(row, "campaignId"),
                    "ad_group_id": _field(row, "adGroupId"),
                    "ad_item_id": _field(row, "adItemId"),
                    "source_line_hash": line_hash,
                    "source_key": _field(row, "key"),
                    "ad_spend_amount": _decimal(row.get("adSpend")),
                    "ad_spend_currency_code": "USD",
                    "attributed_sales_amount": _decimal(row.get("attributedSales")),
                    "attributed_orders": _decimal(row.get("attributedOrders")),
                    "attributed_units": _decimal(row.get("attributedUnits")),
                    "advertised_sku_sales_amount": _decimal(row.get("advertisedSkuSales")),
                    "advertised_sku_units": _decimal(row.get("advertisedSkuUnits")),
                    "num_ads_clicks": _int(row.get("numAdsClicks")),
                    "num_ads_shown": _int(row.get("numAdsShown")),
                    "acos": _decimal(row.get("acos")),
                    "roas": _decimal(row.get("roas")),
                    "cpc": _decimal(row.get("cpc")),
                    "ctr": _decimal(row.get("ctr")),
                    "cvr": _decimal(row.get("cvr")),
                    **_timestamps(),
                },
            )
            count += 1
        self.session.commit()
        return count

    def _refresh_listing_mart(self) -> int:
        self.session.execute(
            text(
                "delete from mart_listing_management_current "
                "where source_account_ref = :source_account_ref"
            ),
            {"source_account_ref": self.source_account_ref},
        )
        self.session.execute(
            text(
                "insert into mart_listing_management_current "
                "(id, source_account_ref, platform_code, store_id, store_name, item_id, msku, "
                "local_sku, local_name, title, picture_url, item_url, sale_price_amount, "
                "sale_price_currency_code, listing_status, listing_start_at_utc, "
                "wfs_available_quantity, available_quantity, sales_7d, sales_14d, sales_30d, "
                "average_rating, review_count, brand, gtin, upc, tags_json, "
                "gpt_analysis_links_json, source_lineage_json, calculated_at, created_at, updated_at) "
                "select gen_random_uuid(), source_account_ref, platform_code, store_id, "
                "store_name, item_id, msku, local_sku, local_name, title, picture_url, item_url, "
                "price_amount, price_currency_code, standard_status, listing_start_at_utc, "
                "wfs_available_quantity, available_quantity, 0, 0, 0, average_rating, "
                "review_count, brand, gtin, upc, '[]'::jsonb, '[]'::jsonb, "
                "jsonb_build_object('runner', :runner_version), :now, :now, :now "
                "from dim_walmart_listings where source_account_ref = :source_account_ref"
            ),
            {
                "source_account_ref": self.source_account_ref,
                "runner_version": RUNNER_VERSION,
                "now": _now(),
            },
        )
        return _row_count(
            self.session,
            "mart_listing_management_current",
            self.source_account_ref,
            None,
        )

    def _refresh_daily_sales_mart(self) -> int:
        self.session.execute(
            text(
                "delete from mart_daily_sales_item_day where source_account_ref = "
                ":source_account_ref and business_date_la = :business_date"
            ),
            {"source_account_ref": self.source_account_ref, "business_date": self.business_date},
        )
        self.session.execute(
            text(
                "insert into mart_daily_sales_item_day "
                "(id, business_date_la, source_account_ref, platform_code, store_id, store_name, "
                "item_id, msku, local_sku, local_name, title, picture_url, sales_qty, order_count, "
                "sales_amount, sales_currency_code, refund_amount, ad_spend_amount, "
                "wfs_available_quantity, commission_rate, cost_status, missing_cost_codes_json, "
                "sales_7d_trend_json, source_lineage_json, calc_version, calculated_at, created_at, "
                "updated_at) select gen_random_uuid(), s.business_date_la, s.source_account_ref, "
                "coalesce(s.platform_code, l.platform_code), s.store_id, coalesce(s.store_name, "
                "l.store_name), s.item_id, coalesce(s.msku, l.msku), coalesce(s.local_sku, "
                "l.local_sku), l.local_name, l.title, l.picture_url, coalesce(s.sales_qty, 0), "
                "coalesce(s.order_count, 0), coalesce(s.sales_amount, 0), "
                "coalesce(s.sales_currency_code, 'USD'), r.refund_amount, a.ad_spend_amount, "
                "l.wfs_available_quantity, 0.15, 'missing', '[\"cost_source_missing\"]'::jsonb, "
                "'[]'::jsonb, jsonb_build_object('runner', :runner_version), :runner_version, "
                ":now, :now, :now from fact_walmart_sales_item_daily s "
                "left join dim_walmart_listings l on l.source_account_ref = s.source_account_ref "
                "and l.store_id = s.store_id and l.item_id = s.item_id "
                "left join (select source_account_ref, business_date_la, store_id, item_id, "
                "sum(refund_amount) refund_amount from fact_walmart_refund_items group by 1,2,3,4) r "
                "on r.source_account_ref = s.source_account_ref and r.business_date_la = "
                "s.business_date_la and r.store_id = s.store_id and r.item_id = s.item_id "
                "left join (select source_account_ref, business_date_la, item_id, sum(ad_spend_amount) "
                "ad_spend_amount from fact_walmart_ad_item_sp_daily group by 1,2,3) a on "
                "a.source_account_ref = s.source_account_ref and a.business_date_la = "
                "s.business_date_la and a.item_id = s.item_id where s.source_account_ref = "
                ":source_account_ref and s.business_date_la = :business_date"
            ),
            {
                "source_account_ref": self.source_account_ref,
                "business_date": self.business_date,
                "runner_version": RUNNER_VERSION,
                "now": _now(),
            },
        )
        return _row_count(
            self.session,
            "mart_daily_sales_item_day",
            self.source_account_ref,
            self.business_date,
        )

    def _refresh_order_profit_mart(self) -> int:
        self.session.execute(
            text(
                "delete from mart_order_profit_sku_day where source_account_ref = "
                ":source_account_ref and business_date_la = :business_date"
            ),
            {"source_account_ref": self.source_account_ref, "business_date": self.business_date},
        )
        self.session.execute(
            text(
                "insert into mart_order_profit_sku_day "
                "(id, business_date_la, source_account_ref, local_sku, item_ids_json, "
                "store_ids_json, store_count, item_count, sales_qty, order_count, sales_amount, "
                "sales_currency_code, refund_amount, ad_spend_amount, commission_fee_amount, "
                "gross_profit_amount, gross_profit_currency_code, cost_status, "
                "missing_cost_codes_json, source_lineage_json, calc_version, calculated_at, "
                "created_at, updated_at) select gen_random_uuid(), business_date_la, "
                "source_account_ref, coalesce(nullif(local_sku, ''), item_id), "
                "jsonb_agg(distinct item_id), jsonb_agg(distinct store_id), count(distinct store_id), "
                "count(distinct item_id), sum(coalesce(sales_qty, 0)), sum(coalesce(order_count, 0)), "
                "sum(coalesce(sales_amount, 0)), coalesce(max(sales_currency_code), 'USD'), "
                "sum(coalesce(refund_amount, 0)), sum(coalesce(ad_spend_amount, 0)), "
                "sum(coalesce(sales_amount, 0)) * 0.15, null, 'USD', 'missing', "
                "'[\"cost_source_missing\"]'::jsonb, jsonb_build_object('runner', :runner_version), "
                ":runner_version, :now, :now, :now from mart_daily_sales_item_day where "
                "source_account_ref = :source_account_ref and business_date_la = :business_date "
                "group by business_date_la, source_account_ref, coalesce(nullif(local_sku, ''), item_id)"
            ),
            {
                "source_account_ref": self.source_account_ref,
                "business_date": self.business_date,
                "runner_version": RUNNER_VERSION,
                "now": _now(),
            },
        )
        return _row_count(
            self.session,
            "mart_order_profit_sku_day",
            self.source_account_ref,
            self.business_date,
        )


def _rows_for(parser_key: DataPagesParserKey, payload: JsonValue) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if parser_key == "seller_list_multi_platform":
        if isinstance(data, dict):
            return _dict_rows(data.get("list") or data.get("rows") or data.get("data"))
        if isinstance(data, list):
            return _flatten(data, "list") or _dict_rows(data)
    if parser_key in {"walmart_listing_list", "walmart_advertiser_list", "walmart_ad_item_sp_list"}:
        if isinstance(data, dict):
            return _dict_rows(data.get("list") or data.get("rows") or data.get("data"))
        return _dict_rows(data)
    if parser_key == "sale_stat_page_list":
        if isinstance(data, dict):
            return _dict_rows(data.get("list") or data.get("rows") or data.get("data"))
        return _dict_rows(data)
    if parser_key == "order_v2_list":
        if isinstance(data, dict):
            return _dict_rows(data.get("list") or data.get("rows") or data.get("data"))
        return _dict_rows(data)
    if parser_key == "walmart_return_order_list":
        if isinstance(data, dict):
            return _dict_rows(data.get("list") or data.get("rows") or data.get("data"))
        return _dict_rows(data)
    return []


def _dict_rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _flatten(rows: Iterable[object], nested_key: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        nested = row.get(nested_key)
        if isinstance(nested, list):
            result.extend(item for item in nested if isinstance(item, dict))
    return result


def _field(row: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = row.get(name)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            text_value = str(value).strip()
            if text_value:
                return text_value
    return None


def _first_value(value: object) -> str | None:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, (str, int, float)) and not isinstance(item, bool):
                text_value = str(item).strip()
                if text_value:
                    return text_value
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value).strip() or None
    return None


def _nested_first(row: dict[str, Any], list_key: str, field_name: str) -> object:
    value = row.get(list_key)
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0].get(field_name)
    return None


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _int(value: object) -> int | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def _bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return True
        if normalized in {"0", "false", "no", "n"}:
            return False
    return None


def _platform_code(value: str | None) -> str | None:
    if value == WALMART_PLATFORM_CODE:
        return "walmart"
    return value


def _sales_amount_fields(result_type: int, volume_total: object) -> dict[str, Decimal | None]:
    value = _decimal(volume_total)
    return {
        "sales_qty": value if result_type == 1 else None,
        "order_count": value if result_type == 2 else None,
        "sales_amount": value if result_type == 3 else None,
    }


def _stable_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(cast(JsonValue, redact_json(value))).encode()).hexdigest()


def _unique(values: Iterable[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _safe_scope(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 128:
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_SOURCE_ACCOUNT_INVALID")
    return normalized


def _now() -> datetime:
    return datetime.combine(date.today(), time.min).astimezone()


def _timestamps() -> dict[str, datetime]:
    now = _now()
    return {"synced_at": now, "created_at": now, "updated_at": now}


def _row_count(
    session: Session,
    table_name: str,
    source_account_ref: str,
    business_date: date | None,
) -> int:
    if business_date is None:
        value = session.execute(
            text(f"select count(*) from {table_name} where source_account_ref = :source_account_ref"),
            {"source_account_ref": source_account_ref},
        ).scalar_one()
    else:
        value = session.execute(
            text(
                f"select count(*) from {table_name} where source_account_ref = "
                ":source_account_ref and business_date_la = :business_date"
            ),
            {"source_account_ref": source_account_ref, "business_date": business_date},
        ).scalar_one()
    return int(value)


if __name__ == "__main__":
    main()
