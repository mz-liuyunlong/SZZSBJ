"""Extra holds are separate from approval Q and attributed to their real inbound sources."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.pmc_domestic.packing_models import now


class PackingExtraAllocation(Base):
    __tablename__ = "ops_domestic_packing_extra_allocations"
    __table_args__ = (
        UniqueConstraint("order_id", "source_board_id"),
        CheckConstraint("qty>0", name="packing_extra_qty"),
        ForeignKeyConstraint(
            ["source_publication_id", "source_board_id"],
            [
                "mart_domestic_inbound_batch_board.publication_id",
                "mart_domestic_inbound_batch_board.id",
            ],
            ondelete="RESTRICT",
        ),
        Index("ix_packing_extra_source", "source_account_ref", "warehouse_id", "source_board_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops_domestic_packing_orders.id", ondelete="RESTRICT"), nullable=False
    )
    source_account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    warehouse_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sku: Mapped[str] = mapped_column(String(255), nullable=False)
    source_publication_id: Mapped[UUID] = mapped_column(nullable=False)
    source_board_id: Mapped[UUID] = mapped_column(nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )
