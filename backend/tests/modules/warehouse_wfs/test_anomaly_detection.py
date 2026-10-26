from datetime import date
from decimal import Decimal

import pytest

from app.modules.warehouse_wfs.anomaly_detection import (
    WfsSalesEvidence,
    WfsStandardFee,
    detect_wfs_anomalies,
)
from app.modules.warehouse_wfs.fee_detection import ResolvedOrderFeeSample, ResolvedWfsFee


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


def test_three_amounts_are_distinct_and_order_evidenced() -> None:
    actual_fee = ResolvedWfsFee(
        source_account_ref="account-a",
        store_id="store-a",
        msku="SKU-TEST",
        unit_fee=Decimal("6.95"),
        sample_units=Decimal("87"),
        fee_orders=87,
        mode_count=38,
        skipped_no_qty=0,
        order_samples=(
            *(
                ResolvedOrderFeeSample(
                    platform_order_no=f"low-{index}",
                    unit_fee=Decimal("6.26"),
                    sales_units=Decimal("1"),
                    settlement_date=date(2026, 9, 1),
                )
                for index in range(49)
            ),
            *(
                ResolvedOrderFeeSample(
                    platform_order_no=f"high-{index}",
                    unit_fee=Decimal("6.95"),
                    sales_units=Decimal("1"),
                    settlement_date=date(2026, 9, 23),
                )
                for index in range(38)
            ),
        ),
        latest_settlement_date=date(2026, 9, 23),
    )
    result = detect_wfs_anomalies(
        [actual_fee],
        [standard(fee="6.55")],
        {
            ("account-a", "store-a", "SKU-TEST"): WfsSalesEvidence(
                historical_units=Decimal("87"),
                sales_start_date=date(2026, 7, 3),
                sales_end_date=date(2026, 9, 22),
                coverage_status="complete",
            )
        },
        as_of=date(2026, 9, 30),
    )
    candidate = result.candidates[0]
    assert candidate.legacy_estimated_overcharge == Decimal("34.80")
    assert candidate.theoretical_overcharge == Decimal("15.20")
    assert candidate.net_sample_difference == Decimal("0.99")
    assert candidate.case_eligible is True


def test_unconfirmed_default_standard_requires_review() -> None:
    actual_fee = ResolvedWfsFee(
        source_account_ref="account-a",
        store_id="store-a",
        msku="SKU-TEST",
        unit_fee=Decimal("6.95"),
        sample_units=Decimal("10"),
        fee_orders=10,
        mode_count=10,
        skipped_no_qty=0,
        latest_settlement_date=date(2026, 10, 16),
    )
    default_standard = WfsStandardFee(
        source_account_ref="account-a",
        store_id="store-a",
        msku="SKU-TEST",
        unit_fee=Decimal("6.55"),
        source="product_management_default_unconfirmed",
        rule_version="sku-pricing-defaults-v1",
    )

    result = detect_wfs_anomalies(
        [actual_fee],
        [default_standard],
        {
            ("account-a", "store-a", "SKU-TEST"): WfsSalesEvidence(
                historical_units=Decimal("87"),
                sales_start_date=date(2026, 7, 3),
                sales_end_date=date(2026, 9, 22),
                coverage_status="complete",
            )
        },
        as_of=date(2026, 10, 17),
    )

    assert result.candidates[0].evidence_status == "REVIEW_REQUIRED"
    assert result.candidates[0].case_eligible is False
