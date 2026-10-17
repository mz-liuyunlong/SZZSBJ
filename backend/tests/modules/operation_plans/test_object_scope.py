from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.operation_plans.repository import OperationPlanRepository
from app.modules.operation_plans.schemas import OperationPlanProductQuery
from app.modules.operation_plans.service import OperationPlanService, ParsedImportRow

PLAN_A = UUID("00000000-0000-0000-0000-0000000000a1")
PLAN_B = UUID("00000000-0000-0000-0000-0000000000b1")
PLAN_MIXED = UUID("00000000-0000-0000-0000-0000000000c1")
PLAN_UNKNOWN = UUID("00000000-0000-0000-0000-0000000000d1")
BATCH_A = UUID("00000000-0000-0000-0000-0000000000a2")
PERIOD_FULL = UUID("10000000-0000-0000-0000-000000000001")
BATCH_FULL = UUID("10000000-0000-0000-0000-000000000002")


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


def _prepare_scope_tables(session: Session) -> None:
    session.execute(
        text(
            """
            create temporary table mart_listing_management_current (
                item_id text not null,
                source_account_ref text not null
            );
            create temporary table ops_operation_product_plans (
                id uuid primary key,
                item_id text not null,
                target_sales_amount numeric(18, 2) not null,
                target_gross_profit_amount numeric(18, 2) not null,
                remark text,
                adjusted boolean not null default false,
                operation_status text not null default 'normal',
                plan_status text not null default 'normal',
                updated_by text,
                updated_at timestamptz not null default now()
            );
            create temporary table ops_operation_plan_events (
                id uuid primary key,
                product_plan_id uuid not null,
                event_type text not null,
                after_data jsonb,
                reason text,
                actor_ref text not null,
                created_at timestamptz not null default now()
            );
            create temporary table ops_operation_plan_import_batches (
                id uuid primary key,
                created_by text not null,
                source_account_refs_json jsonb not null default '[]'::jsonb
            );
            """
        )
    )
    params = {
        "plan_a": PLAN_A,
        "plan_b": PLAN_B,
        "plan_mixed": PLAN_MIXED,
        "plan_unknown": PLAN_UNKNOWN,
        "batch_a": BATCH_A,
    }
    session.execute(
        text(
            """
            insert into mart_listing_management_current (item_id, source_account_ref)
            values
                ('item-a', 'account-a'),
                ('item-b', 'account-b'),
                ('item-mixed', 'account-a'),
                ('item-mixed', 'account-b'),
                ('item-unknown', '')
            """
        )
    )
    session.execute(
        text(
            """
            insert into ops_operation_product_plans (
                id, item_id, target_sales_amount, target_gross_profit_amount
            ) values
                (:plan_a, 'item-a', 10, 2),
                (:plan_b, 'item-b', 20, 4),
                (:plan_mixed, 'item-mixed', 30, 6),
                (:plan_unknown, 'item-unknown', 40, 8)
            """
        ),
        params,
    )
    session.execute(
        text(
            """
            insert into ops_operation_plan_events (
                id, product_plan_id, event_type, after_data, reason, actor_ref
            ) values
                ('00000000-0000-0000-0000-0000000000a3', :plan_a, 'target_update', '{}', null, '1'),
                ('00000000-0000-0000-0000-0000000000b3', :plan_b, 'target_update', '{}', null, '2')
            """
        ),
        params,
    )
    session.execute(
        text(
            """
            insert into ops_operation_plan_import_batches (
                id, created_by, source_account_refs_json
            ) values (:batch_a, '1', '["account-a"]'::jsonb)
            """
        ),
        params,
    )


def test_plan_object_scope_is_enforced_inside_postgresql_reads_and_writes(
    isolated_postgresql_session: Session,
) -> None:
    session = isolated_postgresql_session
    _prepare_scope_tables(session)
    repository = OperationPlanRepository(session)
    scope_a = frozenset({"account-a"})
    scope_all = frozenset({"account-a", "account-b"})

    assert repository.get_plan(PLAN_A, scope_a) is not None
    assert repository.get_plan(PLAN_B, scope_a) is None
    assert repository.get_plan(PLAN_MIXED, scope_a) is None
    assert repository.get_plan(PLAN_MIXED, scope_all) is not None
    assert repository.get_plan(PLAN_UNKNOWN, scope_all) is None

    assert repository.update_plan_targets(
        plan_id=PLAN_A,
        target_sales_amount=Decimal("11"),
        target_gross_profit_amount=Decimal("3"),
        remark="authorized",
        actor_ref="1",
        account_refs=scope_a,
    )
    assert not repository.update_plan_targets(
        plan_id=PLAN_B,
        target_sales_amount=Decimal("99"),
        target_gross_profit_amount=Decimal("9"),
        remark="denied",
        actor_ref="1",
        account_refs=scope_a,
    )
    assert not repository.update_plan_targets(
        plan_id=PLAN_MIXED,
        target_sales_amount=Decimal("99"),
        target_gross_profit_amount=Decimal("9"),
        remark="mixed denied",
        actor_ref="1",
        account_refs=scope_a,
    )
    assert session.scalar(
        text("select target_sales_amount from ops_operation_product_plans where id = :id"),
        {"id": PLAN_B},
    ) == Decimal("20")
    assert not repository.mark_plan_clearance(
        plan_id=PLAN_B,
        actor_ref="1",
        account_refs=scope_a,
    )

    assert len(repository.list_events(PLAN_A, scope_a)) == 1
    assert repository.list_events(PLAN_B, scope_a) == []

    session.execute(
        text(
            "delete from mart_listing_management_current "
            "where item_id = 'item-a' and source_account_ref = 'account-a'"
        )
    )
    assert repository.get_plan(PLAN_A, scope_a) is None
    assert not repository.update_plan_targets(
        plan_id=PLAN_A,
        target_sales_amount=Decimal("12"),
        target_gross_profit_amount=Decimal("3"),
        remark="revoked",
        actor_ref="1",
        account_refs=scope_a,
    )


def test_import_batch_scope_rejects_other_actor_and_revoked_accounts(
    isolated_postgresql_session: Session,
) -> None:
    session = isolated_postgresql_session
    _prepare_scope_tables(session)
    repository = OperationPlanRepository(session)

    assert repository.can_access_import_batch(
        batch_id=BATCH_A,
        actor_ref="1",
        account_refs=frozenset({"account-a"}),
        is_super_admin=False,
    )
    assert not repository.can_access_import_batch(
        batch_id=BATCH_A,
        actor_ref="2",
        account_refs=frozenset({"account-b"}),
        is_super_admin=False,
    )
    assert repository.can_access_import_batch(
        batch_id=BATCH_A,
        actor_ref="9",
        account_refs=frozenset({"account-a", "account-b"}),
        is_super_admin=True,
    )
    assert not repository.can_access_import_batch(
        batch_id=BATCH_A,
        actor_ref="1",
        account_refs=frozenset({"account-b"}),
        is_super_admin=False,
    )
    assert not repository.can_access_import_batch(
        batch_id=UUID("00000000-0000-0000-0000-000000000099"),
        actor_ref="1",
        account_refs=frozenset({"account-a"}),
        is_super_admin=False,
    )


def _prepare_full_scope_rows(session: Session) -> None:
    now = datetime(2026, 10, 17, 0, 0, tzinfo=UTC)
    listings = [
        ("11000000-0000-0000-0000-000000000001", "account-a", "store-a", "item-a"),
        ("11000000-0000-0000-0000-000000000002", "account-b", "store-b", "item-b"),
        ("11000000-0000-0000-0000-000000000003", "account-a", "store-a", "item-mixed"),
        ("11000000-0000-0000-0000-000000000004", "account-b", "store-b", "item-mixed"),
        ("11000000-0000-0000-0000-000000000005", "", "store-unknown", "item-unknown"),
        ("11000000-0000-0000-0000-000000000006", "account-a", "store-a", "item-new"),
    ]
    for listing_id, account_ref, store_id, item_id in listings:
        session.execute(
            text(
                """
                insert into mart_listing_management_current (
                    id, source_account_ref, platform_code, store_id, store_name,
                    item_id, msku, local_sku, local_name, owner_ref, tags_json,
                    sales_7d, sales_14d, sales_30d, gpt_analysis_links_json,
                    source_lineage_json, calculated_at, created_at, updated_at
                ) values (
                    :id, :account_ref, 'walmart', :store_id, :store_name,
                    :item_id, :msku, :sku, :name, :owner_ref, '[]'::jsonb,
                    0, 0, 0, '[]'::jsonb, '{}'::jsonb, :now, :now, :now
                )
                """
            ),
            {
                "id": UUID(listing_id),
                "account_ref": account_ref,
                "store_id": store_id,
                "store_name": store_id,
                "item_id": item_id,
                "msku": f"msku-{item_id}",
                "sku": f"sku-{item_id}",
                "name": f"Synthetic {item_id}",
                "owner_ref": f"owner-{account_ref or 'unknown'}",
                "now": now,
            },
        )

    session.execute(
        text(
            """
            insert into ops_operation_plan_periods (
                id, platform_code, period_type, period_key,
                period_start_date, period_end_date, status, created_by
            ) values (
                :id, 'walmart', 'month', '2099-01',
                :start_date, :end_date, 'active', 'synthetic-actor'
            )
            """
        ),
        {
            "id": PERIOD_FULL,
            "start_date": date(2099, 1, 1),
            "end_date": date(2099, 1, 31),
        },
    )
    plans = [
        (PLAN_A, "item-a", Decimal("10"), Decimal("2")),
        (PLAN_B, "item-b", Decimal("20"), Decimal("4")),
        (PLAN_MIXED, "item-mixed", Decimal("30"), Decimal("6")),
        (PLAN_UNKNOWN, "item-unknown", Decimal("40"), Decimal("8")),
    ]
    for plan_id, item_id, sales, profit in plans:
        session.execute(
            text(
                """
                insert into ops_operation_product_plans (
                    id, period_id, platform_code, source_account_ref, item_id,
                    msku, target_sales_amount, target_gross_profit_amount,
                    currency_code, operation_status, plan_status, stock_status,
                    source_type, adjusted, created_by
                ) values (
                    :id, :period_id, 'walmart', '__item_level__', :item_id,
                    '__ITEM_LEVEL__', :sales, :profit,
                    'USD', 'normal', 'normal', 'normal', 'manual', false, 'synthetic-actor'
                )
                """
            ),
            {
                "id": plan_id,
                "period_id": PERIOD_FULL,
                "item_id": item_id,
                "sales": sales,
                "profit": profit,
            },
        )
    session.execute(
        text(
            """
            insert into ops_operation_plan_import_batches (
                id, period_id, file_name, file_sha256, file_size, status,
                conflict_policy, source_account_refs_json, created_by
            ) values (
                :id, :period_id, 'synthetic.csv', :sha, 1, 'processing',
                'skip_existing', '["account-a"]'::jsonb, 'synthetic-actor'
            )
            """
        ),
        {"id": BATCH_FULL, "period_id": PERIOD_FULL, "sha": "a" * 64},
    )


def test_plan_collection_queries_filter_complete_item_scope_before_aggregation(
    isolated_postgresql_session: Session,
) -> None:
    session = isolated_postgresql_session
    _prepare_full_scope_rows(session)
    repository = OperationPlanRepository(session)
    scope_a = frozenset({"account-a"})
    scope_all = frozenset({"account-a", "account-b"})

    query = OperationPlanProductQuery(period_key="2099-01", page=1, page_size=50)
    rows_a, total_a = repository.list_products(
        period_id=PERIOD_FULL,
        query=query,
        account_refs=scope_a,
    )
    assert total_a == 1
    assert [row["item_id"] for row in rows_a] == ["item-a"]

    rows_b, total_b = repository.list_products(
        period_id=PERIOD_FULL,
        query=query,
        account_refs=frozenset({"account-b"}),
    )
    assert total_b == 1
    assert [row["item_id"] for row in rows_b] == ["item-b"]

    rows_all, total_all = repository.list_products(
        period_id=PERIOD_FULL,
        query=query,
        account_refs=scope_all,
    )
    assert total_all == 3
    assert {row["item_id"] for row in rows_all} == {"item-a", "item-b", "item-mixed"}

    batch_query = OperationPlanProductQuery(
        period_key="2099-01",
        search_field="item_id",
        batch_values=["item-a", "item-mixed", "item-unknown"],
        sort_field="sales_completion_rate",
        sort_order="asc",
        page=1,
        page_size=1,
    )
    batch_rows, batch_total = repository.list_products(
        period_id=PERIOD_FULL,
        query=batch_query,
        account_refs=scope_a,
    )
    assert batch_total == 1
    assert [row["item_id"] for row in batch_rows] == ["item-a"]

    summary_a = repository.summary(period_id=PERIOD_FULL, account_refs=scope_a)
    summary_all = repository.summary(period_id=PERIOD_FULL, account_refs=scope_all)
    assert summary_a["product_count"] == 1
    assert summary_a["sales_target_amount"] == Decimal("10")
    assert summary_all["product_count"] == 3
    assert summary_all["sales_target_amount"] == Decimal("60")

    owners_a = repository.owner_summary(period_id=PERIOD_FULL, account_refs=scope_a)
    owners_all = repository.owner_summary(period_id=PERIOD_FULL, account_refs=scope_all)
    assert sum(row["product_count"] for row in owners_a) == 1
    assert sum(row["product_count"] for row in owners_all) == 3

    options_a = repository.list_options(period_id=PERIOD_FULL, account_refs=scope_a)
    options_all = repository.list_options(period_id=PERIOD_FULL, account_refs=scope_all)
    assert sum(row["count"] for row in options_a["operation_status_counts"]) == 1
    assert sum(row["count"] for row in options_all["operation_status_counts"]) == 3

    session.execute(text("delete from mart_listing_management_current where item_id = 'item-a'"))
    revoked_rows, revoked_total = repository.list_products(
        period_id=PERIOD_FULL,
        query=query,
        account_refs=scope_a,
    )
    assert revoked_rows == []
    assert revoked_total == 0
    assert repository.summary(period_id=PERIOD_FULL, account_refs=scope_a)["product_count"] == 0


def test_import_create_skip_and_overwrite_share_complete_item_scope(
    isolated_postgresql_session: Session,
) -> None:
    session = isolated_postgresql_session
    _prepare_full_scope_rows(session)
    repository = OperationPlanRepository(session)
    service = OperationPlanService(session)
    scope_a = frozenset({"account-a"})
    scope_all = frozenset({"account-a", "account-b"})

    assert repository.resolve_listing_by_item_id(item_id="item-mixed", account_refs=scope_a) is None
    assert (
        repository.get_existing_plan(
            period_id=PERIOD_FULL,
            platform_code="walmart",
            item_id="item-mixed",
            account_refs=scope_a,
        )
        is None
    )
    assert (
        repository.get_existing_plan(
            period_id=PERIOD_FULL,
            platform_code="walmart",
            item_id="item-mixed",
            account_refs=scope_all,
        )
        is not None
    )

    denied = service._import_one_row(
        batch_id=BATCH_FULL,
        period_id=PERIOD_FULL,
        parsed=ParsedImportRow(1, "item-mixed", "", "99", "9", "denied"),
        conflict_policy="overwrite_existing",
        account_refs=scope_a,
        actor_ref="synthetic-actor",
        request_id="synthetic-request",
    )
    assert denied.import_status == "failed"
    assert denied.error_message is not None
    assert str(PLAN_MIXED) not in denied.error_message
    assert (
        session.scalar(
            text(
                """
                select imported_plan_id
                from ops_operation_plan_import_rows
                where batch_id = :batch_id and row_number = 1
                """
            ),
            {"batch_id": BATCH_FULL},
        )
        is None
    )
    assert session.scalar(
        text("select target_sales_amount from ops_operation_product_plans where id = :id"),
        {"id": PLAN_MIXED},
    ) == Decimal("30")

    skipped_denied = service._import_one_row(
        batch_id=BATCH_FULL,
        period_id=PERIOD_FULL,
        parsed=ParsedImportRow(2, "item-mixed", "", "99", "9", "denied skip"),
        conflict_policy="skip_existing",
        account_refs=scope_a,
        actor_ref="synthetic-actor",
        request_id="synthetic-request",
    )
    assert skipped_denied.import_status == "failed"
    assert skipped_denied.error_message is not None
    assert str(PLAN_MIXED) not in skipped_denied.error_message

    for row_number, item_id in ((3, "item-b"), (4, "item-unknown")):
        denied_item = service._import_one_row(
            batch_id=BATCH_FULL,
            period_id=PERIOD_FULL,
            parsed=ParsedImportRow(row_number, item_id, "", "99", "9", "denied item"),
            conflict_policy="overwrite_existing",
            account_refs=scope_a,
            actor_ref="synthetic-actor",
            request_id="synthetic-request",
        )
        assert denied_item.import_status == "failed"
        assert denied_item.error_message is not None
        assert denied_item.suggestion is not None

    session.execute(
        text(
            """
            update ops_operation_plan_import_batches
            set source_account_refs_json = '["account-a", "account-b"]'::jsonb
            where id = :batch_id
            """
        ),
        {"batch_id": BATCH_FULL},
    )
    allowed_skip = service._import_one_row(
        batch_id=BATCH_FULL,
        period_id=PERIOD_FULL,
        parsed=ParsedImportRow(5, "item-mixed", "", "31", "7", "allowed skip"),
        conflict_policy="skip_existing",
        account_refs=scope_all,
        actor_ref="synthetic-actor",
        request_id="synthetic-request",
    )
    assert allowed_skip.import_status == "skipped"

    allowed_overwrite = service._import_one_row(
        batch_id=BATCH_FULL,
        period_id=PERIOD_FULL,
        parsed=ParsedImportRow(6, "item-mixed", "", "32", "7", "allowed overwrite"),
        conflict_policy="overwrite_existing",
        account_refs=scope_all,
        actor_ref="synthetic-actor",
        request_id="synthetic-request",
    )
    assert allowed_overwrite.import_status == "updated"
    assert session.scalar(
        text("select target_sales_amount from ops_operation_product_plans where id = :id"),
        {"id": PLAN_MIXED},
    ) == Decimal("32")

    created = service._import_one_row(
        batch_id=BATCH_FULL,
        period_id=PERIOD_FULL,
        parsed=ParsedImportRow(7, "item-new", "", "15", "3", "create"),
        conflict_policy="skip_existing",
        account_refs=scope_a,
        actor_ref="synthetic-actor",
        request_id="synthetic-request",
    )
    assert created.import_status == "success", created

    stale_listing = repository.resolve_listing_by_item_id(
        item_id="item-new",
        account_refs=scope_a,
    )
    assert stale_listing is not None
    session.execute(
        text(
            """
            insert into mart_listing_management_current (
                id, source_account_ref, platform_code, store_id, store_name,
                item_id, msku, local_sku, local_name, owner_ref, tags_json,
                sales_7d, sales_14d, sales_30d, gpt_analysis_links_json,
                source_lineage_json, calculated_at, created_at, updated_at
            ) select
                :id, 'account-a', platform_code, 'store-a-race', 'store-a-race',
                'item-race', msku, local_sku, local_name, owner_ref, tags_json,
                sales_7d, sales_14d, sales_30d, gpt_analysis_links_json,
                source_lineage_json, calculated_at, created_at, updated_at
            from mart_listing_management_current
            where item_id = 'item-new'
            limit 1
            """
        ),
        {"id": UUID("11000000-0000-0000-0000-000000000008")},
    )
    session.execute(
        text(
            """
            insert into mart_listing_management_current (
                id, source_account_ref, platform_code, store_id, store_name,
                item_id, msku, local_sku, local_name, owner_ref, tags_json,
                sales_7d, sales_14d, sales_30d, gpt_analysis_links_json,
                source_lineage_json, calculated_at, created_at, updated_at
            ) select
                :id, 'account-b', platform_code, 'store-b', 'store-b',
                'item-race', msku, local_sku, local_name, owner_ref, tags_json,
                sales_7d, sales_14d, sales_30d, gpt_analysis_links_json,
                source_lineage_json, calculated_at, created_at, updated_at
            from mart_listing_management_current
            where item_id = 'item-new'
            limit 1
            """
        ),
        {"id": UUID("11000000-0000-0000-0000-000000000007")},
    )
    stale_listing["item_id"] = "item-race"
    assert not repository.insert_plan(
        plan_id=UUID("12000000-0000-0000-0000-000000000007"),
        period_id=PERIOD_FULL,
        listing=stale_listing,
        target_sales_amount=Decimal("10"),
        target_gross_profit_amount=Decimal("2"),
        remark=None,
        import_batch_id=BATCH_FULL,
        actor_ref="synthetic-actor",
        account_refs=scope_a,
    )
