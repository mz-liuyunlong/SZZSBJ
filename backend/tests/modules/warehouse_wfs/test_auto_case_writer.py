from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.modules.warehouse_wfs.anomaly_detection import WfsAnomalyCandidate
from app.modules.warehouse_wfs.auto_case_writer import (
    WfsCaseWriteError,
    build_wfs_case_insert,
    create_wfs_case,
)


def candidate():
    return WfsAnomalyCandidate(
        source_account_ref="primary",
        store_id="110704872940532224",
        msku="YC00115-1A",
        actual_unit_fee=Decimal("6.95"),
        standard_unit_fee=Decimal("6.55"),
        unit_overcharge=Decimal("0.40"),
        sample_units=Decimal("62"),
        sample_orders=54,
        estimated_sample_overcharge=Decimal("24.80"),
        standard_source="product_management_live",
        rule_version="current",
    )


def test_insert_only_with_unique_identity():
    statement = build_wfs_case_insert(
        item_id="20500114893",
        candidate=candidate(),
    )
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "ON CONFLICT" in sql
    assert "DO NOTHING" in sql
    assert "DO UPDATE" not in sql
    assert "RETURNING" in sql


def test_case_values_protect_claim_and_history():
    statement = build_wfs_case_insert(
        item_id="20500114893",
        candidate=candidate(),
    )
    values = {
        column.key: value.value
        for column, value in statement._values.items()
    }

    assert values["source_kind"] == "future_lingxing_profit_order"
    assert values["status"] == "pending_confirm"
    assert values["manual_unit_fee"] == Decimal("6.55")
    assert values["actual_unit_fee"] == Decimal("6.95")
    assert values["unit_fee_diff"] == Decimal("0.40")
    assert values["affected_units"] == 0
    assert values["estimated_recover_amount"] == 0
    assert values["claim_amount"] is None


def test_dry_run_never_accesses_database():
    session = MagicMock()
    result = create_wfs_case(
        session,
        item_id="20500114893",
        candidate=candidate(),
    )
    assert result.action == "dry_run"
    session.execute.assert_not_called()
    session.commit.assert_not_called()
    session.flush.assert_not_called()


def test_execute_true_still_blocked():
    session = MagicMock()
    with pytest.raises(
        WfsCaseWriteError,
        match="WFS_CASE_EXECUTION_NOT_ENABLED",
    ):
        create_wfs_case(
            session,
            item_id="20500114893",
            candidate=candidate(),
            execute=True,
        )
    session.execute.assert_not_called()


def test_missing_item_id_rejected():
    with pytest.raises(WfsCaseWriteError):
        build_wfs_case_insert(item_id="", candidate=candidate())
