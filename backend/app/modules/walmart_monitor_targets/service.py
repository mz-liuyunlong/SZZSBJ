from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.modules.walmart_monitor_targets.repository import (
    MonitorTargetRecord,
    WalmartMonitorTargetRepository,
)
from app.modules.walmart_monitor_targets.schemas import (
    MonitorTargetListData,
    MonitorTargetQuery,
    MonitorTargetRead,
    MonitorTargetReadMeta,
)


class TargetRepository(Protocol):
    def list_page(
        self,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[MonitorTargetRecord], int, datetime | None]: ...


class WalmartMonitorTargetService:
    def __init__(self, session: Session, repository: TargetRepository | None = None) -> None:
        self.repository = repository or WalmartMonitorTargetRepository(session)

    def list_targets(
        self,
        query: MonitorTargetQuery,
    ) -> tuple[MonitorTargetListData, MonitorTargetReadMeta]:
        rows, total, latest_calculated_at = self.repository.list_page(
            page=query.page,
            page_size=query.page_size,
        )
        data = MonitorTargetListData(
            items=[
                MonitorTargetRead(
                    source_account_ref=row.source_account_ref,
                    store_id=row.store_id,
                    item_id=row.item_id,
                    store_name=row.store_name,
                    sku=row.sku,
                    msku=row.msku,
                    owner=row.owner,
                    product_name=row.product_name,
                    product_category=row.product_category,
                    wfs_inventory=row.wfs_inventory,
                    monitoring_eligible=True,
                )
                for row in rows
            ],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )
        return data, MonitorTargetReadMeta(latest_calculated_at=latest_calculated_at)
