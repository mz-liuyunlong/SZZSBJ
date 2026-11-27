"""结算利润 V3 建表（PR-1）的静态检查：不连数据库。"""

from __future__ import annotations

import ast
from pathlib import Path

from sqlalchemy import CheckConstraint, Index, Numeric, String, UniqueConstraint
from sqlalchemy.sql.schema import Table

import app.modules.settlement_profit.models as m
from app.db.base import Base

BACKEND_ROOT = Path(__file__).resolve().parents[3]
REVISION = "20261125_0096_settlement_profit_v3_tables"
MIGRATION = BACKEND_ROOT / "alembic" / "versions" / f"{REVISION}.py"
# 0101 给 manual_settlement_review_actions 补了 Idempotency-Key 索引（#373 复审 P2-4）
ORDER_REVIEW_MIGRATION = (
    BACKEND_ROOT / "alembic" / "versions" / "20261127_0101_finance_order_review_permissions.py"
)

# PRP §6.2 的 18 张表与各自的业务键
PRP_KEYS: dict[str, tuple[str, ...]] = {
    "ods_lingxing_fin_shipping_lists": ("source_account_ref", "store_id", "shipping_list_code"),
    "ods_lingxing_fin_shipping_detail_items": ("source_account_ref", "shipping_list_code", "msku"),
    "ods_lingxing_fin_wms_outbound_orders": ("source_account_ref", "store_id", "outbound_order_no"),
    "ods_walmart_review_accelerator_snapshots": (
        "source_account_ref",
        "store_id",
        "snapshot_date",
        "item_id",
    ),
    "fact_settlement_order_lines": ("store_id", "period_key", "calc_version", "line_key"),
    "fact_settlement_store_month_items": ("store_id", "bill_month", "source_kind", "source_ref"),
    "fact_settlement_post_close_diffs": ("store_id", "bill_month", "line_key", "detected_at"),
    "mart_settlement_profit_item_month": ("store_id", "item_id", "bill_month"),
    "mart_settlement_order_review": ("store_id", "period_key", "line_key"),
    "mart_settlement_reconcile_store_period": ("store_id", "period_key"),
    "mart_settlement_no_order_flags": ("store_id", "item_id", "bill_month"),
    "manual_settlement_sem_month": ("store_id", "item_id", "bill_month"),
    "manual_settlement_month_close": ("store_id", "bill_month", "seq"),
    "cfg_finance_settlement_settings": ("setting_key", "effective_month"),
    "cfg_finance_owner_tag_rules": ("tag_name",),
}
ID_KEYED = {
    "manual_settlement_cost_entries",
    "manual_settlement_order_adjustments",
    "manual_settlement_review_actions",
}
EXTERNAL_ID_COLUMNS = {
    "store_id",
    "item_id",
    "gtin",
    "platform_order_no",
    "order_line_no",
    "shipping_list_code",
    "outbound_order_no",
    "period_key",
    "line_key",
    "logistics_provider_id",
}
# 已取消的 v2 表（库存归仓库板块、待指定并入店铺级项目、纯利设置并入设置表）
REMOVED_V2_TABLES = {
    "fact_inventory_movement_lines",
    "fact_settlement_unassigned_amounts",
    "mart_inventory_movement_month",
    "cfg_net_profit_allocation",
}


def _table(name: str) -> Table:
    return Base.metadata.tables[name]


def _uniques(table: Table) -> list[tuple[str, ...]]:
    return [
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    ]


def _checks(table: Table) -> dict[str, str]:
    return {
        str(constraint.name): str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def test_exactly_the_eighteen_prp_tables_are_registered() -> None:
    assert len(m.SETTLEMENT_PROFIT_TABLES) == 18
    assert set(m.SETTLEMENT_PROFIT_TABLES) == set(PRP_KEYS) | ID_KEYED
    assert set(m.SETTLEMENT_PROFIT_TABLES) <= set(Base.metadata.tables)
    assert not REMOVED_V2_TABLES & set(Base.metadata.tables)
    # 成本计价 flow 归库存索赔 PRP（#308），财务不建；不与 PMC #282 的快照表同名
    assert "ods_lingxing_wfs_cost_valuation_flow" not in m.SETTLEMENT_PROFIT_TABLES
    assert "ods_lingxing_wfs_shipping_lists" not in m.SETTLEMENT_PROFIT_TABLES


def test_business_keys_match_prp() -> None:
    for name, key in PRP_KEYS.items():
        assert key in _uniques(_table(name)), name
    for name in ID_KEYED:
        assert [column.name for column in _table(name).primary_key.columns] == ["id"]


def test_money_is_numeric_18_4_and_fx_rate_18_8() -> None:
    for name in m.SETTLEMENT_PROFIT_TABLES:
        for column in _table(name).columns:
            if column.name.endswith(("_usd", "_cny")) or column.name in {
                "purchase_price",
                "head_stock_price",
                "per_firstlet_cost",
                "per_tax",
                "wfs_stock_price",
                "logistics_fee",
            }:
                assert isinstance(column.type, Numeric), (name, column.name)
                assert (column.type.precision, column.type.scale) == (18, 4), (name, column.name)
            if column.name == "fx_rate":
                assert (column.type.precision, column.type.scale) == (18, 8), name


def test_external_ids_are_strings() -> None:
    for name in m.SETTLEMENT_PROFIT_TABLES:
        for column in _table(name).columns:
            if column.name in EXTERNAL_ID_COLUMNS:
                assert isinstance(column.type, String), (name, column.name)


def test_every_month_column_is_checked_to_be_first_day() -> None:
    for name in m.SETTLEMENT_PROFIT_TABLES:
        table = _table(name)
        for month in ("bill_month", "effective_month"):
            if month in table.columns:
                assert any(
                    f"EXTRACT(DAY FROM {month}) = 1" in text for text in _checks(table).values()
                ), (name, month)


def test_fact_and_mart_rows_carry_calc_version_hash_and_freeze() -> None:
    # fact_settlement_post_close_diffs 不带冻结列：它本身就是结账后才写的差异记录，
    # 只增不改，记录的是冻结版本号 frozen_calc_version 与新版本号，自己不会被“冻结”。
    for name in m.SETTLEMENT_PROFIT_TABLES:
        if not name.startswith(("fact_", "mart_")) or name == "fact_settlement_post_close_diffs":
            continue
        columns = _table(name).columns
        for column in (
            "calc_version",
            "content_hash",
            "frozen_at",
            "frozen_by",
            "frozen_calc_version",
        ):
            assert column in columns, (name, column)
    diffs = _table("fact_settlement_post_close_diffs").columns
    assert "frozen_calc_version" in diffs and not diffs["frozen_calc_version"].nullable


def test_fx_columns_and_missing_status_without_fallback() -> None:
    for name in (
        "fact_settlement_order_lines",
        "fact_settlement_store_month_items",
        "mart_settlement_profit_item_month",
    ):
        table = _table(name)
        assert {"fx_rate", "fx_month", "fx_status"} <= set(table.columns.keys())
        assert table.columns["fx_rate"].nullable  # missing 时留空，不兜底
        checks = _checks(table)
        assert "fx_status IN ('final', 'missing')" in checks["fx_status"]
        assert checks["fx_rate_matches_status"] == "(fx_status = 'final') = (fx_rate IS NOT NULL)"


def test_reason_and_status_vocabularies_match_prp() -> None:
    assert len(m.ORDER_LINE_REASONS) + len(m.STORE_ITEM_REASONS) == 9
    # §0.5 六项 + §8.3 WFS 承运商清单，正好 7 项
    assert set(m.SETTING_KEYS) == {
        "review_accelerator_price_formula",
        "company_cost_allocation",
        "fixed_cost_fallback",
        "review_accelerator_snapshot_frequency",
        "no_order_months",
        "bill_month_cutoff_day",
        "wfs_carrier_provider_ids",
    }
    assert len(m.SETTING_KEYS) == 7
    review = _checks(_table("mart_settlement_order_review"))
    assert "row_kind IN ('order', 'store_item', 'reconcile_diff')" in review["row_kind"]
    kinds = _checks(_table("fact_settlement_store_month_items"))["source_kind"]
    assert "'unassigned_bill'" in kinds and "'unassigned_wfs'" in kinds


def test_cost_entry_scope_rules() -> None:
    table = _table("manual_settlement_cost_entries")
    checks = _checks(table)
    assert (
        "num_nonnulls(shipping_list_code, outbound_order_no, platform_order_no) = 1"
        in checks["one_scope"]
    )
    assert "override" in checks["override_reason"]
    active = next(
        index
        for index in table.indexes
        if isinstance(index, Index) and index.name == "uq_manual_settlement_cost_entry_active"
    )
    assert active.unique
    assert [column.name for column in active.columns] == ["store_id", "msku", "scope_ref"]
    assert "revoked" in str(active.dialect_options["postgresql"]["where"])
    assert "'shipping:' || shipping_list_code" in checks["scope_ref_matches"]
    assert "'outbound:' || outbound_order_no" in checks["scope_ref_matches"]
    assert "'order:' || platform_order_no" in checks["scope_ref_matches"]  # 迁移 0101


def test_one_current_version_per_order_line() -> None:
    table = _table("fact_settlement_order_lines")
    current = next(
        index for index in table.indexes if index.name == "uq_fact_settlement_order_line_current"
    )
    assert current.unique
    assert [column.name for column in current.columns] == ["store_id", "period_key", "line_key"]
    assert str(current.dialect_options["postgresql"]["where"]) == "is_current"


def test_line_keys_fit_the_longest_business_key() -> None:
    # 店铺 32 + reportKey 64 + 订单号 64 + 订单行号 32 + GTIN 64 + 分隔符，约 260
    for name in m.SETTLEMENT_PROFIT_TABLES:
        columns = _table(name).columns
        if "line_key" in columns:
            assert columns["line_key"].type.length == 320, name


def test_quantities_do_not_reuse_the_money_type() -> None:
    assert m.QTY is not m.MONEY
    for name, column in (
        ("ods_lingxing_fin_shipping_detail_items", "delivery_num"),
        ("fact_settlement_order_lines", "quantity"),
        ("mart_settlement_profit_item_month", "quantity"),
        ("mart_settlement_no_order_flags", "wfs_inventory_qty"),
    ):
        assert _table(name).columns[column].type is m.QTY, (name, column)


def test_index_count_matches_migration() -> None:
    orm = sum(len(_table(name).indexes) for name in m.SETTLEMENT_PROFIT_TABLES)
    source = MIGRATION.read_text(encoding="utf-8")
    later = ORDER_REVIEW_MIGRATION.read_text(encoding="utf-8")
    assert orm == 16
    assert source.count("op.create_index(") == 15
    assert source.count("op.drop_index(") == 15
    assert later.count("op.create_index(") == 1
    assert later.count("op.drop_index(") == 1


def test_manual_tables_reference_line_key_not_uuid() -> None:
    for name in ("manual_settlement_order_adjustments", "manual_settlement_review_actions"):
        columns = _table(name).columns
        assert "line_key" in columns and not columns["line_key"].nullable
        assert not [fk for fk in _table(name).foreign_keys]


def test_no_foreign_keys_into_raw_ods_or_fact_from_manual() -> None:
    for name in m.SETTLEMENT_PROFIT_TABLES:
        assert not _table(name).foreign_keys, name


def test_migration_only_creates_and_guards_its_own_tables() -> None:
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    created: list[str] = []
    dropped: list[str] = []
    others: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "op"):
            continue
        name = node.func.attr
        if name == "create_table":
            created.append(ast.literal_eval(node.args[0]))
        elif name == "drop_table":
            dropped.append(ast.literal_eval(node.args[0]))
        elif name not in {"create_index", "drop_index", "f", "get_bind"}:
            others.append(name)
    assert sorted(created) == sorted(m.SETTLEMENT_PROFIT_TABLES)
    assert sorted(dropped) == sorted(created)
    assert others == []
    source = MIGRATION.read_text(encoding="utf-8")
    downgrade = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "downgrade"
    )
    code = (ast.get_source_segment(source, downgrade) or "").upper()
    # 回滚只在全部表都没有数据时才执行，有一条记录就拒绝，不做 DELETE / TRUNCATE（PRP §13）
    assert "ROLLBACK BLOCKED" in code
    assert "DELETE" not in code
    assert "TRUNCATE" not in code
