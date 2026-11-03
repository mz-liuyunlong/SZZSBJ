"""API registry of the PMC overview board (PRP pmc-overview §5)."""

from __future__ import annotations

from dataclasses import dataclass

READ_ONLY_BOUNDARY = (
    "只读；5173 过渡数据源 = 8088 数据日快照文件（PMC_OVERVIEW_SNAPSHOT_FILE），"
    "不读写数据库、不调领星 / Walmart；文件缺失返回 503，不回退示例数据"
)


@dataclass(frozen=True)
class OverviewApiRegistryEntry:
    key: str
    prp_ref: str
    route_path: str
    permission: str
    demo_ref: str
    empty_data_behavior: str
    current_boundary: str = READ_ONLY_BOUNDARY


def _e(key: str, path: str, demo: str, empty: str) -> OverviewApiRegistryEntry:
    return OverviewApiRegistryEntry(
        key=key,
        prp_ref="PRPs/pmc-overview.md §5",
        route_path=path,
        permission="pmc:overview:read",
        demo_ref=f"features/pmc-overview/drafts/src/app.jsx {demo}",
        empty_data_behavior=empty,
    )


PMC_OVERVIEW_API_REGISTRY = {
    e.key: e
    for e in (
        _e("summary", "/api/pmc/overview/summary", "App SummaryCard", "503 未就绪"),
        _e("items", "/api/pmc/overview/items", "TabMain", "items=[]，total=0"),
        _e("item", "/api/pmc/overview/items/{item_id}", "ItemDrawer", "404"),
        _e("filter_options", "/api/pmc/overview/filter-options", "TabMain toolbar", "空列表"),
        _e("warehouses", "/api/pmc/overview/warehouses", "TabWarehouse", "空列表"),
        _e("rules", "/api/pmc/overview/rules", "TabRules", "空列表"),
        _e("export", "/api/pmc/overview/export", "buildWorkbook", "items=[]"),
    )
}
