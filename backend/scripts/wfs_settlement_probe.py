"""One-page WFS settlement API structure probe. No database operations."""

from __future__ import annotations

import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.integrations.lingxing.business_api import LingxingBusinessApiExecutor
from app.integrations.lingxing.openapi import LingxingOpenApiClient
from app.integrations.lingxing.token_manager import get_shared_lingxing_token_manager

INTERFACE_ID = "LX-DB6D62E9EE37"
REQUIRED_FIELDS = (
    "msku",
    "storeName",
    "storeId",
    "platformOrderNo",
    "salesNum",
    "platformLogisticsAmount",
    "settlementDate",
    "uniqueId",
    "rowIndex",
)


def main() -> int:
    if os.getenv("WFS_PROBE_ALLOW_READ") != "YES":
        print("STOP: WFS_PROBE_ALLOW_READ_REQUIRED")
        return 2

    raw_sids = os.getenv("WFS_PROBE_SIDS", "")
    sids = [x.strip() for x in raw_sids.split(",") if x.strip()]

    if len(sids) != 1 or not sids[0].isdigit():
        print("STOP: ONE_NUMERIC_LINGXING_SID_REQUIRED")
        return 2

    settings = get_settings()
    if not settings.lingxing_enable_real_calls:
        print("STOP: LINGXING_REAL_CALLS_DISABLED")
        return 2

    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    end = today - timedelta(days=2)
    start = end - timedelta(days=6)

    request_body = {
        "offset": 0,
        "length": 20,
        "sids": sids,
        "platformCodeS": ["10008"],
        "transactionTypeS": [0],
        "currencyCode": "USD",
        "searchDateType": "2",
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
    }

    executor = LingxingBusinessApiExecutor(
        settings,
        token_provider=get_shared_lingxing_token_manager(settings),
    )

    try:
        client = LingxingOpenApiClient(
            executor=executor,
            enabled_interface_ids=frozenset({INTERFACE_ID}),
        )

        # Validate official contract before the real read.
        preview = client.call(
            INTERFACE_ID,
            request_body,
            dry_run=True,
        )
        assert preview.outbound_attempted is False

        response = client.call(
            INTERFACE_ID,
            request_body,
            dry_run=False,
        )

        print("API_REQUEST_ATTEMPTED: 1")
        print("WINDOW_DAYS: 7")
        print("REQUESTED_PAGE_SIZE: 20")

        if not isinstance(response, dict):
            print("RESPONSE_SHAPE: NON_OBJECT")
            return 1

        # No response values are printed.
        print("RESPONSE_FIELDS:", sorted(response.keys()))

        data = response.get("data")
        if isinstance(data, dict):
            print("DATA_FIELDS:", sorted(data.keys()))

        records = None
        if isinstance(data, dict):
            for key in ("list", "rows", "records"):
                if isinstance(data.get(key), list):
                    records = data[key]
                    print("RECORD_ARRAY_KEY:", key)
                    break
        elif isinstance(data, list):
            records = data
            print("RECORD_ARRAY_KEY: data")

        if records is None:
            print("RECORD_ARRAY_NOT_IDENTIFIED")
            return 1

        print("RETURNED_RECORDS:", len(records))

        objects = [r for r in records if isinstance(r, dict)]
        counts = Counter(
            key for row in objects for key in REQUIRED_FIELDS if row.get(key) is not None
        )

        print("REQUIRED_FIELD_PRESENCE:")
        for key in REQUIRED_FIELDS:
            print(f"  {key}: {counts[key]}/{len(objects)}")

        print(
            "UNSAFE_FLOAT_STORE_ID_ROWS:",
            sum(isinstance(row.get("storeId"), float) for row in objects),
        )

        print(
            "ZERO_SALES_ROWS:", sum(str(row.get("salesNum", "")) in ("0", "0.0") for row in objects)
        )

        print("RAW_OUTPUT: DISABLED")
        print("DATABASE_WRITES: 0")
        return 0

    finally:
        executor.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Never print provider payload, request parameters or credentials.
        print("PROBE_FAILED_TYPE:", type(exc).__name__)
        sys.exit(1)
