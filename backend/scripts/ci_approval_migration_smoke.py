"""Isolated PostgreSQL smoke test for approval migrations 0044 and 0045.

The strict local-only guard must remain in place. This script is never
authorized to modify a production database or run non-CI migrations.
"""

from __future__ import annotations

import os
import sys
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.core.config import get_database_url

EXPECTED_DATABASE = "approval_ci"
EXPECTED_USERNAME = "approval_ci"


def ci_engine():
    """Reject anything but the dedicated local-only CI PostgreSQL instance."""
    url = make_url(get_database_url())
    if (
        os.getenv("APP_ENV") != "dev"
        or url.drivername != "postgresql+psycopg"
        or url.host not in ("127.0.0.1", "localhost")
        or url.port != 5432
        or url.database != EXPECTED_DATABASE
        or url.username != EXPECTED_USERNAME
    ):
        raise RuntimeError("Approval migration smoke requires isolated CI database")
    return create_engine(url)


def bootstrap() -> None:
    engine = ci_engine()
    with engine.begin() as conn:
        assert conn.scalar(text("select to_regclass('public.alembic_version')")) is None
        for statement in (
            "create table alembic_version (version_num varchar(128) primary key)",
            "insert into alembic_version values ('20261017_0042_rbac_backfill')",
            "create table ops_wfs_fee_anomaly_cases (id uuid primary key)",
            (
                "create table dws_purchase_board ("
                "item_id_source varchar(32) not null,"
                "constraint ck_dws_purchase_board_item_id_source "
                "check (item_id_source in ('from_system_plan', 'from_plan_remark',"
                "'from_packing_slip', 'pending_packing_slip', 'unresolved')))"
            ),
            (
                "create table app_approval_requests ("
                "id uuid primary key, approval_type varchar(80) not null,"
                "business_ref varchar(128) not null,"
                "source_account_ref varchar(128) not null,"
                "status varchar(24) not null)"
            ),
            (
                "create unique index uq_approval_active_business "
                "on app_approval_requests (approval_type, business_ref) "
                "where status in ('submitted','info_required')"
            ),
        ):
            conn.execute(text(statement))


def verify() -> None:
    engine = ci_engine()
    with engine.begin() as conn:
        assert (
            conn.scalar(text("select version_num from alembic_version"))
            == "20261019_0045_approval_scope"
        )
        for table in (
            "app_approval_rules",
            "app_approval_rule_events",
            "app_approval_attestations",
            "app_approval_step_decisions",
            "app_approval_notifications",
        ):
            assert conn.scalar(text("select to_regclass(:table)"), {"table": table}) is not None
        assert conn.scalar(text("select count(*) from app_approval_rules")) == 5
        constraint = conn.scalar(
            text("""
                select pg_get_constraintdef(oid) from pg_constraint
                where conname='ck_dws_purchase_board_item_id_source'
            """)
        )
        assert constraint is not None and "from_listing" in constraint
        conn.execute(
            text("insert into dws_purchase_board (item_id_source) values ('from_listing')")
        )
        index_definition = conn.scalar(
            text("""
                select indexdef from pg_indexes
                where schemaname='public'
                  and indexname='uq_approval_active_business'
            """)
        )
        assert index_definition is not None
        assert "source_account_ref" in index_definition

        insert_sql = text("""
            insert into app_approval_requests (
                id, approval_type, source_account_ref, business_ref, status
            ) values (:id, 'purchase_exception', :account, 'same-ref', :status)
        """)
        first = UUID("00000000-0000-0000-0000-000000000001")
        second = UUID("00000000-0000-0000-0000-000000000002")
        third = UUID("00000000-0000-0000-0000-000000000003")
        conn.execute(
            insert_sql,
            {"id": first, "account": "account-1", "status": "submitted"},
        )
        conn.execute(
            insert_sql,
            {"id": second, "account": "account-2", "status": "submitted"},
        )
        try:
            with conn.begin_nested():
                conn.execute(
                    insert_sql,
                    {"id": third, "account": "account-1", "status": "submitted"},
                )
        except IntegrityError:
            pass
        else:
            raise AssertionError("Same-account duplicate active approval was accepted")
        conn.execute(
            insert_sql,
            {"id": third, "account": "account-1", "status": "approved"},
        )
        assert conn.scalar(text("select count(*) from app_approval_requests")) == 3


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("bootstrap", "verify"):
        raise SystemExit("Expected exactly one stage: bootstrap or verify")
    if sys.argv[1] == "bootstrap":
        bootstrap()
    else:
        verify()
