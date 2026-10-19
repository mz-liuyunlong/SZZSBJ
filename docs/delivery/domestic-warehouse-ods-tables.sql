-- Domestic warehouse Lingxing ODS (4 tables). Reference DDL aligned with ORM + Alembic 0047.
-- Do not run on production after Alembic 0047 is applied; use migrations instead.
-- Historical note: production received these tables via manual execution before 0047 landed in Git.

create table ods_lingxing_domestic_warehouses (
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

create table ods_lingxing_domestic_inventory (
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

create index ix_ods_domestic_inventory_wh_sku
    on ods_lingxing_domestic_inventory (source_account_ref, source_warehouse_id, sku);

create table ods_lingxing_domestic_batches (
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

create index ix_ods_domestic_batches_ib_sku
    on ods_lingxing_domestic_batches (source_account_ref, order_sn, sku, store_id);

create table ods_lingxing_domestic_inventory_events (
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
