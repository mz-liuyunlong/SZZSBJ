"""WFS settings: versioned time / reminder rules, FC region choice, creation defaults and
the change log (PRP ``PRPs/pmc-wfs-settings.md`` §4, PR-S2; Rocky 2026-11-03 approved).

Frozen explicit DDL on a local MetaData with the project naming convention (same approach
as 0076); ``tests/modules/pmc_wfs/test_settings.py::test_migration_0077_matches_orm_metadata``
compares it with ``app.modules.pmc_wfs.settings_models``. Seeds rule version 1 with the 11
8088 default rows (data copied here, not imported, so the migration stays frozen).
Downgrade refuses once anything beyond the seed exists.
"""

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261103_0077_wfs_settings"
down_revision = "20261103_0076_wfs_source_files"
branch_labels = None
depends_on = None

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
TABLES = (
    "ref_wfs_rule_setting_versions",
    "ref_wfs_rule_settings",
    "ref_wfs_fc_regions",
    "ref_wfs_creation_defaults",
    "evt_wfs_settings_changes",
)
J = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
SEED_VERSION_ID = "5f0a7d3e-7c2b-4b8e-9a61-0d0c20261010"
SEED_ROWS = (
    (
        "deliveredNotSigned",
        "货代签收 → Walmart 未签收且 Received = 0",
        "全部",
        "全部",
        "全部",
        3,
        0,
        "2026-10-10",
        "物流组 · WFS 组（飞书）",
        "Rocky 2026-10-10 定：货代签收满 3 天；Walmart 一签收即停止本条",
        True,
    ),
    (
        "draftRemind",
        "待创建货件未处理",
        "—",
        "—",
        "—",
        3,
        0,
        "2026-09-21",
        "WFS 组（企业微信）",
        "不自动释放，只提醒",
        True,
    ),
    (
        "internalWarn",
        "收货差异内部预警（自 D0）",
        "全部",
        "全部",
        "全部",
        7,
        0,
        "2026-09-21",
        "WFS 组",
        "D+7 公司内部规则（v3 §21）",
        True,
    ),
    (
        "etaOverdue",
        "预计到仓已过 → Walmart 未签收",
        "全部",
        "全部",
        "全部",
        7,
        2,
        "2026-09-21",
        "物流组 · WFS 组",
        "示例阈值；预计到仓取领星 arrival_time（待核实）",
        False,
    ),
    (
        "diffTol",
        "短少容差（单个 SKU 差异 ≤ N 件不算异常；超收不算异常）",
        "全部",
        "全部",
        "全部",
        10,
        0,
        "2026-10-10",
        "WFS 组",
        "Rocky 2026-10-10 定（可配置）",
        True,
    ),
    (
        "signNoReceipt",
        "Walmart 签收 → 开始上架（满 N 天无 Receipt）",
        "全部",
        "全部",
        "全部",
        10,
        0,
        "2026-10-10",
        "WFS 组",
        "Rocky 2026-10-10 定：自 Walmart 签收日起预留 10 天",
        True,
    ),
    (
        "receivingStuck",
        "Walmart 签收 → 收完（满 N 天未收完 = 收货长期未完成）",
        "全部",
        "全部",
        "全部",
        15,
        0,
        "2026-10-10",
        "WFS 组",
        "Rocky 2026-10-10 定：自 Walmart 签收日起算，单级，不设提示级",
        True,
    ),
    (
        "pendingNoShip",
        "创建后长期未发货",
        "—",
        "—",
        "—",
        7,
        0,
        "2026-09-21",
        "仓库 · WFS 组",
        "示例阈值，待 Rocky 定",
        False,
    ),
    (
        "disputeUrgent",
        "Dispute 临近截止提醒（剩余天数 ≤）",
        "全部",
        "全部",
        "全部",
        5,
        0,
        "2026-09-21",
        "WFS 组 · 主管（钉钉）",
        "示例阈值",
        False,
    ),
    (
        "portToDelivered",
        "到港 → 物流 Delivered 超时",
        "美西",
        "全部",
        "全部",
        5,
        1,
        "2026-09-21",
        "物流组",
        "示例：按地区分别配置",
        False,
    ),
    (
        "portToDelivered",
        "到港 → 物流 Delivered 超时",
        "美东",
        "全部",
        "全部",
        8,
        1,
        "2026-09-21",
        "物流组",
        "示例：美东卡派更久",
        False,
    ),
)


def _tables(metadata: sa.MetaData) -> list[sa.Table]:
    tz = sa.DateTime(timezone=True)
    versions = sa.Table(
        "ref_wfs_rule_setting_versions",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", tz, nullable=False),
        sa.UniqueConstraint("version_no"),
        sa.CheckConstraint("version_no >= 1", name="wfs_rule_version_no"),
        sa.Index("ix_wfs_rule_version_effective", "effective_date", "version_no"),
    )
    rules = sa.Table(
        "ref_wfs_rule_settings",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("ref_wfs_rule_setting_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("rule_key", sa.String(64), nullable=True),
        sa.Column("node", sa.String(255), nullable=False),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("carrier", sa.String(128), nullable=False),
        sa.Column("channel", sa.String(128), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("remind_days", sa.Integer(), nullable=False),
        sa.Column("row_effective_date", sa.Date(), nullable=False),
        sa.Column("notify", sa.String(255), nullable=False),
        sa.Column("remark", sa.Text(), nullable=False),
        sa.Column("decided", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("version_id", "row_no"),
        sa.CheckConstraint("days >= 0 AND remind_days >= 0", name="wfs_rule_setting_days"),
    )
    regions = sa.Table(
        "ref_wfs_fc_regions",
        metadata,
        sa.Column("fc", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=True),
        sa.Column("region", sa.String(16), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at", tz, nullable=False),
        sa.CheckConstraint("region IN ('美西','美中','美东','待定')", name="wfs_fc_region_value"),
    )
    defaults = sa.Table(
        "ref_wfs_creation_defaults",
        metadata,
        sa.Column("source_account_ref", sa.String(128), primary_key=True),
        sa.Column("transport", sa.String(16), nullable=False),
        sa.Column("ship_date_offset", sa.Integer(), nullable=False),
        sa.Column("pallet_boxes", sa.Integer(), nullable=False),
        sa.Column("mixed_boxes", sa.Integer(), nullable=False),
        sa.Column("carrier_opt", sa.String(8), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at", tz, nullable=False),
        sa.CheckConstraint(
            "transport IN ('LTL','SMALL_PARCEL','FTL')", name="wfs_creation_default_transport"
        ),
        sa.CheckConstraint("carrier_opt IN ('own','wm')", name="wfs_creation_default_carrier"),
        sa.CheckConstraint(
            "ship_date_offset >= 0 AND pallet_boxes >= 1 AND mixed_boxes >= 0",
            name="wfs_creation_default_numbers",
        ),
    )
    changes = sa.Table(
        "evt_wfs_settings_changes",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity", sa.String(32), nullable=False),
        sa.Column("entity_key", sa.String(128), nullable=False),
        sa.Column("before_json", J, nullable=True),
        sa.Column("after_json", J, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("created_at", tz, nullable=False),
        sa.CheckConstraint(
            "entity IN ('rules','fc_region','creation_defaults')", name="wfs_settings_change_entity"
        ),
        sa.Index("ix_wfs_settings_change_time", "created_at"),
    )
    return [versions, rules, regions, defaults, changes]


def upgrade() -> None:
    import uuid
    from datetime import UTC, date, datetime

    bind = op.get_bind()
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)
    versions, rules, *_ = tables = _tables(metadata)
    for table in tables:
        table.create(bind=bind, checkfirst=False)
    version_id = uuid.UUID(SEED_VERSION_ID)
    bind.execute(
        versions.insert().values(
            id=version_id,
            version_no=1,
            effective_date=date(2026, 10, 10),
            reason="8088 WFS 设置页默认值（RULE_ROWS_INIT，WFS-RULES-20261010）",
            created_by="system:8088-seed",
            created_at=datetime.now(UTC),
        )
    )
    bind.execute(
        rules.insert(),
        [
            {
                "id": uuid.uuid4(),
                "version_id": version_id,
                "row_no": i,
                "rule_key": key,
                "node": node,
                "region": region,
                "carrier": carrier,
                "channel": channel,
                "days": days,
                "remind_days": remind,
                "row_effective_date": date.fromisoformat(eff),
                "notify": notify,
                "remark": remark,
                "decided": decided,
            }
            for i, (
                key,
                node,
                region,
                carrier,
                channel,
                days,
                remind,
                eff,
                notify,
                remark,
                decided,
            ) in enumerate(SEED_ROWS, start=1)
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    extra = {
        "ref_wfs_rule_setting_versions": "version_no > 1",
        "ref_wfs_fc_regions": "true",
        "ref_wfs_creation_defaults": "true",
        "evt_wfs_settings_changes": "true",
    }
    for table, where in extra.items():
        count = bind.execute(text(f"SELECT count(*) FROM {table} WHERE {where}")).scalar()
        if count:
            raise RuntimeError(
                f"{table} has {count} saved rows; keep WFS settings history, use forward recovery"
            )
    for table in reversed(TABLES):
        op.drop_table(table)
