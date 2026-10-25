"""Structural regression tests to run inside the real SZZSBJ backend environment."""

from sqlalchemy import UniqueConstraint
from sqlalchemy.sql.sqltypes import Text

import app.modules.keyword_planning.models  # noqa: F401
import app.modules.products.models  # noqa: F401 - register existing FK roots
from app.db.base import Base

CORE = {
    "raw_kw_upload_file",
    "raw_kw_upload_row",
    "raw_kw_walmart_page_snapshot",
    "raw_kw_asin_snapshot",
    "raw_kw_asin_image",
    "ai_kw_product_fact_snapshot",
    "dim_kw_term",
    "biz_sku_keyword",
    "biz_kw_market_observation",
    "biz_kw_source_event",
    "biz_sku_asin_reference",
    "ai_kw_rule_set",
    "ai_kw_rule_version",
    "ai_kw_analysis_run",
    "ai_kw_run_file",
    "ai_kw_run_asin",
    "ai_kw_run_keyword",
    "ai_kw_listing_version",
    "ai_kw_export_file",
    "biz_kw_decision_history",
    "ai_kw_rule_evaluation",
}


def unique_sets(table_name: str) -> set[frozenset[str]]:
    table = Base.metadata.tables[table_name]
    return {
        frozenset(c.name for c in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_all_21_keyword_tables_register_and_fk_sort() -> None:
    assert CORE.issubset(Base.metadata.tables.keys())
    assert sum(name in Base.metadata.tables for name in CORE) == 21
    assert CORE.issubset(t.name for t in Base.metadata.sorted_tables)


def test_original_upload_is_never_unique_by_content_hash() -> None:
    assert frozenset({"sha256"}) not in unique_sets("raw_kw_upload_file")
    assert frozenset({"upload_id", "sheet_name", "row_number"}) in unique_sets("raw_kw_upload_row")
    assert frozenset({"keyword_normalized"}) not in unique_sets("raw_kw_upload_row")


def test_one_sku_keyword_and_one_run_keyword_are_unique() -> None:
    assert frozenset({"product_id", "term_id"}) in unique_sets("biz_sku_keyword")
    assert frozenset({"normalized_keyword"}) in unique_sets("dim_kw_term")
    assert frozenset({"run_id", "term_id"}) in unique_sets("ai_kw_run_keyword")


def test_images_keep_all_source_positions_and_unlimited_url_text() -> None:
    table = Base.metadata.tables["raw_kw_asin_image"]
    assert isinstance(table.c.image_url.type, Text)
    assert frozenset({"asin_snapshot_id", "image_index"}) in unique_sets("raw_kw_asin_image")
    assert frozenset({"asin_snapshot_id", "image_url"}) not in unique_sets("raw_kw_asin_image")


def test_scoped_analysis_inputs_use_composite_fks() -> None:
    for table in ("ai_kw_run_file", "ai_kw_run_asin", "ai_kw_run_keyword"):
        assert any(
            {"source_account_ref", "run_id"}.issubset(set(x.parent.name for x in fk.elements))
            for fk in Base.metadata.tables[table].foreign_key_constraints
        )
