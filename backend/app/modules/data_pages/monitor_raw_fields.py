"""Field-level read-only projection from the latest *successful* monitor RAW.

Do not use attempted/failed monitor payloads as values. The existing
mart_walmart_monitor_listing_current -> source_raw_event_id link points to
its last successfully published observation; this module only interprets
that JSON object and never writes to RAW or other business tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MonitorRawFields:
    has_strikethrough: bool | None = None
    strikethrough_source: str | None = None
    seller_names: tuple[str, ...] = ()
    seller_offer_count: int | None = None
    other_sellers_present: bool | None = None
    image_urls: tuple[str, ...] = ()
    image_urls_observed: bool = False
    image_count: int | None = None
    key_features: tuple[str, ...] = ()
    review_fetch_status: str | None = None


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _list_of_text(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(t for item in value if (t := _text(item)) is not None)


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, str)):
        return None
    try:
        result = int(value)
    except ValueError:
        return None
    return result if result >= 0 else None


def parse_monitor_raw_fields(payload: object) -> MonitorRawFields:
    if not isinstance(payload, dict):
        return MonitorRawFields()
    rating = payload.get("ratingSummary")
    rating_summary = rating if isinstance(rating, dict) else {}
    has_strike = payload.get("hasStrikethrough")
    other_sellers = payload.get("otherSellersPresent")
    urls = _list_of_text(payload.get("productImageUrls"))
    count = _nonnegative_int(payload.get("productImageCount"))
    # Explicit count zero is a real monitoring result, not a missing value.
    if count is None and isinstance(payload.get("productImageUrls"), list):
        count = len(urls)
    return MonitorRawFields(
        has_strikethrough=has_strike if isinstance(has_strike, bool) else None,
        strikethrough_source=_text(payload.get("strikethroughSource")),
        seller_names=_list_of_text(payload.get("sellerNames")),
        seller_offer_count=_nonnegative_int(payload.get("sellerOfferCount")),
        other_sellers_present=other_sellers if isinstance(other_sellers, bool) else None,
        image_urls=urls,
        image_urls_observed=isinstance(payload.get("productImageUrls"), list),
        image_count=count,
        key_features=_list_of_text(payload.get("keyFeatures")),
        review_fetch_status=_text(rating_summary.get("reviewFetchStatus")),
    )
