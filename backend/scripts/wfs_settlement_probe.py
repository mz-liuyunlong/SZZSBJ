"""Bounded WFS settlement contract probe. No database or case writes."""

from __future__ import annotations

import os
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import cast

from pydantic import JsonValue

from app.core.config import get_settings
from app.integrations.lingxing.business_api import LingxingBusinessApiExecutor
from app.integrations.lingxing.openapi import LingxingOpenApiClient, LingxingOpenApiDryRun
from app.integrations.lingxing.token_manager import get_shared_lingxing_token_manager

INTERFACE_ID = "LX-DB6D62E9EE37"
APPROVED_SOURCE_ACCOUNT_REF = "primary"
APPROVED_STORE_ID = "110704872940532224"
APPROVED_MSKU = "YC00115-1A"
APPROVED_START_DATE = date(2026, 8, 19)
APPROVED_END_DATE = date(2026, 10, 17)
APPROVED_PAGE_SIZE = 20
APPROVED_MAX_PAGES = 20
REQUIRED_FIELDS = (
    "msku",
    "storeId",
    "platformOrderNo",
    "salesNum",
    "settlementDate",
    "uniqueId",
    "rowIndex",
    "currencyCode",
    "platformCode",
    "transactionTypes",
)
FEE_SCOPE_FIELDS = (
    "platformLogisticsAmount",
    "wfsShipmentFee",
    "platformWfsStorageAmount",
    "platformWfsRemoveAmount",
    "wfsWarehousFee",
)


class ProbeError(RuntimeError):
    """Safe probe failure without request or response values."""


@dataclass(frozen=True, slots=True)
class ProbeConfig:
    source_account_ref: str
    store_id: str
    msku: str
    start_date: date
    end_date: date
    page_size: int
    max_pages: int


def _load_config(environ: Mapping[str, str]) -> ProbeConfig:
    try:
        start_date = date.fromisoformat(environ["WFS_PROBE_START_DATE"])
        end_date = date.fromisoformat(environ["WFS_PROBE_END_DATE"])
        page_size = int(environ.get("WFS_PROBE_PAGE_SIZE", "20"))
        max_pages = int(environ.get("WFS_PROBE_MAX_PAGES", "20"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ProbeError("WFS_PROBE_CONFIG_INVALID") from exc

    source_account_ref = environ.get("WFS_PROBE_SOURCE_ACCOUNT_REF", "").strip()
    store_id = environ.get("WFS_PROBE_STORE_ID", "").strip()
    msku = environ.get("WFS_PROBE_MSKU", "").strip()
    if (
        source_account_ref != APPROVED_SOURCE_ACCOUNT_REF
        or store_id != APPROVED_STORE_ID
        or msku != APPROVED_MSKU
        or start_date != APPROVED_START_DATE
        or end_date != APPROVED_END_DATE
        or page_size != APPROVED_PAGE_SIZE
        or max_pages != APPROVED_MAX_PAGES
    ):
        raise ProbeError("WFS_PROBE_SCOPE_INVALID")
    return ProbeConfig(
        source_account_ref=source_account_ref,
        store_id=store_id,
        msku=msku,
        start_date=start_date,
        end_date=end_date,
        page_size=page_size,
        max_pages=max_pages,
    )


def _request_body(config: ProbeConfig, *, offset: int) -> dict[str, JsonValue]:
    return {
        "offset": offset,
        "length": config.page_size,
        "sids": config.store_id,
        "platformCodeS": ["10008"],
        "transactionTypeS": [0],
        "currencyCode": "USD",
        "searchDateType": "2",
        "startDate": config.start_date.isoformat(),
        "endDate": config.end_date.isoformat(),
        "searchField": "msku",
        "searchValue": config.msku,
    }


def _page(payload: JsonValue) -> tuple[list[dict[str, object]], int]:
    if not isinstance(payload, dict) or str(payload.get("code")) != "0":
        raise ProbeError("WFS_PROBE_PROVIDER_RESPONSE_FAILED")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ProbeError("WFS_PROBE_RESPONSE_SHAPE_INVALID")
    rows = data.get("list")
    top_total = payload.get("total")
    nested_total = data.get("total")
    if (
        not isinstance(rows, list)
        or not all(isinstance(row, dict) for row in rows)
        or (top_total is not None and nested_total is not None and top_total != nested_total)
    ):
        raise ProbeError("WFS_PROBE_RESPONSE_SHAPE_INVALID")
    total = top_total if top_total is not None else nested_total
    if type(total) is not int or total < 0:
        raise ProbeError("WFS_PROBE_TOTAL_INVALID")
    return cast(list[dict[str, object]], rows), total


def _validate_scope(
    rows: list[dict[str, object]],
    *,
    config: ProbeConfig,
) -> None:
    for row in rows:
        store_id = row.get("storeId")
        if isinstance(store_id, float) or str(store_id) != config.store_id:
            raise ProbeError("WFS_PROBE_STORE_SCOPE_MISMATCH")
        if row.get("msku") != config.msku:
            raise ProbeError("WFS_PROBE_MSKU_SCOPE_MISMATCH")
        if (
            row.get("currencyCode") != "USD"
            or str(row.get("platformCode")) != "10008"
            or str(row.get("transactionTypes")) != "0"
        ):
            raise ProbeError("WFS_PROBE_BUSINESS_SCOPE_MISMATCH")
        for field_name in FEE_SCOPE_FIELDS:
            value = row.get(field_name)
            if value is None:
                continue
            try:
                parsed = Decimal(str(value))
            except (InvalidOperation, ValueError) as exc:
                raise ProbeError("WFS_PROBE_FEE_FIELD_TYPE_INVALID") from exc
            if isinstance(value, bool) or not parsed.is_finite():
                raise ProbeError("WFS_PROBE_FEE_FIELD_TYPE_INVALID")


def main() -> int:
    if os.getenv("WFS_PROBE_ALLOW_READ") != "YES":
        print("STOP: WFS_PROBE_ALLOW_READ_REQUIRED")
        return 2
    try:
        config = _load_config(os.environ)
    except ProbeError as exc:
        print("STOP:", str(exc))
        return 2

    settings = get_settings()
    if not settings.lingxing_enable_real_calls:
        print("STOP: LINGXING_REAL_CALLS_DISABLED")
        return 2

    executor = LingxingBusinessApiExecutor(
        settings,
        token_provider=get_shared_lingxing_token_manager(settings),
    )
    captured = 0
    attempted = 0
    expected_total: int | None = None
    field_counts: Counter[str] = Counter()
    try:
        client = LingxingOpenApiClient(
            executor=executor,
            enabled_interface_ids=frozenset({INTERFACE_ID}),
        )
        first_request = _request_body(config, offset=0)
        preview = client.call(INTERFACE_ID, first_request, dry_run=True)
        if not isinstance(preview, LingxingOpenApiDryRun) or preview.outbound_attempted:
            raise ProbeError("WFS_PROBE_DRY_RUN_FAILED")

        for page_no in range(1, config.max_pages + 1):
            attempted += 1
            response = client.call(
                INTERFACE_ID,
                _request_body(config, offset=captured),
                dry_run=False,
            )
            if isinstance(response, LingxingOpenApiDryRun):
                raise ProbeError("WFS_PROBE_OUTBOUND_NOT_ATTEMPTED")
            rows, total = _page(cast(JsonValue, response))
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise ProbeError("WFS_PROBE_TOTAL_CHANGED")
            _validate_scope(rows, config=config)
            field_counts.update(
                field_name
                for row in rows
                for field_name in (*REQUIRED_FIELDS, *FEE_SCOPE_FIELDS)
                if row.get(field_name) is not None
            )
            captured += len(rows)
            print(f"PAGE_{page_no}_RECORDS:", len(rows))
            if captured == total:
                break
            if not rows or len(rows) < config.page_size or captured > total:
                raise ProbeError("WFS_PROBE_PAGINATION_INCOMPLETE")

        if expected_total is None or captured != expected_total:
            raise ProbeError("WFS_PROBE_MAX_PAGES_REACHED")

        print("API_REQUESTS_ATTEMPTED:", attempted)
        print("MAX_ROWS_ALLOWED:", config.page_size * config.max_pages)
        print("EXPECTED_TOTAL:", expected_total)
        print("CAPTURED_TOTAL:", captured)
        print("REQUIRED_FIELD_PRESENCE:")
        for field_name in REQUIRED_FIELDS:
            print(f"  {field_name}: {field_counts[field_name]}/{captured}")
        print("FEE_SCOPE_FIELD_PRESENCE:")
        for field_name in FEE_SCOPE_FIELDS:
            print(f"  {field_name}: {field_counts[field_name]}/{captured}")
        print("WFS_SCOPE_DECISION: OWNER_REVIEW_REQUIRED")
        print("RAW_OUTPUT: DISABLED")
        print("DATABASE_WRITES: 0")
        print("CASE_WRITES: 0")
        return 0
    except ProbeError as exc:
        print("PROBE_FAILED_CODE:", str(exc))
        return 1
    finally:
        executor.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Never print provider payload, request parameters or credentials.
        print("PROBE_FAILED_TYPE:", type(exc).__name__)
        sys.exit(1)
