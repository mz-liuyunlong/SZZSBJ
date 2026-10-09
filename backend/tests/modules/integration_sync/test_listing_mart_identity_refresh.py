from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.integration_sync.data_pages_real_sync import (
    LISTING_MART_BUSINESS_OWNED_COLUMNS,
    LISTING_MART_FILL_ONLY_COLUMNS,
    LISTING_MART_REFRESH_UPDATE_EXPRESSIONS,
    DataPagesRealSyncRunner,
    _listing_mart_refresh_sql,
)

ACCOUNT = "synthetic-account"
LISTING_ID = UUID("00000000-0000-0000-0000-000000000101")


class _ScalarResult:
    def scalar_one(self) -> int:
        return 1


class _CaptureSession:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(
        self,
        statement: object,
        params: dict[str, object] | None = None,
    ) -> _ScalarResult:
        del params
        self.statements.append(str(statement))
        return _ScalarResult()


def _runner(session: Any) -> DataPagesRealSyncRunner:
    return DataPagesRealSyncRunner(
        session=session,
        client=None,
        source_account_ref=ACCOUNT,
        business_date=date(2026, 10, 10),
        page_size=100,
        campaign_type="SP",
        max_advertisers=1,
    )


def _update_columns() -> frozenset[str]:
    return frozenset(LISTING_MART_REFRESH_UPDATE_EXPRESSIONS)


def test_listing_mart_refresh_preserves_existing_listing_id() -> None:
    sql = _listing_mart_refresh_sql().lower()

    assert "on conflict (source_account_ref,store_id,item_id) do update set" in sql
    assert "delete from mart_listing_management_current" not in sql
    assert "id" not in _update_columns()


def test_listing_mart_refresh_twice_is_idempotent() -> None:
    session = _CaptureSession()
    runner = _runner(session)

    runner._refresh_listing_mart()
    runner._refresh_listing_mart()

    refreshes = [sql for sql in session.statements if "insert into mart_listing" in sql]
    assert len(refreshes) == 2
    assert refreshes[0] == refreshes[1]
    assert all("on conflict (source_account_ref,store_id,item_id)" in sql for sql in refreshes)


def test_listing_mart_refresh_does_not_clear_listing_start_at() -> None:
    assert LISTING_MART_FILL_ONLY_COLUMNS == {"listing_start_at_utc"}
    assert "listing_start_at_utc" in LISTING_MART_BUSINESS_OWNED_COLUMNS
    assert LISTING_MART_REFRESH_UPDATE_EXPRESSIONS["listing_start_at_utc"] == (
        "coalesce(current_listing.listing_start_at_utc, excluded.listing_start_at_utc)"
    )


def test_listing_mart_refresh_keeps_listing_start_raw() -> None:
    session = _CaptureSession()
    runner = _runner(session)

    runner._write_listings(
        [
            {
                "item_id": "synthetic-item",
                "store_id": "synthetic-store",
                "listing_start_time": "2026-01-02 03:04:05",
            }
        ]
    )

    dim_upsert = next(
        sql for sql in session.statements if "insert into dim_walmart_listings" in sql
    )
    assert (
        "listing_start_source_raw = coalesce(nullif(trim(excluded.listing_start_source_raw), ''), "
        "dim_walmart_listings.listing_start_source_raw)"
    ) in dim_upsert
    assert "title = coalesce(excluded.title, dim_walmart_listings.title)" in dim_upsert


def test_listing_mart_refresh_keeps_lifecycle() -> None:
    assert "lifecycle_status" in LISTING_MART_BUSINESS_OWNED_COLUMNS
    assert "lifecycle_status" not in _update_columns()


def test_listing_mart_refresh_keeps_gpt_link_association() -> None:
    sql = _listing_mart_refresh_sql().lower()

    assert "delete from mart_listing_management_current" not in sql
    assert "id" not in _update_columns()
    assert "gpt_analysis_links_json" not in _update_columns()


def test_listing_mart_refresh_keeps_archive_association() -> None:
    sql = _listing_mart_refresh_sql().lower()

    assert "delete from mart_listing_management_current" not in sql
    assert "id" not in _update_columns()


def test_listing_mart_refresh_keeps_tags_or_labels() -> None:
    assert "tags_json" in LISTING_MART_BUSINESS_OWNED_COLUMNS
    assert "tags_json" not in _update_columns()


def test_listing_mart_refresh_keeps_grade_or_level() -> None:
    assert "product_grade" in LISTING_MART_BUSINESS_OWNED_COLUMNS
    assert "product_grade" not in _update_columns()


def test_listing_mart_refresh_missing_provider_fields_do_not_null_business_fields() -> None:
    overwrite_protected = LISTING_MART_BUSINESS_OWNED_COLUMNS - LISTING_MART_FILL_ONLY_COLUMNS
    assert overwrite_protected.isdisjoint(_update_columns())


def test_listing_mart_refresh_provider_null_only_updates_allowed_platform_fields() -> None:
    provider_columns = {
        "platform_code",
        "store_name",
        "msku",
        "local_sku",
        "local_name",
        "title",
        "picture_url",
        "item_url",
        "sale_price_amount",
        "sale_price_currency_code",
        "listing_status",
        "fulfillment_type",
        "fulfillment_type_name",
        "wfs_available_quantity",
        "available_quantity",
        "average_rating",
        "review_count",
        "brand",
        "gtin",
        "upc",
    }

    assert provider_columns <= _update_columns()
    assert all(
        "coalesce(" in LISTING_MART_REFRESH_UPDATE_EXPRESSIONS[column]
        for column in provider_columns
    )


def test_listing_mart_refresh_retains_source_absent_rows() -> None:
    assert "delete from mart_listing_management_current" not in _listing_mart_refresh_sql().lower()


@pytest.fixture
def isolated_postgresql_session() -> Iterator[Session]:
    try:
        settings = Settings()  # type: ignore[call-arg]
        url = get_test_database_url(settings)
    except (SettingsError, ValidationError):
        pytest.skip("isolated PostgreSQL test database is not configured")

    engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    yield session
            finally:
                if transaction.is_active:
                    transaction.rollback()
    finally:
        engine.dispose()


def _create_refresh_tables(session: Session) -> None:
    statements = (
        """
        create temporary table dim_walmart_listings (
            source_account_ref text not null,
            platform_code text,
            store_id text not null,
            store_name text,
            item_id text not null,
            msku text,
            local_sku text,
            local_name text,
            title text,
            picture_url text,
            item_url text,
            price_amount numeric,
            price_currency_code text,
            standard_status text,
            fulfillment_type text,
            fulfillment_type_name text,
            listing_start_at_utc timestamptz,
            wfs_available_quantity numeric,
            available_quantity numeric,
            average_rating numeric,
            review_count integer,
            brand text,
            gtin text,
            upc text,
            unique (source_account_ref, store_id, item_id)
        )
        """,
        """
        create temporary table mart_daily_sales_item_day (
            source_account_ref text,
            business_date_la date,
            store_id text,
            item_id text,
            sales_qty numeric
        )
        """,
        """
        create temporary table fact_walmart_ad_item_sp_daily (
            source_account_ref text,
            business_date_la date,
            store_id text,
            item_id text,
            msku text,
            ad_spend_amount numeric
        )
        """,
        """
        create temporary table mart_listing_management_current (
            id uuid primary key,
            source_account_ref text not null,
            platform_code text,
            store_id text not null,
            store_name text,
            item_id text not null,
            msku text,
            local_sku text,
            local_name text,
            title text,
            picture_url text,
            item_url text,
            owner_ref text,
            product_grade text,
            tags_json jsonb,
            strike_price_amount numeric,
            strike_price_currency_code text,
            sale_price_amount numeric,
            sale_price_currency_code text,
            listing_status text,
            lifecycle_status text,
            fulfillment_type text,
            fulfillment_type_name text,
            listing_start_at_utc timestamptz,
            category text,
            wfs_available_quantity numeric,
            available_quantity numeric,
            inbound_quantity numeric,
            sales_7d numeric,
            sales_14d numeric,
            sales_30d numeric,
            ad_spend_30d_amount numeric,
            ad_spend_currency_code text,
            buybox_status text,
            walmart_seller text,
            is_hijacked boolean,
            average_rating numeric,
            review_count integer,
            brand text,
            disabled_reason text,
            wfs_fee_amount numeric,
            wfs_fee_currency_code text,
            gtin text,
            upc text,
            gpt_analysis_links_json jsonb,
            source_lineage_json jsonb,
            calculated_at timestamptz,
            created_at timestamptz,
            updated_at timestamptz,
            unique (source_account_ref, store_id, item_id)
        )
        """,
        "create temporary table listing_gpt_analysis_links (listing_id uuid not null)",
        (
            "create temporary table listing_archive_states "
            "(listing_id uuid not null, archive_reason text)"
        ),
        """
        create temporary table product_custom_tag_assignments (
            source_account_ref text not null,
            item_id text not null,
            tag_id uuid not null
        )
        """,
    )
    for statement in statements:
        session.execute(text(statement))


def test_listing_mart_refresh_preserves_rows_fields_and_associations_in_postgresql(
    isolated_postgresql_session: Session,
) -> None:
    session = isolated_postgresql_session
    _create_refresh_tables(session)
    now = datetime(2026, 10, 10, tzinfo=UTC)
    second_listing_id = UUID("00000000-0000-0000-0000-000000000102")
    tag_id = UUID("00000000-0000-0000-0000-000000000103")

    session.execute(
        text(
            """
            insert into dim_walmart_listings (
                source_account_ref, platform_code, store_id, store_name, item_id, msku,
                local_sku, title, standard_status
            ) values (:account, 'walmart', 'store-1', 'Store', 'item-1', 'msku-1',
                      'sku-1', 'provider-title', 'ONLINE')
            """
        ),
        {"account": ACCOUNT},
    )
    session.execute(
        text(
            """
            insert into dim_walmart_listings (
                source_account_ref, platform_code, store_id, store_name, item_id, msku,
                local_sku, title, standard_status
            ) values (:account, 'walmart', 'store-3', 'Store', 'first-seen', 'msku-3',
                      'sku-3', 'first-seen-title', 'ONLINE')
            """
        ),
        {"account": ACCOUNT},
    )
    session.execute(
        text(
            """
            insert into mart_listing_management_current (
                id, source_account_ref, store_id, item_id, owner_ref, product_grade,
                tags_json, lifecycle_status, listing_start_at_utc, title, sales_7d,
                sales_14d, sales_30d, gpt_analysis_links_json, source_lineage_json,
                calculated_at, created_at, updated_at
            ) values (
                :id, :account, 'store-1', 'item-1', 'owner', 'A',
                '[{"name":"manual"}]'::jsonb, 'stable', :listed_at, 'old-title', 0,
                0, 0, '[{"kind":"legacy"}]'::jsonb, '{}'::jsonb, :now, :now, :now
            )
            """
        ),
        {"id": LISTING_ID, "account": ACCOUNT, "listed_at": now, "now": now},
    )
    session.execute(
        text(
            """
            insert into mart_listing_management_current (
                id, source_account_ref, store_id, item_id, lifecycle_status, sales_7d,
                sales_14d, sales_30d, tags_json, gpt_analysis_links_json,
                source_lineage_json, calculated_at, created_at, updated_at
            ) values (
                :id, :account, 'store-2', 'source-absent', 'keep', 0, 0, 0,
                '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, :now, :now, :now
            )
            """
        ),
        {"id": second_listing_id, "account": ACCOUNT, "now": now},
    )
    session.execute(
        text("insert into listing_gpt_analysis_links (listing_id) values (:id)"),
        {"id": LISTING_ID},
    )
    session.execute(
        text(
            "insert into listing_archive_states (listing_id, archive_reason) "
            "values (:id, 'manual-reason')"
        ),
        {"id": LISTING_ID},
    )
    session.execute(
        text(
            "insert into product_custom_tag_assignments "
            "(source_account_ref, item_id, tag_id) values (:account, 'item-1', :tag_id)"
        ),
        {"account": ACCOUNT, "tag_id": tag_id},
    )

    runner = _runner(session)
    runner._refresh_listing_mart()
    first_seen_listing_id = session.execute(
        text(
            "select id from mart_listing_management_current "
            "where source_account_ref=:account and store_id='store-3' and item_id='first-seen'"
        ),
        {"account": ACCOUNT},
    ).scalar_one()
    runner._refresh_listing_mart()

    row = (
        session.execute(
            text(
                """
            select id, owner_ref, product_grade, lifecycle_status, listing_start_at_utc,
                   tags_json, gpt_analysis_links_json, title
            from mart_listing_management_current
            where source_account_ref=:account and store_id='store-1' and item_id='item-1'
            """
            ),
            {"account": ACCOUNT},
        )
        .mappings()
        .one()
    )

    assert row["id"] == LISTING_ID
    assert row["owner_ref"] == "owner"
    assert row["product_grade"] == "A"
    assert row["lifecycle_status"] == "stable"
    assert row["listing_start_at_utc"] == now
    assert row["tags_json"] == [{"name": "manual"}]
    assert row["gpt_analysis_links_json"] == [{"kind": "legacy"}]
    assert row["title"] == "provider-title"
    assert (
        session.execute(
            text(
                "select id from mart_listing_management_current "
                "where source_account_ref=:account and store_id='store-3' and item_id='first-seen'"
            ),
            {"account": ACCOUNT},
        ).scalar_one()
        == first_seen_listing_id
    )
    assert (
        session.execute(
            text("select count(*) from listing_gpt_analysis_links where listing_id=:id"),
            {"id": LISTING_ID},
        ).scalar_one()
        == 1
    )
    assert (
        session.execute(
            text("select count(*) from listing_archive_states where listing_id=:id"),
            {"id": LISTING_ID},
        ).scalar_one()
        == 1
    )
    assert (
        session.execute(
            text(
                "select count(*) from product_custom_tag_assignments "
                "where source_account_ref=:account and item_id='item-1'"
            ),
            {"account": ACCOUNT},
        ).scalar_one()
        == 1
    )
    assert (
        session.execute(
            text("select count(*) from mart_listing_management_current where id=:id"),
            {"id": second_listing_id},
        ).scalar_one()
        == 1
    )
