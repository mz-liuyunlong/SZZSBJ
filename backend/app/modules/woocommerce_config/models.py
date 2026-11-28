from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WooCommerceStore(Base):
    __tablename__ = "sys_woocommerce_stores"
    __table_args__ = (
        UniqueConstraint("store_url", name="uq_sys_woocommerce_stores_store_url"),
        CheckConstraint(
            "char_length(name) BETWEEN 2 AND 100",
            name="ck_sys_woocommerce_stores_name",
        ),
        CheckConstraint("store_url LIKE 'https://%'", name="ck_sys_woocommerce_stores_https"),
        Index("ix_sys_woocommerce_stores_enabled_updated", "enabled", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    store_url: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    consumer_key_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    consumer_secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
