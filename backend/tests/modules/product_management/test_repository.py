from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.modules.product_management.repository import ProductManagementRepository


def test_batch_sku_filter_is_applied_in_bounded_repository_query() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = 0
    session.execute.return_value.all.return_value = []
    repository = ProductManagementRepository(session)

    rows, total = repository.list_projections(
        account_refs=frozenset({"synthetic-account"}),
        page=1,
        page_size=20,
        sku=None,
        sku_batch=["Synthetic-A", "Synthetic-b"],
        product_name=None,
        product_grade=None,
        calculation_status=None,
        sort_by="sku",
        sort_order="asc",
    )

    statement = session.execute.call_args.args[0]
    sql = str(statement.compile())
    assert rows == []
    assert total == 0
    assert "products.sku IN" in sql
    assert "LIMIT" in sql
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
