"""Account-scope and non-fabrication contract of the real board."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.modules.new_product_workflow.dashboard import read_new_product_dashboard


def test_board_counts_are_generated_only_from_scoped_database_groupings() -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = [
        {"group_type": "purchase_status", "group_name": "pending_market", "product_count": 7},
        {"group_type": "purchase_status", "group_name": "approved_draft", "product_count": 3},
        {"group_type": "tracking_status", "group_name": "observing", "product_count": 3},
        {"group_type": "tracking_status", "group_name": "not_in_pool", "product_count": 7},
        {"group_type": "category", "group_name": "厨房", "product_count": 10},
    ]
    board = read_new_product_dashboard(session, account="account-a")
    statement, params = session.execute.call_args.args
    assert "identity.source_account_ref = :account" in str(statement)
    assert params == {"account": "account-a"}
    assert board["total"] == 10
    assert board["groups"]["category"][0]["name"] == "厨房"
    assert board["formal_grade_distribution"] is None
    assert board["formal_launch_success_rate"] is None
