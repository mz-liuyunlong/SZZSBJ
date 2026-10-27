from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.data_pages.models import ListingArchiveState, ListingManagementCurrentMart


@dataclass(frozen=True, slots=True)
class MonitorTargetRecord:
    source_account_ref: str
    store_id: str
    item_id: str
    store_name: str | None
    sku: str | None
    msku: str | None
    owner: str | None
    product_name: str | None
    product_category: str | None
    wfs_inventory: Decimal | None


class WalmartMonitorTargetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[MonitorTargetRecord], int, datetime | None]:
        not_archived = (
            ~select(ListingArchiveState.id)
            .where(
                ListingArchiveState.listing_id == ListingManagementCurrentMart.id,
                ListingArchiveState.is_archived.is_(True),
            )
            .exists()
        )
        total, latest_calculated_at = self.session.execute(
            select(
                func.count(ListingManagementCurrentMart.id),
                func.max(ListingManagementCurrentMart.calculated_at),
            ).where(not_archived)
        ).one()
        statement = (
            select(
                ListingManagementCurrentMart.source_account_ref,
                ListingManagementCurrentMart.store_id,
                ListingManagementCurrentMart.item_id,
                ListingManagementCurrentMart.store_name,
                ListingManagementCurrentMart.local_sku.label("sku"),
                ListingManagementCurrentMart.msku,
                ListingManagementCurrentMart.owner_ref.label("owner"),
                ListingManagementCurrentMart.local_name.label("product_name"),
                ListingManagementCurrentMart.category.label("product_category"),
                ListingManagementCurrentMart.wfs_available_quantity.label("wfs_inventory"),
            )
            .where(not_archived)
            .order_by(
                ListingManagementCurrentMart.source_account_ref,
                ListingManagementCurrentMart.store_id,
                ListingManagementCurrentMart.item_id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = self.session.execute(statement).mappings().all()
        return (
            [MonitorTargetRecord(**dict(row)) for row in rows],
            int(total or 0),
            latest_calculated_at,
        )
