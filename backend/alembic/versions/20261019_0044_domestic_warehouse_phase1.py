"""Add domestic warehouse phase-1 tables and the batch-board page permission.

Revision ID: 20261019_0044_domestic_warehouse_phase1
Revises: 20261017_0043_purchase_board_listing_item_source
Create Date: 2026-10-19

Tables already created by hand are left in place. This revision does not pull Lingxing
data and does not grant the new page permission to existing roles.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "20261019_0044_domestic_warehouse_phase1"
down_revision: str | Sequence[str] | None = "20261017_0043_purchase_board_listing_item_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAGE_PERMISSION = "page:pmc:domestic-warehouse-board:view"

UPGRADE_SQL = """
create table if not exists ods_lingxing_domestic_warehouses (
    id uuid primary key,
    run_id uuid not null references gov_integration_sync_runs (id) on delete restrict,
    raw_request_ref_id uuid not null references ods_api_raw_request_refs (id) on delete restrict,
    source_account_ref varchar(128) not null,
    source_item_ordinal integer not null check (source_item_ordinal >= 0),
    payload_json jsonb not null,
    observed_at timestamptz not null,
    created_at timestamptz not null,
    source_warehouse_id varchar(64) not null check (char_length(trim(source_warehouse_id)) > 0),
    warehouse_name varchar(255),
    warehouse_type varchar(64),
    sub_type varchar(64),
    unique (raw_request_ref_id, source_item_ordinal),
    unique (run_id, source_account_ref, source_warehouse_id)
);
create table if not exists ods_lingxing_domestic_inventory (
    id uuid primary key,
    run_id uuid not null references gov_integration_sync_runs (id) on delete restrict,
    raw_request_ref_id uuid not null references ods_api_raw_request_refs (id) on delete restrict,
    source_account_ref varchar(128) not null,
    source_item_ordinal integer not null check (source_item_ordinal >= 0),
    payload_json jsonb not null,
    observed_at timestamptz not null,
    created_at timestamptz not null,
    source_warehouse_id varchar(64) not null,
    product_id varchar(64),
    sku varchar(255),
    seller_id varchar(64),
    fnsku varchar(64),
    product_total integer,
    product_valid_num integer,
    product_bad_num integer,
    product_qc_num integer,
    product_lock_num integer,
    good_lock_num integer,
    quantity_receive integer,
    unique (raw_request_ref_id, source_item_ordinal)
);
create index if not exists ix_ods_domestic_inventory_wh_sku
    on ods_lingxing_domestic_inventory (source_account_ref, source_warehouse_id, sku);
create table if not exists ods_lingxing_domestic_batches (
    id uuid primary key,
    run_id uuid not null references gov_integration_sync_runs (id) on delete restrict,
    raw_request_ref_id uuid not null references ods_api_raw_request_refs (id) on delete restrict,
    source_account_ref varchar(128) not null,
    source_item_ordinal integer not null check (source_item_ordinal >= 0),
    payload_json jsonb not null,
    observed_at timestamptz not null,
    created_at timestamptz not null,
    source_warehouse_id varchar(64) not null,
    warehouse_name varchar(255),
    batch_no varchar(64),
    source_batch_no varchar(64),
    order_sn varchar(64),
    batch_type integer,
    batch_type_name varchar(64),
    sku varchar(255),
    product_id varchar(64),
    product_name text,
    store_id varchar(64),
    store_name varchar(255),
    msku varchar(255),
    fnsku varchar(64),
    total_qty integer,
    balance_num integer,
    good_num integer,
    bad_num integer,
    qc_num integer,
    purchase_order_sns text,
    purchase_in_time varchar(32),
    batch_time varchar(32),
    unique (raw_request_ref_id, source_item_ordinal)
);
create index if not exists ix_ods_domestic_batches_ib_sku
    on ods_lingxing_domestic_batches (source_account_ref, order_sn, sku, store_id);
create table if not exists ods_lingxing_domestic_inventory_events (
    id uuid primary key,
    run_id uuid not null references gov_integration_sync_runs (id) on delete restrict,
    raw_request_ref_id uuid not null references ods_api_raw_request_refs (id) on delete restrict,
    source_account_ref varchar(128) not null,
    source_item_ordinal integer not null check (source_item_ordinal >= 0),
    payload_json jsonb not null,
    observed_at timestamptz not null,
    created_at timestamptz not null,
    statement_id varchar(64),
    source_warehouse_id varchar(64) not null,
    warehouse_name varchar(255),
    order_sn varchar(64),
    ref_order_sn varchar(64),
    sku varchar(255),
    product_id varchar(64),
    seller_id varchar(64),
    fnsku varchar(64),
    event_type integer,
    sub_type integer,
    product_good_num integer,
    product_bad_num integer,
    product_qc_num integer,
    opt_time varchar(32),
    remark text,
    unique (raw_request_ref_id, source_item_ordinal)
);
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
    bind.execute(text(UPGRADE_SQL))
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
            drop table if exists ods_lingxing_domestic_inventory_events;
            drop index if exists ix_ods_domestic_batches_ib_sku;
            drop table if exists ods_lingxing_domestic_batches;
            drop index if exists ix_ods_domestic_inventory_wh_sku;
            drop table if exists ods_lingxing_domestic_inventory;
            drop table if exists ods_lingxing_domestic_warehouses;
            """
        )
    )
