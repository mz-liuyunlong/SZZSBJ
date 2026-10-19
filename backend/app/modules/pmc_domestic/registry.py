"""Stable route list for the domestic batch board read API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

DomesticApiKey = Literal["batches", "summary", "detail", "trace", "filter-options"]

PERMISSION_READ: Final = "pmc:domestic-batch:read"
PAGE_PERMISSION: Final = "page:pmc:domestic-warehouse-board:view"
READ_ONLY_BOUNDARY: Final = (
    "Read-only DWD/DIM API. No Lingxing call, no ODS/RAW read, no write, no Celery task."
)


@dataclass(frozen=True, slots=True)
class DomesticApiRegistryEntry:
    key: DomesticApiKey
    route_path: str
    permission: str
    source_objects: tuple[str, ...]


DOMESTIC_BATCH_API_REGISTRY: Final[dict[DomesticApiKey, DomesticApiRegistryEntry]] = {
    "filter-options": DomesticApiRegistryEntry(
        key="filter-options", route_path="/api/pmc/domestic/filter-options",
        permission=PERMISSION_READ,
        source_objects=("dwd_domestic_receipt_batch", "dwd_domestic_receipt_batch_link",
                        "dim_lingxing_stores", "dwd_lingxing_sku_identity_index",
                        "dwd_lingxing_sku_product_info_current"),
    ),
    "batches": DomesticApiRegistryEntry(
        key="batches",
        route_path="/api/pmc/domestic/batches",
        permission=PERMISSION_READ,
        source_objects=("dwd_domestic_receipt_batch", "dwd_domestic_receipt_batch_link"),
    ),
    "summary": DomesticApiRegistryEntry(
        key="summary",
        route_path="/api/pmc/domestic/batches/summary",
        permission=PERMISSION_READ,
        source_objects=("dwd_domestic_receipt_batch", "dwd_domestic_receipt_batch_link"),
    ),
    "detail": DomesticApiRegistryEntry(
        key="detail",
        route_path="/api/pmc/domestic/batches/{batch_id}",
        permission=PERMISSION_READ,
        source_objects=("dwd_domestic_receipt_batch", "dwd_domestic_receipt_batch_link"),
    ),
    "trace": DomesticApiRegistryEntry(
        key="trace",
        route_path="/api/pmc/domestic/batches/{batch_id}/trace",
        permission=PERMISSION_READ,
        source_objects=("dwd_domestic_receipt_batch", "dwd_domestic_receipt_batch_link"),
    ),
}
