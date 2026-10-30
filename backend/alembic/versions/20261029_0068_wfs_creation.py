"""Add WFS V2 operations; preserve all legacy drafts and allocations."""

import sqlalchemy as sa

from alembic import op

revision = "20261029_0068_wfs_creation"
down_revision = "20261028_0067_merge_pmc_main"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        
        CREATE TABLE ops_wfs_creation_operations (
        id UUID NOT NULL,
        order_id UUID NOT NULL,
        source_account_ref VARCHAR(128) NOT NULL,
        store_id VARCHAR(64) NOT NULL,
        idempotency_key UUID NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        snapshot JSONB NOT NULL,
        actor_uid VARCHAR(128) NOT NULL,
        state VARCHAR(16) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT pk_ops_wfs_creation_operations PRIMARY KEY (id),
        CONSTRAINT uq_ops_wfs_creation_operations_source_account_ref UNIQUE
        (source_account_ref, idempotency_key),
        CONSTRAINT wfs_creation_state CHECK (state IN
        ('QUEUED','RUNNING','SUCCEEDED','FAILED','UNKNOWN','PARTIAL')),
        CONSTRAINT fk_ops_wfs_creation_operations_order_id_ops_domestic_pa_d027 FOREIGN
        KEY(order_id) REFERENCES ops_domestic_packing_orders (id) ON DELETE RESTRICT
        )
        
        """
    )
    op.execute(
        """
        CREATE INDEX ix_ops_wfs_creation_operations_order_id ON ops_wfs_creation_operations
        (order_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_ops_wfs_creation_operations_source_account_ref ON
        ops_wfs_creation_operations (source_account_ref)
        """
    )
    op.execute(
        """
        
        CREATE TABLE ops_wfs_creation_tickets (
        id UUID NOT NULL,
        operation_id UUID NOT NULL,
        number INTEGER NOT NULL,
        state VARCHAR(16) NOT NULL,
        allocation JSONB NOT NULL,
        result JSONB NOT NULL,
        error_code VARCHAR(64),
        CONSTRAINT pk_ops_wfs_creation_tickets PRIMARY KEY (id),
        CONSTRAINT uq_ops_wfs_creation_tickets_operation_id UNIQUE (operation_id, number),
        CONSTRAINT wfs_ticket_number CHECK (number > 0),
        CONSTRAINT wfs_ticket_state CHECK (state IN
        ('QUEUED','RUNNING','SUCCEEDED','FAILED','UNKNOWN')),
        CONSTRAINT fk_ops_wfs_creation_tickets_operation_id_ops_wfs_creati_5958 FOREIGN
        KEY(operation_id) REFERENCES ops_wfs_creation_operations (id) ON DELETE RESTRICT
        )
        
        """
    )
    op.execute(
        """
        CREATE INDEX ix_ops_wfs_creation_tickets_operation_id ON ops_wfs_creation_tickets
        (operation_id)
        """
    )
    op.execute(
        """
        
        CREATE TABLE ops_wfs_box_holds (
        id UUID NOT NULL,
        ticket_id UUID NOT NULL,
        order_id UUID NOT NULL,
        box_line_id UUID NOT NULL,
        box_version INTEGER NOT NULL,
        box_ordinal INTEGER NOT NULL,
        CONSTRAINT pk_ops_wfs_box_holds PRIMARY KEY (id),
        CONSTRAINT uq_ops_wfs_box_holds_box_line_id UNIQUE (box_line_id, box_version,
        box_ordinal),
        CONSTRAINT wfs_hold_positive CHECK (box_version > 0 AND box_ordinal > 0),
        CONSTRAINT fk_ops_wfs_box_holds_ticket_id_ops_wfs_creation_tickets FOREIGN
        KEY(ticket_id) REFERENCES ops_wfs_creation_tickets (id) ON DELETE RESTRICT,
        CONSTRAINT fk_ops_wfs_box_holds_order_id_ops_domestic_packing_orders FOREIGN
        KEY(order_id) REFERENCES ops_domestic_packing_orders (id) ON DELETE RESTRICT,
        CONSTRAINT fk_ops_wfs_box_holds_box_line_id_ops_domestic_packing_box_lines FOREIGN
        KEY(box_line_id) REFERENCES ops_domestic_packing_box_lines (id) ON DELETE RESTRICT
        )
        
        """
    )
    op.execute("CREATE INDEX ix_ops_wfs_box_holds_box_line_id ON ops_wfs_box_holds (box_line_id)")
    op.execute("CREATE INDEX ix_ops_wfs_box_holds_order_id ON ops_wfs_box_holds (order_id)")
    op.execute("CREATE INDEX ix_ops_wfs_box_holds_ticket_id ON ops_wfs_box_holds (ticket_id)")
    op.execute(
        """
        
        CREATE TABLE evt_wfs_creation_events (
        id UUID NOT NULL,
        operation_id UUID NOT NULL,
        actor_uid VARCHAR(128) NOT NULL,
        kind VARCHAR(40) NOT NULL,
        evidence JSONB NOT NULL,
        occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT pk_evt_wfs_creation_events PRIMARY KEY (id),
        CONSTRAINT fk_evt_wfs_creation_events_operation_id_ops_wfs_creatio_21a9 FOREIGN
        KEY(operation_id) REFERENCES ops_wfs_creation_operations (id) ON DELETE RESTRICT
        )
        
        """
    )
    op.execute(
        """
        CREATE INDEX ix_evt_wfs_creation_events_operation_id ON evt_wfs_creation_events
        (operation_id)
        """
    )
    op.execute(
        """
        CREATE FUNCTION prevent_wfs_creation_event_change() RETURNS trigger AS $$ BEGIN RAISE
        EXCEPTION 'WFS creation events are immutable'; END; $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER wfs_creation_event_immutable BEFORE UPDATE OR DELETE ON
        evt_wfs_creation_events FOR EACH ROW EXECUTE FUNCTION
        prevent_wfs_creation_event_change()
        """
    )


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM ops_wfs_creation_operations)")):
        raise RuntimeError("WFS V2 has records; retain schema and audit evidence")
    if bind.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM ops_wfs_creation_tickets)")):
        raise RuntimeError("WFS V2 has records; retain schema and audit evidence")
    if bind.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM ops_wfs_box_holds)")):
        raise RuntimeError("WFS V2 has records; retain schema and audit evidence")
    if bind.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM evt_wfs_creation_events)")):
        raise RuntimeError("WFS V2 has records; retain schema and audit evidence")
    op.execute("DROP TRIGGER wfs_creation_event_immutable ON evt_wfs_creation_events")
    op.execute("DROP FUNCTION prevent_wfs_creation_event_change()")
    op.drop_table("evt_wfs_creation_events")
    op.drop_table("ops_wfs_box_holds")
    op.drop_table("ops_wfs_creation_tickets")
    op.drop_table("ops_wfs_creation_operations")
