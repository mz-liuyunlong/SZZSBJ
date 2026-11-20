"""Synthetic reconciliation tests: no source API calls or database writes."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.modules.integration_sync.anomaly_diagnosis import diagnose_sync_anomaly


def _anomaly(**values: object) -> SimpleNamespace:
    defaults = dict(
        error_code="DATA_PAGES_CONFIRMED_SAMPLE_EXCEEDS_SALESTAT",
        source_account_ref="synthetic",
        business_date=date(2026, 8, 11),
        store_id="store-1",
        item_id="item-1",
        msku="SKU-1",
    )
    return SimpleNamespace(**(defaults | values))


def _facts(
    *,
    zero_orders: int = 4,
    zero_qty: str = "4",
    approved_qty: str = "4",
    approved_amount: str = "51.96",
    sale_qty: str = "2",
    sale_amount: str = "25.98",
    mart_qty: str | None = "4",
    mart_gross: str | None = "2",
    warnings: list[str] | None = None,
) -> tuple[dict[str, object], dict[str, object], dict[str, object] | None]:
    return (
        {
            "zero_orders": zero_orders,
            "zero_qty": Decimal(zero_qty),
            "approved_qty": Decimal(approved_qty),
            "approved_amount": Decimal(approved_amount),
        },
        {
            "facts": 1,
            "qty": Decimal(sale_qty),
            "amount": Decimal(sale_amount),
        },
        None
        if mart_qty is None
        else {
            "sample_qty": Decimal(mart_qty),
            "gross_sales_qty": Decimal(mart_gross or "0"),
            "calculation_warnings_json": warnings or [],
        },
    )


def _diagnose(**overrides: object):
    with patch(
        "app.modules.integration_sync.anomaly_diagnosis._sample_values",
        return_value=_facts(**overrides),
    ) as values:
        outcome = diagnose_sync_anomaly(MagicMock(), _anomaly())
        values.assert_called_once_with(
            values.call_args.args[0],
            "synthetic",
            date(2026, 8, 11),
            "store-1",
            "item-1",
            "SKU-1",
        )
        return outcome


def test_zero_paid_sample_mismatch_does_not_falsely_close() -> None:
    outcome = _diagnose()
    assert outcome.status == "blocked_by_salestat"
    assert outcome.recognized_zero_paid_orders == 4
    assert outcome.approved_sample_qty == "4"
    assert outcome.salestat_qty == "2"
    assert "不能直接" in outcome.explanation


def test_unapproved_zero_paid_orders_are_never_silently_ignored() -> None:
    outcome = _diagnose(approved_qty="2", approved_amount="25.98")
    assert outcome.status == "needs_identity"


def test_missing_order_evidence_is_not_equivalent_to_resolved() -> None:
    outcome = _diagnose(zero_orders=0, zero_qty="0", approved_qty="0", approved_amount="0")
    assert outcome.status == "source_missing"


def test_stale_mart_requests_replay_but_does_not_auto_close() -> None:
    outcome = _diagnose(sale_qty="4", sale_amount="51.96", mart_qty="2")
    assert outcome.status == "ready_for_replay"


def test_verified_facts_require_mart_reconciliation() -> None:
    outcome = _diagnose(sale_qty="4", sale_amount="51.96", mart_gross="4")
    assert outcome.status == "verified"


def test_date_level_anomaly_never_invents_an_order_identity() -> None:
    outcome = diagnose_sync_anomaly(MagicMock(), _anomaly(item_id=None, msku=None))
    assert outcome.status == "manual_review"
    assert outcome.recognized_zero_paid_orders is None


def test_ad_anomaly_is_not_auto_closed_from_sample_logic() -> None:
    outcome = diagnose_sync_anomaly(
        MagicMock(), _anomaly(error_code="FINANCE_SP_SPEND_UNALLOCATED")
    )
    assert outcome.status == "manual_review"
