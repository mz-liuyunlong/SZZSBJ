from decimal import Decimal

import pytest

from app.modules.warehouse_wfs.anomaly_detection import (
    WfsStandardFee,
    detect_wfs_anomalies,
)
from app.modules.warehouse_wfs.fee_detection import ResolvedWfsFee


def actual(
    store="store-a",
    fee="5.18",
):
    return ResolvedWfsFee(
        source_account_ref="account-a",
        store_id=store,
        msku="SKU-TEST",
        unit_fee=Decimal(fee) if fee is not None else None,
        sample_units=Decimal("10"),
        fee_orders=2,
        mode_count=2,
        skipped_no_qty=0,
    )


def standard(store="store-a", fee="4.65"):
    return WfsStandardFee(
        source_account_ref="account-a",
        store_id=store,
        msku="SKU-TEST",
        unit_fee=Decimal(fee),
        source="product_management",
        rule_version="test-v1",
    )


def test_overcharge_candidate():
    result = detect_wfs_anomalies(
        [actual()],
        [standard()],
    )
    assert result.anomalies == 1
    candidate = result.candidates[0]
    assert candidate.unit_overcharge == Decimal("0.53")
    assert candidate.estimated_sample_overcharge == Decimal("5.30")


def test_normal_fee_not_reported():
    result = detect_wfs_anomalies(
        [actual(fee="4.65")],
        [standard()],
    )
    assert result.anomalies == 0
    assert result.normal == 1


def test_missing_standard_not_reported():
    result = detect_wfs_anomalies([actual()], [])
    assert result.anomalies == 0
    assert result.missing_standard == 1


def test_insufficient_sample_not_reported():
    result = detect_wfs_anomalies(
        [actual(fee=None)],
        [standard()],
    )
    assert result.insufficient_samples == 1
    assert result.anomalies == 0


def test_store_isolation():
    result = detect_wfs_anomalies(
        [actual(store="store-b")],
        [standard(store="store-a")],
    )
    assert result.anomalies == 0
    assert result.missing_standard == 1


def test_duplicate_standard_rejected():
    with pytest.raises(ValueError, match="DUPLICATE_STANDARD"):
        detect_wfs_anomalies(
            [actual()],
            [standard(), standard()],
        )


def test_duplicate_actual_rejected():
    with pytest.raises(ValueError, match="DUPLICATE_ACTUAL"):
        detect_wfs_anomalies(
            [actual(), actual()],
            [standard()],
        )
