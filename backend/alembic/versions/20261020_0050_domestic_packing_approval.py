"""Four operational tables; no historical approvals or role grants are seeded."""

# Keep already-applied DDL text verbatim; long SQL literals are intentionally stable.
# ruff: noqa: E501

from sqlalchemy import text

from alembic import op

revision = "20261020_0050_domestic_packing_approval"
down_revision = "20261020_0049_domestic_inbound_board"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE ops_domestic_pk_sequences (
 business_date date PRIMARY KEY, last_value integer NOT NULL CHECK(last_value BETWEEN 1 AND 999)
);
CREATE TABLE ops_domestic_packing_orders (
 id uuid PRIMARY KEY, source_account_ref varchar(128) NOT NULL, warehouse_id varchar(64) NOT NULL,
 candidate_id uuid NOT NULL, inbound_order_sn varchar(64) NOT NULL, sku varchar(255) NOT NULL,
 store_id varchar(64), item_id varchar(64), pk varchar(32) UNIQUE, qty integer,
 customs_value boolean, customs_src varchar(16) NOT NULL, rwh varchar(128),
 is_test boolean NOT NULL CHECK(is_test), status varchar(24) NOT NULL CHECK(status IN ('approved','rejected')),
 version integer NOT NULL CHECK(version>0),source_publication_id uuid NOT NULL,source_board_id uuid NOT NULL,
 snapshot_json jsonb NOT NULL,actor_uid varchar(128) NOT NULL,note varchar(500),
 created_at timestamptz NOT NULL,updated_at timestamptz NOT NULL,
 UNIQUE(source_account_ref,candidate_id),
 FOREIGN KEY(source_publication_id,source_board_id) REFERENCES mart_domestic_inbound_batch_board(publication_id,id) ON DELETE RESTRICT,
 CHECK((status='approved' AND pk IS NOT NULL AND qty BETWEEN 1 AND 1000000) OR (status='rejected' AND pk IS NULL AND qty IS NULL)),
 CHECK(status<>'rejected' OR length(trim(note))>0)
);
CREATE INDEX ix_domestic_packing_orders_scope ON ops_domestic_packing_orders(source_account_ref,warehouse_id,created_at DESC,id);
CREATE TABLE ops_domestic_packing_allocations (
 id uuid PRIMARY KEY,order_id uuid NOT NULL UNIQUE REFERENCES ops_domestic_packing_orders(id) ON DELETE RESTRICT,
 source_account_ref varchar(128) NOT NULL,warehouse_id varchar(64) NOT NULL,
 source_board_id uuid NOT NULL,source_publication_id uuid NOT NULL,qty integer NOT NULL CHECK(qty>0),
 FOREIGN KEY(source_publication_id,source_board_id) REFERENCES mart_domestic_inbound_batch_board(publication_id,id) ON DELETE RESTRICT
);
CREATE INDEX ix_domestic_packing_allocation_source ON ops_domestic_packing_allocations(source_account_ref,warehouse_id,source_board_id);
CREATE TABLE evt_domestic_packing_events (
 id uuid PRIMARY KEY,order_id uuid NOT NULL REFERENCES ops_domestic_packing_orders(id) ON DELETE RESTRICT,
 source_account_ref varchar(128) NOT NULL,idempotency_key uuid NOT NULL,actor_uid varchar(128) NOT NULL,
 event_kind varchar(24) NOT NULL CHECK(event_kind IN ('approve','reject')),
 order_version integer NOT NULL CHECK(order_version>0),request_hash varchar(64) NOT NULL,
 request_json jsonb NOT NULL,response_json jsonb NOT NULL,occurred_at timestamptz NOT NULL,
 UNIQUE(source_account_ref,idempotency_key),UNIQUE(order_id,order_version)
);
CREATE FUNCTION prevent_domestic_packing_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'DOMESTIC_PACKING_EVENT_IMMUTABLE'; END;
$$;
CREATE TRIGGER domestic_packing_event_immutable BEFORE UPDATE OR DELETE ON evt_domestic_packing_events
 FOR EACH ROW EXECUTE FUNCTION prevent_domestic_packing_event_mutation();
"""


def upgrade():
    bind = op.get_bind()
    bind.execute(text(DDL))
    for action, label in (
        ("packing-approve", "通过打包审批"),
        ("packing-reject", "驳回打包审批"),
    ):
        bind.execute(
            text("""INSERT INTO app_permissions
         (permission_key,name,group_key,description,permission_type,module_key,page_key,action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
         VALUES (:key,:label,'pmc',:label,'action','pmc','pmc_domestic_warehouse_board',:action,NULL,'normal',100021,true,now(),now())
         ON CONFLICT(permission_key) DO NOTHING"""),
            {
                "key": "action:pmc:domestic-warehouse-board:" + action,
                "label": label,
                "action": action,
            },
        )


def downgrade():
    bind = op.get_bind()
    if bind.scalar(text("SELECT count(*) FROM ops_domestic_packing_orders")):
        raise RuntimeError("PACKING_AUDIT_REQUIRES_RETENTION_NO_DESTRUCTIVE_DOWNGRADE")
    for action in ("packing-approve", "packing-reject"):
        key = "action:pmc:domestic-warehouse-board:" + action
        if bind.scalar(
            text("SELECT count(*) FROM app_role_permissions WHERE permission_key=:key"),
            {"key": key},
        ):
            raise RuntimeError("PACKING_PERMISSION_IN_USE")
        bind.execute(
            text("DELETE FROM app_permissions WHERE permission_key=:key"), {"key": key}
        )
    bind.execute(
        text(
            "DROP TABLE evt_domestic_packing_events; DROP FUNCTION prevent_domestic_packing_event_mutation(); DROP TABLE ops_domestic_packing_allocations; DROP TABLE ops_domestic_packing_orders; DROP TABLE ops_domestic_pk_sequences;"
        )
    )
