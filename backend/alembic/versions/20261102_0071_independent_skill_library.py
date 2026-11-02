"""Independent Skill library, immutable versions, supporting documents and bindings.

Legacy connector-specific Skill revisions are copied (not removed); old queued
jobs keep their original pinned version IDs. New assignments target new IDs.
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261102_0071_skill_lib"
down_revision: str | Sequence[str] | None = "20261102_0070_ai_skill_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_skill_library",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("scene", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "ai_skill_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "skill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_skill_library.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("runtime_instructions", sa.Text()),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft','published','retired')",
            name="ck_ai_skill_revisions_status",
        ),
        sa.UniqueConstraint("skill_id", "version", name="uq_ai_skill_revisions_version"),
    )
    op.create_table(
        "ai_skill_bindings",
        sa.Column(
            "connector_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("biz_connectors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scene", sa.String(64), nullable=False),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_skill_revisions.id", ondelete="RESTRICT"),
        ),
        sa.PrimaryKeyConstraint("connector_id", "scene"),
    )
    # Preserve connector grants for immutable revisions after re-binding.
    op.create_table(
        "ai_skill_revision_grants",
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_skill_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "connector_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("biz_connectors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("revision_id", "connector_id"),
    )
    op.create_table(
        "ai_skill_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_skill_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    conn = op.get_bind()
    # Copy old Skill entries into the independent catalog, without changing old
    # data or the IDs already pinned in historic keyword jobs.
    old_columns = {col["name"] for col in sa.inspect(conn).get_columns("ai_runtime_skill_versions")}
    deleted_filter = "AND deleted_at IS NULL" if "deleted_at" in old_columns else ""
    groups = (
        conn.execute(
            sa.text(
                "SELECT DISTINCT connector_id,scene FROM ai_runtime_skill_versions WHERE 1=1 "
                + deleted_filter
            )
        )
        .mappings()
        .all()
    )
    for group in groups:
        connector_id, scene = group["connector_id"], group["scene"]
        rows = (
            conn.execute(
                sa.text(
                    """SELECT version,status,instructions,runtime_instructions,created_by
                FROM ai_runtime_skill_versions
                WHERE connector_id=:connector AND scene=:scene """
                    + deleted_filter
                    + " ORDER BY version"
                ),
                {"connector": connector_id, "scene": scene},
            )
            .mappings()
            .all()
        )
        if not rows:
            continue
        sid = uuid4()
        slug = "legacy-" + connector_id.hex + "-" + scene.replace("_", "-")
        conn.execute(
            sa.text("""INSERT INTO ai_skill_library
            (id,slug,name,scene,description,created_by)
            VALUES (:id,:slug,:name,:scene,:description,:actor)"""),
            {
                "id": sid,
                "slug": slug[:80],
                "name": "旧版 Skill · " + scene,
                "scene": scene,
                "description": "从旧版服务的 Skill 记录导入，请检查规则后使用。",
                "actor": str(rows[0]["created_by"]),
            },
        )
        published = None
        for row in rows:
            rid = uuid4()
            conn.execute(
                sa.text("""INSERT INTO ai_skill_revisions
                (id,skill_id,version,status,instructions,runtime_instructions,created_by)
                VALUES (:id,:sid,:v,:status,:ins,:runtime,:actor)"""),
                {
                    "id": rid,
                    "sid": sid,
                    "v": row["version"],
                    "status": row["status"],
                    "ins": row["instructions"],
                    "runtime": row["runtime_instructions"],
                    "actor": str(row["created_by"]),
                },
            )
            if row["status"] in ("published", "retired"):
                conn.execute(
                    sa.text("""INSERT INTO ai_skill_revision_grants(revision_id,connector_id)
                        VALUES (:revision,:connector)"""),
                    {"revision": rid, "connector": connector_id},
                )
            if row["status"] == "published":
                published = rid
        if published:
            conn.execute(
                sa.text("""INSERT INTO ai_skill_bindings(connector_id,scene,revision_id)
                    VALUES (:connector,:scene,:revision)"""),
                {"connector": connector_id, "scene": scene, "revision": published},
            )


def downgrade() -> None:
    # Refuse destructive rollback when business records exist. Exporting a backup
    # alone does not authorize deleting these records.
    conn = op.get_bind()
    for table in (
        "ai_skill_documents",
        "ai_skill_bindings",
        "ai_skill_revision_grants",
        "ai_skill_revisions",
        "ai_skill_library",
    ):
        if conn.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar_one():
            raise RuntimeError("0071 rollback blocked: Skill records exist in " + table)
    op.drop_table("ai_skill_documents")
    op.drop_table("ai_skill_bindings")
    op.drop_table("ai_skill_revision_grants")
    op.drop_table("ai_skill_revisions")
    op.drop_table("ai_skill_library")
