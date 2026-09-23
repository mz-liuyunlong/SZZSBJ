from datetime import date
from decimal import Decimal

from app.modules.after_sales.repository import split_csv
from app.modules.after_sales.schemas import RefundItemQuery
from app.modules.after_sales.service import _change_rate, _date_axis, _rate


def test_rate_is_percentage() -> None:
    assert _rate(Decimal("40"), Decimal("800")) == Decimal("5.0000")


def test_rate_is_none_without_denominator() -> None:
    assert _rate(Decimal("40"), Decimal("0")) is None


def test_change_rate_is_none_without_previous_value() -> None:
    assert _change_rate(Decimal("35"), Decimal("0")) is None


def test_date_axis_is_inclusive() -> None:
    assert _date_axis(date(2026, 9, 1), date(2026, 9, 3)) == [
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
    ]


def test_split_csv_trims_and_drops_blanks() -> None:
    assert split_csv(" a, b ,,c ") == ["a", "b", "c"]


def test_refund_item_query_accepts_shared_table_max_page_size() -> None:
    query = RefundItemQuery(
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1),
        page_size=1000,
    )
    assert query.page_size == 1000
