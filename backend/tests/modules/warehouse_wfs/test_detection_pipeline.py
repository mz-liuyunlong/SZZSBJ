from datetime import date
from decimal import Decimal

import pytest

from app.modules.warehouse_wfs.anomaly_detection import WfsStandardFee
from app.modules.warehouse_wfs.detection_pipeline import (
    WfsDetectionError,
    evaluate_wfs_settlements,
    legacy_detection_window,
)
from app.modules.warehouse_wfs.store_discovery import WfsSettlementStore

ACCOUNT = "primary"
STORE = "110704872940532224"
NAME = "Walmart Test Store"
MSKU = "YC00115-1A"


def store_scope():
    return (
        WfsSettlementStore(
            source_account_ref=ACCOUNT,
            store_id=STORE,
            store_name=NAME,
            sid="",
        ),
    )


def settlement_rows():
    rows = []

    for n in (1, 2):
        common = {
            "storeName": NAME,
            "storeId": STORE,
            "platformCode": "10008",
            "transactionTypes": 0,
            "currencyCode": "USD",
            "msku": MSKU,
            "platformOrderNo": f"order-{n}",
            "settlementDate": "2026-10-01",
            "uniqueId": f"order-{n}",
        }

        rows.append(
            {
                **common,
                "rowIndex": 1,
                "salesNum": 5,
                "platformLogisticsAmount": 0,
            }
        )
        rows.append(
            {
                **common,
                "rowIndex": 2,
                "salesNum": 0,
                "platformLogisticsAmount": "-34.75",
            }
        )

    return rows


def standard(amount):
    return WfsStandardFee(
        source_account_ref=ACCOUNT,
        store_id=STORE,
        msku=MSKU,
        unit_fee=Decimal(amount),
        source="product_management",
        rule_version="current",
    )


def evaluate(amount, rows=None):
    return evaluate_wfs_settlements(
        source_account_ref=ACCOUNT,
        stores=store_scope(),
        raw_rows=settlement_rows() if rows is None else rows,
        standards=[standard(amount)],
        window=legacy_detection_window(date(2026, 10, 19)),
    )


def test_legacy_60_day_window():
    window = legacy_detection_window(date(2026, 10, 19))
    assert window.start == date(2026, 8, 19)
    assert window.end == date(2026, 10, 17)


def test_product_management_standard_is_dynamic():
    anomalous = evaluate("6.55")
    assert anomalous.settlement_rows == 4
    assert anomalous.detection.anomalies == 1

    candidate = anomalous.detection.candidates[0]
    assert candidate.actual_unit_fee == Decimal("6.95")
    assert candidate.standard_unit_fee == Decimal("6.55")
    assert candidate.unit_overcharge == Decimal("0.40")
    assert candidate.sample_units == Decimal("10")

    normal = evaluate("7.00")
    assert normal.detection.anomalies == 0
    assert normal.detection.normal == 1


def test_rejects_wrong_store_instead_of_partial_detection():
    rows = settlement_rows()
    rows[0]["storeId"] = "999999999999999999"

    with pytest.raises(
        WfsDetectionError,
        match="WFS_INCOMPLETE_OR_INVALID_SETTLEMENT",
    ):
        evaluate("6.55", rows)


def test_missing_standard_does_not_create_candidate():
    result = evaluate_wfs_settlements(
        source_account_ref=ACCOUNT,
        stores=store_scope(),
        raw_rows=settlement_rows(),
        standards=[],
        window=legacy_detection_window(date(2026, 10, 19)),
    )

    assert result.detection.anomalies == 0
    assert result.detection.missing_standard == 1
