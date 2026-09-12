"""Add integration governance control-plane tables.

Revision ID: 20260912_0003
Revises: 20260910_0002
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260912_0003"
down_revision: str | Sequence[str] | None = "20260910_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "gov_integration_interfaces",
        _uuid("id"),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("interface_key", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("endpoint_path", sa.Text(), nullable=False),
        sa.Column("request_kind", sa.String(32), nullable=False),
        sa.Column("handler_key", sa.String(128), nullable=False),
        sa.Column("contract_version", sa.String(64), nullable=False),
        sa.Column("outbound_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "method = 'POST'", name=op.f("ck_gov_integration_interfaces_method_post")
        ),
        sa.CheckConstraint(
            "request_kind IN ('offset_page', 'id_batch_page')",
            name=op.f("ck_gov_integration_interfaces_request_kind"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gov_integration_interfaces")),
        sa.UniqueConstraint(
            "provider", "interface_key", name=op.f("uq_gov_integration_interfaces_provider")
        ),
        sa.UniqueConstraint(
            "provider", "method", "endpoint_path", name="uq_gov_interface_endpoint"
        ),
    )
    op.create_table(
        "gov_integration_interface_dependencies",
        _uuid("id"),
        _uuid("source_interface_id"),
        _uuid("target_interface_id"),
        sa.Column("dependency_key", sa.String(128), nullable=False),
        sa.Column("dependency_type", sa.String(64), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_interface_id <> target_interface_id",
            name=op.f("ck_gov_integration_interface_dependencies_different_interfaces"),
        ),
        sa.CheckConstraint(
            "dependency_type = 'requires_sku_ids'",
            name=op.f("ck_gov_integration_interface_dependencies_dependency_type"),
        ),
        sa.ForeignKeyConstraint(
            ["source_interface_id"], ["gov_integration_interfaces.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_interface_id"], ["gov_integration_interfaces.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gov_integration_interface_dependencies")),
        sa.UniqueConstraint(
            "source_interface_id",
            "target_interface_id",
            "dependency_type",
            "dependency_key",
            name="uq_gov_interface_dependency",
        ),
    )
    op.create_table(
        "gov_raw_retention_policies",
        _uuid("id"),
        sa.Column("policy_key", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("interface_key", sa.String(128), nullable=True),
        sa.Column("hot_retention_days", sa.Integer(), nullable=False),
        sa.Column("archive_after_days", sa.Integer(), nullable=True),
        sa.Column("delete_after_days", sa.Integer(), nullable=True),
        sa.Column("archive_required", sa.Boolean(), nullable=False),
        sa.Column("legal_hold", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "hot_retention_days >= 0", name=op.f("ck_gov_raw_retention_policies_hot_retention_days")
        ),
        sa.CheckConstraint(
            "archive_after_days IS NULL OR archive_after_days >= 0",
            name=op.f("ck_gov_raw_retention_policies_archive_days"),
        ),
        sa.CheckConstraint(
            "delete_after_days IS NULL OR delete_after_days >= 0",
            name=op.f("ck_gov_raw_retention_policies_delete_days"),
        ),
        sa.CheckConstraint(
            "delete_after_days IS NULL OR archive_after_days IS NULL "
            "OR delete_after_days >= archive_after_days",
            name=op.f("ck_gov_raw_retention_policies_delete_after_archive"),
        ),
        sa.CheckConstraint(
            "NOT archive_required OR archive_after_days IS NOT NULL",
            name=op.f("ck_gov_raw_retention_policies_archive_required_threshold"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gov_raw_retention_policies")),
        sa.UniqueConstraint("policy_key", name=op.f("uq_gov_raw_retention_policies_policy_key")),
    )
    op.create_index(
        "uq_gov_raw_retention_policy_scope",
        "gov_raw_retention_policies",
        [sa.text("coalesce(provider, '')"), sa.text("coalesce(interface_key, '')")],
        unique=True,
    )
    op.create_table(
        "gov_integration_sync_configs",
        _uuid("id"),
        _uuid("interface_id"),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("schedule_enabled", sa.Boolean(), nullable=False),
        sa.Column("schedule_cron", sa.String(128), nullable=True),
        sa.Column("schedule_timezone", sa.String(64), server_default="UTC", nullable=False),
        sa.Column("page_size", sa.Integer(), nullable=True),
        sa.Column("batch_size", sa.Integer(), nullable=True),
        sa.Column("max_pages", sa.Integer(), nullable=True),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        _uuid("retention_policy_id", nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "page_size IS NULL OR page_size BETWEEN 1 AND 10000",
            name=op.f("ck_gov_integration_sync_configs_page_size"),
        ),
        sa.CheckConstraint(
            "batch_size IS NULL OR batch_size BETWEEN 1 AND 10000",
            name=op.f("ck_gov_integration_sync_configs_batch_size"),
        ),
        sa.CheckConstraint(
            "max_pages IS NULL OR max_pages BETWEEN 1 AND 10000",
            name=op.f("ck_gov_integration_sync_configs_max_pages"),
        ),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 10",
            name=op.f("ck_gov_integration_sync_configs_max_attempts"),
        ),
        sa.CheckConstraint(
            "NOT schedule_enabled OR (schedule_cron IS NOT NULL AND schedule_timezone = 'UTC')",
            name=op.f("ck_gov_integration_sync_configs_schedule_contract"),
        ),
        sa.ForeignKeyConstraint(
            ["interface_id"], ["gov_integration_interfaces.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["retention_policy_id"], ["gov_raw_retention_policies.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gov_integration_sync_configs")),
        sa.UniqueConstraint(
            "interface_id", "source_account_ref", name="uq_gov_sync_config_account"
        ),
    )
    op.create_table(
        "gov_integration_sync_runs",
        _uuid("id"),
        _uuid("config_id", nullable=True),
        _uuid("interface_id"),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("interface_key", sa.String(128), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("trigger_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        _uuid("parent_run_id", nullable=True),
        _uuid("retry_of_run_id", nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("work_items_total", sa.Integer(), nullable=False),
        sa.Column("work_items_succeeded", sa.Integer(), nullable=False),
        sa.Column("work_items_failed", sa.Integer(), nullable=False),
        sa.Column("records_seen", sa.Integer(), nullable=False),
        sa.Column("records_written", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "trigger_type IN ('manual', 'schedule', 'retry', 'backfill', 'import')",
            name=op.f("ck_gov_integration_sync_runs_trigger_type"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')",
            name=op.f("ck_gov_integration_sync_runs_status"),
        ),
        sa.CheckConstraint(
            "work_items_total >= 0 AND work_items_succeeded >= 0 "
            "AND work_items_failed >= 0 AND records_seen >= 0 AND records_written >= 0",
            name=op.f("ck_gov_integration_sync_runs_nonnegative_counters"),
        ),
        sa.CheckConstraint(
            "window_end IS NULL OR window_start IS NULL OR window_end >= window_start",
            name=op.f("ck_gov_integration_sync_runs_window_order"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name=op.f("ck_gov_integration_sync_runs_execution_time_order"),
        ),
        sa.ForeignKeyConstraint(
            ["config_id"], ["gov_integration_sync_configs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["interface_id"], ["gov_integration_interfaces.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["parent_run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["retry_of_run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gov_integration_sync_runs")),
        sa.UniqueConstraint(
            "idempotency_key", name=op.f("uq_gov_integration_sync_runs_idempotency_key")
        ),
    )
    op.create_index(
        "uq_gov_integration_sync_runs_running",
        "gov_integration_sync_runs",
        ["provider", "interface_key"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "gov_integration_sync_run_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        _uuid("run_id"),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=True),
        sa.Column("message_code", sa.String(128), nullable=False),
        sa.Column("safe_details", postgresql.JSONB(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_ref", sa.String(255), nullable=True),
        sa.CheckConstraint(
            "from_status IS NULL OR from_status IN "
            "('queued', 'running', 'succeeded', 'failed', 'canceled')",
            name=op.f("ck_gov_integration_sync_run_events_from_status"),
        ),
        sa.CheckConstraint(
            "to_status IS NULL OR to_status IN "
            "('queued', 'running', 'succeeded', 'failed', 'canceled')",
            name=op.f("ck_gov_integration_sync_run_events_to_status"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gov_integration_sync_run_events")),
        sa.UniqueConstraint("run_id", "sequence_no", name="uq_gov_sync_run_event_sequence"),
    )
    op.create_table(
        "gov_integration_sync_locks",
        _uuid("id"),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("interface_key", sa.String(128), nullable=False),
        _uuid("run_id"),
        sa.Column("lock_token_hash", sa.String(64), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(lock_token_hash) = 64",
            name=op.f("ck_gov_integration_sync_locks_token_hash"),
        ),
        sa.CheckConstraint(
            "expires_at > acquired_at", name=op.f("ck_gov_integration_sync_locks_lease_time_order")
        ),
        sa.ForeignKeyConstraint(["run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gov_integration_sync_locks")),
        sa.UniqueConstraint("provider", "interface_key", name="uq_gov_sync_lock_interface"),
        sa.UniqueConstraint("run_id", name=op.f("uq_gov_integration_sync_locks_run_id")),
    )
    op.create_table(
        "gov_integration_sync_run_work_items",
        _uuid("id"),
        _uuid("run_id"),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("request_kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("offset_value", sa.Integer(), nullable=True),
        sa.Column("length_value", sa.Integer(), nullable=True),
        sa.Column("batch_no", sa.Integer(), nullable=True),
        sa.Column("id_count", sa.Integer(), nullable=True),
        sa.Column("id_hash", sa.String(64), nullable=True),
        sa.Column("request_safe_params", postgresql.JSONB(), nullable=False),
        sa.Column("response_count", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "request_kind IN ('offset_page', 'id_batch_page')",
            name=op.f("ck_gov_integration_sync_run_work_items_request_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')",
            name=op.f("ck_gov_integration_sync_run_work_items_status"),
        ),
        sa.CheckConstraint(
            "ordinal >= 1 AND attempt_count >= 0",
            name=op.f("ck_gov_integration_sync_run_work_items_positive_order_attempt"),
        ),
        sa.CheckConstraint(
            "response_count IS NULL OR response_count >= 0",
            name=op.f("ck_gov_integration_sync_run_work_items_response_count"),
        ),
        sa.CheckConstraint(
            "(request_kind = 'offset_page' AND offset_value IS NOT NULL "
            "AND length_value > 0 AND batch_no IS NULL AND id_count IS NULL "
            "AND id_hash IS NULL) OR (request_kind = 'id_batch_page' "
            "AND offset_value IS NULL AND length_value IS NULL AND batch_no > 0 "
            "AND id_count > 0 AND char_length(id_hash) = 64)",
            name=op.f("ck_gov_integration_sync_run_work_items_request_kind_columns"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gov_integration_sync_run_work_items")),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_gov_sync_work_ordinal"),
    )
    op.create_index(
        "uq_gov_sync_work_offset",
        "gov_integration_sync_run_work_items",
        ["run_id", "request_kind", "offset_value"],
        unique=True,
        postgresql_where=sa.text("request_kind = 'offset_page'"),
    )
    op.create_index(
        "uq_gov_sync_work_batch",
        "gov_integration_sync_run_work_items",
        ["run_id", "request_kind", "batch_no"],
        unique=True,
        postgresql_where=sa.text("request_kind = 'id_batch_page'"),
    )


def downgrade() -> None:
    op.drop_table("gov_integration_sync_run_work_items")
    op.drop_table("gov_integration_sync_locks")
    op.drop_table("gov_integration_sync_run_events")
    op.drop_table("gov_integration_sync_runs")
    op.drop_table("gov_integration_sync_configs")
    op.drop_index("uq_gov_raw_retention_policy_scope", table_name="gov_raw_retention_policies")
    op.drop_table("gov_raw_retention_policies")
    op.drop_table("gov_integration_interface_dependencies")
    op.drop_table("gov_integration_interfaces")
