"""Scope Listing tag definitions and assignments to one source account."""

import sqlalchemy as sa

from alembic import op

revision = "20261031_0070_listing_tag_account_scope"
down_revision = "20261031_0069_listing_evaluation_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_custom_tags",
        sa.Column("source_account_ref", sa.String(128), nullable=True),
    )
    # Preserve the first account's tag ID. Split historically shared definitions
    # for other accounts without exposing or mutating their assignments.
    op.execute(
        """
        CREATE TEMP TABLE _listing_tag_scope_map ON COMMIT DROP AS
        SELECT tag_id, source_account_ref, rn,
               CASE WHEN rn = 1 THEN tag_id ELSE gen_random_uuid() END AS scoped_tag_id
        FROM (
            SELECT tag_id, source_account_ref,
                   row_number() OVER (PARTITION BY tag_id ORDER BY source_account_ref) AS rn
            FROM (
                SELECT DISTINCT tag_id, source_account_ref
                FROM product_custom_tag_assignments
            ) assigned_accounts
        ) ranked_accounts
        """
    )
    # Conflicting definitions cannot be merged safely when colors or semantics
    # differ. Stop the migration before changing any persistent row.
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1
            FROM _listing_tag_scope_map AS mapping
            JOIN product_custom_tags AS tag ON tag.id = mapping.tag_id
            WHERE tag.deleted_at IS NULL
            GROUP BY mapping.source_account_ref, lower(tag.name)
            HAVING count(DISTINCT mapping.tag_id) > 1
          ) THEN
            RAISE EXCEPTION 'LISTING_TAG_ACCOUNT_NAME_CONFLICT';
          END IF;
        END $$
        """
    )
    op.execute(
        """
        INSERT INTO product_custom_tags
          (id, name, color, sort_order, is_active, created_at, updated_at,
           deleted_at, source_account_ref)
        SELECT mapping.scoped_tag_id, tag.name, tag.color, tag.sort_order,
               tag.is_active, tag.created_at, tag.updated_at, tag.deleted_at,
               mapping.source_account_ref
        FROM _listing_tag_scope_map AS mapping
        JOIN product_custom_tags AS tag ON tag.id = mapping.tag_id
        WHERE mapping.rn > 1
        """
    )
    op.execute(
        """
        UPDATE product_custom_tags AS tag
        SET source_account_ref = mapping.source_account_ref
        FROM _listing_tag_scope_map AS mapping
        WHERE tag.id = mapping.tag_id AND mapping.rn = 1
        """
    )
    op.execute(
        """
        UPDATE product_custom_tag_assignments AS assignment
        SET tag_id = mapping.scoped_tag_id
        FROM _listing_tag_scope_map AS mapping
        WHERE assignment.tag_id = mapping.tag_id
          AND assignment.source_account_ref = mapping.source_account_ref
          AND mapping.rn > 1
        """
    )
    op.create_check_constraint(
        "ck_product_custom_tag_account_not_blank",
        "product_custom_tags",
        "source_account_ref IS NULL OR source_account_ref <> ''",
    )
    op.create_unique_constraint(
        "uq_product_custom_tag_id_account",
        "product_custom_tags",
        ["id", "source_account_ref"],
    )
    op.create_foreign_key(
        "fk_product_custom_tag_assignment_account",
        "product_custom_tag_assignments",
        "product_custom_tags",
        ["tag_id", "source_account_ref"],
        ["id", "source_account_ref"],
    )
    op.create_index(
        "uq_product_custom_tags_account_active_name",
        "product_custom_tags",
        ["source_account_ref", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND source_account_ref IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_product_custom_tags_account_active_name", table_name="product_custom_tags")
    op.drop_constraint(
        "fk_product_custom_tag_assignment_account",
        "product_custom_tag_assignments",
        type_="foreignkey",
    )
    op.drop_constraint("uq_product_custom_tag_id_account", "product_custom_tags", type_="unique")
    op.drop_constraint(
        "ck_product_custom_tag_account_not_blank", "product_custom_tags", type_="check"
    )
    op.drop_column("product_custom_tags", "source_account_ref")
