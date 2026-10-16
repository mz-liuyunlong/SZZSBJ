"""Regression tests for Listing Management's authoritative SKU owner attribution."""

from unittest.mock import MagicMock
from uuid import uuid4

from app.modules.operation_plans.repository import OperationPlanRepository
from app.modules.operation_plans.schemas import OperationPlanProductQuery


def _repository() -> tuple[OperationPlanRepository, MagicMock]:
    session = MagicMock()
    # The inventory helper may return its empty CTE in tests without a database.
    session.execute.return_value.scalar_one.return_value = 0
    session.execute.return_value.mappings.return_value = []
    return OperationPlanRepository(session), session


def _statements(session: MagicMock) -> list[str]:
    return [str(call.args[0]) for call in session.execute.call_args_list]


def test_owner_lookup_matches_listing_management_account_and_sku_relation() -> None:
    repository, _ = _repository()
    sql = repository._listing_owner_cte_sql()
    assert "from dwd_lingxing_sku_product_info_current" in sql
    assert "from mart_listing_management_current l" in sql
    assert "ol.source_account_ref = l.source_account_ref" in sql
    assert "ol.lingxing_sku_code = l.local_sku" in sql
    assert "l.source_account_ref in :account_refs" in sql
    assert "coalesce(" in sql
    assert "ol.owner_name, nullif(btrim(l.owner_ref), ''), ol.owner_uid" in sql
    assert "p.period_id = :period_id" in sql


def test_conflicting_or_incomplete_sku_owners_are_not_arbitrarily_assigned() -> None:
    repository, _ = _repository()
    sql = repository._listing_owner_cte_sql()
    assert "count(distinct owner_ref) > 1" in sql
    assert "ol.owner_count > 1" in sql
    assert "then 'owner_conflict'" in sql
    assert "then '负责人冲突'" in sql
    assert sql.count("when count(owner_ref) = 0") == 2
    assert "count(owner_ref) <> count(*)" not in sql
    # MAX is only used when exactly one distinct owner ref remains.
    assert "else coalesce(max(owner_ref), 'unassigned')" in sql


def test_single_known_owner_survives_other_listing_rows_without_owner() -> None:
    repository, _ = _repository()
    sql = repository._listing_owner_cte_sql()

    # A blank Listing SKU must not remove the sole owner of the same Item ID.
    # This guards the 59 previously unresolved item-level plans, including
    # 31 previously assigned plans that became unassigned in the first fix.
    assert sql.count("when count(owner_ref) = 0") == 2
    assert "count(owner_ref) <> count(*)" not in sql
    assert "when bool_or(owner_ambiguous)" in sql
    assert "or count(distinct owner_ref) > 1" in sql
    assert "else coalesce(max(owner_ref), 'unassigned')" in sql
    assert "else coalesce(max(owner_name), max(owner_ref), '未分配')" in sql


def test_plan_import_auto_resolves_owner_without_owner_file_column() -> None:
    repository, session = _repository()
    repository.table_exists = lambda _: True  # type: ignore[method-assign]
    repository.table_columns = lambda _: {  # type: ignore[method-assign]
        "platform_code",
        "source_account_ref",
        "store_id",
        "store_name",
        "item_id",
        "local_sku",
        "msku",
        "local_name",
    }
    session.execute.return_value.mappings.return_value = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = {
        "item_id": "synthetic-item",
        "owner_ref": "synthetic-owner",
        "owner_name": "synthetic-name",
        "platform_code": "walmart",
    }

    row = repository.resolve_listing_by_item_id(
        item_id="synthetic-item",
        account_refs=frozenset({"synthetic-account"}),
    )

    assert row is not None
    assert row["owner_ref"] == "synthetic-owner"
    sql = _statements(session)[-1]
    assert "with " in sql
    assert "listing_item_owners as (" in sql
    assert "(select owner_ref from listing_item_owners where item_id = :item_id)" in sql
    assert "(select owner_name from listing_item_owners where item_id = :item_id)" in sql
    assert "and trim(l.item_id::text) = :item_id" in sql


def test_plan_list_filter_and_row_share_live_listing_owner() -> None:
    repository, session = _repository()
    repository.list_products(
        period_id=uuid4(),
        query=OperationPlanProductQuery(
            period_key="2026-10",
            owner_ref="synthetic-owner",
        ),
        account_refs=frozenset({"synthetic-account"}),
    )

    statements = [sql for sql in _statements(session) if "listing_item_owners as (" in sql]
    assert len(statements) == 2
    for sql in statements:
        assert "coalesce(li.owner_ref, 'unassigned') = :owner_ref" in sql
        assert "left join listing_item_owners li" in sql
        assert "nullif(p.owner_ref, '')" not in sql
    assert "coalesce(li.owner_ref, 'unassigned') as resolved_owner_ref" in statements[1]
    assert "coalesce(li.owner_name, '未分配') as resolved_owner_name" in statements[1]


def test_dashboard_and_owner_options_share_current_listing_owner() -> None:
    repository, session = _repository()
    repository.owner_summary(period_id=uuid4(), account_refs=frozenset({"synthetic-account"}))
    repository.list_options(period_id=uuid4(), account_refs=frozenset({"synthetic-account"}))
    sqls = [sql for sql in _statements(session) if "listing_item_owners as (" in sql]
    assert len(sqls) == 2
    for sql in sqls:
        assert "left join listing_item_owners li" in sql
        assert "nullif(p.owner_ref, '')" not in sql
        assert "ol.lingxing_sku_code = l.local_sku" in sql
    assert "coalesce(li.owner_ref, 'unassigned') as owner_ref" in sqls[0]
    assert "coalesce(li.owner_ref, 'unassigned') as owner_value" in sqls[1]
    assert "group by owner_ref" in sqls[0]
    assert "group by owner_value" in sqls[1]
