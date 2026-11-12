"""PR337: persist performance, tracking, staged purchase dates and review records.

Data-only schema: no backfill, scheduler, write triggers or business status changes.
Requires the existing PR337 0087 migration; reconcile revision IDs before main merge.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261112_0088_new_product_tracking_foundation"
down_revision: str | Sequence[str] | None = "20261112_0087_new_product_performance"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(20, 4)
RATIO = sa.Numeric(12, 6)
QTY = sa.Numeric(16, 4)


def uid():
    return sa.Column("id", sa.Uuid(), primary_key=True)


def created():
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def updated():
    return sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def registry_fk(*, primary_key=False, nullable=False):
    return sa.Column(
        "registry_id",
        sa.Uuid(),
        sa.ForeignKey("biz_new_product_registry.id", ondelete="RESTRICT"),
        primary_key=primary_key,
        nullable=False if primary_key else nullable,
    )


def jsoncol(name, *, nullable=True):
    return sa.Column(name, postgresql.JSONB(), nullable=nullable)


def upgrade() -> None:
    # The registry is a point-in-time reference to an existing listing, NOT a
    # second authoritative listing/product catalog. Only verified tag matches
    # may be enrolled by future service logic.
    op.create_table(
        "biz_new_product_registry",
        uid(),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column(
            "listing_source_tag",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'小批量测品'"),
        ),
        sa.Column(
            "is_currently_tagged", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("image_url", sa.Text()),
        sa.Column("product_name", sa.Text()),
        sa.Column("sku", sa.String(128)),
        sa.Column("msku", sa.String(128)),
        sa.Column("store_name", sa.String(255)),
        sa.Column("owner_name", sa.String(255)),
        sa.Column("category_l1", sa.Text()),
        sa.Column("category_l2", sa.Text()),
        sa.Column("listing_date_la", sa.Date()),
        sa.Column(
            "first_detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_source_seen_at", sa.DateTime(timezone=True)),
        created(),
        updated(),
        sa.UniqueConstraint(
            "source_account_ref", "store_id", "item_id", name="uq_np_registry_identity"
        ),
    )
    op.create_index(
        "ix_np_registry_store", "biz_new_product_registry", ["source_account_ref", "store_id"]
    )
    op.create_index(
        "ix_np_registry_owner", "biz_new_product_registry", ["source_account_ref", "owner_name"]
    )

    op.create_table(
        "biz_new_product_performance_current",
        registry_fk(primary_key=True),
        sa.Column("listing_date_la", sa.Date()),
        sa.Column("first_wfs_available_date_la", sa.Date()),
        sa.Column("first_order_date_la", sa.Date()),
        sa.Column("first_wfs_snapshot_at", sa.DateTime(timezone=True)),
        sa.Column("initial_observed_wfs_qty", QTY),
        sa.Column("first_batch_sold_out_date_la", sa.Date()),
        sa.Column("sold_out_evidence_status", sa.String(32)),
        jsoncol("sold_out_evidence_json"),
        sa.Column("metric_window_start_la", sa.Date()),
        sa.Column("metric_window_end_la", sa.Date()),
        sa.Column("sales_units", QTY),
        sa.Column("sales_orders", sa.Integer()),
        sa.Column("sales_amount_usd", MONEY),
        sa.Column("ad_spend_usd", MONEY),
        sa.Column("ad_clicks", sa.BigInteger()),
        sa.Column("ad_sales_usd", MONEY),
        sa.Column("ad_spend_ratio_pct", RATIO),
        sa.Column("acos_pct", RATIO),
        sa.Column("sample_units", QTY),
        sa.Column("sample_amount_usd", MONEY),
        sa.Column("profit_usd", MONEY),
        sa.Column("roi", RATIO),
        sa.Column("profit_margin_pct", RATIO),
        sa.Column("returned_units", QTY),
        sa.Column("returned_orders", sa.Integer()),
        sa.Column("return_rate_units_pct", RATIO),
        sa.Column("return_rate_orders_pct", RATIO),
        jsoncol("return_reasons_json"),
        sa.Column("score", sa.Numeric(10, 4)),
        sa.Column("grade", sa.String(16)),
        sa.Column("process_status", sa.String(48)),
        sa.Column(
            "rule_version_id",
            sa.Uuid(),
            sa.ForeignKey("biz_new_product_rule_versions.id", ondelete="RESTRICT"),
        ),
        sa.Column("data_status", sa.String(32)),
        jsoncol("data_coverage_json"),
        sa.Column("calculated_at", sa.DateTime(timezone=True)),
        updated(),
    )
    op.create_index(
        "ix_np_performance_process",
        "biz_new_product_performance_current",
        ["process_status", "calculated_at"],
    )

    op.create_table(
        "biz_new_product_tracking_current",
        registry_fk(primary_key=True),
        sa.Column(
            "purchase_application_id",
            sa.Uuid(),
            sa.ForeignKey("biz_new_product_purchase_applications.id", ondelete="RESTRICT"),
        ),
        sa.Column("initial_grade", sa.String(16)),
        sa.Column("purchase_suggested_qty", QTY),
        sa.Column("purchase_approved_qty", QTY),
        sa.Column("purchase_status", sa.String(48)),
        sa.Column("purchase_order_ref", sa.String(128)),
        sa.Column("purchase_submitted_at", sa.DateTime(timezone=True)),
        sa.Column("first_domestic_arrival_at", sa.DateTime(timezone=True)),
        sa.Column("full_domestic_arrival_at", sa.DateTime(timezone=True)),
        sa.Column("domestic_dispatched_at", sa.DateTime(timezone=True)),
        jsoncol("purchase_shipments_json"),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("tracking_started_date_la", sa.Date()),
        sa.Column("tracking_start_status", sa.String(32)),
        jsoncol("tracking_start_evidence_json"),
        sa.Column("wfs_available_qty", QTY),
        sa.Column("wfs_inventory_as_of", sa.DateTime(timezone=True)),
        sa.Column("cumulative_sales_units", QTY),
        sa.Column("cumulative_sales_orders", sa.Integer()),
        sa.Column("cumulative_sales_amount_usd", MONEY),
        sa.Column("cumulative_ad_spend_usd", MONEY),
        sa.Column("cumulative_ad_clicks", sa.BigInteger()),
        sa.Column("cumulative_profit_usd", MONEY),
        sa.Column("cumulative_roi", RATIO),
        sa.Column("cumulative_profit_margin_pct", RATIO),
        sa.Column("returned_units", QTY),
        sa.Column("returned_orders", sa.Integer()),
        sa.Column("return_rate_units_pct", RATIO),
        sa.Column("return_rate_orders_pct", RATIO),
        jsoncol("return_reasons_json"),
        jsoncol("trend_7d_json"),
        jsoncol("trend_14d_json"),
        jsoncol("trend_30d_json"),
        sa.Column("system_recommendation", sa.String(48)),
        jsoncol("triggered_rules_json"),
        sa.Column(
            "rule_version_id",
            sa.Uuid(),
            sa.ForeignKey("biz_new_product_rule_versions.id", ondelete="RESTRICT"),
        ),
        sa.Column("tracking_status", sa.String(48)),
        sa.Column("final_result", sa.String(24)),
        sa.Column("final_result_at", sa.DateTime(timezone=True)),
        sa.Column("final_review_application_id", sa.Uuid()),
        jsoncol("final_result_snapshot_json"),
        sa.Column("data_status", sa.String(32)),
        sa.Column("calculated_at", sa.DateTime(timezone=True)),
        updated(),
        sa.CheckConstraint(
            "final_result IS NULL OR final_result IN ('打品成功','打品失败')",
            name="ck_np_tracking_final_result",
        ),
    )
    op.create_index(
        "ix_np_tracking_current_state",
        "biz_new_product_tracking_current",
        ["tracking_status", "calculated_at"],
    )
    op.create_index(
        "ix_np_tracking_current_start",
        "biz_new_product_tracking_current",
        ["tracking_started_date_la"],
    )

    op.create_table(
        "biz_new_product_daily_snapshots",
        uid(),
        registry_fk(),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("snapshot_date_la", sa.Date(), nullable=False),
        sa.Column("metric_window_start_la", sa.Date()),
        sa.Column("metric_window_end_la", sa.Date()),
        sa.Column("wfs_available_qty", QTY),
        sa.Column("sales_units", QTY),
        sa.Column("sales_orders", sa.Integer()),
        sa.Column("sales_amount_usd", MONEY),
        sa.Column("ad_spend_usd", MONEY),
        sa.Column("ad_clicks", sa.BigInteger()),
        sa.Column("ad_spend_ratio_pct", RATIO),
        sa.Column("sample_units", QTY),
        sa.Column("sample_amount_usd", MONEY),
        sa.Column("profit_usd", MONEY),
        sa.Column("roi", RATIO),
        sa.Column("profit_margin_pct", RATIO),
        sa.Column("returned_units", QTY),
        sa.Column("returned_orders", sa.Integer()),
        sa.Column("return_rate_units_pct", RATIO),
        sa.Column("return_rate_orders_pct", RATIO),
        jsoncol("return_reasons_json"),
        sa.Column("score", sa.Numeric(10, 4)),
        sa.Column("grade", sa.String(16)),
        jsoncol("metrics_json"),
        jsoncol("triggered_rules_json"),
        sa.Column(
            "rule_version_id",
            sa.Uuid(),
            sa.ForeignKey("biz_new_product_rule_versions.id", ondelete="RESTRICT"),
        ),
        sa.Column("data_status", sa.String(32)),
        jsoncol("source_coverage_json"),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "registry_id", "phase", "snapshot_date_la", name="uq_np_daily_registry_phase_date"
        ),
        sa.CheckConstraint("phase IN ('performance','tracking')", name="ck_np_daily_phase"),
    )
    op.create_index(
        "ix_np_daily_phase_date", "biz_new_product_daily_snapshots", ["phase", "snapshot_date_la"]
    )

    op.create_table(
        "biz_new_product_tracking_review_applications",
        uid(),
        registry_fk(),
        sa.Column("proposed_result", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("applicant_id", sa.String(128), nullable=False),
        sa.Column("applicant_reason", sa.Text(), nullable=False),
        sa.Column("system_recommendation_snapshot", sa.String(48)),
        jsoncol("triggered_rules_snapshot_json"),
        jsoncol("facts_snapshot_json", nullable=False),
        sa.Column(
            "rule_version_id",
            sa.Uuid(),
            sa.ForeignKey("biz_new_product_rule_versions.id", ondelete="RESTRICT"),
        ),
        sa.Column("approval_request_ref", sa.String(128)),
        sa.Column("reviewed_by", sa.String(128)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_reason", sa.Text()),
        created(),
        sa.CheckConstraint(
            "proposed_result IN ('打品成功','打品失败')", name="ck_np_review_proposed_result"
        ),
        sa.CheckConstraint(
            "status IN ('submitted','approved','rejected')", name="ck_np_review_status"
        ),
    )
    op.create_index(
        "ix_np_review_state_time",
        "biz_new_product_tracking_review_applications",
        ["status", "created_at"],
    )
    op.create_index(
        "uq_np_review_pending",
        "biz_new_product_tracking_review_applications",
        ["registry_id"],
        unique=True,
        postgresql_where=sa.text("status = 'submitted'"),
    )

    # Requested separate replenishment approval storage is strictly MANUAL;
    # this schema intentionally defines no auto-replenishment trigger or job.
    op.create_table(
        "biz_new_product_replenishment_applications",
        uid(),
        registry_fk(),
        sa.Column("requested_qty", QTY, nullable=False),
        sa.Column("approved_qty", QTY),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("applicant_id", sa.String(128), nullable=False),
        sa.Column("application_reason", sa.Text(), nullable=False),
        jsoncol("facts_snapshot_json", nullable=False),
        sa.Column("approval_request_ref", sa.String(128)),
        sa.Column("reviewed_by", sa.String(128)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_reason", sa.Text()),
        created(),
        sa.CheckConstraint("requested_qty > 0", name="ck_np_replenishment_qty"),
        sa.CheckConstraint(
            "status IN ('submitted','approved','rejected')", name="ck_np_replenishment_status"
        ),
    )
    op.create_index(
        "ix_np_replenishment_state_time",
        "biz_new_product_replenishment_applications",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_np_replenishment_item_time",
        "biz_new_product_replenishment_applications",
        ["registry_id", "created_at"],
    )

    # 0087 had requested_qty but no actual approved amount or workbench ref.
    op.add_column("biz_new_product_purchase_applications", sa.Column("approved_qty", sa.Integer()))
    op.add_column(
        "biz_new_product_purchase_applications", sa.Column("approval_request_ref", sa.String(128))
    )


def downgrade() -> None:
    bind = op.get_bind()
    # Never silently destroy approvals, current results or daily histories.
    for name in (
        "biz_new_product_replenishment_applications",
        "biz_new_product_tracking_review_applications",
        "biz_new_product_daily_snapshots",
        "biz_new_product_tracking_current",
        "biz_new_product_performance_current",
        "biz_new_product_registry",
    ):
        if bind.scalar(sa.text(f"SELECT count(*) FROM {name}")):
            raise RuntimeError("REFUSE destructive downgrade: " + name + " has business data")
    # Extra columns on 0087 can also contain user decisions.
    if bind.scalar(
        sa.text("""
        SELECT count(*) FROM biz_new_product_purchase_applications
        WHERE approved_qty IS NOT NULL OR approval_request_ref IS NOT NULL
    """)
    ):
        raise RuntimeError("REFUSE destructive downgrade: purchase approval values exist")
    op.drop_column("biz_new_product_purchase_applications", "approval_request_ref")
    op.drop_column("biz_new_product_purchase_applications", "approved_qty")
    op.drop_index(
        "ix_np_replenishment_item_time", table_name="biz_new_product_replenishment_applications"
    )
    op.drop_index(
        "ix_np_replenishment_state_time", table_name="biz_new_product_replenishment_applications"
    )
    op.drop_table("biz_new_product_replenishment_applications")
    op.drop_index("uq_np_review_pending", table_name="biz_new_product_tracking_review_applications")
    op.drop_index(
        "ix_np_review_state_time", table_name="biz_new_product_tracking_review_applications"
    )
    op.drop_table("biz_new_product_tracking_review_applications")
    op.drop_index("ix_np_daily_phase_date", table_name="biz_new_product_daily_snapshots")
    op.drop_table("biz_new_product_daily_snapshots")
    op.drop_index("ix_np_tracking_current_start", table_name="biz_new_product_tracking_current")
    op.drop_index("ix_np_tracking_current_state", table_name="biz_new_product_tracking_current")
    op.drop_table("biz_new_product_tracking_current")
    op.drop_index("ix_np_performance_process", table_name="biz_new_product_performance_current")
    op.drop_table("biz_new_product_performance_current")
    op.drop_index("ix_np_registry_owner", table_name="biz_new_product_registry")
    op.drop_index("ix_np_registry_store", table_name="biz_new_product_registry")
    op.drop_table("biz_new_product_registry")
