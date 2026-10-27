"""Typed projection of immutable Walmart monitor RAW events.

RAW remains the replay/audit boundary. This module is the only place that gives
provider fields the governed Listing semantics approved for the new system.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.walmart_monitor.models import (
    RawWalmartMonitorEvent,
    StandardizedWalmartMonitorListingObservation,
    WalmartMonitorListingCurrent,
)
from app.modules.walmart_monitor.schemas import MonitorTarget, WalmartMonitorRawEventRequest

PARSER_VERSION = "walmart-monitor-listing-v1"
_TRUE_HIJACK = {"hijacked", "reseller_detected", "external_seller", "abnormal"}
_FALSE_HIJACK = {
    "clear",
    "no_reseller",
    "not_reseller",
    "normal",
    "owned_only",
    "recovered",
}
_SUCCESS_OUTCOMES = {"success", "check_ok"}


@dataclass(frozen=True, slots=True)
class MonitorListingValues:
    title: str | None
    strike_price_amount: Decimal | None
    strike_price_currency_code: str | None
    sale_price_amount: Decimal | None
    sale_price_currency_code: str | None
    category: str | None
    source_category_raw: str | None
    buybox_status: str | None
    walmart_seller: str | None
    is_hijacked: bool | None
    average_rating: Decimal | None
    review_count: int | None
    brand: str | None
    image_urls_json: list[str]


def parse_monitor_listing_values(
    parsed: dict[str, Any],
    *,
    target: MonitorTarget,
) -> MonitorListingValues:
    rating = parsed.get("ratingSummary")
    rating_summary = rating if isinstance(rating, dict) else {}
    currency = _currency(parsed.get("currency"))
    strike = _money(parsed.get("strikethroughPrice"))
    if strike is None:
        cents = _money(parsed.get("strikethroughPriceCents"))
        strike = cents / Decimal(100) if cents is not None else None
    sale = _money(parsed.get("currentPrice"))

    return MonitorListingValues(
        title=_text(parsed.get("productTitle")),
        strike_price_amount=strike,
        strike_price_currency_code=currency if strike is not None else None,
        sale_price_amount=sale,
        sale_price_currency_code=currency if sale is not None else None,
        category=_category(parsed.get("walmartCategory")),
        source_category_raw=_text(target.product_category),
        buybox_status=_text(parsed.get("cartStatus")),
        walmart_seller=_text(parsed.get("sellerName")),
        is_hijacked=_explicit_hijack(parsed),
        average_rating=_rating(rating_summary.get("rating", parsed.get("rating"))),
        review_count=_nonnegative_int(rating_summary.get("reviewCount", parsed.get("reviewCount"))),
        brand=_text(parsed.get("productBrand")),
        image_urls_json=_string_list(parsed.get("productImageUrls")),
    )


class WalmartMonitorProjectionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def project(self, raw_event: RawWalmartMonitorEvent) -> int:
        payload = WalmartMonitorRawEventRequest.model_validate(raw_event.payload_json)
        parsed = (
            payload.final_observation.parsed_result
            if _is_publishable_observation(
                payload.final_observation.outcome,
                payload.final_observation.parsed_result,
            )
            else {}
        )
        return sum(
            self._project_target(raw_event=raw_event, payload=payload, target=target, parsed=parsed)
            for target in payload.targets
        )

    def _project_target(
        self,
        *,
        raw_event: RawWalmartMonitorEvent,
        payload: WalmartMonitorRawEventRequest,
        target: MonitorTarget,
        parsed: dict[str, Any],
    ) -> int:
        values = parse_monitor_listing_values(parsed, target=target)
        observation_id = self.session.scalar(
            insert(StandardizedWalmartMonitorListingObservation)
            .values(
                id=uuid4(),
                raw_event_id=raw_event.id,
                source_account_ref=target.source_account_ref,
                store_id=target.store_id,
                item_id=target.item_id,
                captured_at=payload.captured_at,
                monitor_outcome=payload.final_observation.outcome,
                monitor_source=payload.final_observation.data_source,
                monitor_error_code=payload.final_observation.error_code,
                **asdict(values),
                parser_version=PARSER_VERSION,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    StandardizedWalmartMonitorListingObservation.raw_event_id,
                    StandardizedWalmartMonitorListingObservation.source_account_ref,
                    StandardizedWalmartMonitorListingObservation.store_id,
                    StandardizedWalmartMonitorListingObservation.item_id,
                ]
            )
            .returning(StandardizedWalmartMonitorListingObservation.id)
        )
        if not isinstance(observation_id, UUID):
            return 0
        if not _is_publishable_observation(
            payload.final_observation.outcome,
            payload.final_observation.parsed_result,
        ):
            # Failure evidence belongs in immutable L3, but must not replace the
            # last successful monitor-owned values exposed to Listing Management.
            return 1

        current_values = {
            "source_observation_id": observation_id,
            "source_raw_event_id": raw_event.id,
            "observed_at": payload.captured_at,
            "monitor_outcome": payload.final_observation.outcome,
            "monitor_source": payload.final_observation.data_source,
            "monitor_error_code": payload.final_observation.error_code,
            **asdict(values),
        }
        excluded = insert(WalmartMonitorListingCurrent).excluded
        self.session.execute(
            insert(WalmartMonitorListingCurrent)
            .values(
                id=uuid4(),
                source_account_ref=target.source_account_ref,
                store_id=target.store_id,
                item_id=target.item_id,
                **current_values,
            )
            .on_conflict_do_update(
                index_elements=[
                    WalmartMonitorListingCurrent.source_account_ref,
                    WalmartMonitorListingCurrent.store_id,
                    WalmartMonitorListingCurrent.item_id,
                ],
                set_={
                    **{name: getattr(excluded, name) for name in current_values},
                    "updated_at": func.now(),
                },
                where=excluded.observed_at >= WalmartMonitorListingCurrent.observed_at,
            )
        )
        return 1

    def replay_unprojected(self, *, limit: int) -> int:
        rows = self.session.scalars(
            select(RawWalmartMonitorEvent)
            .outerjoin(
                StandardizedWalmartMonitorListingObservation,
                StandardizedWalmartMonitorListingObservation.raw_event_id
                == RawWalmartMonitorEvent.id,
            )
            .where(StandardizedWalmartMonitorListingObservation.id.is_(None))
            .order_by(RawWalmartMonitorEvent.captured_at, RawWalmartMonitorEvent.id)
            .limit(limit)
        ).all()
        return sum(self.project(row) for row in rows)


def _is_publishable_observation(outcome: str, parsed: dict[str, Any]) -> bool:
    return outcome.casefold() in _SUCCESS_OUTCOMES and bool(parsed)


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip()
    return result or None


def _money(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result >= 0 and result.is_finite() else None


def _rating(value: object) -> Decimal | None:
    result = _money(value)
    return result if result is not None and result <= 5 else None


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _currency(value: object) -> str | None:
    result = _text(value)
    if result is None:
        return None
    result = result.upper()
    return result if len(result) == 3 else None


def _category(value: object) -> str | None:
    if isinstance(value, list):
        parts = [_text(item) for item in value]
        return " > ".join(part for part in parts if part) or None
    if isinstance(value, dict):
        path = value.get("path")
        if isinstance(path, list):
            parts = [
                _text(item.get("name")) if isinstance(item, dict) else _text(item) for item in path
            ]
            return " > ".join(part for part in parts if part) or None
        return _text(value.get("name"))
    return _text(value)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for raw in value if (item := _text(raw)) is not None]


def _explicit_hijack(parsed: dict[str, Any]) -> bool | None:
    direct = parsed.get("isHijacked", parsed.get("is_hijacked"))
    if isinstance(direct, bool):
        return direct
    status = parsed.get("resellerStatus", parsed.get("reseller_status"))
    if isinstance(status, bool):
        return status
    normalized = _text(status)
    if normalized is None:
        return None
    normalized = normalized.casefold()
    if normalized in _TRUE_HIJACK:
        return True
    if normalized in _FALSE_HIJACK:
        return False
    return None
