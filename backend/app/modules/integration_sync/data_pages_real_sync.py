from __future__ import annotations

import argparse
import hashlib
import json
import os
import time as sleep_time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from pydantic import JsonValue
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment, Settings, get_settings
from app.db.session import get_session_factory
from app.integrations.lingxing.query_sign import build_query_auth_params
from app.integrations.lingxing.security import canonical_json, redact_json
from app.integrations.lingxing.token_manager import LingxingTokenClient, LingxingTokenManager
from app.modules.integration_sync.catalog import IntegrationCatalogService
from app.modules.integration_sync.data_pages_catalog import DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY
from app.modules.integration_sync.parsers.lingxing_data_pages import DataPagesParserKey

AUTHORIZED_ENV = "DATA_PAGES_REAL_SYNC_AUTHORIZED"
RUNNER_VERSION = "real-data-2.0"
DEFAULT_DATE = date(2026, 9, 1)
DEFAULT_PAGE_SIZE = 100
WALMART_PLATFORM_CODE = "10008"
WALMART_PLATFORM_CODE_INT = 10008
CHINA_TZ = ZoneInfo("Asia/Shanghai")
SP_CAMPAIGN_TYPES = ("sponsoredProducts-manual", "sponsoredProducts-auto")


class DataPagesRealSyncError(RuntimeError):
    """Safe real-sync error that never includes credentials or raw payloads."""


@dataclass(slots=True)
class DataPagesRealSyncSummary:
    source_account_ref: str
    business_date: date
    raw_blobs: int = 0
    store_rows: int = 0
    listing_rows: int = 0
    listing_skipped_rows: int = 0
    advertiser_rows: int = 0
    sales_rows: int = 0
    sales_unallocated_rows: int = 0
    order_rows: int = 0
    order_unresolved_rows: int = 0
    refund_rows: int = 0
    refund_unresolved_rows: int = 0
    return_permission_403: bool = False
    ad_rows: int = 0
    ad_mapped_rows: int = 0
    ad_unresolved_rows: int = 0
    ad_unresolved_positive_spend: Decimal = Decimal("0")
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
            f"listing_skipped_rows={self.listing_skipped_rows}",
            f"advertiser_rows={self.advertiser_rows}",
            f"sales_rows={self.sales_rows}",
            f"sales_unallocated_rows={self.sales_unallocated_rows}",
            f"order_rows={self.order_rows}",
            f"order_unresolved_rows={self.order_unresolved_rows}",
            f"refund_rows={self.refund_rows}",
            f"refund_unresolved_rows={self.refund_unresolved_rows}",
            f"return_permission_403={str(self.return_permission_403).lower()}",
            f"ad_rows={self.ad_rows}",
            f"ad_mapped_rows={self.ad_mapped_rows}",
            f"ad_unresolved_rows={self.ad_unresolved_rows}",
            f"ad_unresolved_positive_spend={self.ad_unresolved_positive_spend}",
            f"mart_daily_sales_rows={self.mart_daily_sales_rows}",
            f"mart_order_profit_rows={self.mart_order_profit_rows}",
            f"mart_listing_rows={self.mart_listing_rows}",
        ]


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    parser_key: DataPagesParserKey
    response_json: JsonValue
    rows: tuple[dict[str, Any], ...]
    page_no: int
    page_size: int
    pulled_at: datetime
    provider_code: int | None
    response_code: int


class DataPagesRealHttpClient:
    """Authorized full-pagination client for the one-day DATA-PAGES runner.

    This deliberately does not relax the generic bounded-probe client. The real runner
    is separately gated by DATA_PAGES_REAL_SYNC_AUTHORIZED and keeps the approved
    DATA-PAGES endpoint catalog as its allowlist.
    """

    def __init__(
        self,
        settings: Settings,
        token_manager: LingxingTokenManager,
        *,
        transport: httpx.BaseTransport | None = None,
        sleeper: Any = sleep_time.sleep,
    ) -> None:
        if settings.lingxing_base_url is None:
            raise DataPagesRealSyncError("DATA_PAGES_BASE_URL_UNAVAILABLE")
        self._settings = settings
        self._token_manager = token_manager
        self._sleeper = sleeper
        self._client = httpx.Client(
            base_url=settings.lingxing_base_url,
            timeout=settings.lingxing_timeout_ms / 1_000,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def post(
        self,
        parser_key: DataPagesParserKey,
        body: dict[str, Any],
        *,
        page_no: int,
        page_size: int,
        label: str,
    ) -> ProviderResponse:
        spec = DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY[parser_key]
        recovered_auth = False
        last_status = 0
        for attempt in range(1, 7):
            try:
                token = self._token_manager.get_access_token()
                if not self._settings.lingxing_app_id:
                    raise DataPagesRealSyncError("DATA_PAGES_APP_ID_UNAVAILABLE")
                params = build_query_auth_params(
                    cast(dict[str, JsonValue], body),
                    access_token=token,
                    app_id=self._settings.lingxing_app_id,
                )
                response = self._client.post(
                    spec.endpoint_path,
                    params=params,
                    json=body,
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                )
                last_status = response.status_code
                if len(response.content) > self._settings.lingxing_max_response_bytes:
                    raise DataPagesRealSyncError(f"DATA_PAGES_RESPONSE_TOO_LARGE:{spec.interface_key}")
                payload = cast(JsonValue, response.json())
            except (httpx.TimeoutException, httpx.TransportError, ValueError) as exc:
                if attempt >= 6:
                    raise DataPagesRealSyncError(
                        f"DATA_PAGES_TRANSPORT_FAILED:{spec.interface_key}"
                    ) from exc
                self._sleeper(min(attempt * 3, 15))
                continue

            provider_code = _provider_code(payload)
            if provider_code == 2001003 and not recovered_auth:
                self._token_manager.recover_from_access_error(provider_code)
                recovered_auth = True
                continue
            if provider_code == 3001008 and attempt < 6:
                self._sleeper(min(attempt * 4, 20))
                continue
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 6:
                self._sleeper(min(attempt * 3, 15))
                continue
            if not response.is_success:
                raise DataPagesRealSyncError(f"DATA_PAGES_HTTP_FAILED:{spec.interface_key}")

            return ProviderResponse(
                parser_key=parser_key,
                response_json=payload,
                rows=tuple(_rows_for(parser_key, payload)),
                page_no=page_no,
                page_size=page_size,
                pulled_at=datetime.now(UTC),
                provider_code=provider_code,
                response_code=last_status,
            )
        raise DataPagesRealSyncError(f"DATA_PAGES_RETRY_EXHAUSTED:{label}")


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one authorized, fully paginated DATA-PAGES real sync for one date."
    )
    parser.add_argument("--business-date", default=DEFAULT_DATE.isoformat())
    parser.add_argument("--source-account-ref", required=True)
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--campaign-type", default="SP")
    parser.add_argument("--max-advertisers", type=int, default=20)
    return parser.parse_args()


@contextmanager
def data_pages_client() -> Iterable[DataPagesRealHttpClient]:
    settings = get_settings()
    token_client = LingxingTokenClient(settings)
    token_manager = LingxingTokenManager(token_client, settings)
    client = DataPagesRealHttpClient(settings, token_manager)
    try:
        yield client
    finally:
        client.close()
        token_client.close()


def data_pages_response_succeeded(
    endpoint: object,
    response: httpx.Response,
    payload: JsonValue,
) -> bool:
    del endpoint
    if not response.is_success:
        return False
    code = _provider_code(payload)
    return code in {None, 0, 200}


class DataPagesRealSyncRunner:
    def __init__(
        self,
        *,
        session: Session,
        client: DataPagesRealHttpClient | None,
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
        self.store_ids: tuple[str, ...] = ()
        self.advertiser_ids: tuple[str, ...] = ()

    def execute(self) -> DataPagesRealSyncSummary:
        if self.client is None:
            raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_CLIENT_REQUIRED")
        try:
            stores = self._fetch_offset_all(
                "seller_list_multi_platform",
                self._seller_body,
                minimum_page_size=20,
            )
            self.store_ids = tuple(_unique(_field(row, "store_id", "sid") for row in stores))
            if not self.store_ids:
                raise DataPagesRealSyncError("DATA_PAGES_NO_WALMART_STORES")

            advertisers = self._fetch_page_all(
                "walmart_advertiser_list",
                self._advertiser_body,
            )
            self.advertiser_ids = tuple(
                _unique(_field(row, "advertiserId", "advertiser_id") for row in advertisers)
            )

            listings = self._fetch_offset_all("walmart_listing_list", self._listing_body)

            sales_rows: list[dict[str, Any]] = []
            for result_type in (1, 2, 3):
                rows = self._fetch_page_all(
                    "sale_stat_page_list",
                    lambda page, size, result_type=result_type: self._sale_stat_body(
                        page, size, result_type
                    ),
                    body_suffix=f"result_type={result_type}",
                )
                sales_rows.extend({**row, "_result_type": result_type} for row in rows)

            orders = self._fetch_offset_all(
                "order_v2_list",
                self._order_body,
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
            self.summary.refund_rows = self._write_refunds(refunds)
            self.summary.ad_rows = self._write_ads(ad_rows)

            self.summary.order_unresolved_rows = self._resolve_order_items()
            self.summary.refund_unresolved_rows = self._resolve_refund_items()
            self._resolve_ads(ad_rows)

            self.summary.mart_daily_sales_rows = self._refresh_daily_sales_mart()
            self.summary.mart_order_profit_rows = self._refresh_order_profit_mart()
            self.summary.mart_listing_rows = self._refresh_listing_mart()
            self.session.commit()
            return self.summary
        except Exception:
            self.session.rollback()
            raise

    def _request_page(
        self,
        parser_key: DataPagesParserKey,
        body: dict[str, Any],
        *,
        page_no: int,
        page_size: int,
        body_suffix: str | None = None,
    ) -> ProviderResponse:
        if self.client is None:
            raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_CLIENT_REQUIRED")
        spec = DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY[parser_key]
        response = self.client.post(
            parser_key,
            body,
            page_no=page_no,
            page_size=page_size,
            label=f"{parser_key}:{body_suffix or page_no}",
        )
        self.summary.requested_interfaces.append(spec.interface_key)
        self._persist_raw_blob(parser_key, response.response_json, response.pulled_at)
        if response.provider_code not in {None, 0, 200}:
            if parser_key == "walmart_return_order_list" and response.provider_code == 403:
                self.summary.return_permission_403 = True
                marker = "walmartReturnOrderList:provider_permission_403"
                if marker not in self.summary.skipped_interfaces:
                    self.summary.skipped_interfaces.append(marker)
                return response
            raise DataPagesRealSyncError(f"DATA_PAGES_PROVIDER_FAILED:{spec.interface_key}")
        return response

    def _fetch_offset_all(
        self,
        parser_key: DataPagesParserKey,
        body_builder: Any,
        *,
        minimum_page_size: int = 1,
    ) -> list[dict[str, Any]]:
        spec = DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY[parser_key]
        size = max(self.page_size, minimum_page_size)
        offset = 0
        page_no = 1
        rows: list[dict[str, Any]] = []
        previous_signature: str | None = None
        while page_no <= spec.default_max_pages:
            response = self._request_page(
                parser_key,
                body_builder(offset, size),
                page_no=page_no,
                page_size=size,
            )
            current = list(response.rows)
            signature = _page_signature(current) if current else None
            if current and previous_signature == signature:
                raise DataPagesRealSyncError(f"DATA_PAGES_PAGINATION_STALLED:{spec.interface_key}")
            previous_signature = signature
            rows.extend(current)
            total = _total_of(response.response_json)
            if not current or len(current) < size or (total and len(rows) >= total):
                return rows
            offset += size
            page_no += 1
        raise DataPagesRealSyncError(f"DATA_PAGES_MAX_PAGES_EXCEEDED:{spec.interface_key}")

    def _fetch_page_all(
        self,
        parser_key: DataPagesParserKey,
        body_builder: Any,
        *,
        body_suffix: str | None = None,
    ) -> list[dict[str, Any]]:
        spec = DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY[parser_key]
        size = self.page_size
        page_no = 1
        rows: list[dict[str, Any]] = []
        previous_signature: str | None = None
        while page_no <= spec.default_max_pages:
            response = self._request_page(
                parser_key,
                body_builder(page_no, size),
                page_no=page_no,
                page_size=size,
                body_suffix=body_suffix,
            )
            current = list(response.rows)
            signature = _page_signature(current) if current else None
            if current and previous_signature == signature:
                raise DataPagesRealSyncError(f"DATA_PAGES_PAGINATION_STALLED:{spec.interface_key}")
            previous_signature = signature
            rows.extend(current)
            total = _total_of(response.response_json)
            if not current or len(current) < size or (total and len(rows) >= total):
                return rows
            page_no += 1
        raise DataPagesRealSyncError(f"DATA_PAGES_MAX_PAGES_EXCEEDED:{spec.interface_key}")

    def _fetch_return_all(self) -> list[dict[str, Any]]:
        spec = DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY["walmart_return_order_list"]
        rows: list[dict[str, Any]] = []
        previous_signature: str | None = None
        for page_no in range(1, spec.default_max_pages + 1):
            response = self._request_page(
                "walmart_return_order_list",
                self._return_body(page_no, self.page_size),
                page_no=page_no,
                page_size=self.page_size,
            )
            if response.provider_code == 403:
                return []
            current = list(response.rows)
            signature = _page_signature(current) if current else None
            if current and previous_signature == signature:
                raise DataPagesRealSyncError("DATA_PAGES_PAGINATION_STALLED:walmartReturnOrderList")
            previous_signature = signature
            rows.extend(current)
            total = _total_of(response.response_json)
            if not current or len(current) < self.page_size or (total and len(rows) >= total):
                return rows
        raise DataPagesRealSyncError("DATA_PAGES_MAX_PAGES_EXCEEDED:walmartReturnOrderList")

    def _fetch_ads_all(self, advertiser_id: str) -> list[dict[str, Any]]:
        spec = DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY["walmart_ad_item_sp_list"]
        size = min(self.page_size, 200)
        rows: list[dict[str, Any]] = []
        previous_signature: str | None = None
        for page_no in range(1, spec.default_max_pages + 1):
            response = self._request_page(
                "walmart_ad_item_sp_list",
                self._ad_item_body(advertiser_id, page_no, size),
                page_no=page_no,
                page_size=size,
                body_suffix="advertiserId",
            )
            current = list(response.rows)
            signature = _page_signature(current) if current else None
            if current and previous_signature == signature:
                raise DataPagesRealSyncError("DATA_PAGES_PAGINATION_STALLED:walmartAdItemSpList")
            previous_signature = signature
            rows.extend(current)
            if not current or len(current) < size:
                return rows
        raise DataPagesRealSyncError("DATA_PAGES_MAX_PAGES_EXCEEDED:walmartAdItemSpList")

    def _persist_raw_blob(
        self,
        parser_key: DataPagesParserKey,
        payload: JsonValue,
        pulled_at: datetime,
    ) -> str | None:
        spec = DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY[parser_key]
        policy_id = self.session.execute(
            text(
                "select id from gov_raw_retention_policies "
                "where policy_key = :policy_key and is_active = true"
            ),
            {"policy_key": spec.retention_policy_key},
        ).scalar_one()
        redacted = redact_json(payload)
        encoded = canonical_json(redacted).encode("utf-8")
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
                "payload_json": canonical_json(redacted),
                "payload_bytes": len(encoded),
                "content_type": "application/json",
                "retention_policy_id": str(policy_id),
                "received_at": pulled_at,
                "created_at": _now(),
            },
        ).scalar_one()
        self.summary.raw_blobs += 1
        return str(row)

    def _seller_body(self, offset: int, size: int) -> dict[str, Any]:
        return {
            "offset": offset,
            "length": size,
            "platform_code": [WALMART_PLATFORM_CODE_INT],
            "is_sync": 1,
            "status": 1,
        }

    def _advertiser_body(self, page: int, size: int) -> dict[str, Any]:
        return {"paging": True, "page": page, "limit": size}

    def _listing_body(self, offset: int, size: int) -> dict[str, Any]:
        return {"offset": offset, "length": size}

    def _sale_stat_body(self, page: int, size: int, result_type: int) -> dict[str, Any]:
        return {
            "data_type": 1,
            "date_unit": "4",
            "start_date": self.business_date.isoformat(),
            "end_date": self.business_date.isoformat(),
            "page": page,
            "length": size,
            "result_type": str(result_type),
            "sids": list(self.store_ids),
        }

    def _order_body(self, offset: int, size: int) -> dict[str, Any]:
        return {
            "date_type": "global_purchase_time",
            "start_time": _china_epoch(self.business_date, end=False),
            "end_time": _china_epoch(self.business_date, end=True),
            "offset": offset,
            "length": size,
            "platform_code": [WALMART_PLATFORM_CODE_INT],
            "store_id": list(self.store_ids),
        }

    def _return_body(self, page: int, size: int) -> dict[str, Any]:
        return {
            "dateType": 1,
            "startDate": self.business_date.isoformat(),
            "endDate": self.business_date.isoformat(),
            "pageNum": page,
            "pageSize": size,
            "returnTypeList": ["REFUND"],
            "storeIdList": list(self.store_ids),
        }

    def _ad_item_body(self, advertiser_id: str, page: int, size: int) -> dict[str, Any]:
        advertiser_value: int | str = (
            int(advertiser_id) if advertiser_id.isdecimal() else advertiser_id
        )
        campaign_types = (
            list(SP_CAMPAIGN_TYPES) if self.campaign_type == "SP" else [self.campaign_type]
        )
        return {
            "advertiserIds": [advertiser_value],
            "campaignType": campaign_types,
            "startDate": self.business_date.isoformat(),
            "endDate": self.business_date.isoformat(),
            "pageNum": page,
            "pageSize": size,
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
                    "(id, source_account_ref, platform_name_raw, platform_code_raw, platform_code, "
                    "store_id, store_name, sid, currency_code, raw_status, is_sync, synced_at, "
                    "created_at, updated_at) values (:id, :source_account_ref, :platform_name_raw, "
                    ":platform_code_raw, :platform_code, :store_id, :store_name, :sid, :currency_code, "
                    ":raw_status, :is_sync, :synced_at, :created_at, :updated_at) "
                    "on conflict (source_account_ref, platform_code_raw, store_id) do update set "
                    "store_name = excluded.store_name, sid = excluded.sid, raw_status = excluded.raw_status, "
                    "is_sync = excluded.is_sync, synced_at = excluded.synced_at, updated_at = excluded.updated_at"
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
                    "(id, source_account_ref, advertiser_id, advertiser_name, store_id, platform_code, "
                    "raw_status, standard_status, synced_at, created_at, updated_at) values "
                    "(:id, :source_account_ref, :advertiser_id, :advertiser_name, :store_id, "
                    ":platform_code, :raw_status, :standard_status, :synced_at, :created_at, :updated_at) "
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
        return count

    def _write_listings(self, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            item_id = _field(row, "item_id", "itemId")
            store_id = _field(row, "store_id", "sid")
            if not item_id or not store_id:
                self.summary.listing_skipped_rows += 1
                continue
            self.session.execute(
                text(
                    "insert into dim_walmart_listings "
                    "(id, source_account_ref, platform_code, platform_code_raw, store_id, store_name, "
                    "item_id, msku, local_sku, local_name, title, picture_url, item_url, price_amount, "
                    "price_currency_code, listing_start_source_raw, available_quantity, "
                    "wfs_available_quantity, average_rating, review_count, gtin, upc, brand, raw_status, "
                    "standard_status, fulfillment_type, fulfillment_type_name, variant_unique_id, synced_at, "
                    "created_at, updated_at) values (:id, :source_account_ref, :platform_code, "
                    ":platform_code_raw, :store_id, :store_name, :item_id, :msku, :local_sku, :local_name, "
                    ":title, :picture_url, :item_url, :price_amount, :price_currency_code, "
                    ":listing_start_source_raw, :available_quantity, :wfs_available_quantity, "
                    ":average_rating, :review_count, :gtin, :upc, :brand, :raw_status, :standard_status, "
                    ":fulfillment_type, :fulfillment_type_name, :variant_unique_id, :synced_at, :created_at, "
                    ":updated_at) on conflict (source_account_ref, store_id, item_id) do update set "
                    "store_name = excluded.store_name, msku = excluded.msku, local_sku = excluded.local_sku, "
                    "local_name = excluded.local_name, title = excluded.title, picture_url = excluded.picture_url, "
                    "item_url = excluded.item_url, price_amount = excluded.price_amount, "
                    "price_currency_code = excluded.price_currency_code, available_quantity = excluded.available_quantity, "
                    "wfs_available_quantity = excluded.wfs_available_quantity, review_count = excluded.review_count, "
                    "average_rating = excluded.average_rating, raw_status = excluded.raw_status, "
                    "standard_status = excluded.standard_status, synced_at = excluded.synced_at, "
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
        return count

    def _write_sales(self, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            item_candidates = _scalar_candidates(row.get("platform_product_id"))
            store_candidates = _scalar_candidates(row.get("sid"))
            if len(item_candidates) != 1 or len(store_candidates) != 1:
                self.summary.sales_unallocated_rows += 1
                continue
            item_id = item_candidates[0]
            store_id = store_candidates[0]
            result_type = _int(row.get("_result_type")) or 0
            amount_fields = _sales_amount_fields(result_type, row.get("volumeTotal"))
            self.session.execute(
                text(
                    "insert into fact_walmart_sales_item_daily "
                    "(id, business_date_la, source_account_ref, platform_code, platform_code_raw, store_id, "
                    "sid, store_name, item_id, msku, local_sku, product_name, sales_qty, order_count, "
                    "sales_amount, sales_currency_code, source_date_raw, source_group_key, allocation_status, "
                    "date_collect_json, synced_at, created_at, updated_at) values (:id, :business_date_la, "
                    ":source_account_ref, :platform_code, :platform_code_raw, :store_id, :sid, :store_name, "
                    ":item_id, :msku, :local_sku, :product_name, :sales_qty, :order_count, :sales_amount, "
                    ":sales_currency_code, :source_date_raw, :source_group_key, :allocation_status, "
                    "cast(:date_collect_json as jsonb), :synced_at, :created_at, :updated_at) "
                    "on conflict (business_date_la, source_account_ref, store_id, item_id) do update set "
                    "sales_qty = coalesce(excluded.sales_qty, fact_walmart_sales_item_daily.sales_qty), "
                    "order_count = coalesce(excluded.order_count, fact_walmart_sales_item_daily.order_count), "
                    "sales_amount = coalesce(excluded.sales_amount, fact_walmart_sales_item_daily.sales_amount), "
                    "updated_at = excluded.updated_at"
                ),
                {
                    "id": str(uuid4()),
                    "business_date_la": self.business_date,
                    "source_account_ref": self.source_account_ref,
                    "platform_code": WALMART_PLATFORM_CODE,
                    "platform_code_raw": _field(row, "platform_code") or WALMART_PLATFORM_CODE,
                    "store_id": store_id,
                    "sid": store_id,
                    "store_name": _single_scalar(row.get("store_name")),
                    "item_id": item_id,
                    "msku": _single_scalar(row.get("msku")),
                    "local_sku": _single_scalar(row.get("sku")) or _single_scalar(row.get("local_sku")),
                    "product_name": _single_scalar(row.get("product_name")) or _single_scalar(row.get("platform_product_title")),
                    "sales_currency_code": _field(row, "currency_code") or "USD",
                    "source_date_raw": _single_scalar(row.get("date_collect")) or self.business_date.isoformat(),
                    "source_group_key": _stable_hash(row),
                    "allocation_status": "direct",
                    "date_collect_json": canonical_json(cast(JsonValue, row.get("date_collect"))),
                    **amount_fields,
                    **_timestamps(),
                },
            )
            count += 1
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
                        "source_purchase_at_raw, business_date_la, order_status_raw, order_sub_status_raw, "
                        "flow_node_raw, sales_revenue_amount, sales_revenue_currency_code, order_total_amount, "
                        "order_total_currency_code, discount_amount, discount_currency_code, is_sample_order, "
                        "synced_at, created_at, updated_at) values (:id, :source_account_ref, :store_id, "
                        ":source_order_id, :source_order_line_id, :source_line_hash, :source_line_ordinal, "
                        ":item_id, :msku, :local_sku, :quantity, :source_purchase_at_raw, :business_date_la, "
                        ":order_status_raw, :order_sub_status_raw, :flow_node_raw, :sales_revenue_amount, "
                        ":sales_revenue_currency_code, :order_total_amount, :order_total_currency_code, "
                        ":discount_amount, :discount_currency_code, :is_sample_order, :synced_at, :created_at, "
                        ":updated_at) on conflict (source_account_ref, source_order_id, source_line_hash) "
                        "do update set store_id = excluded.store_id, msku = excluded.msku, "
                        "local_sku = excluded.local_sku, quantity = excluded.quantity, "
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
                        "item_id": _field(item, "item_id", "platform_product_id"),
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
                        "(id, source_account_ref, store_id, source_return_order_id, source_return_line_id, "
                        "source_line_hash, source_line_ordinal, customer_order_id, purchase_order_id, item_id, "
                        "msku, local_sku, return_type_raw, return_type_name, refund_status_raw, "
                        "return_order_date_raw, business_date_la, status_time_raw, quantity, refund_amount, "
                        "refund_currency_code, tracking_no, synced_at, created_at, updated_at) values "
                        "(:id, :source_account_ref, :store_id, :source_return_order_id, :source_return_line_id, "
                        ":source_line_hash, :source_line_ordinal, :customer_order_id, :purchase_order_id, :item_id, "
                        ":msku, :local_sku, :return_type_raw, :return_type_name, :refund_status_raw, "
                        ":return_order_date_raw, :business_date_la, :status_time_raw, :quantity, :refund_amount, "
                        ":refund_currency_code, :tracking_no, :synced_at, :created_at, :updated_at) on conflict "
                        "(source_account_ref, source_return_order_id, source_line_hash) do update set "
                        "store_id = excluded.store_id, msku = excluded.msku, local_sku = excluded.local_sku, "
                        "quantity = excluded.quantity, refund_amount = excluded.refund_amount, "
                        "updated_at = excluded.updated_at"
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
                    "(id, business_date_la, source_account_ref, advertiser_id, store_id, item_id, msku, "
                    "campaign_id, ad_group_id, ad_item_id, source_line_hash, source_key, ad_spend_amount, "
                    "ad_spend_currency_code, attributed_sales_amount, attributed_orders, attributed_units, "
                    "advertised_sku_sales_amount, advertised_sku_units, num_ads_clicks, num_ads_shown, acos, "
                    "roas, cpc, ctr, cvr, synced_at, created_at, updated_at) values (:id, :business_date_la, "
                    ":source_account_ref, :advertiser_id, :store_id, :item_id, :msku, :campaign_id, "
                    ":ad_group_id, :ad_item_id, :source_line_hash, :source_key, :ad_spend_amount, "
                    ":ad_spend_currency_code, :attributed_sales_amount, :attributed_orders, :attributed_units, "
                    ":advertised_sku_sales_amount, :advertised_sku_units, :num_ads_clicks, :num_ads_shown, "
                    ":acos, :roas, :cpc, :ctr, :cvr, :synced_at, :created_at, :updated_at) on conflict "
                    "(business_date_la, source_account_ref, advertiser_id, source_line_hash) do update set "
                    "item_id = coalesce(excluded.item_id, fact_walmart_ad_item_sp_daily.item_id), "
                    "ad_spend_amount = excluded.ad_spend_amount, "
                    "attributed_sales_amount = excluded.attributed_sales_amount, "
                    "attributed_orders = excluded.attributed_orders, attributed_units = excluded.attributed_units, "
                    "advertised_sku_sales_amount = excluded.advertised_sku_sales_amount, "
                    "advertised_sku_units = excluded.advertised_sku_units, num_ads_clicks = excluded.num_ads_clicks, "
                    "num_ads_shown = excluded.num_ads_shown, acos = excluded.acos, roas = excluded.roas, "
                    "cpc = excluded.cpc, ctr = excluded.ctr, cvr = excluded.cvr, updated_at = excluded.updated_at"
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
        return count

    def _resolve_order_items(self) -> int:
        now = _now()
        self.session.execute(
            text(
                "with candidates as (select o.id, "
                "(select count(*) from dim_walmart_listings l where l.source_account_ref = :account "
                "and l.store_id = o.store_id and trim(l.local_sku) = trim(o.local_sku)) sku_count, "
                "(select min(l.item_id) from dim_walmart_listings l where l.source_account_ref = :account "
                "and l.store_id = o.store_id and trim(l.local_sku) = trim(o.local_sku)) sku_item, "
                "(select count(*) from dim_walmart_listings l where l.source_account_ref = :account "
                "and l.store_id = o.store_id and trim(l.local_sku) = trim(o.local_sku) "
                "and trim(l.msku) = trim(o.msku)) exact_count, "
                "(select min(l.item_id) from dim_walmart_listings l where l.source_account_ref = :account "
                "and l.store_id = o.store_id and trim(l.local_sku) = trim(o.local_sku) "
                "and trim(l.msku) = trim(o.msku)) exact_item from fact_walmart_order_items o "
                "where o.source_account_ref = :account and o.business_date_la = :day and o.item_id is null), "
                "resolved as (select id, case when sku_count = 1 then sku_item "
                "when sku_count > 1 and exact_count = 1 then exact_item else null end item_id from candidates) "
                "update fact_walmart_order_items o set item_id = r.item_id, updated_at = :now "
                "from resolved r where o.id = r.id and r.item_id is not null"
            ),
            {"account": self.source_account_ref, "day": self.business_date, "now": now},
        )
        return int(
            self.session.execute(
                text(
                    "select count(*) from fact_walmart_order_items where source_account_ref = :account "
                    "and business_date_la = :day and item_id is null"
                ),
                {"account": self.source_account_ref, "day": self.business_date},
            ).scalar_one()
        )

    def _resolve_refund_items(self) -> int:
        if self.summary.return_permission_403:
            return 0
        now = _now()
        self.session.execute(
            text(
                "with candidates as (select r.id, "
                "(select count(*) from dim_walmart_listings l where l.source_account_ref = :account "
                "and l.store_id = r.store_id and trim(l.local_sku) = trim(r.local_sku)) sku_count, "
                "(select min(l.item_id) from dim_walmart_listings l where l.source_account_ref = :account "
                "and l.store_id = r.store_id and trim(l.local_sku) = trim(r.local_sku)) sku_item, "
                "(select count(*) from dim_walmart_listings l where l.source_account_ref = :account "
                "and l.store_id = r.store_id and trim(l.local_sku) = trim(r.local_sku) "
                "and trim(l.msku) = trim(r.msku)) exact_count, "
                "(select min(l.item_id) from dim_walmart_listings l where l.source_account_ref = :account "
                "and l.store_id = r.store_id and trim(l.local_sku) = trim(r.local_sku) "
                "and trim(l.msku) = trim(r.msku)) exact_item from fact_walmart_refund_items r "
                "where r.source_account_ref = :account and r.business_date_la = :day and r.item_id is null), "
                "resolved as (select id, case when sku_count = 1 then sku_item "
                "when sku_count > 1 and exact_count = 1 then exact_item else null end item_id from candidates) "
                "update fact_walmart_refund_items r set item_id = x.item_id, updated_at = :now "
                "from resolved x where r.id = x.id and x.item_id is not null"
            ),
            {"account": self.source_account_ref, "day": self.business_date, "now": now},
        )
        return int(
            self.session.execute(
                text(
                    "select count(*) from fact_walmart_refund_items where source_account_ref = :account "
                    "and business_date_la = :day and item_id is null"
                ),
                {"account": self.source_account_ref, "day": self.business_date},
            ).scalar_one()
        )

    def _resolve_ads(self, rows: Iterable[dict[str, Any]]) -> None:
        store_name_rows = self.session.execute(
            text(
                "select store_id, store_name from dim_lingxing_stores "
                "where source_account_ref = :account"
            ),
            {"account": self.source_account_ref},
        ).all()
        listing_rows = self.session.execute(
            text(
                "select store_id, item_id, msku from dim_walmart_listings "
                "where source_account_ref = :account"
            ),
            {"account": self.source_account_ref},
        ).all()
        store_name_map: dict[str, set[str]] = defaultdict(set)
        store_item_map: dict[tuple[str, str], set[str]] = defaultdict(set)
        item_map: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for store_id, store_name in store_name_rows:
            if store_name:
                store_name_map[_normalize_name(store_name)].add(str(store_id).strip())
        for store_id, item_id, msku in listing_rows:
            if not store_id or not item_id:
                continue
            sid = str(store_id).strip()
            iid = str(item_id).strip()
            msku_text = str(msku).strip() if msku is not None else ""
            store_item_map[(sid, iid)].add(msku_text)
            item_map[iid].add((sid, msku_text))

        mapped = 0
        unresolved = 0
        positive_unresolved = Decimal("0")
        now = _now()
        for row in rows:
            advertiser_id = _field(row, "advertiserId", "advertiser_id")
            item_id = _field(row, "itemId", "item_id")
            if not advertiser_id or not item_id:
                spend = _decimal(row.get("adSpend")) or Decimal("0")
                unresolved += 1
                positive_unresolved += spend
                continue
            store_id, msku, _method = _resolve_ad_identity(
                row,
                item_id=item_id,
                store_name_map=store_name_map,
                store_item_map=store_item_map,
                item_map=item_map,
            )
            if store_id and msku:
                self.session.execute(
                    text(
                        "update fact_walmart_ad_item_sp_daily set store_id = :store_id, msku = :msku, "
                        "item_id = :item_id, updated_at = :now where source_account_ref = :account "
                        "and business_date_la = :day and advertiser_id = :advertiser_id "
                        "and source_line_hash = :source_line_hash"
                    ),
                    {
                        "store_id": store_id,
                        "msku": msku,
                        "item_id": item_id,
                        "now": now,
                        "account": self.source_account_ref,
                        "day": self.business_date,
                        "advertiser_id": advertiser_id,
                        "source_line_hash": _stable_hash(row),
                    },
                )
                mapped += 1
            else:
                unresolved += 1
                positive_unresolved += _decimal(row.get("adSpend")) or Decimal("0")

        self.summary.ad_mapped_rows = mapped
        self.summary.ad_unresolved_rows = unresolved
        self.summary.ad_unresolved_positive_spend = positive_unresolved
        if positive_unresolved != Decimal("0"):
            raise DataPagesRealSyncError("DATA_PAGES_POSITIVE_AD_SPEND_UNRESOLVED")

    def _refresh_daily_sales_mart(self) -> int:
        now = _now()
        return_status = "provider_permission_403" if self.summary.return_permission_403 else "loaded"
        missing_codes = ["cost_source_missing"]
        if self.summary.return_permission_403:
            missing_codes.append("return_provider_403")
        self.session.execute(
            text(
                "delete from mart_daily_sales_item_day where source_account_ref = :account "
                "and business_date_la = :day"
            ),
            {"account": self.source_account_ref, "day": self.business_date},
        )
        self.session.execute(
            text(
                "with o as (select business_date_la, source_account_ref, store_id, item_id, "
                "sum(coalesce(quantity,0)) sales_qty, count(distinct source_order_id) order_count, "
                "sum(coalesce(sales_revenue_amount,0)) sales_amount, "
                "sum(case when is_sample_order then coalesce(sales_revenue_amount,0) else 0 end) sample_amount, "
                "sum(case when not is_sample_order then coalesce(sales_revenue_amount,0) else 0 end) "
                "sales_excluding_sample, coalesce(max(sales_revenue_currency_code),'USD') currency_code "
                "from fact_walmart_order_items where source_account_ref = :account and business_date_la = :day "
                "and store_id is not null and item_id is not null group by 1,2,3,4), "
                "r as (select source_account_ref, business_date_la, store_id, item_id, "
                "sum(coalesce(quantity,0)) return_qty, sum(coalesce(refund_amount,0)) refund_amount, "
                "coalesce(max(refund_currency_code),'USD') refund_currency_code "
                "from fact_walmart_refund_items where source_account_ref = :account and business_date_la = :day "
                "and store_id is not null and item_id is not null group by 1,2,3,4), "
                "a as (select source_account_ref, business_date_la, store_id, item_id, msku, "
                "sum(coalesce(ad_spend_amount,0)) ad_spend from fact_walmart_ad_item_sp_daily "
                "where source_account_ref = :account and business_date_la = :day and store_id is not null "
                "and item_id is not null and msku is not null and trim(msku) <> '' group by 1,2,3,4,5) "
                "insert into mart_daily_sales_item_day "
                "(id,business_date_la,source_account_ref,platform_code,store_id,store_name,item_id,msku,local_sku,"
                "local_name,title,picture_url,sales_qty,order_count,sales_amount,sales_currency_code,sample_amount,"
                "sales_amount_excluding_sample,return_qty,refund_amount,refund_currency_code,ad_spend_amount,"
                "ad_spend_currency_code,ad_ratio,wfs_available_quantity,commission_rate,commission_fee_amount,"
                "commission_fee_currency_code,cost_status,missing_cost_codes_json,sales_7d_trend_json,"
                "source_lineage_json,calc_version,calculated_at,created_at,updated_at) "
                "select gen_random_uuid(),o.business_date_la,o.source_account_ref,coalesce(l.platform_code,'walmart'),"
                "o.store_id,l.store_name,o.item_id,l.msku,coalesce(nullif(trim(l.local_sku),''),o.item_id),"
                "l.local_name,l.title,l.picture_url,o.sales_qty,o.order_count,o.sales_amount,o.currency_code,"
                "o.sample_amount,o.sales_excluding_sample,r.return_qty,r.refund_amount,r.refund_currency_code,"
                "coalesce(a.ad_spend,0),'USD',case when o.sales_amount > 0 then coalesce(a.ad_spend,0)/o.sales_amount "
                "else null end,l.wfs_available_quantity,0.15,o.sales_amount*0.15,o.currency_code,'missing',"
                "cast(:missing_codes as jsonb),'[]'::jsonb,jsonb_build_object('runner',cast(:runner as text),"
                "'basis','fact_walmart_order_items','ads_match_key','store_id+item_id+msku','return_status',"
                "cast(:return_status as text),'unresolved_order_lines',cast(:unresolved as integer)),"
                "cast(:runner as text),:now,:now,:now from o join dim_walmart_listings l on "
                "l.source_account_ref=o.source_account_ref and l.store_id=o.store_id and l.item_id=o.item_id "
                "left join r on r.source_account_ref=o.source_account_ref and r.business_date_la=o.business_date_la "
                "and r.store_id=o.store_id and r.item_id=o.item_id left join a on "
                "a.source_account_ref=o.source_account_ref and a.business_date_la=o.business_date_la "
                "and a.store_id=o.store_id and a.item_id=o.item_id and a.msku=l.msku"
            ),
            {
                "account": self.source_account_ref,
                "day": self.business_date,
                "missing_codes": canonical_json(cast(JsonValue, missing_codes)),
                "runner": RUNNER_VERSION,
                "return_status": return_status,
                "unresolved": self.summary.order_unresolved_rows,
                "now": now,
            },
        )
        return _row_count(self.session, "mart_daily_sales_item_day", self.source_account_ref, self.business_date)

    def _refresh_order_profit_mart(self) -> int:
        now = _now()
        missing_codes = ["cost_source_missing"]
        if self.summary.return_permission_403:
            missing_codes.append("return_provider_403")
        self.session.execute(
            text(
                "delete from mart_order_profit_sku_day where source_account_ref = :account "
                "and business_date_la = :day"
            ),
            {"account": self.source_account_ref, "day": self.business_date},
        )
        self.session.execute(
            text(
                "insert into mart_order_profit_sku_day "
                "(id,business_date_la,source_account_ref,local_sku,item_ids_json,store_ids_json,store_count,item_count,"
                "sales_qty,order_count,sales_amount,sales_currency_code,refund_amount,ad_spend_amount,"
                "commission_fee_amount,gross_profit_amount,gross_profit_currency_code,cost_status,"
                "missing_cost_codes_json,source_lineage_json,calc_version,calculated_at,created_at,updated_at) "
                "select gen_random_uuid(),business_date_la,source_account_ref,coalesce(nullif(local_sku,''),item_id),"
                "jsonb_agg(distinct item_id),jsonb_agg(distinct store_id),count(distinct store_id),count(distinct item_id),"
                "sum(coalesce(sales_qty,0)),sum(coalesce(order_count,0)),sum(coalesce(sales_amount,0)),"
                "coalesce(max(sales_currency_code),'USD'),sum(coalesce(refund_amount,0)),sum(coalesce(ad_spend_amount,0)),"
                "sum(coalesce(commission_fee_amount,0)),null,'USD','missing',cast(:missing_codes as jsonb),"
                "jsonb_build_object('runner',cast(:runner as text),'basis','mart_daily_sales_item_day',"
                "'ads_match_key','store_id+item_id+msku'),cast(:runner as text),:now,:now,:now "
                "from mart_daily_sales_item_day where source_account_ref = :account and business_date_la = :day "
                "group by business_date_la,source_account_ref,coalesce(nullif(local_sku,''),item_id)"
            ),
            {
                "account": self.source_account_ref,
                "day": self.business_date,
                "missing_codes": canonical_json(cast(JsonValue, missing_codes)),
                "runner": RUNNER_VERSION,
                "now": now,
            },
        )
        daily_spend = _decimal(
            self.session.execute(
                text(
                    "select coalesce(sum(ad_spend_amount),0) from mart_daily_sales_item_day "
                    "where source_account_ref=:account and business_date_la=:day"
                ),
                {"account": self.source_account_ref, "day": self.business_date},
            ).scalar_one()
        ) or Decimal("0")
        profit_spend = _decimal(
            self.session.execute(
                text(
                    "select coalesce(sum(ad_spend_amount),0) from mart_order_profit_sku_day "
                    "where source_account_ref=:account and business_date_la=:day"
                ),
                {"account": self.source_account_ref, "day": self.business_date},
            ).scalar_one()
        ) or Decimal("0")
        if daily_spend != profit_spend:
            raise DataPagesRealSyncError("DATA_PAGES_MART_AD_SPEND_MISMATCH")
        return _row_count(self.session, "mart_order_profit_sku_day", self.source_account_ref, self.business_date)

    def _refresh_listing_mart(self) -> int:
        now = _now()
        self.session.execute(
            text("delete from mart_listing_management_current where source_account_ref = :account"),
            {"account": self.source_account_ref},
        )
        self.session.execute(
            text(
                "with sales as (select store_id,item_id,"
                "sum(sales_qty) filter (where business_date_la between :day - 6 and :day) sales_7d,"
                "sum(sales_qty) filter (where business_date_la between :day - 13 and :day) sales_14d,"
                "sum(sales_qty) filter (where business_date_la between :day - 29 and :day) sales_30d "
                "from mart_daily_sales_item_day where source_account_ref=:account and business_date_la between :day - 29 and :day "
                "group by store_id,item_id), ads as (select store_id,item_id,msku,sum(coalesce(ad_spend_amount,0)) ad_spend_30d "
                "from fact_walmart_ad_item_sp_daily where source_account_ref=:account and business_date_la between :day - 29 and :day "
                "and store_id is not null and item_id is not null and msku is not null and trim(msku)<>'' group by store_id,item_id,msku) "
                "insert into mart_listing_management_current "
                "(id,source_account_ref,platform_code,store_id,store_name,item_id,msku,local_sku,local_name,title,picture_url,"
                "item_url,sale_price_amount,sale_price_currency_code,listing_status,listing_start_at_utc,wfs_available_quantity,"
                "available_quantity,sales_7d,sales_14d,sales_30d,ad_spend_30d_amount,ad_spend_currency_code,average_rating,"
                "review_count,brand,gtin,upc,tags_json,gpt_analysis_links_json,source_lineage_json,calculated_at,created_at,updated_at) "
                "select gen_random_uuid(),l.source_account_ref,l.platform_code,l.store_id,l.store_name,l.item_id,l.msku,l.local_sku,"
                "l.local_name,l.title,l.picture_url,l.item_url,l.price_amount,l.price_currency_code,l.standard_status,l.listing_start_at_utc,"
                "l.wfs_available_quantity,l.available_quantity,coalesce(s.sales_7d,0),coalesce(s.sales_14d,0),coalesce(s.sales_30d,0),"
                "coalesce(a.ad_spend_30d,0),'USD',l.average_rating,l.review_count,l.brand,l.gtin,l.upc,'[]'::jsonb,'[]'::jsonb,"
                "jsonb_build_object('runner',cast(:runner as text),'as_of_date',cast(:day as text),"
                "'ads_match_key','store_id+item_id+msku'),:now,:now,:now from dim_walmart_listings l "
                "left join sales s on s.store_id=l.store_id and s.item_id=l.item_id "
                "left join ads a on a.store_id=l.store_id and a.item_id=l.item_id and a.msku=l.msku "
                "where l.source_account_ref=:account"
            ),
            {
                "account": self.source_account_ref,
                "day": self.business_date,
                "runner": RUNNER_VERSION,
                "now": now,
            },
        )
        return _row_count(self.session, "mart_listing_management_current", self.source_account_ref, None)


def _resolve_ad_identity(
    row: dict[str, Any],
    *,
    item_id: str,
    store_name_map: dict[str, set[str]],
    store_item_map: dict[tuple[str, str], set[str]],
    item_map: dict[str, set[tuple[str, str]]],
) -> tuple[str | None, str | None, str | None]:
    direct_store = _field(row, "storeId", "store_id")
    direct_msku = _field(row, "msku")
    if direct_store and direct_msku and direct_msku in store_item_map.get((direct_store, item_id), set()):
        return direct_store, direct_msku, "provider_triple"

    seller_name = _normalize_name(row.get("mpSellerName"))
    seller_stores = store_name_map.get(seller_name, set()) if seller_name else set()
    if len(seller_stores) == 1:
        store_id = next(iter(seller_stores))
        msku_candidates = {value for value in store_item_map.get((store_id, item_id), set()) if value}
        if len(msku_candidates) == 1:
            return store_id, next(iter(msku_candidates)), "seller_store_item"

    candidates = {(store_id, msku) for store_id, msku in item_map.get(item_id, set()) if store_id and msku}
    stores = {store_id for store_id, _ in candidates}
    if len(stores) == 1:
        store_id = next(iter(stores))
        mskus = {msku for candidate_store, msku in candidates if candidate_store == store_id}
        if len(mskus) == 1:
            return store_id, next(iter(mskus)), "unique_item_store_msku"
    return None, None, None


def _provider_code(value: JsonValue) -> int | None:
    if not isinstance(value, dict):
        return None
    code = value.get("code")
    if isinstance(code, bool) or code is None:
        return None
    try:
        return int(str(code).strip())
    except ValueError:
        return None


def _total_of(payload: JsonValue) -> int | None:
    if not isinstance(payload, dict):
        return None
    candidates = [payload]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.append(data)
    for candidate in candidates:
        value = candidate.get("total")
        if isinstance(value, bool) or value is None:
            continue
        try:
            parsed = int(str(value))
        except ValueError:
            continue
        if parsed >= 0:
            return parsed
    return None


def _rows_for(parser_key: DataPagesParserKey, payload: JsonValue) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if parser_key == "seller_list_multi_platform":
        if isinstance(data, dict):
            return _dict_rows(data.get("list") or data.get("rows") or data.get("data"))
        if isinstance(data, list):
            return _flatten(data, "list") or _dict_rows(data)
    if parser_key in {
        "walmart_listing_list",
        "walmart_advertiser_list",
        "walmart_ad_item_sp_list",
        "sale_stat_page_list",
        "order_v2_list",
        "walmart_return_order_list",
    }:
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


def _single_scalar(value: object) -> str | None:
    values = _scalar_candidates(value)
    return values[0] if len(values) == 1 else None


def _scalar_candidates(value: object) -> list[str]:
    source = value if isinstance(value, list) else [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in source:
        if isinstance(item, (str, int, float)) and not isinstance(item, bool):
            normalized = str(item).strip()
            if normalized and normalized not in seen:
                result.append(normalized)
                seen.add(normalized)
    return result


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


def _page_signature(rows: list[dict[str, Any]]) -> str:
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _unique(values: Iterable[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _normalize_name(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _china_epoch(day: date, *, end: bool) -> int:
    clock = time(23, 59, 59) if end else time(0, 0, 0)
    return int(datetime.combine(day, clock, tzinfo=CHINA_TZ).timestamp())


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamps() -> dict[str, datetime]:
    now = _now()
    return {"synced_at": now, "created_at": now, "updated_at": now}


def _safe_scope(value: str) -> str:
    normalized = value.strip()
    if not normalized or normalized != value:
        raise DataPagesRealSyncError("DATA_PAGES_REAL_SYNC_SCOPE_INVALID")
    return normalized


def _row_count(session: Session, table_name: str, account: str, business_date: date | None) -> int:
    allowed = {
        "mart_daily_sales_item_day",
        "mart_order_profit_sku_day",
        "mart_listing_management_current",
    }
    if table_name not in allowed:
        raise DataPagesRealSyncError("DATA_PAGES_ROW_COUNT_TABLE_INVALID")
    sql = f"select count(*) from {table_name} where source_account_ref = :account"
    params: dict[str, object] = {"account": account}
    if business_date is not None:
        sql += " and business_date_la = :business_date"
        params["business_date"] = business_date
    return int(session.execute(text(sql), params).scalar_one())
