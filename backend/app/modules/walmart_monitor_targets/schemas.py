from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TargetSourceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, hide_input_in_errors=True)


class MonitorTargetQuery(TargetSourceSchema):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=200, ge=1, le=500)


class MonitorTargetRead(TargetSourceSchema):
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
    monitoring_eligible: bool = True


class MonitorTargetListData(TargetSourceSchema):
    items: list[MonitorTargetRead]
    total: int
    page: int
    page_size: int


class MonitorTargetReadMeta(TargetSourceSchema):
    source: str = "listing_management"
    source_tables: list[str] = Field(
        default_factory=lambda: ["mart_listing_management_current", "listing_archive_states"]
    )
    latest_calculated_at: datetime | None = None
