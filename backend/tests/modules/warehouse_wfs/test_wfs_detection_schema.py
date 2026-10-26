from pathlib import Path
from typing import cast

from sqlalchemy import Table

from app.modules.integration_sync.models import IntegrationSyncRunWorkItem
from app.modules.warehouse_wfs.models import WalmartWfsFeeActualFact, WfsFeeAnomalyCase


def test_wfs_detection_metadata_keeps_source_identity_and_store_page_scope() -> None:
    actual_table = WalmartWfsFeeActualFact.__table__
    case_table = WfsFeeAnomalyCase.__table__
    work_table = cast(Table, IntegrationSyncRunWorkItem.__table__)

    assert {
        "platform_order_no",
        "sales_num",
        "platform_logistics_amount",
        "settlement_date",
        "source_raw_request_ref_id",
    }.issubset(actual_table.columns.keys())
    assert {
        "valid_sample_units",
        "valid_fee_orders",
        "mode_count",
        "theoretical_overcharge_amount",
        "net_sample_difference_amount",
        "latest_settlement_date",
        "detection_status",
        "data_freshness_status",
        "standard_fee_source",
        "detected_at",
    }.issubset(case_table.columns.keys())
    assert work_table.c.scope_key.nullable is False
    offset_index = next(
        index for index in work_table.indexes if index.name == "uq_gov_sync_work_offset"
    )
    assert [column.name for column in offset_index.columns] == [
        "run_id",
        "request_kind",
        "scope_key",
        "offset_value",
    ]


def test_wfs_migration_is_schema_only_and_reversible() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/20261026_0061_wfs_fee_detection_evidence.py"
    ).read_text()

    assert (
        'down_revision: str | Sequence[str] | None = "20261026_0060_merge_listing_business_heads"'
        in migration
    )
    assert "def upgrade()" in migration
    assert "def downgrade()" in migration
    assert "op.execute" not in migration
    assert "fact_walmart_wfs_fee_actual" in migration
    assert "ops_wfs_fee_anomaly_cases" in migration
