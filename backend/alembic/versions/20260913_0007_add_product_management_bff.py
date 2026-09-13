"""Add Product Management BFF configuration and pricing projections.

Revision ID: 20260913_0007
Revises: 20260912_0006
Create Date: 2026-09-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260913_0007"
down_revision: str | Sequence[str] | None = "20260912_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_platform_listings",
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index(
        "uq_product_platform_listings_primary_walmart",
        "product_platform_listings",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text(
            "is_primary IS TRUE AND platform = 'walmart' AND deleted_at IS NULL"
        ),
    )

    op.create_table(
        "manual_product_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("color", sa.String(32), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deactivated_by", sa.String(255), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manual_product_tags")),
        sa.UniqueConstraint("tag_key", name=op.f("uq_manual_product_tags_tag_key")),
    )
    op.create_table(
        "manual_product_tag_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_by", sa.String(255), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name=op.f("ck_manual_product_tag_assignments_effective_period"),
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tag_id"], ["manual_product_tags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manual_product_tag_assignments")),
        sa.UniqueConstraint(
            "product_id",
            "tag_id",
            "effective_from",
            name=op.f("uq_manual_product_tag_assignments_product_id"),
        ),
    )
    op.create_index(
        op.f("ix_manual_product_tag_assignments_product_id"),
        "manual_product_tag_assignments",
        ["product_id"],
    )

    op.create_table(
        "ref_product_pricing_rule_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "rule_key",
            sa.String(64),
            server_default=sa.text("'product_management'"),
            nullable=False,
        ),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("wfs_source_url", sa.Text(), nullable=False),
        sa.Column("wfs_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("wfs_confirmed_by", sa.String(255), nullable=False),
        sa.Column("wfs_fulfillment_rates_json", postgresql.JSONB(), nullable=False),
        sa.Column("wfs_storage_rates_json", postgresql.JSONB(), nullable=False),
        sa.Column("identity_wfs_overrides_json", postgresql.JSONB(), nullable=False),
        sa.Column("storage_month_basis_days", sa.Integer(), nullable=False),
        sa.Column("pricing_storage_days", sa.Integer(), nullable=False),
        sa.Column("include_first_leg_fee", sa.Boolean(), nullable=False),
        sa.Column("include_wfs_fulfillment_fee", sa.Boolean(), nullable=False),
        sa.Column("include_storage_fee", sa.Boolean(), nullable=False),
        sa.Column("other_fixed_cost_cny", sa.Numeric(18, 4), nullable=False),
        sa.Column("usd_cny_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("fx_date", sa.Date(), nullable=True),
        sa.Column("fx_source", sa.String(255), nullable=True),
        sa.Column("platform_commission_rate", sa.Numeric(9, 6), nullable=True),
        sa.Column("first_leg_cost_per_kg_cny", sa.Numeric(18, 4), nullable=False),
        sa.Column("suggested_gross_margin_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("minimum_gross_margin_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("clearance_gross_margin_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("roi_base", sa.String(32), nullable=False),
        sa.Column("grade_a_min_margin_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("grade_a_min_roi", sa.Numeric(9, 6), nullable=False),
        sa.Column("grade_b_min_margin_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("grade_b_min_roi", sa.Numeric(9, 6), nullable=False),
        sa.Column("rounding_mode", sa.String(32), server_default=sa.text("'none'"), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("approval_ref", sa.String(255), nullable=False),
        sa.Column("approved_by", sa.String(255), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_ref", sa.String(255), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name=op.f("ck_ref_product_pricing_rule_versions_effective_period"),
        ),
        sa.CheckConstraint(
            "storage_month_basis_days > 0 AND pricing_storage_days >= 0",
            name=op.f("ck_ref_product_pricing_rule_versions_storage_days"),
        ),
        sa.CheckConstraint(
            "other_fixed_cost_cny >= 0",
            name=op.f("ck_ref_product_pricing_rule_versions_other_cost_nonnegative"),
        ),
        sa.CheckConstraint(
            "usd_cny_rate IS NULL OR usd_cny_rate > 0",
            name=op.f("ck_ref_product_pricing_rule_versions_fx_positive"),
        ),
        sa.CheckConstraint(
            "(fx_date IS NULL AND fx_source IS NULL) OR "
            "(fx_date IS NOT NULL AND fx_source IS NOT NULL)",
            name=op.f("ck_ref_product_pricing_rule_versions_fx_pair"),
        ),
        sa.CheckConstraint(
            "platform_commission_rate IS NULL OR "
            "(platform_commission_rate >= 0 AND platform_commission_rate < 1)",
            name=op.f("ck_ref_product_pricing_rule_versions_commission_rate"),
        ),
        sa.CheckConstraint(
            "first_leg_cost_per_kg_cny >= 0",
            name=op.f("ck_ref_product_pricing_rule_versions_first_leg_rate"),
        ),
        sa.CheckConstraint(
            "suggested_gross_margin_rate >= minimum_gross_margin_rate AND "
            "minimum_gross_margin_rate >= clearance_gross_margin_rate",
            name=op.f("ck_ref_product_pricing_rule_versions_margin_order"),
        ),
        sa.CheckConstraint(
            "roi_base IN ('purchase_cost', 'total_cost')",
            name=op.f("ck_ref_product_pricing_rule_versions_roi_base"),
        ),
        sa.CheckConstraint(
            "grade_a_min_margin_rate >= grade_b_min_margin_rate AND "
            "grade_a_min_roi >= grade_b_min_roi",
            name=op.f("ck_ref_product_pricing_rule_versions_grade_threshold_order"),
        ),
        sa.CheckConstraint(
            "rounding_mode = 'none'",
            name=op.f("ck_ref_product_pricing_rule_versions_rounding_mode"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ref_product_pricing_rule_versions")),
        sa.UniqueConstraint(
            "rule_key",
            "source_account_ref",
            "version",
            name=op.f("uq_ref_product_pricing_rule_versions_rule_key"),
        ),
    )
    op.create_index(
        "ix_ref_product_pricing_rule_versions_active_period",
        "ref_product_pricing_rule_versions",
        ["rule_key", "source_account_ref", "is_active", "effective_from"],
    )
    op.create_index(
        "uq_ref_product_pricing_rule_versions_open_active",
        "ref_product_pricing_rule_versions",
        ["rule_key", "source_account_ref"],
        unique=True,
        postgresql_where=sa.text("is_active IS TRUE AND effective_to IS NULL"),
    )

    op.create_table(
        "product_pricing_recalculation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_ref", sa.String(255), nullable=False),
        sa.Column("actor_ref", sa.String(255), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("page_key", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(128), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("selected_count", sa.Integer(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
        sa.Column("affected_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("pricing_rule_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(request_digest) = 64",
            name=op.f("ck_product_pricing_recalculation_runs_request_digest"),
        ),
        sa.CheckConstraint(
            "selected_count >= 0 AND matched_count >= 0 AND eligible_count >= 0 AND "
            "affected_count >= 0 AND skipped_count >= 0 AND failed_count >= 0",
            name=op.f("ck_product_pricing_recalculation_runs_counts_nonnegative"),
        ),
        sa.CheckConstraint(
            "mode IN ('preview', 'execute')",
            name=op.f("ck_product_pricing_recalculation_runs_mode"),
        ),
        sa.CheckConstraint(
            "status IN ('running', 'previewed', 'succeeded', 'partial', 'no_items', 'failed')",
            name=op.f("ck_product_pricing_recalculation_runs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["pricing_rule_version_id"],
            ["ref_product_pricing_rule_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_pricing_recalculation_runs")),
        sa.UniqueConstraint(
            "principal_ref",
            "source_account_ref",
            "page_key",
            "capability",
            "mode",
            "idempotency_key",
            name=op.f("uq_product_pricing_recalculation_runs_principal_ref"),
        ),
    )
    op.create_index(
        "ix_product_pricing_recalculation_runs_status_created",
        "product_pricing_recalculation_runs",
        ["status", "created_at"],
    )

    op.create_table(
        "dws_product_management_pricing_current",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rule_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pricing_effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("calc_version", sa.String(64), nullable=False),
        sa.Column("calculation_status", sa.String(64), nullable=False),
        sa.Column("wfs_calc_status", sa.String(64), nullable=False),
        sa.Column("wfs_calc_reason", sa.String(128), nullable=True),
        sa.Column("wfs_fee_source", sa.String(64), nullable=False),
        sa.Column("wfs_fulfillment_fee_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("wfs_fulfillment_fee_cny", sa.Numeric(18, 4), nullable=True),
        sa.Column("storage_calc_status", sa.String(64), nullable=False),
        sa.Column("package_volume_cuft", sa.Numeric(18, 6), nullable=True),
        sa.Column("daily_storage_fee_per_unit_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("daily_storage_fee_per_unit_cny", sa.Numeric(18, 4), nullable=True),
        sa.Column("estimated_storage_fee_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("estimated_storage_fee_cny", sa.Numeric(18, 4), nullable=True),
        sa.Column("first_leg_calc_status", sa.String(64), nullable=False),
        sa.Column("first_leg_fee_cny", sa.Numeric(18, 4), nullable=True),
        sa.Column("suggested_target_margin_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("minimum_target_margin_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("clearance_target_margin_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("suggested_price_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("minimum_price_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("clearance_price_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column(
            "price_currency_code",
            sa.String(3),
            server_default=sa.text("'USD'"),
            nullable=False,
        ),
        sa.Column("suggested_gross_margin_rate", sa.Numeric(9, 6), nullable=True),
        sa.Column("suggested_roi", sa.Numeric(18, 6), nullable=True),
        sa.Column("product_grade", sa.String(32), nullable=False),
        sa.Column("grade_reason", sa.String(128), nullable=False),
        sa.Column("commission_source", sa.String(32), nullable=False),
        sa.Column("pricing_breakdown_json", postgresql.JSONB(), nullable=False),
        sa.Column("recalculation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recalculation_idempotency_key", sa.String(255), nullable=True),
        sa.Column("recalculation_reason", sa.Text(), nullable=True),
        sa.Column("recalculated_by", sa.String(255), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(input_hash) = 64",
            name=op.f("ck_dws_product_management_pricing_current_input_hash"),
        ),
        sa.CheckConstraint(
            "wfs_fulfillment_fee_usd IS NULL OR wfs_fulfillment_fee_usd >= 0",
            name=op.f("ck_dws_product_management_pricing_current_wfs_fee_usd_nonnegative"),
        ),
        sa.CheckConstraint(
            "wfs_fulfillment_fee_cny IS NULL OR wfs_fulfillment_fee_cny >= 0",
            name=op.f("ck_dws_product_management_pricing_current_wfs_fee_cny_nonnegative"),
        ),
        sa.CheckConstraint(
            "estimated_storage_fee_usd IS NULL OR estimated_storage_fee_usd >= 0",
            name=op.f("ck_dws_product_management_pricing_current_storage_fee_usd_nonnegative"),
        ),
        sa.CheckConstraint(
            "price_currency_code = 'USD'",
            name=op.f("ck_dws_product_management_pricing_current_price_currency_usd"),
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["dwd_lingxing_sku_identity_index.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["dwd_lingxing_sku_product_info_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_version_id"],
            ["ref_product_pricing_rule_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recalculation_run_id"],
            ["product_pricing_recalculation_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dws_product_management_pricing_current")),
        sa.UniqueConstraint(
            "identity_id",
            name=op.f("uq_dws_product_management_pricing_current_identity_id"),
        ),
    )
    op.create_index(
        "ix_dws_product_management_pricing_current_product_id",
        "dws_product_management_pricing_current",
        ["product_id"],
    )
    op.create_index(
        "ix_dws_product_management_pricing_current_recalculation_key",
        "dws_product_management_pricing_current",
        ["recalculation_idempotency_key"],
    )

    op.create_table(
        "user_table_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_ref", sa.String(255), nullable=False),
        sa.Column("page_key", sa.String(64), nullable=False),
        sa.Column("view_key", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("applied_column_keys_json", postgresql.JSONB(), nullable=False),
        sa.Column("column_widths_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("schema_version >= 1", name=op.f("ck_user_table_views_schema_version")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_table_views")),
        sa.UniqueConstraint(
            "principal_ref",
            "page_key",
            "view_key",
            name=op.f("uq_user_table_views_principal_ref"),
        ),
    )


def downgrade() -> None:
    op.drop_table("user_table_views")
    op.drop_index(
        "ix_dws_product_management_pricing_current_recalculation_key",
        table_name="dws_product_management_pricing_current",
    )
    op.drop_index(
        "ix_dws_product_management_pricing_current_product_id",
        table_name="dws_product_management_pricing_current",
    )
    op.drop_table("dws_product_management_pricing_current")
    op.drop_index(
        "ix_product_pricing_recalculation_runs_status_created",
        table_name="product_pricing_recalculation_runs",
    )
    op.drop_table("product_pricing_recalculation_runs")
    op.drop_index(
        "uq_ref_product_pricing_rule_versions_open_active",
        table_name="ref_product_pricing_rule_versions",
    )
    op.drop_index(
        "ix_ref_product_pricing_rule_versions_active_period",
        table_name="ref_product_pricing_rule_versions",
    )
    op.drop_table("ref_product_pricing_rule_versions")
    op.drop_index(
        op.f("ix_manual_product_tag_assignments_product_id"),
        table_name="manual_product_tag_assignments",
    )
    op.drop_table("manual_product_tag_assignments")
    op.drop_table("manual_product_tags")
    op.drop_index(
        "uq_product_platform_listings_primary_walmart",
        table_name="product_platform_listings",
    )
    op.drop_column("product_platform_listings", "is_primary")
