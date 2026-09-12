"""Add governed ODS storage, parsing, and lineage tables.

Revision ID: 20260912_0004
Revises: 20260912_0003
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260912_0004"
down_revision: str | Sequence[str] | None = "20260912_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "ods_api_raw_blobs",
        _uuid("id"),
        sa.Column("response_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=True),
        sa.Column("payload_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("storage_mode", sa.String(16), nullable=False),
        sa.Column("archive_uri", sa.Text(), nullable=True),
        _uuid("retention_policy_id"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(response_hash) = 64", name=op.f("ck_ods_api_raw_blobs_response_hash")
        ),
        sa.CheckConstraint("payload_bytes >= 0", name=op.f("ck_ods_api_raw_blobs_payload_bytes")),
        sa.CheckConstraint(
            "storage_mode IN ('database', 'archive')",
            name=op.f("ck_ods_api_raw_blobs_storage_mode"),
        ),
        sa.CheckConstraint(
            "(storage_mode = 'database' AND payload_json IS NOT NULL) OR "
            "(storage_mode = 'archive' AND archive_uri IS NOT NULL)",
            name=op.f("ck_ods_api_raw_blobs_storage_payload"),
        ),
        sa.ForeignKeyConstraint(
            ["retention_policy_id"], ["gov_raw_retention_policies.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ods_api_raw_blobs")),
        sa.UniqueConstraint("response_hash", name=op.f("uq_ods_api_raw_blobs_response_hash")),
    )
    op.create_table(
        "ods_api_raw_request_refs",
        _uuid("id"),
        _uuid("run_id"),
        _uuid("work_item_id"),
        _uuid("raw_blob_id"),
        sa.Column("request_kind", sa.String(32), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("request_safe_params", postgresql.JSONB(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("provider_code", sa.String(64), nullable=True),
        sa.Column("is_success", sa.Boolean(), nullable=False),
        sa.Column("response_count", sa.Integer(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "request_kind IN ('offset_page', 'id_batch_page')",
            name=op.f("ck_ods_api_raw_request_refs_request_kind"),
        ),
        sa.CheckConstraint("attempt_no >= 1", name=op.f("ck_ods_api_raw_request_refs_attempt_no")),
        sa.CheckConstraint(
            "response_count IS NULL OR response_count >= 0",
            name=op.f("ck_ods_api_raw_request_refs_response_count"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["work_item_id"], ["gov_integration_sync_run_work_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["raw_blob_id"], ["ods_api_raw_blobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ods_api_raw_request_refs")),
        sa.UniqueConstraint("work_item_id", "attempt_no", name="uq_ods_raw_ref_attempt"),
    )
    op.create_table(
        "ods_lingxing_productlist_sku_refs",
        _uuid("id"),
        _uuid("run_id"),
        _uuid("raw_request_ref_id"),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("lingxing_sku_id", sa.String(255), nullable=False),
        sa.Column("source_item_ordinal", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(trim(lingxing_sku_id)) > 0",
            name=op.f("ck_ods_lingxing_productlist_sku_refs_nonblank_sku_id"),
        ),
        sa.CheckConstraint(
            "source_item_ordinal >= 0",
            name=op.f("ck_ods_lingxing_productlist_sku_refs_source_item_ordinal"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["raw_request_ref_id"], ["ods_api_raw_request_refs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ods_lingxing_productlist_sku_refs")),
        sa.UniqueConstraint(
            "raw_request_ref_id", "source_item_ordinal", name="uq_ods_productlist_ref_ordinal"
        ),
        sa.UniqueConstraint(
            "run_id", "source_account_ref", "lingxing_sku_id", name="uq_ods_productlist_run_sku"
        ),
    )
    op.create_table(
        "ods_lingxing_product_info_batch_items",
        _uuid("id"),
        _uuid("run_id"),
        _uuid("work_item_id"),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("batch_no", sa.Integer(), nullable=False),
        sa.Column("item_ordinal", sa.Integer(), nullable=False),
        sa.Column("lingxing_sku_id", sa.String(255), nullable=False),
        _uuid("raw_request_ref_id", nullable=True),
        sa.Column("item_status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "item_status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')",
            name=op.f("ck_ods_lingxing_product_info_batch_items_item_status"),
        ),
        sa.CheckConstraint(
            "batch_no > 0 AND item_ordinal >= 0",
            name=op.f("ck_ods_lingxing_product_info_batch_items_batch_ordinal"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["work_item_id"], ["gov_integration_sync_run_work_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["raw_request_ref_id"], ["ods_api_raw_request_refs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ods_lingxing_product_info_batch_items")),
        sa.UniqueConstraint(
            "run_id", "source_account_ref", "lingxing_sku_id", name="uq_ods_product_info_batch_sku"
        ),
        sa.UniqueConstraint(
            "work_item_id", "item_ordinal", name="uq_ods_product_info_batch_ordinal"
        ),
    )
    op.create_table(
        "gov_parse_jobs",
        _uuid("id"),
        _uuid("run_id"),
        _uuid("raw_request_ref_id"),
        sa.Column("parser_key", sa.String(128), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("target_layer", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("records_seen", sa.Integer(), nullable=False),
        sa.Column("records_written", sa.Integer(), nullable=False),
        sa.Column("records_rejected", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')",
            name=op.f("ck_gov_parse_jobs_status"),
        ),
        sa.CheckConstraint("target_layer = 'DWD'", name=op.f("ck_gov_parse_jobs_target_layer")),
        sa.CheckConstraint(
            "records_seen >= 0 AND records_written >= 0 AND records_rejected >= 0",
            name=op.f("ck_gov_parse_jobs_nonnegative_counters"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["raw_request_ref_id"], ["ods_api_raw_request_refs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gov_parse_jobs")),
        sa.UniqueConstraint(
            "raw_request_ref_id", "parser_key", "parser_version", name="uq_gov_parse_job_version"
        ),
    )
    op.create_table(
        "gov_data_lineage",
        _uuid("id"),
        _uuid("run_id"),
        _uuid("parse_job_id", nullable=True),
        _uuid("raw_request_ref_id"),
        _uuid("raw_blob_id"),
        sa.Column("source_path", sa.String(512), nullable=False),
        sa.Column("target_table", sa.String(128), nullable=False),
        sa.Column("target_record_id", sa.String(128), nullable=False),
        sa.Column("target_field", sa.String(128), nullable=False),
        sa.Column("transform_key", sa.String(128), nullable=False),
        sa.Column("transform_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parse_job_id"], ["gov_parse_jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["raw_request_ref_id"], ["ods_api_raw_request_refs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["raw_blob_id"], ["ods_api_raw_blobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gov_data_lineage")),
        sa.UniqueConstraint(
            "raw_request_ref_id",
            "target_table",
            "target_record_id",
            "target_field",
            "source_path",
            "transform_version",
            name="uq_gov_data_lineage_target",
        ),
    )


def downgrade() -> None:
    op.drop_table("gov_data_lineage")
    op.drop_table("gov_parse_jobs")
    op.drop_table("ods_lingxing_product_info_batch_items")
    op.drop_table("ods_lingxing_productlist_sku_refs")
    op.drop_table("ods_api_raw_request_refs")
    op.drop_table("ods_api_raw_blobs")
