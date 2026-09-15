from decimal import Decimal
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
        category=None,
        internal_tag=None,
        product_grade=None,
        calculation_status=None,
        sort_by="sku",
        sort_order="asc",
    )

    statement = session.execute.call_args.args[0]
    sql = str(statement.compile())
    assert rows == []
    assert total == 0
    assert "coalesce(products.sku, dwd_lingxing_sku_identity_index.lingxing_sku_code) IN" in sql
    assert "LIMIT" in sql
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


def test_issue_and_owner_filters_are_applied_server_side() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = 0
    session.execute.return_value.all.return_value = []
    repository = ProductManagementRepository(session)

    repository.list_projections(
        account_refs=frozenset({"synthetic-account"}),
        page=1,
        page_size=50,
        sku=None,
        sku_batch=[],
        product_name=None,
        category=None,
        internal_tag=None,
        product_grade=None,
        calculation_status=None,
        sort_by="sku",
        sort_order="asc",
        owner_uid="owner-1",
        developer_uid="developer-1",
        source_tag="tag-1",
        issue_code="missing_image",
    )

    statement = session.execute.call_args.args[0]
    sql = str(statement.compile())
    assert "owner_uid" in sql
    assert "product_developer_uid" in sql
    assert "dwd_lingxing_sku_global_tags" in sql
    assert "dwd_lingxing_sku_product_images" in sql


def test_summary_uses_filtered_identity_scope_and_persisted_detail_signals() -> None:
    session = MagicMock(spec=Session)
    session.execute.return_value.one.return_value = (
        1188,
        1188,
        Decimal("80.25"),
        1000,
        1188,
        188,
        20,
        25,
        30,
        40,
        45,
        50,
        0,
        1048,
    )
    repository = ProductManagementRepository(session)

    result = repository.summarize_projections(
        account_refs=frozenset({"synthetic-account"}),
        sku="SYNTHETIC",
        sku_batch=[],
        product_name=None,
        category=None,
        internal_tag=None,
        product_grade=None,
        calculation_status=None,
    )

    statement = session.execute.call_args.args[0]
    sql = str(statement.compile())
    assert result == (
        1188,
        1188,
        Decimal("80.25"),
        1000,
        1188,
        188,
        20,
        25,
        30,
        40,
        45,
        50,
        0,
        1048,
    )
    assert "dwd_lingxing_sku_product_info_current" in sql
    assert "dwd_lingxing_sku_product_images" in sql
    assert "dwd_lingxing_sku_global_tags" in sql
    assert "synthetic-account" not in sql
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
