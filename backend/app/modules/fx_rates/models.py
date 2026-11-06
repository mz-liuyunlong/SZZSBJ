from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LingxingFxRate(Base):
    """领星月汇率：全系统唯一的汇率来源，按「月份 + 币种」一行。"""

    __tablename__ = "fact_lingxing_fx_rate"
    __table_args__ = (
        CheckConstraint("rate_month ~ '^[0-9]{4}-[0-9]{2}$'", name="rate_month_format"),
        CheckConstraint("rate_org IS NULL OR rate_org > 0", name="rate_org_positive"),
        CheckConstraint("my_rate IS NULL OR my_rate > 0", name="my_rate_positive"),
        CheckConstraint("source IN ('sync', 'seed')", name="source"),
    )

    rate_month: Mapped[str] = mapped_column(String(7), primary_key=True)
    currency_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    currency_name: Mapped[str | None] = mapped_column(String(64))
    rate_org: Mapped[Decimal | None] = mapped_column(Numeric(18, 10))
    my_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 10))
    lx_update_time: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    raw_request_ref_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ods_api_raw_request_refs.id", ondelete="RESTRICT")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
