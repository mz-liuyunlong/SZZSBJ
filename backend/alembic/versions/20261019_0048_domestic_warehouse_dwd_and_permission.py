"""Domestic warehouse DWD read models and batch-board page permission.

Revision ID: 20261019_0048_domestic_warehouse_dwd_and_permission
Revises: 20261019_0047_domestic_warehouse_ods

ODS four tables are created or adopted in 0047. This revision adds DWD tables and the
page permission only. It does not pull Lingxing data or grant the permission to roles.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "20261019_0048_domestic_warehouse_dwd_and_permission"
down_revision: str | Sequence[str] | None = "20261019_0047_domestic_warehouse_ods"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAGE_PERMISSION = "page:pmc:domestic-warehouse-board:view"

DWD_UPGRADE_SQL = """
create table if not exists dwd_domestic_receipt_batch (
    id uuid primary key,
    source_account_ref varchar(128) not null,
    source_run_id uuid not null references gov_integration_sync_runs (id) on delete restrict,
    source_ods_id uuid not null,
    source_observed_at timestamptz not null,
    provider_update_time varchar(32),
    builder_version varchar(64) not null,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    receipt_order_sn varchar(64) not null check (char_length(trim(receipt_order_sn)) > 0),
    line_ordinal integer not null check (line_ordinal >= 0),
    purchase_order_sn varchar(64),
    source_warehouse_id varchar(64),
    sku varchar(255),
    received_qty integer,
    receive_time varchar(32),
    received_business_date date,
    unique (source_account_ref, receipt_order_sn, line_ordinal)
);
create table if not exists dwd_domestic_receipt_batch_link (
    id uuid primary key,
    source_account_ref varchar(128) not null,
    receipt_batch_id uuid not null references dwd_domestic_receipt_batch (id) on delete restrict,
    batch_order_sn varchar(64),
    batch_no varchar(64),
    store_id varchar(64),
    mapped_qty integer,
    mapping_status varchar(32) not null default 'unresolved'
        check (mapping_status in ('unresolved', 'matched')),
    mapping_method varchar(64),
    created_at timestamptz not null,
    updated_at timestamptz not null
);
create index if not exists ix_dwd_domestic_receipt_batch_link_batch
    on dwd_domestic_receipt_batch_link (receipt_batch_id);
"""


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text(DWD_UPGRADE_SQL))
    bind.execute(
        text(
            """
            insert into app_permissions (
                permission_key, name, group_key, description, permission_type,
                module_key, page_key, action_key, field_key, risk_level,
                sort_order, is_active, created_at, updated_at
            )
            values (
                :permission_key,
                '国内仓看板',
                'pmc',
                '允许进入并查看「国内仓看板」页面',
                'page',
                'pmc',
                'pmc_domestic_warehouse_board',
                null,
                null,
                'normal',
                100020,
                true,
                now(),
                now()
            )
            on conflict (permission_key) do update set
                name = excluded.name,
                description = excluded.description,
                is_active = true,
                updated_at = now()
            """
        ),
        {"permission_key": PAGE_PERMISSION},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text("delete from app_role_permissions where permission_key = :permission_key"),
        {"permission_key": PAGE_PERMISSION},
    )
    bind.execute(
        text("delete from app_permissions where permission_key = :permission_key"),
        {"permission_key": PAGE_PERMISSION},
    )
    bind.execute(
        text(
            """
            drop index if exists ix_dwd_domestic_receipt_batch_link_batch;
            drop table if exists dwd_domestic_receipt_batch_link;
            drop table if exists dwd_domestic_receipt_batch;
            """
        )
    )
