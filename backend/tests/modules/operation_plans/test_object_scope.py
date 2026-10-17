from collections.abc import Iterator
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.operation_plans.repository import OperationPlanRepository

PLAN_A = UUID("00000000-0000-0000-0000-0000000000a1")
PLAN_B = UUID("00000000-0000-0000-0000-0000000000b1")
PLAN_MIXED = UUID("00000000-0000-0000-0000-0000000000c1")
BATCH_A = UUID("00000000-0000-0000-0000-0000000000a2")


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
                ('item-mixed', 'account-b')
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
                (:plan_mixed, 'item-mixed', 30, 6)
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
