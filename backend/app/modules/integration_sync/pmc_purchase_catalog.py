"""Static governance catalog for the PMC purchase-board sync interfaces (Gate 2, PR-C).

Mirrors ``data_pages_catalog.py``: one immutable spec per interface, consumed by
``IntegrationCatalogService.bootstrap_pmc_purchase_governance`` to create the
``gov_integration_interfaces`` / ``gov_raw_retention_policies`` /
``gov_integration_sync_configs`` rows. Everything is created disabled:
``outbound_enabled=False``, ``is_enabled=False``, ``schedule_enabled=False``.
Enabling any of them is a separate, owner-authorized production step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

RequestKind = Literal["offset_page"]

PMC_PURCHASE_HANDLER_PREFIX: Final = "lingxing.pmc_purchase."
PMC_PURCHASE_POLICY_PREFIX: Final = "lingxing-pmc-purchase-"
# Provider maximum for all three endpoints (official_verified_interfaces.csv).
PMC_PURCHASE_PAGE_SIZE: Final = 500


@dataclass(frozen=True, slots=True)
class PmcPurchaseSyncInterfaceSpec:
    """Static catalog contract for one PMC purchase Lingxing interface."""

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
    initial_outbound_enabled: bool = False
    schedule_enabled: bool = False
    notes: tuple[str, ...] = ()


PMC_PURCHASE_SYNC_INTERFACE_SPECS: Final[tuple[PmcPurchaseSyncInterfaceSpec, ...]] = (
    PmcPurchaseSyncInterfaceSpec(
        interface_key="purchasePlanList",
        registry_interface_id="LX-03B82747B50A",
        display_name="Lingxing Purchase Plan List",
        endpoint_path="/erp/sc/routing/data/local_inventory/getPurchasePlans",
        request_kind="offset_page",
        handler_key=f"{PMC_PURCHASE_HANDLER_PREFIX}purchase_plan_list.v1",
        target_tables=("ods_lingxing_purchase_plans",),
        retention_policy_key=f"{PMC_PURCHASE_POLICY_PREFIX}purchase-plan-list-v1",
        default_page_size=PMC_PURCHASE_PAGE_SIZE,
        default_max_pages=1000,
        returns_total=True,
        notes=(
            "Approval-cycle start and ITEMID remark source for the purchase board.",
            "Pulled without sids filter; store attribution happens in DWD/DWS.",
        ),
    ),
    PmcPurchaseSyncInterfaceSpec(
        interface_key="purchaseOrderList",
        registry_interface_id="LX-D332F931885E",
        display_name="Lingxing Purchase Order List",
        endpoint_path="/erp/sc/routing/data/local_inventory/purchaseOrderList",
        request_kind="offset_page",
        handler_key=f"{PMC_PURCHASE_HANDLER_PREFIX}purchase_order_list.v1",
        target_tables=("ods_lingxing_purchase_orders", "ods_lingxing_purchase_order_items"),
        retention_policy_key=f"{PMC_PURCHASE_POLICY_PREFIX}purchase-order-list-v1",
        default_page_size=PMC_PURCHASE_PAGE_SIZE,
        default_max_pages=1000,
        returns_total=False,
        notes=(
            "Provider returns no total; pagination stops on a short page.",
            "Header rows and item_list rows are written to separate ODS tables.",
        ),
    ),
    PmcPurchaseSyncInterfaceSpec(
        interface_key="purchaseReceiptOrderList",
        registry_interface_id="LX-4B9473A2D2E1",
        display_name="Lingxing Purchase Receipt Order List",
        endpoint_path="/erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/getOrderList",
        request_kind="offset_page",
        handler_key=f"{PMC_PURCHASE_HANDLER_PREFIX}purchase_receipt_order_list.v1",
        target_tables=("ods_lingxing_receipt_orders", "ods_lingxing_receipt_order_items"),
        retention_policy_key=f"{PMC_PURCHASE_POLICY_PREFIX}purchase-receipt-order-list-v1",
        default_page_size=PMC_PURCHASE_PAGE_SIZE,
        default_max_pages=1000,
        returns_total=True,
        notes=(
            "READY_FOR_PRP by Owner decision 2026-09-18 (docs/data-sources/decisions/"
            "pmc-purchase-board-decision.md); real calls still need separate authorization.",
            "receive_time is the purchase-board arrival date; rows nest under data.list.",
        ),
    ),
)

PMC_PURCHASE_SPECS_BY_INTERFACE_KEY: Final[dict[str, PmcPurchaseSyncInterfaceSpec]] = {
    spec.interface_key: spec for spec in PMC_PURCHASE_SYNC_INTERFACE_SPECS
}


def pmc_purchase_interface_keys() -> frozenset[str]:
    return frozenset(PMC_PURCHASE_SPECS_BY_INTERFACE_KEY)
