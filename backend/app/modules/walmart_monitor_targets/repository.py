from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.modules.data_pages.models import ListingArchiveState, ListingManagementCurrentMart
from app.modules.sku_detail.models import (
    LingxingSkuIdentity,
    LingxingSkuProductInfoCurrent,
)


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
        product_owner = func.coalesce(
            func.nullif(func.trim(LingxingSkuProductInfoCurrent.owner_name), ""),
            func.nullif(func.trim(LingxingSkuProductInfoCurrent.owner_uid), ""),
        )
        product_sku_key = func.lower(func.trim(LingxingSkuIdentity.lingxing_sku_code))
        unique_product_owner = (
            select(
                LingxingSkuIdentity.source_account_ref.label("source_account_ref"),
                product_sku_key.label("sku_key"),
                case(
                    (func.count(func.distinct(product_owner)) == 1, func.max(product_owner)),
                    else_=None,
                ).label("owner"),
            )
            .join(
                LingxingSkuProductInfoCurrent,
                LingxingSkuProductInfoCurrent.identity_id == LingxingSkuIdentity.id,
            )
            .where(
                LingxingSkuIdentity.is_active.is_(True),
                LingxingSkuIdentity.lingxing_sku_code.is_not(None),
                product_owner.is_not(None),
            )
            .group_by(LingxingSkuIdentity.source_account_ref, product_sku_key)
            .subquery()
        )
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
        listing_owner = func.coalesce(
            func.nullif(func.trim(ListingManagementCurrentMart.owner_ref), ""),
            unique_product_owner.c.owner,
        )
        statement = (
            select(
                ListingManagementCurrentMart.source_account_ref,
                ListingManagementCurrentMart.store_id,
                ListingManagementCurrentMart.item_id,
                ListingManagementCurrentMart.store_name,
                ListingManagementCurrentMart.local_sku.label("sku"),
                ListingManagementCurrentMart.msku,
                listing_owner.label("owner"),
                ListingManagementCurrentMart.local_name.label("product_name"),
                ListingManagementCurrentMart.category.label("product_category"),
                ListingManagementCurrentMart.wfs_available_quantity.label("wfs_inventory"),
            )
            .outerjoin(
                unique_product_owner,
                (
                    unique_product_owner.c.source_account_ref
                    == ListingManagementCurrentMart.source_account_ref
                )
                & (
                    unique_product_owner.c.sku_key
                    == func.lower(func.trim(ListingManagementCurrentMart.local_sku))
                ),
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
