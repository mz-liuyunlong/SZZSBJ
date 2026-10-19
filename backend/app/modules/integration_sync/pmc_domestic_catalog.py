"""Governance catalog for domestic warehouse Lingxing sync (Gate 2, phase 1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

RequestKind = Literal["offset_page"]

PMC_DOMESTIC_HANDLER_PREFIX: Final = "lingxing.pmc_domestic."
PMC_DOMESTIC_POLICY_PREFIX: Final = "lingxing-pmc-domestic-"


@dataclass(frozen=True, slots=True)
class PmcDomesticSyncInterfaceSpec:
    interface_key: str
    registry_interface_id: str
    display_name: str
    endpoint_path: str
    request_kind: RequestKind
    handler_key: str
    target_tables: tuple[str, ...]
    retention_policy_key: str
    default_page_size: int
    default_max_pages: int
    returns_total: bool
    requires_date_window: bool
    initial_outbound_enabled: bool = False
    schedule_enabled: bool = False
    notes: tuple[str, ...] = ()


PMC_DOMESTIC_SYNC_INTERFACE_SPECS: Final[tuple[PmcDomesticSyncInterfaceSpec, ...]] = (
    PmcDomesticSyncInterfaceSpec(
        interface_key="domesticWarehouseList",
        registry_interface_id="LX-41E509578C0D",
        display_name="Lingxing Domestic Warehouse List",
        endpoint_path="/erp/sc/data/local_inventory/warehouse",
        request_kind="offset_page",
        handler_key=f"{PMC_DOMESTIC_HANDLER_PREFIX}warehouse_list.v1",
        target_tables=("ods_lingxing_domestic_warehouses",),
        retention_policy_key=f"{PMC_DOMESTIC_POLICY_PREFIX}warehouse-list-v1",
        default_page_size=500,
        default_max_pages=100,
        returns_total=True,
        requires_date_window=False,
        notes=("Full warehouse catalog snapshot; append-only ODS.",),
    ),
    PmcDomesticSyncInterfaceSpec(
        interface_key="domesticInventoryDetails",
        registry_interface_id="LX-41B3AF612B29",
        display_name="Lingxing Domestic Inventory Details",
        endpoint_path="/erp/sc/routing/data/local_inventory/inventoryDetails",
        request_kind="offset_page",
        handler_key=f"{PMC_DOMESTIC_HANDLER_PREFIX}inventory_details.v1",
        target_tables=("ods_lingxing_domestic_inventory",),
        retention_policy_key=f"{PMC_DOMESTIC_POLICY_PREFIX}inventory-details-v1",
        default_page_size=800,
        default_max_pages=2000,
        returns_total=True,
        requires_date_window=False,
        notes=("Inventory snapshot; optional wid filter via sync config notes only.",),
    ),
    PmcDomesticSyncInterfaceSpec(
        interface_key="domesticBatchDetailList",
        registry_interface_id="LX-1181D4F827FB",
        display_name="Lingxing Domestic Batch Detail List",
        endpoint_path="/erp/sc/routing/data/local_inventory/getBatchDetailList",
        request_kind="offset_page",
        handler_key=f"{PMC_DOMESTIC_HANDLER_PREFIX}batch_detail_list.v1",
        target_tables=("ods_lingxing_domestic_batches",),
        retention_policy_key=f"{PMC_DOMESTIC_POLICY_PREFIX}batch-detail-list-v1",
        default_page_size=400,
        default_max_pages=5000,
        returns_total=True,
        requires_date_window=False,
        notes=("Batch inventory snapshot for reconciliation; board reads DWD receipts only.",),
    ),
    PmcDomesticSyncInterfaceSpec(
        interface_key="domesticBatchStatementList",
        registry_interface_id="LX-BCB9BCE2437F",
        display_name="Lingxing Domestic Batch Statement List",
        endpoint_path="/erp/sc/routing/data/local_inventory/getBatchStatementList",
        request_kind="offset_page",
        handler_key=f"{PMC_DOMESTIC_HANDLER_PREFIX}batch_statement_list.v1",
        target_tables=("ods_lingxing_domestic_inventory_events",),
        retention_policy_key=f"{PMC_DOMESTIC_POLICY_PREFIX}batch-statement-list-v1",
        default_page_size=400,
        default_max_pages=5000,
        returns_total=True,
        requires_date_window=True,
        notes=(
            "Bounded operate_time window on the run; default time_filter_field=operate_time.",
        ),
    ),
)

PMC_DOMESTIC_SPECS_BY_INTERFACE_KEY: Final[dict[str, PmcDomesticSyncInterfaceSpec]] = {
    spec.interface_key: spec for spec in PMC_DOMESTIC_SYNC_INTERFACE_SPECS
}


def pmc_domestic_interface_keys() -> frozenset[str]:
    return frozenset(PMC_DOMESTIC_SPECS_BY_INTERFACE_KEY)
