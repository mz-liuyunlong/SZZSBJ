"""WFS settings stored by this system (PRP ``PRPs/pmc-wfs-settings.md`` §4, PR-S2).

* Time / reminder rules are versioned: each save appends a version (effective date,
  operator, reason) with all its rows; history is never edited or deleted (S2 = a).
* FC region keeps only the company's own choice per FC; FC code / ZIP / city / state stay
  the Lingxing values read from the published board.
* Creation defaults: one row per source account; absent = the 8088 defaults.
* Every change appends a before / after record to ``evt_wfs_settings_changes``.

None of these tables is sent to Walmart; nothing here calls an external system.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.pmc_wfs.lingxing_models import JSON_TYPE, utc_now

SETTINGS_TABLES: Final = (
    "ref_wfs_rule_setting_versions",
    "ref_wfs_rule_settings",
    "ref_wfs_fc_regions",
    "ref_wfs_creation_defaults",
    "evt_wfs_settings_changes",
)
REGIONS: Final = ("美西", "美中", "美东", "待定")
TRANSPORTS: Final = ("LTL", "SMALL_PARCEL", "FTL")
CARRIER_OPTS: Final = ("own", "wm")


class WfsRuleSettingVersion(Base):
    __tablename__ = "ref_wfs_rule_setting_versions"
    __table_args__ = (
        UniqueConstraint("version_no"),
        CheckConstraint("version_no >= 1", name="wfs_rule_version_no"),
        Index("ix_wfs_rule_version_effective", "effective_date", "version_no"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class WfsRuleSetting(Base):
    __tablename__ = "ref_wfs_rule_settings"
    __table_args__ = (
        UniqueConstraint("version_id", "row_no"),
        CheckConstraint("days >= 0 AND remind_days >= 0", name="wfs_rule_setting_days"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("ref_wfs_rule_setting_versions.id", ondelete="RESTRICT"), nullable=False
    )
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_key: Mapped[str | None] = mapped_column(String(64))  # None = custom row
    node: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    carrier: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(128), nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    remind_days: Mapped[int] = mapped_column(Integer, nullable=False)
    row_effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    notify: Mapped[str] = mapped_column(String(255), nullable=False)
    remark: Mapped[str] = mapped_column(Text, nullable=False)
    decided: Mapped[bool] = mapped_column(Boolean, nullable=False)  # False = 示例 · 待定


class WfsFcRegion(Base):
    __tablename__ = "ref_wfs_fc_regions"
    __table_args__ = (
        CheckConstraint("region IN ('美西','美中','美东','待定')", name="wfs_fc_region_value"),
    )

    fc: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(128))
    region: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class WfsCreationDefaults(Base):
    __tablename__ = "ref_wfs_creation_defaults"
    __table_args__ = (
        CheckConstraint(
            "transport IN ('LTL','SMALL_PARCEL','FTL')", name="wfs_creation_default_transport"
        ),
        CheckConstraint("carrier_opt IN ('own','wm')", name="wfs_creation_default_carrier"),
        CheckConstraint(
            "ship_date_offset >= 0 AND pallet_boxes >= 1 AND mixed_boxes >= 0",
            name="wfs_creation_default_numbers",
        ),
    )

    source_account_ref: Mapped[str] = mapped_column(String(128), primary_key=True)
    transport: Mapped[str] = mapped_column(String(16), nullable=False)
    ship_date_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    pallet_boxes: Mapped[int] = mapped_column(Integer, nullable=False)
    mixed_boxes: Mapped[int] = mapped_column(Integer, nullable=False)
    carrier_opt: Mapped[str] = mapped_column(String(8), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class WfsSettingsChange(Base):
    __tablename__ = "evt_wfs_settings_changes"
    __table_args__ = (
        CheckConstraint(
            "entity IN ('rules','fc_region','creation_defaults')", name="wfs_settings_change_entity"
        ),
        Index("ix_wfs_settings_change_time", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    entity: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_key: Mapped[str] = mapped_column(String(128), nullable=False)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    after_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


# 「全部店铺通用」那一行在 ref_wfs_store_creation_defaults 里的 store_id（领星店铺 ID 不会是它）。
COMMON_STORE = "*"


class WfsStoreCreationDefaults(Base):
    """创建默认值按店铺（Rocky 2026-11-04）：店铺行优先，其次账号行，最后 8088 默认值。

    退货地址和 ITS 也在这里，创建弹窗自动带出；弹窗里改了只影响这一次。
    """

    __tablename__ = "ref_wfs_store_creation_defaults"
    __table_args__ = (
        CheckConstraint(
            "transport IN ('LTL','SMALL_PARCEL','FTL')", name="wfs_store_default_transport"
        ),
        CheckConstraint("carrier_opt IN ('own','wm')", name="wfs_store_default_carrier"),
        CheckConstraint(
            "ship_date_offset >= 0 AND pallet_boxes >= 1 AND mixed_boxes >= 0",
            name="wfs_store_default_numbers",
        ),
    )

    source_account_ref: Mapped[str] = mapped_column(String(128), primary_key=True)
    store_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    transport: Mapped[str] = mapped_column(String(16), nullable=False)
    ship_date_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    pallet_boxes: Mapped[int] = mapped_column(Integer, nullable=False)
    mixed_boxes: Mapped[int] = mapped_column(Integer, nullable=False)
    carrier_opt: Mapped[str] = mapped_column(String(8), nullable=False)
    its: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    return_address: Mapped[dict | None] = mapped_column(JSON_TYPE)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
