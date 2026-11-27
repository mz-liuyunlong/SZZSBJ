from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.modules.integration_sync.data_pages_ad_spend_recovery import (
    recover_standard_ad_spend,
)


def _result(value):
    result = Mock()
    result.scalar_one.return_value = value
    result.one.return_value = value
    return result


def test_recovery_updates_daily_and_profit_only_when_totals_agree():
    session = Mock()
    session.execute.side_effect = [
        _result(0),  # no ambiguous Daily Sales business keys
        _result(285),
        _result(6185),
        _result(None),  # update Daily Sales SP spend
        _result(None),  # reconcile Daily Sales profit, margin and ROI
        _result(None),  # roll up SKU-day SP spend and profit
        _result((Decimal("2020.51"), Decimal("2020.51"))),
    ]
    assert recover_standard_ad_spend(session, "account", "2026-10-29") == Decimal("2020.51")
    sql = [str(call.args[0]).lower() for call in session.execute.call_args_list]
    assert len(sql) == 7
    assert "update mart_daily_sales_item_day" in sql[3]
    assert "update mart_daily_sales_item_day" in sql[4]
    assert "gross_profit_amount = e.profit" in sql[4]
    assert "gross_margin = e.margin" in sql[4]
    assert "roi = e.roi" in sql[4]
    assert "update mart_order_profit_sku_day" in sql[5]
    assert "gross_profit_amount = e.profit" in sql[5]
    assert "source_account_ref=:account" in sql[3]
    assert "business_date_la = :day" in sql[5]
    assert "insert into" not in " ".join(sql)
    assert "delete from" not in " ".join(sql)


def test_recovery_refuses_ambiguous_mart_keys():
    session = Mock()
    session.execute.return_value = _result(1)
    with pytest.raises(ValueError, match="DUPLICATE_MART_KEYS"):
        recover_standard_ad_spend(session, "account", "2026-10-29")
    assert session.execute.call_count == 1


def test_recovery_refuses_missing_daily_sales():
    session = Mock()
    session.execute.side_effect = [_result(0), _result(0)]
    with pytest.raises(ValueError, match="MART_MISSING"):
        recover_standard_ad_spend(session, "account", "2026-10-29")
    assert session.execute.call_count == 2


def test_recovery_refuses_inconsistent_profit_rollup():
    session = Mock()
    session.execute.side_effect = [
        _result(0),
        _result(285),
        _result(6185),
        _result(None),  # update Daily Sales SP spend
        _result(None),  # reconcile Daily Sales profit, margin and ROI
        _result(None),  # roll up SKU-day SP spend and profit
        _result((Decimal("2020.51"), Decimal("0"))),
    ]
    with pytest.raises(ValueError, match="PROFIT_ROLLUP_MISMATCH"):
        recover_standard_ad_spend(session, "account", "2026-10-29")


def test_recovery_refuses_missing_source_snapshot():
    session = Mock()
    session.execute.side_effect = [_result(0), _result(285), _result(0)]
    with pytest.raises(ValueError, match="SOURCE_MISSING"):
        recover_standard_ad_spend(session, "account", "2026-10-29")
    assert session.execute.call_count == 3
