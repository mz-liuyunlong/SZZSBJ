"""Add standardized Lingxing SKU DWD tables.

Revision ID: 20260912_0005
Revises: 20260912_0004
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260912_0005"
down_revision: str | Sequence[str] | None = "20260912_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _detail_columns() -> tuple[sa.Column[object], ...]:
    return (
        sa.Column("product_name", sa.String(500), nullable=True),
        sa.Column("lingxing_sku_code", sa.String(255), nullable=True),
        sa.Column("main_image_url", sa.Text(), nullable=True),
        sa.Column("product_developer_name", sa.String(255), nullable=True),
        sa.Column("product_developer_uid", sa.String(255), nullable=True),
        sa.Column("purchase_delivery_days", sa.Integer(), nullable=True),
        sa.Column("purchase_cost_cny", sa.Numeric(18, 4), nullable=True),
        sa.Column("purchase_cost_currency_code", sa.String(3), nullable=True),
        sa.Column("purchase_material", sa.Text(), nullable=True),
        sa.Column("customs_export_name_cn", sa.String(500), nullable=True),
        sa.Column("customs_import_name_en", sa.String(500), nullable=True),
        sa.Column("customs_declared_unit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("customs_declared_currency", sa.String(3), nullable=True),
        sa.Column("china_hs_code", sa.String(64), nullable=True),
        sa.Column("owner_uid", sa.String(255), nullable=True),
        sa.Column("owner_name", sa.String(255), nullable=True),
        sa.Column("clearance_material_cn", sa.Text(), nullable=True),
        sa.Column("clearance_usage_cn", sa.Text(), nullable=True),
        sa.Column("clearance_material_en", sa.Text(), nullable=True),
        sa.Column("us_first_leg_cost", sa.Numeric(18, 4), nullable=True),
        sa.Column("us_first_leg_currency", sa.String(3), nullable=True),
        sa.Column("product_length_cm", sa.Numeric(18, 4), nullable=True),
        sa.Column("product_width_cm", sa.Numeric(18, 4), nullable=True),
        sa.Column("product_height_cm", sa.Numeric(18, 4), nullable=True),
        sa.Column("product_net_weight_g", sa.Numeric(18, 4), nullable=True),
        sa.Column("package_length_cm", sa.Numeric(18, 4), nullable=True),
        sa.Column("package_width_cm", sa.Numeric(18, 4), nullable=True),
        sa.Column("package_height_cm", sa.Numeric(18, 4), nullable=True),
        sa.Column("box_length_cm", sa.Numeric(18, 4), nullable=True),
        sa.Column("box_width_cm", sa.Numeric(18, 4), nullable=True),
        sa.Column("box_height_cm", sa.Numeric(18, 4), nullable=True),
        sa.Column("box_pcs", sa.Integer(), nullable=True),
        sa.Column("product_gross_weight_g", sa.Numeric(18, 4), nullable=True),
        sa.Column("box_weight_kg", sa.Numeric(18, 4), nullable=True),
    )


def _detail_checks(prefix: str) -> tuple[sa.CheckConstraint, ...]:
    names = (
        "purchase_delivery_days",
        "purchase_cost_cny",
        "customs_declared_unit_price",
        "us_first_leg_cost",
        "product_length_cm",
        "product_width_cm",
        "product_height_cm",
        "product_net_weight_g",
        "package_length_cm",
        "package_width_cm",
        "package_height_cm",
        "box_length_cm",
        "box_width_cm",
        "box_height_cm",
        "box_pcs",
        "product_gross_weight_g",
        "box_weight_kg",
    )
    checks = [
        sa.CheckConstraint(
            f"{name} IS NULL OR {name} >= 0",
            name=op.f(f"ck_{prefix}_{name}_nonnegative"),
        )
        for name in names
    ]
    checks.extend(
        (
            sa.CheckConstraint(
                "(purchase_cost_cny IS NULL AND purchase_cost_currency_code IS NULL) OR "
                "(purchase_cost_cny IS NOT NULL AND purchase_cost_currency_code = 'CNY')",
                name=op.f(f"ck_{prefix}_purchase_cost_currency"),
            ),
            sa.CheckConstraint(
                "(us_first_leg_cost IS NULL AND us_first_leg_currency IS NULL) OR "
                "(us_first_leg_cost IS NOT NULL AND us_first_leg_currency IS NOT NULL)",
                name=op.f(f"ck_{prefix}_first_leg_currency"),
            ),
        )
    )
    return tuple(checks)


def upgrade() -> None:
    op.create_table(
        "dwd_lingxing_sku_identity_index",
        _uuid("id"),
        sa.Column("provider", sa.String(32), server_default="lingxing", nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("lingxing_sku_id", sa.String(255), nullable=False),
        sa.Column("lingxing_sku_code", sa.String(255), nullable=True),
        _uuid("product_id", nullable=True),
        sa.Column("mapping_status", sa.String(32), server_default="unmapped", nullable=False),
        sa.Column("mapping_evidence_ref", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        _uuid("first_seen_run_id"),
        _uuid("last_seen_run_id"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inactive_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider = 'lingxing'",
            name=op.f("ck_dwd_lingxing_sku_identity_index_provider_lingxing"),
        ),
        sa.CheckConstraint(
            "mapping_status IN ('unmapped', 'confirmed')",
            name=op.f("ck_dwd_lingxing_sku_identity_index_mapping_status"),
        ),
        sa.CheckConstraint(
            "mapping_status <> 'confirmed' OR "
            "(product_id IS NOT NULL AND mapping_evidence_ref IS NOT NULL)",
            name=op.f("ck_dwd_lingxing_sku_identity_index_confirmed_mapping_evidence"),
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["first_seen_run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dwd_lingxing_sku_identity_index")),
        sa.UniqueConstraint(
            "provider", "source_account_ref", "lingxing_sku_id", name="uq_dwd_lingxing_sku_identity"
        ),
    )
    op.create_table(
        "dwd_lingxing_sku_product_info_snapshots",
        _uuid("id"),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        _uuid("identity_id"),
        sa.Column("lingxing_sku_id", sa.String(255), nullable=False),
        _uuid("source_run_id"),
        _uuid("source_raw_request_ref_id"),
        sa.Column("parser_version", sa.String(64), nullable=False),
        *_detail_columns(),
        sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *_detail_checks("dwd_lingxing_sku_product_info_snapshots"),
        sa.ForeignKeyConstraint(
            ["identity_id"], ["dwd_lingxing_sku_identity_index.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_raw_request_ref_id"], ["ods_api_raw_request_refs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dwd_lingxing_sku_product_info_snapshots")),
        sa.UniqueConstraint(
            "source_run_id",
            "source_account_ref",
            "lingxing_sku_id",
            name="uq_dwd_lingxing_snapshot_run_sku",
        ),
    )
    op.create_table(
        "dwd_lingxing_sku_product_info_current",
        _uuid("id"),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        _uuid("identity_id"),
        sa.Column("lingxing_sku_id", sa.String(255), nullable=False),
        _uuid("source_snapshot_id"),
        _uuid("source_run_id"),
        *_detail_columns(),
        sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *_detail_checks("dwd_lingxing_sku_product_info_current"),
        sa.ForeignKeyConstraint(
            ["identity_id"], ["dwd_lingxing_sku_identity_index.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["dwd_lingxing_sku_product_info_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"], ["gov_integration_sync_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dwd_lingxing_sku_product_info_current")),
        sa.UniqueConstraint(
            "provider", "source_account_ref", "lingxing_sku_id", name="uq_dwd_lingxing_current_sku"
        ),
        sa.UniqueConstraint(
            "source_snapshot_id",
            name=op.f("uq_dwd_lingxing_sku_product_info_current_source_snapshot_id"),
        ),
    )
    op.create_table(
        "dwd_lingxing_sku_product_images",
        _uuid("id"),
        _uuid("source_snapshot_id"),
        _uuid("identity_id"),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("pic_url", sa.Text(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name=op.f("ck_dwd_lingxing_sku_product_images_ordinal")),
        sa.CheckConstraint(
            "pic_url LIKE 'https://%'", name=op.f("ck_dwd_lingxing_sku_product_images_https_url")
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["dwd_lingxing_sku_product_info_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"], ["dwd_lingxing_sku_identity_index.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dwd_lingxing_sku_product_images")),
        sa.UniqueConstraint("source_snapshot_id", "ordinal", name="uq_dwd_lingxing_image_ordinal"),
    )
    op.create_index(
        "uq_dwd_lingxing_sku_images_primary",
        "dwd_lingxing_sku_product_images",
        ["source_snapshot_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )
    op.create_table(
        "dwd_lingxing_sku_global_tags",
        _uuid("id"),
        _uuid("source_snapshot_id"),
        _uuid("identity_id"),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("global_tag_id", sa.String(255), nullable=True),
        sa.Column("tag_name", sa.String(255), nullable=True),
        sa.Column("color", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name=op.f("ck_dwd_lingxing_sku_global_tags_ordinal")),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["dwd_lingxing_sku_product_info_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"], ["dwd_lingxing_sku_identity_index.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dwd_lingxing_sku_global_tags")),
        sa.UniqueConstraint("source_snapshot_id", "ordinal", name="uq_dwd_lingxing_tag_ordinal"),
    )
    op.create_index(
        "uq_dwd_lingxing_sku_tags_external_id",
        "dwd_lingxing_sku_global_tags",
        ["source_snapshot_id", "global_tag_id"],
        unique=True,
        postgresql_where=sa.text("global_tag_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("dwd_lingxing_sku_global_tags")
    op.drop_table("dwd_lingxing_sku_product_images")
    op.drop_table("dwd_lingxing_sku_product_info_current")
    op.drop_table("dwd_lingxing_sku_product_info_snapshots")
    op.drop_table("dwd_lingxing_sku_identity_index")
