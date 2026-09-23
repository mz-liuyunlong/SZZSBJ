from datetime import date
from typing import Any

from app.modules.after_sales.repository import AfterSalesRefundRepository
from app.modules.after_sales.schemas import RefundBaseQuery


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


def _query(**overrides: str) -> RefundBaseQuery:
    return RefundBaseQuery(
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        **overrides,
    )


def test_reason_and_responsibility_filters_use_manual_override_first() -> None:
    repository = AfterSalesRefundRepository(_CaptureSession())  # type: ignore[arg-type]
    where, params = repository._refund_where(  # noqa: SLF001
        _query(reason="PRODUCT_DEFECTIVE", responsibility="PRODUCT"),
        frozenset({"primary"}),
    )
    sql = " and ".join(where)

    assert "manual_reason_code" in sql
    assert "normalized_reason_code" in sql
    assert "manual_responsibility_code" in sql
    assert "responsibility_code" in sql
    assert params["reasons"] == ["PRODUCT_DEFECTIVE"]
    assert params["responsibilities"] == ["PRODUCT"]


def test_product_summary_ranks_dominant_reason_by_refund_quantity() -> None:
    session = _CaptureSession()
    repository = AfterSalesRefundRepository(session)  # type: ignore[arg-type]
    repository.product_summary(_query(), frozenset({"primary"}), limit=20)

    sql, _ = session.calls[0]
    assert "reason_rank as" in sql
    assert "responsibility_rank as" in sql
    assert "order by" in sql
    assert "sum(return_qty) desc" in sql
    assert "rr.rank_no = 1" in sql
    assert "rp.rank_no = 1" in sql
    assert "after_sales_reason_dict" in sql
    assert "after_sales_responsibility_dict" in sql
