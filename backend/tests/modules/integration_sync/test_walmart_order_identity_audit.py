from datetime import date

from scripts.audit_walmart_order_identity_conflicts import _report


def test_order_identity_audit_report_exposes_only_hashes_counts_and_field_versions() -> None:
    report = _report(
        [
            {
                "source_account_ref": "synthetic-account",
                "store_id": "synthetic-store",
                "source_order_id": "synthetic-order",
                "source_order_line_id": "synthetic-line",
                "business_date": date(2026, 10, 16),
                "physical_versions": 4,
                "current_versions": 1,
                "quantity_versions": 2,
                "amount_versions": 2,
                "item_versions": 1,
                "status_versions": 2,
            }
        ],
        100,
    )

    assert report["write_performed"] is False
    preview = report["preview"]
    assert isinstance(preview, list)
    assert preview == [
        {
            "scope_hash": preview[0]["scope_hash"],
            "business_date": "2026-10-16",
            "physical_versions": 4,
            "current_versions": 1,
            "quantity_versions": 2,
            "amount_versions": 2,
            "item_versions": 1,
            "status_versions": 2,
            "repair_action": "OWNER_REVIEW_REQUIRED_NO_AUTOMATIC_DELETE",
        }
    ]
    serialized = str(report)
    assert "synthetic-account" not in serialized
    assert "synthetic-store" not in serialized
    assert "synthetic-order" not in serialized
    assert "synthetic-line" not in serialized
