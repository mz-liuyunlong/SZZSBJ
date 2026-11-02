"""WFS exception center cases and event timelines."""

from sqlalchemy import text

from alembic import op

revision = "20261029_0069_wfs_exception_center"
down_revision = "20261029_0068_wfs_creation"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE ops_wfs_exception_cases (
            id UUID NOT NULL,
            dedupe_key VARCHAR(512) NOT NULL,
            source_account_ref VARCHAR(128) NOT NULL,
            store_id VARCHAR(64) NOT NULL,
            shipment_id VARCHAR(128) NOT NULL,
            shipment_row_id VARCHAR(256),
            ticket_id UUID,
            rule_family VARCHAR(64) NOT NULL,
            severity VARCHAR(16) NOT NULL,
            status VARCHAR(32) NOT NULL,
            summary TEXT NOT NULL,
            assignee_user_id VARCHAR(128),
            platform_case_ref VARCHAR(128),
            due_at TIMESTAMP WITH TIME ZONE,
            due_basis TEXT,
            pk VARCHAR(64),
            sku VARCHAR(128),
            item_id VARCHAR(64),
            gtin VARCHAR(32),
            msku VARCHAR(128),
            qty_variance INTEGER,
            business_test BOOLEAN NOT NULL DEFAULT FALSE,
            evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
            rule_version VARCHAR(64) NOT NULL DEFAULT 'M1_STUB',
            version INTEGER NOT NULL DEFAULT 1,
            first_detected_at TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            CONSTRAINT pk_ops_wfs_exception_cases PRIMARY KEY (id),
            CONSTRAINT uq_ops_wfs_exception_cases_dedupe_key UNIQUE (dedupe_key),
            CONSTRAINT wfs_exception_severity CHECK (severity IN ('HIGH','MEDIUM','LOW')),
            CONSTRAINT wfs_exception_status CHECK (
                status IN ('OPEN','IN_PROGRESS','WAITING_EXTERNAL','RESOLVED','CLOSED')
            ),
            CONSTRAINT wfs_exception_version CHECK (version >= 1)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_ops_wfs_exception_cases_account_store ON "
        "ops_wfs_exception_cases (source_account_ref, store_id)"
    )
    op.execute(
        "CREATE INDEX ix_ops_wfs_exception_cases_shipment ON ops_wfs_exception_cases (shipment_id)"
    )
    op.execute("CREATE INDEX ix_ops_wfs_exception_cases_status ON ops_wfs_exception_cases (status)")
    op.execute(
        """
        CREATE TABLE evt_wfs_exception_detections (
            id UUID NOT NULL,
            case_id UUID NOT NULL,
            outcome VARCHAR(32) NOT NULL,
            rule_version VARCHAR(64) NOT NULL,
            evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
            detected_at TIMESTAMP WITH TIME ZONE NOT NULL,
            CONSTRAINT pk_evt_wfs_exception_detections PRIMARY KEY (id),
            CONSTRAINT fk_evt_wfs_exception_detections_case FOREIGN KEY (case_id)
                REFERENCES ops_wfs_exception_cases (id) ON DELETE RESTRICT,
            CONSTRAINT wfs_exception_detection_outcome CHECK (
                outcome IN ('HIT','MISS','CANNOT_JUDGE')
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_evt_wfs_exception_detections_case "
        "ON evt_wfs_exception_detections (case_id)"
    )
    op.execute(
        """
        CREATE TABLE evt_wfs_exception_actions (
            id UUID NOT NULL,
            case_id UUID NOT NULL,
            action_type VARCHAR(32) NOT NULL,
            actor_uid VARCHAR(128) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            CONSTRAINT pk_evt_wfs_exception_actions PRIMARY KEY (id),
            CONSTRAINT fk_evt_wfs_exception_actions_case FOREIGN KEY (case_id)
                REFERENCES ops_wfs_exception_cases (id) ON DELETE RESTRICT,
            CONSTRAINT wfs_exception_action_type CHECK (
                action_type IN ('ASSIGN','NOTE','RESOLVE','CLOSE','REOPEN','MARK_WAITING')
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_evt_wfs_exception_actions_case ON evt_wfs_exception_actions (case_id)"
    )


EXCEPTION_TABLES = (
    "evt_wfs_exception_actions",
    "evt_wfs_exception_detections",
    "ops_wfs_exception_cases",
)


def downgrade():
    # Data protection (DATABASE_MIGRATION_RULES): cases and their append-only timelines are
    # business records. Never drop them while any row exists; an operator must back up and
    # clear them under a separate, approved plan first. Empty tables may be dropped.
    # Names resolve through search_path (public in production, a throwaway schema in tests).
    conn = op.get_bind()
    populated = [
        table
        for table in EXCEPTION_TABLES
        if conn.scalar(text("select to_regclass(:name)"), {"name": table}) is not None
        and conn.scalar(text(f'select exists (select 1 from "{table}" limit 1)'))
    ]
    if populated:
        raise RuntimeError(
            "WFS_EXCEPTION_DOWNGRADE_BLOCKED: tables contain data: " + ", ".join(populated)
        )
    for table in EXCEPTION_TABLES:
        op.drop_table(table)
