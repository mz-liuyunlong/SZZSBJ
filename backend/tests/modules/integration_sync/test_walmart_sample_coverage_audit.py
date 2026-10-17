from datetime import date
from decimal import Decimal

from scripts.audit_walmart_sample_coverage import _report


def _row(
    *,
    captured: int,
    fact_qty: str,
    mart_qty: str,
) -> dict[str, object]:
    return {
        "day_us": date(2026, 10, 16),
        "source_account_ref": "synthetic",
        "store_id": "store-a",
        "item_id": "item-a",
        "msku": "msku-a",
        "gross_qty": Decimal("3"),
        "sample_captured": captured,
        "sample_qty": Decimal(fact_qty),
        "mart_sample_qty": Decimal(mart_qty),
    }


def test_missing_samples_are_unknown_not_confirmed_zero() -> None:
    report = _report([_row(captured=0, fact_qty="0", mart_qty="0")], limit=50)

    assert report["status_counts"] == {"SAMPLE_NOT_OBSERVED_UNKNOWN_NOT_ZERO": 1}
    assert report["sample_findings"][0]["captured_sample_lines"] == 0
    assert "store-a" not in str(report)
    assert "item-a" not in str(report)


def test_sample_mart_mismatch_is_flagged() -> None:
    report = _report([_row(captured=1, fact_qty="2", mart_qty="0")], limit=50)

    assert report["status_counts"] == {"SAMPLE_FACT_MART_MISMATCH": 1}
    assert report["sample_findings"][0]["valid_sample_qty"] == "2"
    assert report["sample_findings"][0]["mart_sample_qty"] == "0"


def test_matching_persisted_samples_are_not_exported_as_findings() -> None:
    report = _report([_row(captured=2, fact_qty="2", mart_qty="2")], limit=50)

    assert report["status_counts"] == {"MATCHES_PERSISTED_SAMPLE_FACT": 1}
    assert report["sample_findings"] == []
    assert report["truncated"] is False
