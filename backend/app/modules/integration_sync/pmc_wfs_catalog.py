"""Governance catalog for the WFS shipment-board Lingxing sync (read-only, manual runs)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

RequestKind = Literal["offset_page"]

PMC_WFS_HANDLER_PREFIX: Final = "lingxing.pmc_wfs."
PMC_WFS_POLICY_PREFIX: Final = "lingxing-pmc-wfs-"


@dataclass(frozen=True, slots=True)
class PmcWfsSyncInterfaceSpec:
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


PMC_WFS_SYNC_INTERFACE_SPECS: Final[tuple[PmcWfsSyncInterfaceSpec, ...]] = (
    PmcWfsSyncInterfaceSpec(
        interface_key="wfsCargoPage",
        registry_interface_id="LX-C95DBD64F2A9",
        display_name="Lingxing WFS Cargo Page",
        endpoint_path="/cepf/warehouse/api/openApi/queryWFSCargoPage",
        request_kind="offset_page",
        handler_key=f"{PMC_WFS_HANDLER_PREFIX}cargo_page.v1",
        target_tables=("ods_lingxing_wfs_cargos", "ods_lingxing_wfs_cargo_goods"),
        retention_policy_key=f"{PMC_WFS_POLICY_PREFIX}cargo-page-v1",
        default_page_size=200,
        default_max_pages=200,
        returns_total=True,
        requires_date_window=True,
        notes=(
            "Account-wide WFS cargo snapshot by creation window; nested cargo_good_list "
            "lands in its own append-only ODS table.",
        ),
    ),
    PmcWfsSyncInterfaceSpec(
        interface_key="wfsShippingListPage",
        registry_interface_id="LX-C99E2D00C76D",
        display_name="Lingxing WFS Shipping List Page",
        endpoint_path="/cepf/warehouse/api/openApi/queryShippingListPage",
        request_kind="offset_page",
        handler_key=f"{PMC_WFS_HANDLER_PREFIX}shipping_list_page.v1",
        target_tables=("ods_lingxing_wfs_shipping_lists",),
        retention_policy_key=f"{PMC_WFS_POLICY_PREFIX}shipping-list-page-v1",
        # 200/page timed out at 30 s against production data on 2026-10-30; 50/page finished
        # 10 pages in 65 s.
        default_page_size=50,
        default_max_pages=200,
        returns_total=True,
        requires_date_window=True,
        notes=(
            "Platform-warehouse shipping lists (SP) by creation window; query-only despite "
            "the registry export marking the v1 endpoint as write.",
        ),
    ),
)

PMC_WFS_SPECS_BY_INTERFACE_KEY: Final[dict[str, PmcWfsSyncInterfaceSpec]] = {
    spec.interface_key: spec for spec in PMC_WFS_SYNC_INTERFACE_SPECS
}


def pmc_wfs_interface_keys() -> frozenset[str]:
    return frozenset(PMC_WFS_SPECS_BY_INTERFACE_KEY)
