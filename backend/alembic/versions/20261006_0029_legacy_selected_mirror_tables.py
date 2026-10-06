"""add legacy selected mirror tables

Revision ID: 20261006_0029_legacy_selected_mirror_tables
Revises: 20260929_0028_listing_archive_reason
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "20261006_0029_legacy_selected_mirror_tables"
down_revision: str | Sequence[str] | None = "20260929_0028_listing_archive_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute_statements(statements: Sequence[str]) -> None:
    bind = op.get_bind()
    for statement in statements:
        bind.execute(text(statement))


def upgrade() -> None:
    _execute_statements(
        [
            "create schema if not exists legacy_mirror",
            (
                "comment on schema legacy_mirror is "
                "'Temporary selected legacy MySQL mirror; not a formal business model.'"
            ),
            """
            create table if not exists legacy_mirror.biz_product_operation_log (
                id bigint primary key,
                log_date date not null,
                editable_date date not null,
                platform varchar(32) not null,
                store_id varchar(64) not null,
                store_name varchar(128) not null,
                store_key varchar(128) not null,
                item_id varchar(64) not null,
                msku varchar(128) not null,
                owner varchar(128),
                profit_level_snapshot varchar(32),
                data_issue text,
                solution text,
                log_content text,
                ai_diagnosis text,
                is_locked smallint not null,
                source varchar(64) not null,
                source_raw_id bigint,
                source_row_no integer,
                created_by varchar(64) not null,
                updated_by varchar(64) not null,
                created_at timestamp not null,
                updated_at timestamp not null
            )
            """,
            (
                "comment on table legacy_mirror.biz_product_operation_log is "
                "'Temporary mirror of legacy biz_product_operation_log.'"
            ),
            (
                "create index if not exists ix_legacy_bpol_log_date "
                "on legacy_mirror.biz_product_operation_log (log_date)"
            ),
            (
                "create index if not exists ix_legacy_bpol_editable_date "
                "on legacy_mirror.biz_product_operation_log (editable_date)"
            ),
            (
                "create index if not exists ix_legacy_bpol_store_id "
                "on legacy_mirror.biz_product_operation_log (store_id)"
            ),
            (
                "create index if not exists ix_legacy_bpol_store_key "
                "on legacy_mirror.biz_product_operation_log (store_key)"
            ),
            (
                "create index if not exists ix_legacy_bpol_msku "
                "on legacy_mirror.biz_product_operation_log (msku)"
            ),
            (
                "create index if not exists ix_legacy_bpol_owner "
                "on legacy_mirror.biz_product_operation_log (owner)"
            ),
            (
                "create index if not exists ix_legacy_bpol_source_raw_id "
                "on legacy_mirror.biz_product_operation_log (source_raw_id)"
            ),
            (
                "create index if not exists ix_legacy_bpol_updated_at "
                "on legacy_mirror.biz_product_operation_log (updated_at)"
            ),
            """
            create table if not exists legacy_mirror.event_wfs_fee_case (
                id bigint primary key,
                platform varchar(20) not null,
                store_id varchar(64) not null,
                store_name varchar(255) not null,
                item_id varchar(64) not null,
                msku varchar(128) not null,
                owner_name varchar(64) not null,
                manual_fee numeric(10,4) not null,
                actual_fee numeric(10,4) not null,
                total_units integer not null,
                est_recover numeric(12,2) not null,
                status varchar(16) not null,
                case_nos varchar(255) not null,
                reason varchar(500) not null,
                follow_log text,
                log_updated_at timestamp,
                claim_amount numeric(12,2),
                recovered_amount numeric(12,2),
                decided_by varchar(64) not null,
                approved_by varchar(64) not null,
                approved_at timestamp,
                done_at timestamp,
                first_alert_at timestamp,
                remark varchar(255) not null,
                created_at timestamp not null,
                updated_at timestamp not null
            )
            """,
            (
                "comment on table legacy_mirror.event_wfs_fee_case is "
                "'Temporary mirror of legacy event_wfs_fee_case.'"
            ),
            (
                "create index if not exists ix_legacy_wfs_case_platform "
                "on legacy_mirror.event_wfs_fee_case (platform)"
            ),
            (
                "create index if not exists ix_legacy_wfs_case_status "
                "on legacy_mirror.event_wfs_fee_case (status)"
            ),
            (
                "create index if not exists ix_legacy_wfs_case_store_id "
                "on legacy_mirror.event_wfs_fee_case (store_id)"
            ),
            (
                "create index if not exists ix_legacy_wfs_case_updated_at "
                "on legacy_mirror.event_wfs_fee_case (updated_at)"
            ),
            """
            create table if not exists legacy_mirror.event_ops_action_log (
                id bigint primary key,
                event_date date not null,
                platform varchar(32) not null,
                store_id varchar(64) not null,
                store_name varchar(255) not null,
                item_id varchar(64) not null,
                msku varchar(128) not null,
                action_type varchar(40) not null,
                object_type varchar(24) not null,
                object_id varchar(64) not null,
                object_name varchar(512) not null,
                old_value varchar(255) not null,
                new_value varchar(255) not null,
                verify_status varchar(24) not null,
                verify_window varchar(24) not null,
                matched_orders integer not null,
                checked_orders integer not null,
                log_content text not null,
                highlight smallint not null,
                ad_group_name varchar(512) not null,
                match_type varchar(32) not null,
                source varchar(32) not null,
                operator varchar(128) not null,
                detected_at timestamp not null,
                created_at timestamp not null,
                updated_at timestamp not null
            )
            """,
            (
                "comment on table legacy_mirror.event_ops_action_log is "
                "'Temporary mirror of legacy snapshot-diff operation events; not an audit log.'"
            ),
            (
                "create index if not exists ix_legacy_ops_action_event_date "
                "on legacy_mirror.event_ops_action_log (event_date)"
            ),
            (
                "create index if not exists ix_legacy_ops_action_platform "
                "on legacy_mirror.event_ops_action_log (platform)"
            ),
            (
                "create index if not exists ix_legacy_ops_action_store_id "
                "on legacy_mirror.event_ops_action_log (store_id)"
            ),
            (
                "create index if not exists ix_legacy_ops_action_action_type "
                "on legacy_mirror.event_ops_action_log (action_type)"
            ),
            (
                "create index if not exists ix_legacy_ops_action_updated_at "
                "on legacy_mirror.event_ops_action_log (updated_at)"
            ),
            """
            create table if not exists legacy_mirror.raw_walmart_sem_csv (
                id bigint primary key,
                task_id varchar(40) not null,
                row_index integer not null,
                csv_type varchar(20) not null,
                row_json jsonb not null,
                report_date varchar(20),
                store_id varchar(64) not null,
                store_name varchar(255),
                operator varchar(128),
                raw_hash varchar(64) not null,
                created_at timestamp not null
            )
            """,
            (
                "comment on table legacy_mirror.raw_walmart_sem_csv is "
                "'Temporary mirror of legacy SEM daily and billing raw CSV rows.'"
            ),
            (
                "create index if not exists ix_legacy_sem_task_id "
                "on legacy_mirror.raw_walmart_sem_csv (task_id)"
            ),
            (
                "create index if not exists ix_legacy_sem_csv_type "
                "on legacy_mirror.raw_walmart_sem_csv (csv_type)"
            ),
            (
                "create index if not exists ix_legacy_sem_store_id "
                "on legacy_mirror.raw_walmart_sem_csv (store_id)"
            ),
            (
                "create index if not exists ix_legacy_sem_created_at "
                "on legacy_mirror.raw_walmart_sem_csv (created_at)"
            ),
            """
            create table if not exists app_users (
                id integer primary key,
                username varchar(64) not null unique,
                feishu_member_id varchar(64),
                password_hash varchar(255) not null,
                is_active smallint not null,
                created_at timestamp not null,
                updated_at timestamp not null
            )
            """,
            (
                "comment on table app_users is "
                "'Users copied from legacy dim_app_user. Credentials are copied as-is; "
                "this migration does not enable login.'"
            ),
            (
                "create index if not exists ix_app_users_feishu_member_id "
                "on app_users (feishu_member_id)"
            ),
            "create index if not exists ix_app_users_is_active on app_users (is_active)",
        ]
    )


def downgrade() -> None:
    _execute_statements(
        [
            "drop table if exists app_users",
            "drop table if exists legacy_mirror.raw_walmart_sem_csv",
            "drop table if exists legacy_mirror.event_ops_action_log",
            "drop table if exists legacy_mirror.event_wfs_fee_case",
            "drop table if exists legacy_mirror.biz_product_operation_log",
            "drop schema if exists legacy_mirror",
        ]
    )
