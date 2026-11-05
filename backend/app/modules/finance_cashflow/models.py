from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FinanceCashAccount(Base):
    """账户主数据。银行账号不进仓库：本表由上线时的导入脚本写入，迁移不带种子。"""

    __tablename__ = "dim_finance_cash_accounts"

    account_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    entity: Mapped[str] = mapped_column(String(128), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(8), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    account_no_last4: Mapped[str] = mapped_column(
        String(8), nullable=False, default="", server_default=""
    )
    identity_hint: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class FinanceCashImport(Base):
    __tablename__ = "landing_finance_cashflow_imports"

    import_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    uploader: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="received", server_default="received"
    )
    request_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[str | None] = mapped_column(String(255))
    void_reason: Mapped[str | None] = mapped_column(Text)


class FinanceCashRawFile(Base):
    """原件留存记录；文件本身在 MEDIA_STORAGE_ROOT 下，这里只记相对路径和 sha256。"""

    __tablename__ = "raw_finance_cashflow_files"
    __table_args__ = (
        Index("ix_raw_finance_cashflow_files_sha256", "sha256"),
        Index("ix_raw_finance_cashflow_files_import_id", "import_id"),
    )

    file_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    import_id: Mapped[UUID] = mapped_column(
        ForeignKey("landing_finance_cashflow_imports.import_id"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(32))
    account_keys: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    declared_range_from: Mapped[date | None] = mapped_column(Date)
    declared_range_to: Mapped[date | None] = mapped_column(Date)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class FinanceCashLine(Base):
    __tablename__ = "std_finance_cashflow_lines"
    __table_args__ = (
        Index("ix_std_finance_cashflow_lines_account_date", "account_key", "business_date"),
    )

    line_uid: Mapped[str] = mapped_column(String(16), primary_key=True)
    account_key: Mapped[str] = mapped_column(
        ForeignKey("dim_finance_cash_accounts.account_key"), nullable=False
    )
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    source_time_raw: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(8), nullable=False)
    balance_after: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    counterparty_name: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    counterparty_account_last4: Mapped[str] = mapped_column(
        String(8), nullable=False, default="", server_default=""
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    memo: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    source_ref: Mapped[str] = mapped_column(
        String(16), nullable=False, default="", server_default=""
    )
    dup_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    statement_row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    file_row_order: Mapped[int] = mapped_column(Integer, nullable=False)
    first_import_id: Mapped[UUID] = mapped_column(
        ForeignKey("landing_finance_cashflow_imports.import_id"), nullable=False
    )
    first_raw_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_finance_cashflow_files.file_id"), nullable=False
    )
    last_import_id: Mapped[UUID] = mapped_column(
        ForeignKey("landing_finance_cashflow_imports.import_id"), nullable=False
    )
    last_raw_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_finance_cashflow_files.file_id"), nullable=False
    )
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class FinanceCashLineOccurrence(Base):
    """一行流水出现在哪些批次；作废时靠它把归属退回到最近一个未作废批次。"""

    __tablename__ = "std_finance_cashflow_line_occurrences"
    __table_args__ = (Index("ix_std_finance_cashflow_line_occurrences_import", "import_id"),)

    line_uid: Mapped[str] = mapped_column(
        ForeignKey("std_finance_cashflow_lines.line_uid"), primary_key=True
    )
    raw_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_finance_cashflow_files.file_id"), primary_key=True
    )
    import_id: Mapped[UUID] = mapped_column(
        ForeignKey("landing_finance_cashflow_imports.import_id"), nullable=False
    )
    statement_row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    file_row_order: Mapped[int] = mapped_column(Integer, nullable=False)
    seen_seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False)


class FinanceCashImportQuality(Base):
    __tablename__ = "dq_run_finance_cashflow_import"

    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_finance_cashflow_files.file_id"), primary_key=True
    )
    rows_parsed: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_new: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_duplicate: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_chain_ok: Mapped[bool | None] = mapped_column(Boolean)
    warnings: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )


class FinanceCashCategory(Base):
    __tablename__ = "dim_finance_cash_categories"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    big: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_internal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_exclude: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class FinanceCashClassifyRule(Base):
    """分类规则：不带名字的随迁移写入（source=seed），带名字的上线时导入（source=deploy）。"""

    __tablename__ = "cfg_finance_cash_classify_rules"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    rule_type: Mapped[str] = mapped_column(String(16), nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    category_code: Mapped[str] = mapped_column(
        ForeignKey("dim_finance_cash_categories.code"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)


class FinanceCashLineEvent(Base):
    """人工动作事件：只追加。"""

    __tablename__ = "evt_finance_cash_line_reviews"
    __table_args__ = (
        Index("ix_evt_finance_cash_line_reviews_line", "line_uid"),
        Index(
            "uq_evt_finance_cash_line_reviews_idempotency",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    line_uid: Mapped[str] = mapped_column(
        ForeignKey("std_finance_cashflow_lines.line_uid"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class FinanceCashLineState(Base):
    """每行的人工当前状态。规则类别、配对、异常都在读取时算，不落这里。"""

    __tablename__ = "manual_finance_cash_line_state"

    line_uid: Mapped[str] = mapped_column(
        ForeignKey("std_finance_cashflow_lines.line_uid"), primary_key=True
    )
    manual_category: Mapped[str | None] = mapped_column(
        ForeignKey("dim_finance_cash_categories.code")
    )
    refs: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    exclude_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    exclude_reason: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(
        String(8), nullable=False, default="todo", server_default="todo"
    )
    stage_reason: Mapped[str | None] = mapped_column(Text)
    review_note: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class FinanceCashExclusion(Base):
    """剔除清单：只由上线导入脚本写入；按审批单号或「日期 + 账户 + 摘要关键词」命中流水。"""

    __tablename__ = "manual_finance_cash_exclusions"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    entry_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    ref: Mapped[str | None] = mapped_column(String(32))
    txn_date: Mapped[date | None] = mapped_column(Date)
    account_key: Mapped[str | None] = mapped_column(String(64))
    summary_contains: Mapped[str | None] = mapped_column(Text)
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    registered_by: Mapped[str] = mapped_column(String(255), nullable=False)
    registered_on: Mapped[date | None] = mapped_column(Date)
