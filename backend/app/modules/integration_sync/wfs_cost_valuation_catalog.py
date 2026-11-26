"""Governance catalog for the Lingxing WFS cost valuation flow (LX-8437AD0BCB9E).

Owned by the inventory claim PRP (PR 1). Outbound calls and schedules start disabled;
the first enable and any history backfill need the project owner's written approval.
"""

from __future__ import annotations

from typing import Final

from app.integrations.lingxing.wfs_cost_valuation_contracts import (
    WFS_COST_VALUATION_ENDPOINT,
    WFS_COST_VALUATION_INTERFACE_ID,
    WFS_COST_VALUATION_MAX_PAGE_SIZE,
)
from app.modules.integration_sync.wfs_catalog import WfsSyncInterfaceSpec
from app.modules.warehouse_wfs.inventory_flow_models import WFS_COST_VALUATION_FLOW_TABLE

WFS_COST_VALUATION_REGISTRY_INTERFACE_ID: Final = WFS_COST_VALUATION_INTERFACE_ID

WFS_COST_VALUATION_SYNC_SPEC: Final = WfsSyncInterfaceSpec(
    interface_key="wfsCostValuationFlow",
    display_name="WFS 成本计价流水同步",
    endpoint_path=WFS_COST_VALUATION_ENDPOINT,
    request_kind="offset_page",
    handler_key="lingxing.wfs.cost_valuation_flow.v1",
    target_table=WFS_COST_VALUATION_FLOW_TABLE,
    retention_policy_key="lingxing-wfs-cost-valuation-flow-v1",
    default_page_size=WFS_COST_VALUATION_MAX_PAGE_SIZE,
    default_max_pages=1000,
)
