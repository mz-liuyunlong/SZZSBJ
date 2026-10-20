from datetime import date
from decimal import Decimal

from app.modules.warehouse_wfs.verified_fee_evidence import (
    analyze_wfs_evidence,
)


def rows_for(rate, quantity, start):
    rows = []
    for index in range(quantity):
        order = f"order-{start + index}"
        rows.extend(
            [
                {
                    "msku": "YC00115-1A",
                    "platformOrderNo": order,
                    "uniqueId": f"sale-{start + index}",
                    "rowIndex": 0,
                    "salesNum": 1,
                    "platformLogisticsAmount": 0,
                    "settlementDate": "2026-09-10",
                },
                {
                    "msku": "YC00115-1A",
                    "platformOrderNo": order,
                    "uniqueId": f"fee-{start + index}",
                    "rowIndex": 1,
                    "salesNum": 0,
                    "platformLogisticsAmount": str(-rate),
                    "settlementDate": "2026-09-10",
                },
            ]
        )
    return rows


def test_evidenced_overcharge_and_legacy_estimate():
    rows = rows_for(Decimal("6.26"), 49, 0) + rows_for(Decimal("6.95"), 38, 100)
    result = analyze_wfs_evidence(
        rows,
        msku="YC00115-1A",
        standard_fee=Decimal("6.55"),
        historical_units=87,
        as_of=date(2026, 9, 15),
    )
    assert result.settlement_units == 87
    assert result.settlement_orders == 87
    assert result.evidenced_overcharge == Decimal("15.20")
    assert result.evidenced_net_difference == Decimal("0.99")
    assert result.status == "NO_OVERCHARGE"


def test_stale_data_prevents_automatic_candidate():
    result = analyze_wfs_evidence(
        rows_for(Decimal("6.95"), 12, 0),
        msku="YC00115-1A",
        standard_fee=Decimal("6.55"),
        historical_units=87,
        as_of=date(2026, 10, 21),
    )
    assert result.actual_fee == Decimal("6.95")
    assert result.legacy_estimate == Decimal("34.80")
    assert result.status == "STALE"


def test_missing_evidence():
    result = analyze_wfs_evidence(
        [],
        msku="YC00115-1A",
        standard_fee=Decimal("6.55"),
    )
    assert result.actual_fee is None
    assert result.status == "INSUFFICIENT_EVIDENCE"
