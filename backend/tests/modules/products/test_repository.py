from unittest.mock import MagicMock
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.sql import ClauseElement

from app.modules.products.models import Product
from app.modules.products.repository import ProductRepository

PRODUCT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _sql(statement: ClauseElement) -> str:
    return str(statement.compile())


def test_product_list_uses_scoped_filters_soft_delete_and_stable_order() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = 2
    session.scalars.return_value.all.return_value = []
    repository = ProductRepository(session)

    products, total = repository.list_products(
        page=2,
        page_size=20,
        sku="SKU",
        product_name="Synthetic",
        platform="walmart",
        store_name="Synthetic Store",
        msku="MSKU",
    )

    count_sql = _sql(session.scalar.call_args.args[0])
    list_sql = _sql(session.scalars.call_args.args[0])
    assert products == []
    assert total == 2
    assert "products.deleted_at IS NULL" in count_sql
    assert "EXISTS" in count_sql
    assert "product_platform_listings.deleted_at IS NULL" in count_sql
    assert "ORDER BY products.sku ASC, products.id ASC" in list_sql
    assert "LIMIT" in list_sql and "OFFSET" in list_sql
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


def test_listing_list_uses_product_boundary_and_stable_order() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = 0
    session.scalars.return_value.all.return_value = []
    repository = ProductRepository(session)

    repository.list_listings(product_id=PRODUCT_ID, page=1, page_size=20)

    list_sql = _sql(session.scalars.call_args.args[0])
    assert "product_platform_listings.product_id" in list_sql
    assert "product_platform_listings.deleted_at IS NULL" in list_sql
    assert (
        "ORDER BY product_platform_listings.platform ASC, "
        "product_platform_listings.store_name ASC, "
        "product_platform_listings.msku ASC, "
        "product_platform_listings.id ASC"
    ) in list_sql


def test_repository_flushes_but_never_owns_transaction() -> None:
    session = MagicMock(spec=Session)
    repository = ProductRepository(session)
    product = Product(sku="SKU-SYNTHETIC", product_name="Synthetic Product")

    repository.add_product(product)
    repository.update_product(product, {"product_name": "Updated Synthetic Product"})

    session.add.assert_called_once_with(product)
    assert session.flush.call_count == 2
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
