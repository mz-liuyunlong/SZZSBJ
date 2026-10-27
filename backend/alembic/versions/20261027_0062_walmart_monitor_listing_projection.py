"""Add typed Walmart monitor observations and current Listing projection."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261027_0062_walmart_monitor_listing_projection"
down_revision: str | Sequence[str] | None = "20261027_0061_listing_evaluation_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _monitor_value_columns() -> list[sa.Column]:
    return [
        sa.Column("monitor_outcome", sa.String(64), nullable=False),
        sa.Column("monitor_source", sa.String(64)),
        sa.Column("monitor_error_code", sa.String(128)),
        sa.Column("title", sa.Text()),
        sa.Column("strike_price_amount", sa.Numeric(18, 4)),
        sa.Column("strike_price_currency_code", sa.String(3)),
        sa.Column("sale_price_amount", sa.Numeric(18, 4)),
        sa.Column("sale_price_currency_code", sa.String(3)),
        sa.Column("category", sa.Text()),
        sa.Column("source_category_raw", sa.Text()),
        sa.Column("buybox_status", sa.String(64)),
        sa.Column("walmart_seller", sa.Text()),
        sa.Column("is_hijacked", sa.Boolean()),
        sa.Column("average_rating", sa.Numeric(8, 4)),
        sa.Column("review_count", sa.Integer()),
        sa.Column("brand", sa.Text()),
        sa.Column(
            "image_urls_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "std_walmart_monitor_listing_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "raw_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_walmart_monitor_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        *_monitor_value_columns(),
        sa.Column("parser_version", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "raw_event_id",
            "source_account_ref",
            "store_id",
            "item_id",
            name="uq_std_walmart_monitor_observation_event_listing",
        ),
        sa.CheckConstraint(
            "strike_price_amount IS NULL OR strike_price_amount >= 0",
            name="ck_wm_obs_strike_nonneg",
        ),
        sa.CheckConstraint(
            "sale_price_amount IS NULL OR sale_price_amount >= 0",
            name="ck_wm_obs_sale_nonneg",
        ),
        sa.CheckConstraint(
            "average_rating IS NULL OR (average_rating >= 0 AND average_rating <= 5)",
            name="ck_wm_obs_rating_range",
        ),
        sa.CheckConstraint(
            "review_count IS NULL OR review_count >= 0",
            name="ck_wm_obs_review_nonneg",
        ),
    )
    op.create_index(
        "ix_std_walmart_monitor_observation_listing_captured",
        "std_walmart_monitor_listing_observations",
        ["source_account_ref", "store_id", "item_id", "captured_at"],
    )

    op.create_table(
        "mart_walmart_monitor_listing_current",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128), nullable=False),
        sa.Column("item_id", sa.String(128), nullable=False),
        sa.Column(
            "source_observation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("std_walmart_monitor_listing_observations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_raw_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_walmart_monitor_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        *_monitor_value_columns(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "source_account_ref",
            "store_id",
            "item_id",
            name="uq_mart_walmart_monitor_listing_current_identity",
        ),
    )
    op.create_index(
        "ix_mart_walmart_monitor_listing_current_item",
        "mart_walmart_monitor_listing_current",
        ["store_id", "item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mart_walmart_monitor_listing_current_item",
        table_name="mart_walmart_monitor_listing_current",
    )
    op.drop_table("mart_walmart_monitor_listing_current")
    op.drop_index(
        "ix_std_walmart_monitor_observation_listing_captured",
        table_name="std_walmart_monitor_listing_observations",
    )
    op.drop_table("std_walmart_monitor_listing_observations")
