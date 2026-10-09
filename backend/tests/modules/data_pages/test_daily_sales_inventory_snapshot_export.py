from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.modules.data_pages import daily_sales_export
from app.modules.data_pages.repository import DailySalesRepository


class _FakeResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows


class _FakeSession:
    def __init__(self) -> None:
        self.execute_calls: list[object] = []

    def scalar(self, statement: object) -> object:
        return "fact_walmart_listing_inventory_daily"

    def execute(self, statement: object) -> _FakeResult:
        self.execute_calls.append(statement)
        batch_no = len(self.execute_calls)
        return _FakeResult(
            [
                (
                    date(2026, 9, batch_no),
                    "synthetic-account",
                    "store-1",
                    f"item-{batch_no}",
                    Decimal(batch_no),
                )
            ]
        )


def _daily_sales_row(index: int) -> SimpleNamespace:
    return SimpleNamespace(
        business_date_la=date(2026, 9, (index % 30) + 1),
        source_account_ref="synthetic-account",
        store_id=f"store-{index % 7}",
        item_id=f"item-{index}",
    )


def test_daily_sales_inventory_snapshot_map_batches_large_key_sets() -> None:
    session = _FakeSession()
    repository = DailySalesRepository(session)  # type: ignore[arg-type]
    rows = [_daily_sales_row(index) for index in range(1301)]
    rows.extend(
        [
            SimpleNamespace(
                business_date_la=None,
                source_account_ref="synthetic-account",
                store_id="store-1",
                item_id="missing-date",
            ),
            SimpleNamespace(
                business_date_la=date(2026, 9, 1),
                source_account_ref=None,
                store_id="store-1",
                item_id="missing-account",
            ),
            SimpleNamespace(
                business_date_la=date(2026, 9, 1),
                source_account_ref="synthetic-account",
                store_id=None,
                item_id="missing-store",
            ),
            SimpleNamespace(
                business_date_la=date(2026, 9, 1),
                source_account_ref="synthetic-account",
                store_id="store-1",
                item_id=None,
            ),
        ]
    )

    snapshots = repository.daily_sales_inventory_snapshot_map(rows)  # type: ignore[arg-type]

    assert len(session.execute_calls) == 7
    assert snapshots[(date(2026, 9, 1), "synthetic-account", "store-1", "item-1")] == Decimal("1")
    assert snapshots[(date(2026, 9, 7), "synthetic-account", "store-1", "item-7")] == Decimal("7")


def test_daily_sales_export_skips_inventory_snapshot_lookup_when_not_selected(
    monkeypatch,
) -> None:
    class _Repository:
        def daily_sales_inventory_snapshot_map(self, rows: object) -> object:
            raise AssertionError("inventory snapshot lookup should be skipped")

    class _Service:
        repository = _Repository()

    monkeypatch.setattr(
        daily_sales_export,
        "_filtered_daily_sales_rows",
        lambda service, query, account_refs: [],
    )

    csv_content, filename = daily_sales_export.export_daily_sales_csv(
        _Service(),  # type: ignore[arg-type]
        query=SimpleNamespace(
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
        ),
        account_refs=frozenset({"synthetic-account"}),
        period="month",
        dimension="item_id",
        columns="product_id,sales_amount",
    )

    assert "商品ID" in csv_content
    assert "销售额" in csv_content
    assert "WFS历史库存" not in csv_content
    assert filename == "daily-sales-month-item_id-20260901-20260930.csv"
