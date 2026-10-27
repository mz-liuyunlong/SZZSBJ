"""Keyword-planning V1.1 data model.

Schema only.  Immutable source evidence, versioned decisions, and durable SKU library
are separate.  No live ad/API execution is implemented by this module.

The store/account scope is intentionally stored alongside SKU references because
SZZSBJ products are global while provider observations are account-scoped.
Service/repository access MUST enforce source_account_ref and store authorization.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RowIdentity:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AccountScope:
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)


class RawKwUploadFile(RowIdentity, AccountScope, Base):
    """One record for EVERY submitted original workbook, including exact repeats."""

    __tablename__ = "raw_kw_upload_file"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "id"),
        CheckConstraint("file_size_bytes > 0", name="ck_raw_kw_upload_file_positive_size"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_raw_kw_upload_file_sha256"),
        CheckConstraint(
            "status IN ('uploaded','parsing','parsed','failed')",
            name="ck_raw_kw_upload_file_status",
        ),
        Index("ix_raw_kw_upload_file_sku_created", "product_id", "created_at"),
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parser_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'uploaded'")
    )
    uploaded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))


class RawKwUploadRow(RowIdentity, AccountScope, Base):
    """Original row coordinates/cells; NEVER deduplicated or rewritten."""

    __tablename__ = "raw_kw_upload_row"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "id"),
        ForeignKeyConstraint(
            ["source_account_ref", "upload_id"],
            ["raw_kw_upload_file.source_account_ref", "raw_kw_upload_file.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("upload_id", "sheet_name", "row_number"),
        CheckConstraint("row_number >= 1", name="ck_raw_kw_upload_row_number"),
        Index("ix_raw_kw_upload_row_account_upload", "source_account_ref", "upload_id"),
    )

    upload_id: Mapped[UUID] = mapped_column(nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_cells: Mapped[object] = mapped_column(JSONB, nullable=False)
    keyword_raw: Mapped[str | None] = mapped_column(Text)
    keyword_normalized: Mapped[str | None] = mapped_column(Text)
    parse_errors: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )


class RawKwWalmartPageSnapshot(RowIdentity, AccountScope, Base):
    """Immutable PAGE evidence, not operator-confirmed product attributes."""

    __tablename__ = "raw_kw_walmart_page_snapshot"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "id"),
        CheckConstraint(
            "verification_status IN ('verified','partial','failed','mismatch')",
            name="ck_raw_kw_walmart_page_verification",
        ),
        Index("ix_raw_kw_walmart_page_lookup", "source_account_ref", "item_id", "created_at"),
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    listing_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("product_platform_listings.id", ondelete="RESTRICT")
    )
    store_id: Mapped[str | None] = mapped_column(String(128))
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False)
    fetch_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    page_title: Mapped[str | None] = mapped_column(Text)
    description_text: Mapped[str | None] = mapped_column(Text)
    features_json: Mapped[list[object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    attributes_json: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    page_images_json: Mapped[list[object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    raw_object_key: Mapped[str | None] = mapped_column(Text)
    evidence_hash: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(128))


class RawKwAsinSnapshot(RowIdentity, AccountScope, Base):
    """Immutable original Amazon ASIN response snapshot, not Walmart facts."""

    __tablename__ = "raw_kw_asin_snapshot"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "id"),
        CheckConstraint("asin ~ '^[A-Z0-9]{10}$'", name="ck_raw_kw_asin_snapshot_asin"),
        CheckConstraint(
            "fetch_status IN ('succeeded','partial','failed')",
            name="ck_raw_kw_asin_snapshot_fetch_status",
        ),
        Index("ix_raw_kw_asin_history", "source_account_ref", "asin", "created_at"),
    )

    asin: Mapped[str] = mapped_column(String(10), nullable=False)
    fetch_status: Mapped[str] = mapped_column(String(16), nullable=False)
    fetch_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(Text)
    features_json: Mapped[list[object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    description_text: Mapped[str | None] = mapped_column(Text)
    raw_object_key: Mapped[str | None] = mapped_column(Text)
    response_hash: Mapped[str | None] = mapped_column(String(64))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))


class RawKwAsinImage(RowIdentity, AccountScope, Base):
    """All image URLs, including repeated URLs and multiple size variants, in API order."""

    __tablename__ = "raw_kw_asin_image"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_account_ref", "asin_snapshot_id"],
            ["raw_kw_asin_snapshot.source_account_ref", "raw_kw_asin_snapshot.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("asin_snapshot_id", "image_index"),
        CheckConstraint("image_index >= 0", name="ck_raw_kw_asin_image_index"),
        CheckConstraint("width IS NULL OR width > 0", name="ck_raw_kw_asin_image_width"),
        CheckConstraint("height IS NULL OR height > 0", name="ck_raw_kw_asin_image_height"),
    )

    asin_snapshot_id: Mapped[UUID] = mapped_column(nullable=False)
    image_index: Mapped[int] = mapped_column(Integer, nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    image_type: Mapped[str | None] = mapped_column(String(64))
    source_image_id: Mapped[str | None] = mapped_column(String(255))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    url_hash: Mapped[str | None] = mapped_column(String(64))


class AiKwProductFactSnapshot(RowIdentity, AccountScope, Base):
    """Confirmed product facts with per-field provenance; never inferred from keywords."""

    __tablename__ = "ai_kw_product_fact_snapshot"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "id"),
        ForeignKeyConstraint(
            ["source_account_ref", "walmart_page_snapshot_id"],
            ["raw_kw_walmart_page_snapshot.source_account_ref", "raw_kw_walmart_page_snapshot.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('draft','confirmed','invalid')",
            name="ck_ai_kw_product_fact_snapshot_status",
        ),
        CheckConstraint(
            "status <> 'confirmed' OR (confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL "
            "AND item_verified IS TRUE AND missing_required_json = '[]'::jsonb)",
            name="ck_ai_kw_product_fact_snapshot_confirmed",
        ),
        Index("ix_ai_kw_facts_product", "source_account_ref", "product_id", "created_at"),
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    walmart_page_snapshot_id: Mapped[UUID | None] = mapped_column()
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'draft'"))
    # Example: {"material":{"value":"PET","source":"operator","evidence_ref":"..."}}
    facts_with_sources_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    facts_sha256: Mapped[str | None] = mapped_column(String(64))
    missing_required_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    confirmed_by: Mapped[str | None] = mapped_column(String(255))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DimKwTerm(RowIdentity, Base):
    """Global conservative normalized term; NOT an advertising target."""

    __tablename__ = "dim_kw_term"
    __table_args__ = (
        UniqueConstraint("normalized_keyword"),
        CheckConstraint("length(btrim(normalized_keyword)) > 0", name="ck_dim_kw_term_nonempty"),
    )

    canonical_keyword: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_keyword: Mapped[str] = mapped_column(Text, nullable=False)
    translation_default: Mapped[str | None] = mapped_column(Text)
    translation_source: Mapped[str | None] = mapped_column(String(32))
    normalization_version: Mapped[str] = mapped_column(String(32), nullable=False)


class BizSkuKeyword(RowIdentity, AccountScope, Base):
    """One current SKU keyword asset, independent of uploads and analysis runs."""

    __tablename__ = "biz_sku_keyword"
    __table_args__ = (
        UniqueConstraint("product_id", "term_id"),
        UniqueConstraint("source_account_ref", "id"),
        CheckConstraint(
            "status IN ('active','review','paused','excluded')",
            name="ck_biz_sku_keyword_status",
        ),
        Index("ix_biz_sku_keyword_product", "source_account_ref", "product_id"),
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    term_id: Mapped[UUID] = mapped_column(
        ForeignKey("dim_kw_term.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'review'"))
    manual_translation: Mapped[str | None] = mapped_column(Text)
    operator_note: Mapped[str | None] = mapped_column(Text)
    confirmed_by: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BizKwMarketObservation(RowIdentity, AccountScope, Base):
    """Metrics remain at source observation granularity; never overwrite history."""

    __tablename__ = "biz_kw_market_observation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_account_ref", "upload_row_id"],
            ["raw_kw_upload_row.source_account_ref", "raw_kw_upload_row.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("upload_row_id"),
        CheckConstraint(
            "monthly_searches IS NULL OR monthly_searches >= 0",
            name="ck_biz_kw_observation_searches",
        ),
        CheckConstraint(
            "monthly_purchases IS NULL OR monthly_purchases >= 0",
            name="ck_biz_kw_observation_purchases",
        ),
        Index("ix_biz_kw_observation_product_term", "product_id", "term_id", "created_at"),
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    term_id: Mapped[UUID] = mapped_column(
        ForeignKey("dim_kw_term.id", ondelete="RESTRICT"), nullable=False
    )
    upload_row_id: Mapped[UUID | None] = mapped_column()
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    monthly_searches: Mapped[int | None] = mapped_column(BigInteger)
    monthly_purchases: Mapped[int | None] = mapped_column(BigInteger)
    ppc_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    bid_min_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    bid_max_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    source_metrics_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class BizKwSourceEvent(RowIdentity, AccountScope, Base):
    """Every independent source discovery/event, including when term is not admitted."""

    __tablename__ = "biz_kw_source_event"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "id"),
        UniqueConstraint(
            "source_account_ref",
            "source_kind",
            "source_event_key",
            "product_id",
            "term_id",
            name="uq_biz_kw_source_event_dedupe",
        ),
        CheckConstraint(
            "source_kind IN ('excel','operator_manual','auto_search_term',"
            "'system_ad','amazon_text','other')",
            name="ck_biz_kw_source_event_kind",
        ),
        Index("ix_biz_kw_source_event_sku", "product_id", "term_id", "created_at"),
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    term_id: Mapped[UUID] = mapped_column(
        ForeignKey("dim_kw_term.id", ondelete="RESTRICT"), nullable=False
    )
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text)
    store_id: Mapped[str | None] = mapped_column(String(128))
    evidence_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BizSkuAsinReference(RowIdentity, AccountScope, Base):
    """Persistent SKU competitor ASIN selections, independent of API snapshot versions."""

    __tablename__ = "biz_sku_asin_reference"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_account_ref", "latest_snapshot_id"],
            ["raw_kw_asin_snapshot.source_account_ref", "raw_kw_asin_snapshot.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("product_id", "asin", "reference_role"),
        CheckConstraint("asin ~ '^[A-Z0-9]{10}$'", name="ck_biz_sku_asin_reference_asin"),
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    asin: Mapped[str] = mapped_column(String(10), nullable=False)
    reference_role: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'competitor'")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    latest_snapshot_id: Mapped[UUID | None] = mapped_column()
    selected_by: Mapped[str] = mapped_column(String(255), nullable=False)


class AiKwRuleSet(RowIdentity, Base):
    """Logical rule family (scoring, admission, auto-create, optimization, export)."""

    __tablename__ = "ai_kw_rule_set"
    __table_args__ = (
        UniqueConstraint("rule_key", "scope_key"),
        CheckConstraint(
            "rule_type IN ('scoring','search_term_admission','ad_creation',"
            "'ad_optimization','export')",
            name="ck_ai_kw_rule_set_type",
        ),
    )

    rule_key: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_key: Mapped[str] = mapped_column(
        String(128), nullable=False, server_default=text("'global'")
    )
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)


class AiKwRuleVersion(RowIdentity, Base):
    """Published versions immutable in application layer; only explicit publish is executable."""

    __tablename__ = "ai_kw_rule_version"
    __table_args__ = (
        UniqueConstraint("rule_set_id", "version_number"),
        CheckConstraint(
            "status IN ('draft','published','retired')",
            name="ck_ai_kw_rule_version_status",
        ),
        CheckConstraint(
            "status <> 'published' OR (published_by IS NOT NULL AND published_at IS NOT NULL)",
            name="ck_ai_kw_rule_version_published",
        ),
    )

    rule_set_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_kw_rule_set.id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'draft'"))
    config_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    published_by: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiKwRuleDecision(RowIdentity, Base):
    """One independently reviewed D01-D08 decision for a frozen draft."""

    __tablename__ = "ai_kw_rule_decision"
    __table_args__ = (
        UniqueConstraint("rule_version_id", "decision_key"),
        CheckConstraint(
            "decision_key IN ('D01','D02','D03','D04','D05','D06','D07','D08')",
            name="ck_ai_kw_rule_decision_key",
        ),
        CheckConstraint(
            "status IN ('pending_review','approved','rejected')",
            name="ck_ai_kw_rule_decision_status",
        ),
    )

    rule_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_kw_rule_version.id", ondelete="RESTRICT"), nullable=False
    )
    decision_key: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    decision_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiKwRuleDecisionEvent(RowIdentity, Base):
    """Append-only audit evidence; never edit an existing review event."""

    __tablename__ = "ai_kw_rule_decision_event"

    decision_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_kw_rule_decision.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    status_before: Mapped[str | None] = mapped_column(String(16))
    status_after: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_ref: Mapped[str] = mapped_column(String(255), nullable=False)


class AiKwAnalysisRun(RowIdentity, AccountScope, Base):
    """One immutable, attributable scoring run; no product keyword overwrite."""

    __tablename__ = "ai_kw_analysis_run"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "id"),
        ForeignKeyConstraint(
            ["source_account_ref", "product_fact_snapshot_id"],
            ["ai_kw_product_fact_snapshot.source_account_ref", "ai_kw_product_fact_snapshot.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_account_ref", "walmart_page_snapshot_id"],
            ["raw_kw_walmart_page_snapshot.source_account_ref", "raw_kw_walmart_page_snapshot.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "source_account_ref",
            "request_key",
            name="uq_ai_kw_analysis_run_request_key",
        ),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','blocked')",
            name="ck_ai_kw_analysis_run_status",
        ),
        Index("ix_ai_kw_analysis_run_sku_time", "source_account_ref", "product_id", "created_at"),
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(128))
    product_fact_snapshot_id: Mapped[UUID] = mapped_column(nullable=False)
    walmart_page_snapshot_id: Mapped[UUID | None] = mapped_column()
    rule_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_kw_rule_version.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'queued'"))
    request_key: Mapped[str] = mapped_column(String(255), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(128))
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    confirmed_input_sha256: Mapped[str | None] = mapped_column(String(64))
    confirmed_by: Mapped[str | None] = mapped_column(String(255))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_json: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    error_code: Mapped[str | None] = mapped_column(String(128))


class AiKwRunFile(RowIdentity, AccountScope, Base):
    __tablename__ = "ai_kw_run_file"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_account_ref", "run_id"],
            ["ai_kw_analysis_run.source_account_ref", "ai_kw_analysis_run.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_account_ref", "upload_id"],
            ["raw_kw_upload_file.source_account_ref", "raw_kw_upload_file.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("run_id", "upload_id"),
    )

    run_id: Mapped[UUID] = mapped_column(nullable=False)
    upload_id: Mapped[UUID] = mapped_column(nullable=False)


class AiKwRunAsin(RowIdentity, AccountScope, Base):
    __tablename__ = "ai_kw_run_asin"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_account_ref", "run_id"],
            ["ai_kw_analysis_run.source_account_ref", "ai_kw_analysis_run.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_account_ref", "asin_snapshot_id"],
            ["raw_kw_asin_snapshot.source_account_ref", "raw_kw_asin_snapshot.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("run_id", "asin_snapshot_id"),
    )

    run_id: Mapped[UUID] = mapped_column(nullable=False)
    asin_snapshot_id: Mapped[UUID] = mapped_column(nullable=False)


class AiKwRunKeyword(RowIdentity, AccountScope, Base):
    """ONE keyword-level source of truth for all UI projections and 5 exports."""

    __tablename__ = "ai_kw_run_keyword"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_account_ref", "run_id"],
            ["ai_kw_analysis_run.source_account_ref", "ai_kw_analysis_run.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("run_id", "term_id"),
        CheckConstraint(
            "score IS NULL OR score BETWEEN 0 AND 100",
            name="ck_ai_kw_run_keyword_score",
        ),
        CheckConstraint(
            "match_points IS NULL OR match_points BETWEEN 0 AND 30",
            name="ck_ai_kw_run_keyword_match_points",
        ),
        CheckConstraint(
            "intent_points IS NULL OR intent_points BETWEEN 0 AND 20",
            name="ck_ai_kw_run_keyword_intent_points",
        ),
        CheckConstraint(
            "page_points IS NULL OR page_points BETWEEN 0 AND 20",
            name="ck_ai_kw_run_keyword_page_points",
        ),
        CheckConstraint(
            "root_points IS NULL OR root_points BETWEEN 0 AND 15",
            name="ck_ai_kw_run_keyword_root_points",
        ),
        CheckConstraint(
            "data_points IS NULL OR data_points BETWEEN 0 AND 15",
            name="ck_ai_kw_run_keyword_data_points",
        ),
        CheckConstraint(
            "risk_points IS NULL OR risk_points BETWEEN -40 AND 0",
            name="ck_ai_kw_run_keyword_risk_points",
        ),
        CheckConstraint(
            "NOT hard_risk OR (NOT exact_selected AND NOT broad_selected)",
            name="ck_ai_kw_run_keyword_hard_risk_block",
        ),
        CheckConstraint(
            "NOT (exact_selected OR broad_selected) OR "
            "(score IS NOT NULL AND allocation_grade IN ('P0','P1','P2'))",
            name="ck_ai_kw_run_keyword_ad_selection_requires_score",
        ),
        CheckConstraint(
            "NOT broad_selected OR broad_role IN ('root','long_tail')",
            name="ck_ai_kw_run_keyword_broad_role",
        ),
        Index("ix_ai_kw_run_keyword_run_rank", "run_id", "rank_index"),
    )

    run_id: Mapped[UUID] = mapped_column(nullable=False)
    term_id: Mapped[UUID] = mapped_column(
        ForeignKey("dim_kw_term.id", ondelete="RESTRICT"), nullable=False
    )
    keyword_primary_type: Mapped[str | None] = mapped_column(String(64))
    auxiliary_types_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    core_root: Mapped[str | None] = mapped_column(Text)
    root_grade: Mapped[str | None] = mapped_column(String(32))
    page_coverage: Mapped[str | None] = mapped_column(String(64))
    page_evidence_json: Mapped[list[object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    component_evidence_json: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    match_points: Mapped[int | None] = mapped_column(Integer)
    intent_points: Mapped[int | None] = mapped_column(Integer)
    page_points: Mapped[int | None] = mapped_column(Integer)
    root_points: Mapped[int | None] = mapped_column(Integer)
    data_points: Mapped[int | None] = mapped_column(Integer)
    risk_points: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[int | None] = mapped_column(Integer)
    base_grade: Mapped[str | None] = mapped_column(String(32))
    allocation_grade: Mapped[str | None] = mapped_column(String(32))
    hard_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    risk_reasons_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    exact_selected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    broad_selected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    broad_role: Mapped[str | None] = mapped_column(String(32))
    exact_reason: Mapped[str | None] = mapped_column(Text)
    broad_reason: Mapped[str | None] = mapped_column(Text)
    quality_note: Mapped[str | None] = mapped_column(Text)
    suggested_optimization_bid: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    rank_index: Mapped[int | None] = mapped_column(Integer)
    decision_status: Mapped[str] = mapped_column(String(32), nullable=False)


class AiKwListingVersion(RowIdentity, AccountScope, Base):
    __tablename__ = "ai_kw_listing_version"
    __table_args__ = (
        UniqueConstraint("run_id", "version_number"),
        ForeignKeyConstraint(
            ["source_account_ref", "run_id"],
            ["ai_kw_analysis_run.source_account_ref", "ai_kw_analysis_run.id"],
            ondelete="RESTRICT",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    features_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    description_text: Mapped[str | None] = mapped_column(Text)
    edited_by: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence_json: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class AiKwExportFile(RowIdentity, AccountScope, Base):
    """Archived output binary with exact version and explicit confirmation trail."""

    __tablename__ = "ai_kw_export_file"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_account_ref", "run_id"],
            ["ai_kw_analysis_run.source_account_ref", "ai_kw_analysis_run.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("file_sha256 ~ '^[0-9a-f]{64}$'", name="ck_ai_kw_export_file_sha256"),
        Index("ix_ai_kw_export_file_run", "run_id", "created_at"),
    )

    run_id: Mapped[UUID] = mapped_column(nullable=False)
    export_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    template_version: Mapped[str] = mapped_column(String(64), nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    original_run_input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class BizKwDecisionHistory(RowIdentity, AccountScope, Base):
    """Immutable human or rules-driven decisions, separate from source observations."""

    __tablename__ = "biz_kw_decision_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_account_ref", "sku_keyword_id"],
            ["biz_sku_keyword.source_account_ref", "biz_sku_keyword.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_biz_kw_decision_history_sku", "sku_keyword_id", "created_at"),
    )

    sku_keyword_id: Mapped[UUID] = mapped_column(nullable=False)
    rule_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ai_kw_rule_version.id", ondelete="RESTRICT")
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    before_state_json: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    after_state_json: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(255), nullable=False)


class AiKwRuleEvaluation(RowIdentity, AccountScope, Base):
    """Rule decisions for ALL candidates, including rejected auto-ad search terms."""

    __tablename__ = "ai_kw_rule_evaluation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_account_ref", "source_event_id"],
            ["biz_kw_source_event.source_account_ref", "biz_kw_source_event.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("source_account_ref", "idempotency_key"),
        CheckConstraint(
            "decision IN ('admit','reject','review','skip')",
            name="ck_ai_kw_rule_evaluation_decision",
        ),
        Index("ix_ai_kw_rule_evaluation_sku", "product_id", "created_at"),
    )

    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    term_id: Mapped[UUID | None] = mapped_column(ForeignKey("dim_kw_term.id", ondelete="RESTRICT"))
    source_event_id: Mapped[UUID | None] = mapped_column()
    rule_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_kw_rule_version.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_keyword: Mapped[str] = mapped_column(Text, nullable=False)
    metric_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metric_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_metrics_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_codes_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
