from datetime import date
from decimal import Decimal

import pytest

from scripts.audit_walmart_sem_attribution import _report


def _row(status: str, spend: str, campaign: str = "123") -> dict:
    return {
        "business_date": date(2026, 8, 4),
        "store_id": "synthetic-store",
        "campaign_id": campaign,
        "campaign_name": "synthetic campaign",
        "attribution_status": status,
        "spend_usd": Decimal(spend),
        "listing_matches": 0 if status == "ITEM_ID_UNRESOLVED" else 1,
    }


def test_unallocated_campaigns_keep_money_and_redact_identifiers() -> None:
    result = _report(
        [
            _row("ITEM_ID_UNRESOLVED", "8.35"),
            _row("ONE_LISTING_MATCH", "4.00", "456"),
        ],
        limit=10,
    )
    assert result["campaign_rows"] == 2
    assert result["total_spend_usd"] == "12.35"
    assert result["unallocated_spend_usd"] == "8.35"
    assert result["by_status"]["ITEM_ID_UNRESOLVED"]["campaign_rows"] == 1
    assert result["write_performed"] is False
    assert result["ownership_verification"] == "NOT_PROVEN_BY_CSV"
    assert "synthetic-store" not in str(result)
    assert "synthetic campaign" not in str(result)


def test_unallocated_report_limit_does_not_hide_aggregate_total() -> None:
    result = _report([_row("ITEM_ID_UNRESOLVED", "0.01", str(n)) for n in range(6)], 2)
    assert len(result["findings"]) == 2
    assert result["truncated"] is True
    assert result["unallocated_spend_usd"] == "0.06"


def test_negative_credit_is_not_silently_mixed_into_positive_spend() -> None:
    with pytest.raises(ValueError, match="Negative SEM credit"):
        _report([_row("ITEM_ID_UNRESOLVED", "-1.00")], 10)
