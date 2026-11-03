"""Static checks for settlement profit V2 storage (PRP §6.2, PR-1). No database needed."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import CheckConstraint, Index, Numeric, String, UniqueConstraint
from sqlalchemy.sql.schema import Table

from app.db.base import Base
from app.modules.finance import settlement_profit_models as m

ODS_TABLES = {
    "ods_lingxing_mp_profit_order_lines",
    "ods_walmart_wfs_fee_detail_lines",
    "ods_walmart_storage_fee_lines",
    "ods_walmart_review_accelerator_snapshots",
}
EXTERNAL_ID_COLUMNS = {
    "store_id",
    "item_id",
    "gtin",
    "platform_order_no",
    "order_item_no",
    "serial_number",
    "report_id",
    "report_key",
    "snapshot_report_key",
    "line_key",
}


def _table(name: str) -> Table:
    return Base.metadata.tables[name]


def _uniques(name: str) -> list[tuple[str, ...]]:
    return [
        tuple(col.name for col in c.columns)
        for c in _table(name).constraints
        if isinstance(c, UniqueConstraint)
    ]


def _index_columns(name: str) -> list[tuple[str, ...]]:
    return [
        tuple(col.name for col in i.columns) for i in _table(name).indexes if isinstance(i, Index)
    ]


def test_all_prp_tables_are_registered_and_no_removed_table_exists() -> None:
    assert set(m.SETTLEMENT_PROFIT_TABLES) <= set(Base.metadata.tables)
    assert len(m.SETTLEMENT_PROFIT_TABLES) == 16
    # Rev 4: no Lingxing WFS cargo list table, no own FX table.  The Lingxing WFS cost
    # valuation ODS belongs to the inventory-claim PRP (ods_lingxing_wfs_cost_valuation_flow).
    assert "ods_lingxing_wfs_cargo_goods" not in Base.metadata.tables
    assert "ods_lingxing_wfs_cost_valuation_lines" not in Base.metadata.tables
    assert "ods_lingxing_wfs_cost_valuation_flow" not in m.SETTLEMENT_PROFIT_TABLES
    assert "cfg_fx_monthly_rate" not in Base.metadata.tables
    assert ODS_TABLES <= set(m.SETTLEMENT_PROFIT_TABLES)


@pytest.mark.parametrize("table_name", m.SETTLEMENT_PROFIT_TABLES)
def test_money_is_numeric_18_4_and_external_ids_are_strings(table_name: str) -> None:
    for column in _table(table_name).columns:
        if column.name in EXTERNAL_ID_COLUMNS:
            assert isinstance(column.type, String), column
        if column.name.endswith(("_usd", "_cny")) or column.name.endswith("_amount"):
            assert isinstance(column.type, Numeric), column
            assert (column.type.precision, column.type.scale) == (18, 4), column


def test_order_line_unique_key_is_line_key_within_calc_version_only() -> None:
    # M1: a sale in period 1 and its refund in period 2 must not collide.
    assert _uniques("fact_settlement_order_lines") == [
        ("store_id", "bill_month", "calc_version", "line_key")
    ]
    assert ("store_id", "bill_month", "platform_order_no", "order_item_no") in _index_columns(
        "fact_settlement_order_lines"
    )
    line_key = _table("fact_settlement_order_lines").c.line_key
    assert not line_key.nullable


def test_order_review_unique_key_and_row_kinds() -> None:
    assert _uniques("mart_settlement_order_review") == [("store_id", "bill_month", "line_key")]
    assert ("store_id", "bill_month", "platform_order_no", "order_item_no") in _index_columns(
        "mart_settlement_order_review"
    )
    assert m.REVIEW_ROW_KINDS == ("order", "unassigned", "reconcile_diff")


@pytest.mark.parametrize(
    ("table_name", "expected"),
    [
        (
            "ods_lingxing_mp_profit_order_lines",
            (
                "source_account_ref",
                "store_id",
                "platform_order_no",
                "order_item_no",
                "transaction_type",
                "settlement_date",
                "source_row_seq",
            ),
        ),
        (
            "ods_walmart_wfs_fee_detail_lines",
            ("source_account_ref", "store_id", "report_id", "line_no"),
        ),
        (
            "ods_walmart_storage_fee_lines",
            (
                "source_account_ref",
                "store_id",
                "report_period_start",
                "report_period_end",
                "gtin",
            ),
        ),
        (
            "ods_walmart_review_accelerator_snapshots",
            ("source_account_ref", "store_id", "snapshot_report_key", "item_id"),
        ),
        ("fact_inventory_movement_lines", ("source_flow_id", "calc_version")),
        (
            "fact_settlement_unassigned_amounts",
            ("store_id", "bill_month", "source_kind", "source_ref"),
        ),
        (
            "fact_settlement_post_close_diffs",
            ("store_id", "bill_month", "line_key", "detected_at"),
        ),
        ("mart_settlement_profit_item_month", ("store_id", "item_id", "bill_month")),
        ("mart_settlement_reconcile_store_month", ("store_id", "bill_month")),
        ("mart_inventory_movement_month", ("store_id", "item_id", "month", "category")),
        ("manual_settlement_month_close", ("store_scope", "bill_month")),
        ("cfg_net_profit_allocation", ("effective_month",)),
    ],
)
def test_prp_identity_keys(table_name: str, expected: tuple[str, ...]) -> None:
    assert expected in _uniques(table_name)


def test_inventory_movement_is_not_keyed_by_serial_number() -> None:
    # Lingxing serial numbers repeat and can change; stores come from store_code mapping.
    assert _uniques("fact_inventory_movement_lines") == [("source_flow_id", "calc_version")]
    table = _table("fact_inventory_movement_lines")
    assert table.c.serial_number.nullable
    assert not table.c.store_code.nullable
    assert table.c.store_id.nullable
    assert not table.foreign_keys  # flow table is owned by the inventory-claim PRP
    assert m.STORE_MAPPING_STATUSES == ("mapped", "unmapped", "manual_assigned")


def test_fx_status_has_no_fallback_state() -> None:
    # Rocky 2026-11-03: no rate -> no conversion; there is no provisional / estimated state.
    assert m.FX_STATUSES == ("final", "missing")
    for name in (
        "fact_settlement_order_lines",
        "fact_inventory_movement_lines",
        "mart_settlement_profit_item_month",
        "mart_settlement_reconcile_store_month",
    ):
        column = _table(name).c.fx_status
        assert column.server_default is not None
        assert "missing" in str(column.server_default.arg)


def test_inventory_categories_mark_vdg_unclassified() -> None:
    assert "unclassified" in m.INVENTORY_CATEGORIES
    assert "supplier" not in m.INVENTORY_CATEGORIES


def test_reserved_columns_are_nullable_and_not_defaulted() -> None:
    table = _table("fact_settlement_order_lines")
    for name in ("promotion_fee_usd", "packaging_fee_usd"):
        assert table.c[name].nullable
        assert table.c[name].server_default is None


def test_manual_tables_carry_full_audit_columns() -> None:
    for name in (
        "manual_settlement_order_adjustments",
        "manual_settlement_review_actions",
        "manual_settlement_month_close",
    ):
        columns = _table(name).c
        for audit in ("actor_id", "actor_role", "acted_at", "request_id", "before", "after"):
            assert audit in columns, (name, audit)
        assert not columns.actor_id.nullable
        assert not columns.request_id.nullable
        assert not columns.idempotency_key.nullable


def test_manual_tables_do_not_reference_raw_ods_or_fact_rows() -> None:
    for name in (
        "manual_settlement_order_adjustments",
        "manual_settlement_review_actions",
        "manual_settlement_month_close",
    ):
        assert not _table(name).foreign_keys


def test_month_columns_require_first_day() -> None:
    for name in m.SETTLEMENT_PROFIT_TABLES:
        for column_name in ("bill_month", "movement_month", "month", "effective_month"):
            if column_name not in _table(name).c:
                continue
            checks = [
                str(c.sqltext) for c in _table(name).constraints if isinstance(c, CheckConstraint)
            ]
            assert f"EXTRACT(DAY FROM {column_name}) = 1" in checks, (name, column_name)


def test_net_profit_config_has_no_hard_coded_people() -> None:
    column = _table("cfg_net_profit_allocation").c.excluded_owner_ids
    assert "[]" in str(column.server_default.arg)
    assert _table("cfg_net_profit_allocation").c.fixed_cny.server_default is not None


def test_python_defaults_build_valid_objects() -> None:
    row = m.SettlementUnassignedAmount(
        line_key="fixture-store|2026-10-01|wfs_service_fee|fixture-ref",
        store_id="fixture-store",
        bill_month=date(2026, 10, 1),
        source_kind="wfs_service_fee",
        source_ref="fixture-ref",
        amount_usd=Decimal("1.0000"),
        calc_version=1,
    )
    assert row.line_key.startswith("fixture-store|")
