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
    UniqueConstraint,
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


class FinancePayoneerStatementRow(Base):
    """派安盈月结明细的每一行（月底补充导入）：只用来给已有提现补实际到账金额，不是流水。

    和流水的对应在读取时按「账户 + 金额 + 交易时间」算，不落表；作废批次的行读取时跳过。
    """

    __tablename__ = "std_finance_payoneer_statement_rows"
    __table_args__ = (
        UniqueConstraint("raw_file_id", "row_no"),
        Index("ix_std_finance_payoneer_statement_rows_account_txn", "account_key", "txn_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    raw_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_finance_cashflow_files.file_id"), nullable=False
    )
    import_id: Mapped[UUID] = mapped_column(
        ForeignKey("landing_finance_cashflow_imports.import_id"), nullable=False
    )
    account_key: Mapped[str] = mapped_column(
        ForeignKey("dim_finance_cash_accounts.account_key"), nullable=False
    )
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    txn_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default="")
    txn_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(8), nullable=False)
    transfer_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    transfer_currency: Mapped[str] = mapped_column(
        String(8), nullable=False, default="", server_default=""
    )


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
    # 人工改过的摘要 / 备注（只用于显示；银行原文在 std 表里不动，分类规则照原文算）。
    manual_description: Mapped[str | None] = mapped_column(Text)
    manual_memo: Mapped[str | None] = mapped_column(Text)
    # 拆分：[{"amount": "100.0000", "category_code": "G02" | null}]；null = 没拆分。
    parts: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    # 人工配对号：同号的几笔算同一笔内部转账（rocky 11-05）。
    manual_pair: Mapped[str | None] = mapped_column(String(40))
    # 人工改的折人民币（Rocky 11-10：约定汇率每笔不同）；有值就用它，原因必填。
    manual_amount_cny: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    manual_cny_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class FinanceCashAlertClosure(Base):
    """关闭异常（Rocky 11-10）：确认不用处理的异常写原因关掉；可以重新打开，留历史。"""

    __tablename__ = "manual_finance_cash_alert_closures"
    __table_args__ = (
        Index(
            "uq_manual_finance_cash_alert_closures_open",
            "alert_key",
            unique=True,
            postgresql_where=text("reopened_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    alert_key: Mapped[str] = mapped_column(String(200), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    closed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    reopened_by: Mapped[str | None] = mapped_column(String(255))
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopen_reason: Mapped[str | None] = mapped_column(Text)


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


class FinanceCashApproval(Base):
    """飞书审批单（费用报销、付款申请、备用金申请、备用金核销）。

    只留账号尾号，不存完整银行账号；附件只留元数据，不存下载链接。
    """

    __tablename__ = "std_finance_feishu_approvals"
    __table_args__ = (
        Index("uq_std_finance_feishu_approvals_serial", "serial_number", unique=True),
        Index("ix_std_finance_feishu_approvals_started", "started_at"),
        Index("ix_std_finance_feishu_approvals_org", "org"),
    )

    instance_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 哪家公司的飞书（approval_orgs）：zsbj = 主公司，yc = 第二家（单号带 YC- 前缀）
    org: Mapped[str] = mapped_column(
        String(16), nullable=False, default="zsbj", server_default="zsbj"
    )
    serial_number: Mapped[str] = mapped_column(String(32), nullable=False)
    approval_code: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applicant_user_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    department_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency_code: Mapped[str] = mapped_column(
        String(8), nullable=False, default="CNY", server_default="CNY"
    )
    pay_method: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    invoice: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    payee: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    payee_bank: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    payee_account_last4: Mapped[str] = mapped_column(
        String(8), nullable=False, default="", server_default=""
    )
    fee_category: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    related_serial: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    records: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    comments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # 第二家公司的人不在系统员工表里：同步时从它的通讯录查到的 user_id → 姓名
    people_names: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    last_run_id: Mapped[UUID | None] = mapped_column()
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
