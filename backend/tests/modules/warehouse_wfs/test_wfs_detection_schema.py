from pathlib import Path
from typing import cast
from decimal import Decimal

import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock

from sqlalchemy import Table

from app.modules.integration_sync.models import IntegrationSyncRunWorkItem
from app.modules.warehouse_wfs.models import (
    WalmartWfsFeeActualFact,
    WfsFeeAnomalyCase,
    WfsFeeDetectionEvidence,
    WfsSettlementCollection,
)
from app.modules.warehouse_wfs.schemas import WfsFeeRecoveredWrite
from app.modules.warehouse_wfs.service import WfsFeeAlertService


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
    assert {
        "missing_store_count",
        "wfs_scope_status",
        "verified_count",
    }.issubset(WfsSettlementCollection.__table__.columns.keys())
    assert {
        "sales_coverage_start_date",
        "sales_coverage_end_date",
        "sales_source_watermark",
        "fee_scope_status",
    }.issubset(WfsFeeDetectionEvidence.__table__.columns.keys())
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


def test_latest_evidence_projection_does_not_label_review_states_current() -> None:
    projection = " ".join(WfsFeeAlertService(MagicMock())._case_select_sql().split())

    assert "evidence_status = 'STALE' then 'stale'" in projection
    assert "evidence_status = 'FUTURE_EVIDENCE' then 'invalid'" in projection
    assert "evidence_status = 'OVERCHARGE_CANDIDATE' then 'current'" in projection
    assert "detected_at is not null then 'review_required'" in projection


def test_recovered_amount_must_be_positive_and_cents_precision() -> None:
    assert WfsFeeRecoveredWrite(recovered_amount="0.01").recovered_amount == Decimal("0.01")
    with pytest.raises(ValidationError):
        WfsFeeRecoveredWrite(recovered_amount="0")
    with pytest.raises(ValidationError):
        WfsFeeRecoveredWrite(recovered_amount="-1")
    with pytest.raises(ValidationError):
        WfsFeeRecoveredWrite(recovered_amount="1.234")
