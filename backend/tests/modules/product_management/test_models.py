import inspect

from sqlalchemy import UniqueConstraint

import app.modules.product_management.models  # noqa: F401
from app.db.base import Base
from app.modules.product_management.repository import ProductManagementRepository


def test_product_management_tables_use_single_metadata() -> None:
    assert {
        "manual_product_tags",
        "manual_product_tag_assignments",
        "ref_product_pricing_rule_versions",
        "product_pricing_recalculation_runs",
        "dws_product_management_pricing_current",
        "user_table_views",
    } <= set(Base.metadata.tables)
    assert "is_primary" in Base.metadata.tables["product_platform_listings"].c
    pricing = Base.metadata.tables["dws_product_management_pricing_current"].c
    assert {
        "pricing_effective_at",
        "suggested_target_margin_rate",
        "minimum_target_margin_rate",
        "clearance_target_margin_rate",
        "price_currency_code",
    } <= set(pricing.keys())
    rules = Base.metadata.tables["ref_product_pricing_rule_versions"]
    assert {"source_account_ref", "request_id", "action", "status"} <= set(rules.c.keys())
    assert "uq_ref_product_pricing_rule_versions_open_active" in {
        index.name for index in rules.indexes
    }
    runs = Base.metadata.tables["product_pricing_recalculation_runs"]
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in runs.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert (
        "principal_ref",
        "source_account_ref",
        "page_key",
        "capability",
        "mode",
        "idempotency_key",
    ) in unique_columns


def test_repository_does_not_own_transactions_or_external_io() -> None:
    source = inspect.getsource(ProductManagementRepository)
    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "create_engine" not in source
    assert "httpx" not in source
    assert "payload_json" not in source
