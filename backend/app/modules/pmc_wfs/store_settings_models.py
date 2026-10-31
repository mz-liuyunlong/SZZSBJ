"""Per-store WFS creation settings (owner decision 2026-10-31, handover chapter 74.6).

A Lingxing store must be mapped to its Walmart store code and explicitly marked as
able to use ITS (inventory transfer service) before the creation adapter will build a
shipment for it. Rows are maintained from the WFS settings page (step 4); until that
page exists they are seeded by an owner-authorized SQL ticket.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.pmc_domestic.packing_models import now


class WfsStoreSetting(Base):
    __tablename__ = "ops_wfs_store_settings"
    __table_args__ = (
        UniqueConstraint("source_account_ref", "store_id", name="uq_wfs_store_setting_store"),
        UniqueConstraint(
            "source_account_ref", "walmart_store_code", name="uq_wfs_store_setting_code"
        ),
        # Code format (HK|CN + 4 digits) is validated in the adapter so the table also
        # creates on SQLite in tests.
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    # Lingxing store id as it appears on packing orders / dim_lingxing_stores.
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Walmart seller store code used for SCF routing (HK2614, CN2501, ...).
    walmart_store_code: Mapped[str] = mapped_column(String(16), nullable=False)
    # Owner-confirmed: the store has ITS available in Seller Center.
    its_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Master switch per store; off = creation refused before any box hold is taken.
    creation_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(String(500))
    actor_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now, onupdate=now
    )
