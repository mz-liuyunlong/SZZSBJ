from decimal import Decimal

from app.modules.warehouse_wfs.service import (
    CASE_LABEL_TO_STATUS,
    CASE_STATUS_TO_LABEL,
    map_legacy_status,
    map_priority_by_amount,
)


def test_legacy_status_mapping() -> None:
    assert map_legacy_status("waiting") == "pending_confirm"
    assert map_legacy_status("following") == "following"
    assert map_legacy_status("approving") == "archive_pending"
    assert map_legacy_status("closed") == "archived"
    assert map_legacy_status("done") == "recovered"
    assert map_legacy_status("unknown") == "pending_confirm"


def test_case_label_mapping_is_frontend_compatible() -> None:
    assert CASE_STATUS_TO_LABEL["pending_confirm"] == "未开Case"
    assert CASE_LABEL_TO_STATUS["已开Case"] == "following"
    assert CASE_LABEL_TO_STATUS["跟进中"] == "following"
    assert CASE_LABEL_TO_STATUS["已追回"] == "recovered"


def test_priority_from_amount() -> None:
    assert map_priority_by_amount(Decimal("99.99")) == "low"
    assert map_priority_by_amount(Decimal("100")) == "medium"
    assert map_priority_by_amount(Decimal("500")) == "high"
