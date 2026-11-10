"""Walmart SP search terms facts and internal action tracking.

Revision ID: 20261109_0083_ads_search_terms
Revises: 20261108_0082_clearance_center

New additive facts preserve daily date, advertiser/campaign identity and RAW lineage.
Internal action rows record operator-confirmed manual work only; no provider write is
performed by this migration or by these tables.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261109_0083_ads_search_terms"
down_revision = "20261108_0082_clearance_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fact_walmart_ad_search_term_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("business_date_la", sa.Date(), nullable=False),
        sa.Column(
            "business_timezone",
            sa.String(64),
            server_default=sa.text("'America/Los_Angeles'"),
            nullable=False,
        ),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("advertiser_id", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128)),
        sa.Column("item_id", sa.String(128)),
        sa.Column(
            "listing_mapping_status",
            sa.String(32),
            server_default=sa.text("'unresolved'"),
            nullable=False,
        ),
        sa.Column("mp_seller_name", sa.Text()),
        sa.Column("mp_advertiser_name", sa.Text()),
        sa.Column("campaign_id", sa.String(128), nullable=False),
        sa.Column("campaign_name", sa.Text()),
        sa.Column("campaign_type", sa.String(64)),
        sa.Column("campaign_status", sa.String(64)),
        sa.Column("bidding_strategy", sa.String(64)),
        sa.Column("targeting_type", sa.String(32), nullable=False),
        sa.Column("searched_keyword", sa.Text(), nullable=False),
        sa.Column("normalized_search_term", sa.Text(), nullable=False),
        sa.Column("attribution_days", sa.Integer(), server_default="14", nullable=False),
        sa.Column("num_ads_shown", sa.Integer()),
        sa.Column("num_ads_clicks", sa.Integer()),
        sa.Column("ad_spend_amount", sa.Numeric(18, 4)),
        sa.Column("ad_spend_currency_code", sa.String(3)),
        sa.Column("attributed_orders", sa.Numeric(18, 4)),
        sa.Column("advertised_sku_sales_amount", sa.Numeric(18, 4)),
        sa.Column("advertised_sku_units", sa.Numeric(18, 4)),
        sa.Column("other_sku_sales_amount", sa.Numeric(18, 4)),
        sa.Column("other_sku_units", sa.Numeric(18, 4)),
        sa.Column("cpc", sa.Numeric(18, 6)),
        sa.Column("ctr", sa.Numeric(18, 6)),
        sa.Column("cvr", sa.Numeric(18, 6)),
        sa.Column("cpa", sa.Numeric(18, 6)),
        sa.Column("ad_spend_percent", sa.Numeric(18, 6)),
        sa.Column("num_ads_shown_percent", sa.Numeric(18, 6)),
        sa.Column("num_ads_clicks_percent", sa.Numeric(18, 6)),
        sa.Column("attributed_orders_percent", sa.Numeric(18, 6)),
        sa.Column("advertised_sku_sales_percent", sa.Numeric(18, 6)),
        sa.Column("advertised_sku_units_percent", sa.Numeric(18, 6)),
        sa.Column("other_sku_sales_percent", sa.Numeric(18, 6)),
        sa.Column("other_sku_units_percent", sa.Numeric(18, 6)),
        sa.Column("source_identity_hash", sa.String(64), nullable=False),
        sa.Column("source_line_hash", sa.String(64), nullable=False),
        sa.Column(
            "source_raw_request_ref_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ods_api_raw_request_refs.id", ondelete="SET NULL"),
        ),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "business_date_la",
            "source_account_ref",
            "advertiser_id",
            "source_identity_hash",
            name="uq_walmart_ad_search_term_daily_identity",
        ),
        sa.CheckConstraint(
            "advertiser_id <> ''",
            name="ck_fact_walmart_ad_search_term_daily_advertiser_id_not_blank",
        ),
        sa.CheckConstraint(
            "campaign_id <> ''",
            name="ck_fact_walmart_ad_search_term_daily_campaign_id_not_blank",
        ),
        sa.CheckConstraint(
            "searched_keyword <> ''",
            name="ck_fact_walmart_ad_search_term_daily_searched_keyword_not_blank",
        ),
        sa.CheckConstraint(
            "normalized_search_term <> ''",
            name="ck_fact_walmart_ad_search_term_daily_normalized_term_not_blank",
        ),
        sa.CheckConstraint(
            "char_length(source_identity_hash) = 64",
            name="ck_fact_walmart_ad_search_term_daily_source_identity_sha256",
        ),
        sa.CheckConstraint(
            "char_length(source_line_hash) = 64",
            name="ck_fact_walmart_ad_search_term_daily_source_line_sha256",
        ),
        sa.CheckConstraint("attribution_days IN (3, 14, 30)", name="ck_fact_walmart_ad_search_term_daily_attribution_days"),
        sa.CheckConstraint(
            "num_ads_shown IS NULL OR num_ads_shown >= 0",
            name="ck_fact_walmart_ad_search_term_daily_impressions_nonnegative",
        ),
        sa.CheckConstraint(
            "num_ads_clicks IS NULL OR num_ads_clicks >= 0",
            name="ck_fact_walmart_ad_search_term_daily_clicks_nonnegative",
        ),
        sa.CheckConstraint(
            "ad_spend_amount IS NULL OR ad_spend_amount >= 0",
            name="ck_fact_walmart_ad_search_term_daily_spend_nonnegative",
        ),
        sa.CheckConstraint(
            "attributed_orders IS NULL OR attributed_orders >= 0",
            name="ck_fact_walmart_ad_search_term_daily_orders_nonnegative",
        ),
    )
    op.create_index(
        "ix_walmart_search_term_account_day",
        "fact_walmart_ad_search_term_daily",
        ["source_account_ref", "business_date_la"],
    )
    op.create_index(
        "ix_walmart_search_term_normalized_day",
        "fact_walmart_ad_search_term_daily",
        ["normalized_search_term", "business_date_la"],
    )
    op.create_index(
        "ix_walmart_search_term_campaign_day",
        "fact_walmart_ad_search_term_daily",
        ["campaign_id", "business_date_la"],
    )
    op.create_index(
        "ix_walmart_search_term_listing_day",
        "fact_walmart_ad_search_term_daily",
        ["source_account_ref", "store_id", "item_id", "business_date_la"],
    )

    op.create_table(
        "fact_walmart_keyword_sp_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("business_date_la", sa.Date(), nullable=False),
        sa.Column(
            "business_timezone",
            sa.String(64),
            server_default=sa.text("'America/Los_Angeles'"),
            nullable=False,
        ),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column("advertiser_id", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(128)),
        sa.Column("item_id", sa.String(128)),
        sa.Column(
            "listing_mapping_status",
            sa.String(32),
            server_default=sa.text("'unresolved'"),
            nullable=False,
        ),
        sa.Column("mp_seller_name", sa.Text()),
        sa.Column("mp_advertiser_name", sa.Text()),
        sa.Column("campaign_id", sa.String(128), nullable=False),
        sa.Column("campaign_name", sa.Text()),
        sa.Column("ad_group_id", sa.String(128), nullable=False),
        sa.Column("ad_group_name", sa.Text()),
        sa.Column("campaign_status", sa.String(64)),
        sa.Column("ad_group_status", sa.String(64)),
        sa.Column("keyword_id", sa.String(128)),
        sa.Column("keyword_name", sa.Text(), nullable=False),
        sa.Column("normalized_keyword", sa.Text(), nullable=False),
        sa.Column("keyword_status", sa.String(32)),
        sa.Column("keyword_state", sa.String(32)),
        sa.Column("targeting_type", sa.String(32), nullable=False),
        sa.Column("attribution_days", sa.Integer(), server_default="14", nullable=False),
        sa.Column("keyword_bid_amount", sa.Numeric(18, 4)),
        sa.Column("num_ads_shown", sa.Integer()),
        sa.Column("num_ads_clicks", sa.Integer()),
        sa.Column("ad_spend_amount", sa.Numeric(18, 4)),
        sa.Column("ad_spend_currency_code", sa.String(3)),
        sa.Column("attributed_orders", sa.Numeric(18, 4)),
        sa.Column("advertised_sku_sales_amount", sa.Numeric(18, 4)),
        sa.Column("other_sku_sales_amount", sa.Numeric(18, 4)),
        sa.Column("cpc", sa.Numeric(18, 6)),
        sa.Column("ctr", sa.Numeric(18, 6)),
        sa.Column("cvr", sa.Numeric(18, 6)),
        sa.Column("acos", sa.Numeric(18, 6)),
        sa.Column("roas", sa.Numeric(18, 6)),
        sa.Column("source_identity_hash", sa.String(64), nullable=False),
        sa.Column("source_line_hash", sa.String(64), nullable=False),
        sa.Column(
            "source_raw_request_ref_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ods_api_raw_request_refs.id", ondelete="SET NULL"),
        ),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "business_date_la",
            "source_account_ref",
            "advertiser_id",
            "source_identity_hash",
            name="uq_walmart_keyword_sp_daily_identity",
        ),
        sa.CheckConstraint(
            "advertiser_id <> ''",
            name="ck_fact_walmart_keyword_sp_daily_advertiser_id_not_blank",
        ),
        sa.CheckConstraint(
            "campaign_id <> ''",
            name="ck_fact_walmart_keyword_sp_daily_campaign_id_not_blank",
        ),
        sa.CheckConstraint(
            "ad_group_id <> ''",
            name="ck_fact_walmart_keyword_sp_daily_ad_group_id_not_blank",
        ),
        sa.CheckConstraint(
            "keyword_name <> ''",
            name="ck_fact_walmart_keyword_sp_daily_keyword_name_not_blank",
        ),
        sa.CheckConstraint(
            "normalized_keyword <> ''",
            name="ck_fact_walmart_keyword_sp_daily_normalized_keyword_not_blank",
        ),
        sa.CheckConstraint(
            "char_length(source_identity_hash) = 64",
            name="ck_fact_walmart_keyword_sp_daily_source_identity_sha256",
        ),
        sa.CheckConstraint(
            "char_length(source_line_hash) = 64",
            name="ck_fact_walmart_keyword_sp_daily_source_line_sha256",
        ),
        sa.CheckConstraint("attribution_days IN (3, 14, 30)", name="ck_fact_walmart_keyword_sp_daily_attribution_days"),
        sa.CheckConstraint(
            "num_ads_shown IS NULL OR num_ads_shown >= 0",
            name="ck_fact_walmart_keyword_sp_daily_impressions_nonnegative",
        ),
        sa.CheckConstraint(
            "num_ads_clicks IS NULL OR num_ads_clicks >= 0",
            name="ck_fact_walmart_keyword_sp_daily_clicks_nonnegative",
        ),
        sa.CheckConstraint(
            "ad_spend_amount IS NULL OR ad_spend_amount >= 0",
            name="ck_fact_walmart_keyword_sp_daily_spend_nonnegative",
        ),
    )
    op.create_index(
        "ix_walmart_manual_keyword_account_day",
        "fact_walmart_keyword_sp_daily",
        ["source_account_ref", "business_date_la"],
    )
    op.create_index(
        "ix_walmart_manual_keyword_normalized_day",
        "fact_walmart_keyword_sp_daily",
        ["normalized_keyword", "business_date_la"],
    )
    op.create_index(
        "ix_walmart_manual_keyword_campaign_group",
        "fact_walmart_keyword_sp_daily",
        ["advertiser_id", "campaign_id", "ad_group_id"],
    )
    op.create_index(
        "ix_walmart_manual_keyword_listing",
        "fact_walmart_keyword_sp_daily",
        ["source_account_ref", "store_id", "item_id"],
    )

    op.create_table(
        "ops_ads_search_term_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_account_ref", sa.String(128), nullable=False),
        sa.Column(
            "source_fact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fact_walmart_ad_search_term_daily.id", ondelete="SET NULL"),
        ),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("search_term", sa.Text(), nullable=False),
        sa.Column("normalized_search_term", sa.Text(), nullable=False),
        sa.Column("target_scope_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "status", sa.String(32), server_default=sa.text("'pending_manual'"), nullable=False
        ),
        sa.Column(
            "effect_status", sa.String(32), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("reason", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("completed_by", sa.String(128)),
        sa.Column("completion_note", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("baseline_window_start", sa.Date()),
        sa.Column("baseline_window_end", sa.Date()),
        sa.Column("followup_window_start", sa.Date()),
        sa.Column("followup_window_end", sa.Date()),
        sa.Column("before_metrics_json", postgresql.JSONB()),
        sa.Column("after_metrics_json", postgresql.JSONB()),
        sa.Column("last_followup_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action_type IN ('add_keyword','add_negative_keyword')", name="ck_ops_ads_search_term_actions_action_type"),
        sa.CheckConstraint("status IN ('pending_manual','manually_completed','cancelled')", name="ck_ops_ads_search_term_actions_status"),
        sa.CheckConstraint("effect_status IN ('pending','improved','unchanged','declined','insufficient_data')", name="ck_ops_ads_search_term_actions_effect_status"),
        sa.CheckConstraint("search_term <> ''", name="ck_ops_ads_search_term_actions_search_term_not_blank"),
    )
    op.create_index(
        "ix_ads_search_term_actions_account_status",
        "ops_ads_search_term_actions",
        ["source_account_ref", "status", "created_at"],
    )
    op.create_index(
        "ix_ads_search_term_actions_term",
        "ops_ads_search_term_actions",
        ["normalized_search_term", "created_at"],
    )
    op.create_index(
        "ix_ads_search_term_actions_actor",
        "ops_ads_search_term_actions",
        ["created_by", "created_at"],
    )

    op.create_table(
        "ops_ads_search_term_action_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ops_ads_search_term_actions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("actor_ref", sa.String(128), nullable=False),
        sa.Column(
            "detail_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ads_search_term_action_events_history",
        "ops_ads_search_term_action_events",
        ["action_id", "created_at"],
    )


    # Governed child interfaces used only by the existing walmartAdItemSpList
    # execution. Their configs remain disabled and unscheduled; the parent run
    # owns execution and its DATA_PAGES_REAL_SYNC_AUTHORIZED guard.
    op.execute(
        sa.text(
            """
            INSERT INTO gov_integration_interfaces
                (id, provider, interface_key, display_name, method, endpoint_path,
                 request_kind, handler_key, contract_version, outbound_enabled,
                 created_at, updated_at)
            VALUES
                (gen_random_uuid(), 'lingxing', 'walmartSpCampaignList',
                 'SP 广告活动来源同步', 'POST',
                 '/basicOpen/multiplatform/ads/queryCampaignSpList',
                 'offset_page', 'lingxing.data_pages.walmart_sp_campaign_list.v1',
                 'v1', true, now(), now()),
                (gen_random_uuid(), 'lingxing', 'walmartSpSearchTermList',
                 'SP 搜索词报表同步', 'POST',
                 '/basicOpen/multiplatform/ads/reportSearchImpressionSpList',
                 'offset_page', 'lingxing.data_pages.walmart_sp_search_term_list.v1',
                 'v1', true, now(), now()),
                (gen_random_uuid(), 'lingxing', 'walmartSpKeywordList',
                 'SP 手动关键词来源同步', 'POST',
                 '/basicOpen/multiplatform/ads/reportKeywordSpList',
                 'offset_page', 'lingxing.data_pages.walmart_sp_keyword_list.v1',
                 'v1', true, now(), now())
            ON CONFLICT (provider, interface_key) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO gov_raw_retention_policies
                (id, policy_key, provider, interface_key, hot_retention_days,
                 archive_after_days, delete_after_days, archive_required,
                 legal_hold, is_active, created_at, updated_at)
            VALUES
                (gen_random_uuid(), 'lingxing-data-pages-walmart-sp-campaign-list-v1',
                 'lingxing', 'walmartSpCampaignList', 365, NULL, NULL, false,
                 false, true, now(), now()),
                (gen_random_uuid(), 'lingxing-data-pages-walmart-sp-search-term-list-v1',
                 'lingxing', 'walmartSpSearchTermList', 365, NULL, NULL, false,
                 false, true, now(), now()),
                (gen_random_uuid(), 'lingxing-data-pages-walmart-sp-keyword-list-v1',
                 'lingxing', 'walmartSpKeywordList', 365, NULL, NULL, false,
                 false, true, now(), now())
            ON CONFLICT (policy_key) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO gov_integration_sync_configs
                (id, interface_id, source_account_ref, is_enabled,
                 schedule_enabled, schedule_cron, schedule_timezone, page_size,
                 batch_size, max_pages, max_attempts, retention_policy_id,
                 next_run_at, last_scheduled_at, created_at, updated_at)
            SELECT gen_random_uuid(), child.id, parent_config.source_account_ref,
                   false, false, NULL, 'UTC',
                   CASE child.interface_key
                       WHEN 'walmartSpCampaignList' THEN 100
                       ELSE 200
                   END,
                   NULL, 1000, 1, policy.id, NULL, NULL, now(), now()
            FROM gov_integration_sync_configs parent_config
            JOIN gov_integration_interfaces parent_interface
              ON parent_interface.id = parent_config.interface_id
             AND parent_interface.provider = 'lingxing'
             AND parent_interface.interface_key = 'walmartAdItemSpList'
            JOIN gov_integration_interfaces child
              ON child.provider = 'lingxing'
             AND child.interface_key IN (
                 'walmartSpCampaignList',
                 'walmartSpSearchTermList',
                 'walmartSpKeywordList'
             )
            JOIN gov_raw_retention_policies policy
              ON policy.interface_key = child.interface_key
             AND policy.provider = 'lingxing'
            ON CONFLICT (interface_id, source_account_ref) DO NOTHING
            """
        )
    )



def downgrade() -> None:
    connection = op.get_bind()
    for table_name in (
        "ops_ads_search_term_action_events",
        "ops_ads_search_term_actions",
        "fact_walmart_keyword_sp_daily",
        "fact_walmart_ad_search_term_daily",
    ):
        count = connection.execute(sa.text(f"SELECT count(*) FROM {table_name}")).scalar_one()
        if count:
            raise RuntimeError("ADS_SEARCH_TERMS_DOWNGRADE_BLOCKED_BY_RETAINED_DATA")
    op.drop_index(
        "ix_ads_search_term_action_events_history", table_name="ops_ads_search_term_action_events"
    )
    op.drop_table("ops_ads_search_term_action_events")
    op.drop_index("ix_ads_search_term_actions_actor", table_name="ops_ads_search_term_actions")
    op.drop_index("ix_ads_search_term_actions_term", table_name="ops_ads_search_term_actions")
    op.drop_index(
        "ix_ads_search_term_actions_account_status", table_name="ops_ads_search_term_actions"
    )
    op.drop_table("ops_ads_search_term_actions")
    op.drop_index("ix_walmart_manual_keyword_listing", table_name="fact_walmart_keyword_sp_daily")
    op.drop_index(
        "ix_walmart_manual_keyword_campaign_group", table_name="fact_walmart_keyword_sp_daily"
    )
    op.drop_index(
        "ix_walmart_manual_keyword_normalized_day", table_name="fact_walmart_keyword_sp_daily"
    )
    op.drop_index(
        "ix_walmart_manual_keyword_account_day", table_name="fact_walmart_keyword_sp_daily"
    )
    op.drop_table("fact_walmart_keyword_sp_daily")
    op.drop_index(
        "ix_walmart_search_term_listing_day", table_name="fact_walmart_ad_search_term_daily"
    )
    op.drop_index(
        "ix_walmart_search_term_campaign_day", table_name="fact_walmart_ad_search_term_daily"
    )
    op.drop_index(
        "ix_walmart_search_term_normalized_day", table_name="fact_walmart_ad_search_term_daily"
    )
    op.drop_index(
        "ix_walmart_search_term_account_day", table_name="fact_walmart_ad_search_term_daily"
    )
    op.drop_table("fact_walmart_ad_search_term_daily")
