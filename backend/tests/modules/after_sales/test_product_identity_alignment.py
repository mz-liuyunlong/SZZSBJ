from datetime import date
from typing import Any

from app.modules.after_sales.repository import AfterSalesRefundRepository
from app.modules.after_sales.schemas import RefundBaseQuery, RefundItemQuery


class _MappingsResult:
    def mappings(self) -> "_MappingsResult":
        return self

    def all(self) -> list[dict[str, Any]]:
        return []


class _CaptureSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def execute(self, statement: Any, params: dict[str, object]) -> _MappingsResult:
        self.calls.append((statement.text, params))
        return _MappingsResult()


def _query() -> RefundBaseQuery:
    return RefundBaseQuery(
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
    )


def test_product_risk_sales_join_uses_store_item_msku_and_same_date_window() -> None:
    session = _CaptureSession()
    repository = AfterSalesRefundRepository(session)  # type: ignore[arg-type]

    repository.product_summary(_query(), frozenset({"primary"}), limit=20)

    sql, params = session.calls[0]
    assert "group by m.store_id, m.item_id, m.msku" in sql
    assert "s.store_id = r.store_id" in sql
    assert "s.item_id = r.item_id" in sql
    assert "s.msku = r.msku" in sql
    assert "m.business_date_la between :sales_start_date and :sales_end_date" in sql
    assert params["start_date"] == date(2026, 9, 1)
    assert params["end_date"] == date(2026, 9, 30)
    assert params["sales_start_date"] == date(2026, 9, 1)
    assert params["sales_end_date"] == date(2026, 9, 30)


def test_product_risk_one_day_uses_same_one_day_sales_window() -> None:
    session = _CaptureSession()
    repository = AfterSalesRefundRepository(session)  # type: ignore[arg-type]
    query = RefundBaseQuery(
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1),
    )

    repository.product_summary(query, frozenset({"primary"}), limit=20)

    _, params = session.calls[0]
    assert params["start_date"] == date(2026, 9, 1)
    assert params["end_date"] == date(2026, 9, 1)
    assert params["sales_start_date"] == date(2026, 9, 1)
    assert params["sales_end_date"] == date(2026, 9, 1)


def test_selected_product_sales_filter_uses_composite_identity() -> None:
    session = _CaptureSession()
    repository = AfterSalesRefundRepository(session)  # type: ignore[arg-type]
    product_key = '["store-a", "item-a", "msku-a"]'

    where, params = repository._sales_where(  # noqa: SLF001
        _query(),
        frozenset({"primary"}),
        product_key=product_key,
    )

    sql = " and ".join(where)
    assert "json_build_array(coalesce(m.store_id,''), coalesce(m.item_id,'')" in sql
    assert "coalesce(m.msku,''))::text = :product_key" in sql
    assert params["product_key"] == product_key


def test_item_drilldown_accepts_exact_product_key() -> None:
    session = _CaptureSession()
    repository = AfterSalesRefundRepository(session)  # type: ignore[arg-type]
    product_key = '["store-a", "item-a", "msku-a"]'
    query = RefundItemQuery(
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1),
        product_key=product_key,
    )

    where, params = repository._refund_where(  # noqa: SLF001
        query,
        frozenset({"primary"}),
    )

    sql = " and ".join(where)
    assert "json_build_array(coalesce(r.store_id,''), coalesce(r.item_id,'')" in sql
    assert "coalesce(r.msku,''))::text = :product_key" in sql
    assert params["product_key"] == product_key

def test_refund_window_uses_governed_refund_effective_date() -> None:
    session = _CaptureSession()
    repository = AfterSalesRefundRepository(session)  # type: ignore[arg-type]

    where, _ = repository._refund_where(  # noqa: SLF001
        _query(),
        frozenset({"primary"}),
    )

    sql = " and ".join(where)
    assert "r.refund_effective_date is not null" in sql
    assert "r.refund_effective_date between :start_date and :end_date" in sql
    assert "r.return_order_at::date between" not in sql
