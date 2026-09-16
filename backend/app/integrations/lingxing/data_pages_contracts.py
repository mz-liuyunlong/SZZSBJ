from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from pydantic import JsonValue

WALMART_PLATFORM_CODE = 10008
CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")
SP_CAMPAIGN_TYPES: tuple[str, str] = (
    "sponsoredProducts-manual",
    "sponsoredProducts-auto",
)

SELLER_ENDPOINT = "/pb/mp/shop/v2/getSellerList"
WALMART_LISTING_ENDPOINT = "/basicOpen/multiplatform/walmart/list"
SALE_STAT_ENDPOINT = "/basicOpen/platformStatisticsV2/saleStat/pageList"
ORDER_ENDPOINT = "/pb/mp/order/v2/list"
RETURN_ENDPOINT = "/basicOpen/openapi/multiplatform/walmart/returnOrder/list"
ADVERTISER_ENDPOINT = "/basicOpen/adReport/advertiser/list"
AD_ITEM_SP_ENDPOINT = "/basicOpen/multiplatform/ads/reportAdItemSpList"

DATA_PAGES_ENDPOINTS = frozenset(
    {
        SELLER_ENDPOINT,
        WALMART_LISTING_ENDPOINT,
        SALE_STAT_ENDPOINT,
        ORDER_ENDPOINT,
        RETURN_ENDPOINT,
        ADVERTISER_ENDPOINT,
        AD_ITEM_SP_ENDPOINT,
    }
)


@dataclass(frozen=True, slots=True)
class DataPagesProviderPageContract:
    """Observed/verified provider page-size constraints for bounded DATA-PAGES calls."""

    minimum_page_size: int = 1
    maximum_probe_page_size: int = 3
    observed_response_floor: int | None = None


# Seller and Order V2 were provider-verified on 2026-09-17 to reject length < 20.
# The other endpoints were successfully probed with a requested size of 3. Advertiser
# returned 10 rows despite limit=3, so its response floor is recorded as an observation
# rather than guessed into request semantics.
DATA_PAGES_PROVIDER_PAGE_CONTRACTS: dict[str, DataPagesProviderPageContract] = {
    SELLER_ENDPOINT: DataPagesProviderPageContract(20, 20),
    WALMART_LISTING_ENDPOINT: DataPagesProviderPageContract(1, 3),
    SALE_STAT_ENDPOINT: DataPagesProviderPageContract(1, 3),
    ORDER_ENDPOINT: DataPagesProviderPageContract(20, 20),
    RETURN_ENDPOINT: DataPagesProviderPageContract(1, 3),
    ADVERTISER_ENDPOINT: DataPagesProviderPageContract(1, 3, observed_response_floor=10),
    AD_ITEM_SP_ENDPOINT: DataPagesProviderPageContract(1, 3),
}

DATA_PAGES_PAGE_SIZE_FIELDS: dict[str, str] = {
    SELLER_ENDPOINT: "length",
    WALMART_LISTING_ENDPOINT: "length",
    SALE_STAT_ENDPOINT: "length",
    ORDER_ENDPOINT: "length",
    RETURN_ENDPOINT: "pageSize",
    ADVERTISER_ENDPOINT: "limit",
    AD_ITEM_SP_ENDPOINT: "pageSize",
}


def data_pages_probe_page_size(api_path: str, requested_page_size: int) -> int:
    """Resolve a bounded request size while honoring provider minimums.

    Callers may continue to request the global safe sample size (normally <=3). For
    endpoints whose provider rejects that size, this raises only to the smallest
    provider-verified value. It never expands beyond the endpoint-specific probe cap.
    """

    contract = DATA_PAGES_PROVIDER_PAGE_CONTRACTS.get(api_path)
    if contract is None:
        return requested_page_size
    resolved = max(requested_page_size, contract.minimum_page_size)
    return min(resolved, contract.maximum_probe_page_size)


def data_pages_probe_page_size_limit(api_path: str, configured_limit: int) -> int:
    """Return the largest page size this bounded DATA-PAGES path may emit."""

    contract = DATA_PAGES_PROVIDER_PAGE_CONTRACTS.get(api_path)
    if contract is None:
        return configured_limit
    return max(configured_limit, contract.maximum_probe_page_size)


def normalize_data_pages_body(
    api_path: str,
    body: JsonValue,
    *,
    page_size: int | None = None,
) -> JsonValue:
    """Normalize DATA-PAGES bodies against owner docs and provider validation.

    Authentication remains outside the business body. When ``page_size`` is supplied,
    the endpoint's documented pagination field is normalized to the bounded provider-
    compatible request size so signing values and transmitted JSON stay identical.
    """

    if api_path not in DATA_PAGES_ENDPOINTS or not isinstance(body, dict):
        return body

    normalized: dict[str, Any] = dict(body)

    if page_size is not None:
        page_size_field = DATA_PAGES_PAGE_SIZE_FIELDS.get(api_path)
        if page_size_field is not None:
            normalized[page_size_field] = data_pages_probe_page_size(api_path, page_size)

    if api_path == SELLER_ENDPOINT:
        normalized["platform_code"] = _platform_codes(normalized.get("platform_code"))
        # The owner-provided endpoint example and the successful parameter-validation
        # probe both use active + synchronized stores. Keep these explicit for REAL-DATA.
        normalized.setdefault("is_sync", 1)
        normalized.setdefault("status", 1)

    elif api_path == SALE_STAT_ENDPOINT:
        # Official enums: data_type=4 -> SKU, date_unit=4 -> day.
        normalized["data_type"] = "4"
        normalized["date_unit"] = "4"
        result_type = normalized.get("result_type")
        if isinstance(result_type, int) and not isinstance(result_type, bool):
            normalized["result_type"] = str(result_type)

    elif api_path == ORDER_ENDPOINT:
        normalized["platform_code"] = _platform_codes(normalized.get("platform_code"))
        store_id = normalized.get("store_id")
        if store_id is not None and not isinstance(store_id, list):
            normalized["store_id"] = [store_id]
        for field_name in ("start_time", "end_time"):
            value = normalized.get(field_name)
            if isinstance(value, str) and not value.isdecimal():
                normalized[field_name] = _china_datetime_to_epoch_seconds(value)

    elif api_path == RETURN_ENDPOINT:
        date_type = normalized.get("dateType")
        if isinstance(date_type, str) and date_type.isdecimal():
            normalized["dateType"] = int(date_type)

    elif api_path == AD_ITEM_SP_ENDPOINT:
        campaign_type = normalized.get("campaignType")
        if campaign_type == "SP":
            normalized["campaignType"] = list(SP_CAMPAIGN_TYPES)
        elif isinstance(campaign_type, str):
            normalized["campaignType"] = [campaign_type]
        advertiser_ids = normalized.get("advertiserIds")
        if isinstance(advertiser_ids, list):
            normalized["advertiserIds"] = [_decimal_id(value) for value in advertiser_ids]

    return cast(JsonValue, normalized)


def _platform_codes(value: object) -> list[int | str]:
    if isinstance(value, list):
        return [
            item for item in value if isinstance(item, (int, str)) and not isinstance(item, bool)
        ]
    if isinstance(value, bool) or value is None:
        return [WALMART_PLATFORM_CODE]
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdecimal():
            return [int(stripped)]
        if stripped:
            return [stripped]
    return [WALMART_PLATFORM_CODE]


def _decimal_id(value: object) -> object:
    if isinstance(value, str) and value.strip().isdecimal():
        return int(value.strip())
    return value


def _china_datetime_to_epoch_seconds(value: str) -> int | str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=CHINA_TIMEZONE)
    except ValueError:
        return value
    return int(parsed.timestamp())
