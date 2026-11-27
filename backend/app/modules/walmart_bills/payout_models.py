"""回款对账（PR-2）：收款账户映射、到账配对、审核记录、跟进记录。

- 账单期次只读 mart_walmart_bill_periods（同步任务写）；
  到账只读日记账流水 std_finance_cashflow_lines。
- 这里四张表只放人工 / 自动配对的结果和审核、跟进留痕；审核状态由审核记录按时间重放得出。
- 真实收款账户、户名、邮箱只在生产库录入，仓库里只有空表和合成测试数据。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
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


class WalmartPayoutAccount(Base):
    """店铺 → 收款账户（日记账账户）+ 收款账户识别（派安盈付款邮箱 / PingPong 公司名）。

    一个店同一天只有一条生效记录；换账户 = 旧记录写 effective_to、再加一条新记录（留历史）。
    """

    __tablename__ = "cfg_walmart_payout_accounts"
    __table_args__ = (
        Index("ix_cfg_walmart_payout_accounts_store", "store_id", "effective_from"),
        Index(
            "uq_cfg_walmart_payout_accounts_store_from",
            "source_account_ref",
            "store_id",
            "effective_from",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        CheckConstraint("store_id ~ '^[0-9]+$'", name="store_id_digits"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name="effective_range"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    account_key: Mapped[str] = mapped_column(
        ForeignKey("dim_finance_cash_accounts.account_key"), nullable=False
    )
    payee: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    change_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class WalmartPayoutMatch(Base):
    """一笔到账（日记账流水）配给一期或几期账单。同一 match_id 的几行 = 一次配对（合并打款）。

    撤销配对只写 undone_*，不删行；生效中的配对：一期只能配一次，一笔到账只能在一组里。
    memo_before / memo_set / category_set：配对前日记账的备注、配对写上的备注、是否自动填了
    「平台回款」；撤销时备注没被人改过才恢复。
    """

    __tablename__ = "manual_walmart_payout_matches"
    __table_args__ = (
        Index(
            "uq_manual_walmart_payout_matches_period",
            "source_account_ref",
            "store_id",
            "report_key",
            unique=True,
            postgresql_where=text("undone_at IS NULL"),
        ),
        Index(
            "uq_manual_walmart_payout_matches_line",
            "line_uid",
            "seq",
            unique=True,
            postgresql_where=text("undone_at IS NULL"),
        ),
        Index("ix_manual_walmart_payout_matches_match", "match_id"),
        CheckConstraint("method IN ('auto', 'manual')", name="method"),
        CheckConstraint("seq >= 0", name="seq_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    match_id: Mapped[UUID] = mapped_column(nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    line_uid: Mapped[str] = mapped_column(
        ForeignKey("std_finance_cashflow_lines.line_uid"), nullable=False
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    report_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payable_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    memo_before: Mapped[str | None] = mapped_column(Text)
    memo_set: Mapped[str | None] = mapped_column(Text)
    category_set: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    undone_by: Mapped[str | None] = mapped_column(String(255))
    undo_reason: Mapped[str | None] = mapped_column(Text)


class WalmartPayoutReviewEvent(Base):
    """回款对账的审核留痕：只追加。kind = review1_pass / review2_pass / review2_reject / reset。"""

    __tablename__ = "evt_walmart_payout_reviews"
    __table_args__ = (
        Index(
            "ix_evt_walmart_payout_reviews_period",
            "source_account_ref",
            "store_id",
            "report_key",
            "created_at",
        ),
        CheckConstraint(
            "kind IN ('review1_pass', 'review2_pass', 'review2_reject', 'reset')", name="kind"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # 全局递增序号：同一事务里 created_at 相同，按它排先后。
    seq_no: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    report_key: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class WalmartPayoutFollowUp(Base):
    """打款异常跟进：每次保存追加一条（跟进内容必填，Case 编号、下次跟进日期可空）。"""

    __tablename__ = "evt_walmart_payout_follow_ups"
    __table_args__ = (
        Index(
            "ix_evt_walmart_payout_follow_ups_period",
            "source_account_ref",
            "store_id",
            "report_key",
            "created_at",
        ),
        CheckConstraint("length(btrim(content)) > 0", name="content_not_blank"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    store_id: Mapped[str] = mapped_column(String(32), nullable=False)
    report_key: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    case_no: Mapped[str | None] = mapped_column(String(128))
    next_follow_date: Mapped[date | None] = mapped_column(Date)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
