from __future__ import annotations

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


def normalize_data_pages_body(api_path: str, body: JsonValue) -> JsonValue:
    """Normalize the approved DATA-PAGES request body to the official Lingxing contract.

    The REAL-DATA-1 runner was originally built from the derived repository index. The
    owner's complete Lingxing documentation snapshot confirms several value types and
    enum values that differ from that derived index. Keep the compatibility correction
    at the integration boundary so the actual signed body is also the body preserved in
    the safe request envelope.
    """

    if api_path not in DATA_PAGES_ENDPOINTS or not isinstance(body, dict):
        return body

    normalized: dict[str, Any] = dict(body)

    if api_path == SELLER_ENDPOINT:
        normalized["platform_code"] = _platform_codes(normalized.get("platform_code"))

    elif api_path == SALE_STAT_ENDPOINT:
        # DATA-PAGES is SKU/item-grained. Official values are string enums:
        # data_type=4 (SKU) and date_unit=4 (day).
        normalized["data_type"] = "4"
        normalized["date_unit"] = "4"

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

    elif api_path == ADVERTISER_ENDPOINT:
        paging = normalized.get("paging")
        if isinstance(paging, bool):
            normalized["paging"] = "true" if paging else "false"

    elif api_path == AD_ITEM_SP_ENDPOINT:
        campaign_type = normalized.get("campaignType")
        if campaign_type == "SP":
            normalized["campaignType"] = list(SP_CAMPAIGN_TYPES)
        elif isinstance(campaign_type, str):
            normalized["campaignType"] = [campaign_type]

    return cast(JsonValue, normalized)


def _platform_codes(value: object) -> list[int | str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, (int, str)) and not isinstance(item, bool)]
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


def _china_datetime_to_epoch_seconds(value: str) -> int | str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=CHINA_TIMEZONE)
    except ValueError:
        return value
    return int(parsed.timestamp())
