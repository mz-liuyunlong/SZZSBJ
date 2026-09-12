from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


def detail_value_constraints() -> tuple[CheckConstraint, ...]:
    nonnegative = (
        "purchase_delivery_days",
        "purchase_cost_cny",
        "customs_declared_unit_price",
        "us_first_leg_cost",
        "product_length_cm",
        "product_width_cm",
        "product_height_cm",
        "product_net_weight_g",
        "package_length_cm",
        "package_width_cm",
        "package_height_cm",
        "box_length_cm",
        "box_width_cm",
        "box_height_cm",
        "box_pcs",
        "product_gross_weight_g",
        "box_weight_kg",
    )
    checks = [
        CheckConstraint(f"{name} IS NULL OR {name} >= 0", name=f"{name}_nonnegative")
        for name in nonnegative
    ]
    checks.extend(
        (
            CheckConstraint(
                "(purchase_cost_cny IS NULL AND purchase_cost_currency_code IS NULL) OR "
                "(purchase_cost_cny IS NOT NULL AND purchase_cost_currency_code = 'CNY')",
                name="purchase_cost_currency",
            ),
            CheckConstraint(
                "(us_first_leg_cost IS NULL AND us_first_leg_currency IS NULL) OR "
                "(us_first_leg_cost IS NOT NULL AND us_first_leg_currency IS NOT NULL)",
                name="first_leg_currency",
            ),
        )
    )
    return tuple(checks)


class SkuDetailFields:
    product_name: Mapped[str | None] = mapped_column(String(500))
    lingxing_sku_code: Mapped[str | None] = mapped_column(String(255))
    main_image_url: Mapped[str | None] = mapped_column(Text)
    product_developer_name: Mapped[str | None] = mapped_column(String(255))
    product_developer_uid: Mapped[str | None] = mapped_column(String(255))
    purchase_delivery_days: Mapped[int | None] = mapped_column(Integer)
    purchase_cost_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    purchase_cost_currency_code: Mapped[str | None] = mapped_column(String(3))
    purchase_material: Mapped[str | None] = mapped_column(Text)
    customs_export_name_cn: Mapped[str | None] = mapped_column(String(500))
    customs_import_name_en: Mapped[str | None] = mapped_column(String(500))
    customs_declared_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    customs_declared_currency: Mapped[str | None] = mapped_column(String(3))
    china_hs_code: Mapped[str | None] = mapped_column(String(64))
    owner_uid: Mapped[str | None] = mapped_column(String(255))
    owner_name: Mapped[str | None] = mapped_column(String(255))
    clearance_material_cn: Mapped[str | None] = mapped_column(Text)
    clearance_usage_cn: Mapped[str | None] = mapped_column(Text)
    clearance_material_en: Mapped[str | None] = mapped_column(Text)
    us_first_leg_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    us_first_leg_currency: Mapped[str | None] = mapped_column(String(3))
    product_length_cm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    product_width_cm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    product_height_cm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    product_net_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    package_length_cm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    package_width_cm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    package_height_cm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    box_length_cm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    box_width_cm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    box_height_cm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    box_pcs: Mapped[int | None] = mapped_column(Integer)
    product_gross_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    box_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))


class LingxingSkuIdentity(Base):
    __tablename__ = "dwd_lingxing_sku_identity_index"
    __table_args__ = (
        UniqueConstraint("provider", "source_account_ref", "lingxing_sku_id"),
        CheckConstraint("provider = 'lingxing'", name="provider_lingxing"),
        CheckConstraint("mapping_status IN ('unmapped', 'confirmed')", name="mapping_status"),
        CheckConstraint(
            "mapping_status <> 'confirmed' OR "
            "(product_id IS NOT NULL AND mapping_evidence_ref IS NOT NULL)",
            name="confirmed_mapping_evidence",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(
        String(32), default="lingxing", server_default=text("'lingxing'"), nullable=False
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    lingxing_sku_id: Mapped[str] = mapped_column(String(255), nullable=False)
    lingxing_sku_code: Mapped[str | None] = mapped_column(String(255))
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    mapping_status: Mapped[str] = mapped_column(
        String(32), default="unmapped", server_default=text("'unmapped'"), nullable=False
    )
    mapping_evidence_ref: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    first_seen_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
    )
    last_seen_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    inactive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class LingxingSkuProductInfoSnapshot(SkuDetailFields, Base):
    __tablename__ = "dwd_lingxing_sku_product_info_snapshots"
    __table_args__ = (
        UniqueConstraint("source_run_id", "source_account_ref", "lingxing_sku_id"),
        *detail_value_constraints(),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("dwd_lingxing_sku_identity_index.id", ondelete="RESTRICT"), nullable=False
    )
    lingxing_sku_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
    )
    source_raw_request_ref_id: Mapped[UUID] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="RESTRICT"), nullable=False
    )
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class LingxingSkuProductInfoCurrent(SkuDetailFields, Base):
    __tablename__ = "dwd_lingxing_sku_product_info_current"
    __table_args__ = (
        UniqueConstraint("provider", "source_account_ref", "lingxing_sku_id"),
        UniqueConstraint("source_snapshot_id"),
        *detail_value_constraints(),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("dwd_lingxing_sku_identity_index.id", ondelete="RESTRICT"), nullable=False
    )
    lingxing_sku_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dwd_lingxing_sku_product_info_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
    )
    source_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class LingxingSkuProductImage(Base):
    __tablename__ = "dwd_lingxing_sku_product_images"
    __table_args__ = (
        UniqueConstraint("source_snapshot_id", "ordinal"),
        CheckConstraint("ordinal >= 0", name="ordinal"),
        CheckConstraint("pic_url LIKE 'https://%'", name="https_url"),
        Index(
            "uq_dwd_lingxing_sku_images_primary",
            "source_snapshot_id",
            unique=True,
            postgresql_where=text("is_primary IS TRUE"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dwd_lingxing_sku_product_info_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("dwd_lingxing_sku_identity_index.id", ondelete="RESTRICT"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    pic_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class LingxingSkuGlobalTag(Base):
    __tablename__ = "dwd_lingxing_sku_global_tags"
    __table_args__ = (
        UniqueConstraint("source_snapshot_id", "ordinal"),
        CheckConstraint("ordinal >= 0", name="ordinal"),
        Index(
            "uq_dwd_lingxing_sku_tags_external_id",
            "source_snapshot_id",
            "global_tag_id",
            unique=True,
            postgresql_where=text("global_tag_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dwd_lingxing_sku_product_info_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("dwd_lingxing_sku_identity_index.id", ondelete="RESTRICT"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    global_tag_id: Mapped[str | None] = mapped_column(String(255))
    tag_name: Mapped[str | None] = mapped_column(String(255))
    color: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class SkuBaseProfileCurrent(Base):
    __tablename__ = "dws_sku_base_profile_current"
    __table_args__ = (
        UniqueConstraint("provider", "source_account_ref", "lingxing_sku_id"),
        UniqueConstraint("source_snapshot_id"),
        CheckConstraint("data_quality_score BETWEEN 0 AND 100", name="quality_score"),
        CheckConstraint(
            "(purchase_cost_cny IS NULL AND purchase_cost_currency_code IS NULL) OR "
            "(purchase_cost_cny IS NOT NULL AND purchase_cost_currency_code = 'CNY')",
            name="purchase_currency",
        ),
        CheckConstraint(
            "(us_first_leg_cost IS NULL AND us_first_leg_currency IS NULL) OR "
            "(us_first_leg_cost IS NOT NULL AND us_first_leg_currency IS NOT NULL)",
            name="first_leg_currency",
        ),
        CheckConstraint(
            "(unit_first_leg_cost IS NULL AND unit_first_leg_currency IS NULL) OR "
            "(unit_first_leg_cost IS NOT NULL AND unit_first_leg_currency IS NOT NULL)",
            name="unit_first_leg_currency",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("dwd_lingxing_sku_identity_index.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    lingxing_sku_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("gov_integration_sync_runs.id", ondelete="RESTRICT"), nullable=False
    )
    source_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dwd_lingxing_sku_product_info_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    calc_version: Mapped[str] = mapped_column(String(64), nullable=False)
    product_volume_cm3: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    package_volume_cm3: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    box_volume_cm3: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    box_volume_cbm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    product_net_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    product_gross_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit_box_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    purchase_cost_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    purchase_cost_currency_code: Mapped[str | None] = mapped_column(String(3))
    us_first_leg_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    us_first_leg_currency: Mapped[str | None] = mapped_column(String(3))
    unit_first_leg_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit_first_leg_currency: Mapped[str | None] = mapped_column(String(3))
    has_customs_info: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_package_info: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_logistics_info: Mapped[bool] = mapped_column(Boolean, nullable=False)
    missing_fields_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    data_quality_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
