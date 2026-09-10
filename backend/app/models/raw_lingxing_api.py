from datetime import UTC, date, datetime

from pydantic import JsonValue
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Identity,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class RawLingxingApi(Base):
    __tablename__ = "raw_lingxing_api"
    __table_args__ = (
        CheckConstraint("source_system = 'lingxing'", name="ck_raw_lingxing_api_source_system"),
        CheckConstraint("request_method = 'POST'", name="ck_raw_lingxing_api_request_method"),
        CheckConstraint(
            "api_path IN ("
            "'/basicOpen/multiplatform/walmart/list', "
            "'/basicOpen/platformStatisticsV2/saleStat/pageList', "
            "'/erp/sc/routing/data/local_inventory/batchGetProductInfo', "
            "'/pb/mp/shop/v2/getSellerList', "
            "'/basicOpen/multiplatform/profit/report/order'"
            ")",
            name="ck_raw_lingxing_api_api_path",
        ),
        CheckConstraint("attempt_no >= 1", name="ck_raw_lingxing_api_attempt_no"),
        CheckConstraint("page_no IS NULL OR page_no >= 1", name="ck_raw_lingxing_api_page_no"),
        CheckConstraint(
            "page_size IS NULL OR page_size BETWEEN 1 AND 3", name="ck_raw_lingxing_api_page_size"
        ),
        CheckConstraint("char_length(raw_hash) = 64", name="ck_raw_lingxing_api_raw_hash"),
        Index("ix_raw_lingxing_api_raw_hash", "raw_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_system: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="lingxing",
    )
    api_path: Mapped[str] = mapped_column(Text, nullable=False)
    request_method: Mapped[str] = mapped_column(String(10), nullable=False, default="POST")
    request_params_json: Mapped[JsonValue | None] = mapped_column(JSONB)
    request_body_json: Mapped[JsonValue | None] = mapped_column(JSONB)
    response_json: Mapped[JsonValue | None] = mapped_column(JSONB)
    response_code: Mapped[int | None] = mapped_column(Integer)
    is_success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    data_date: Mapped[date | None] = mapped_column(Date)
    pulled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer)
    page_size: Mapped[int | None] = mapped_column(Integer)
    store_id: Mapped[str | None] = mapped_column(Text)
    store_name: Mapped[str | None] = mapped_column(Text)
    object_type: Mapped[str] = mapped_column(Text, nullable=False)
    trace_id: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    batch_id: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    extra_json: Mapped[JsonValue | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
