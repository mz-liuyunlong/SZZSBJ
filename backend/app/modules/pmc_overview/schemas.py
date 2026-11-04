"""Request / response models of the PMC overview board (read-only)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


CATEGORIES = (
    "Listing 异常",
    "已断货",
    "断货风险",
    "供应链异常",
    "执行异常",
    "库存过剩",
    "严重过剩",
    "滞销",
    "近 90 天无库存",
    "有库存不足 30 天",
    "海外仓可补",
    "超期未上架",
    "缺默认箱规",
)
type Category = Literal[
    "Listing 异常",
    "已断货",
    "断货风险",
    "供应链异常",
    "执行异常",
    "库存过剩",
    "严重过剩",
    "滞销",
    "近 90 天无库存",
    "有库存不足 30 天",
    "海外仓可补",
    "超期未上架",
    "缺默认箱规",
]


# --- queries ---------------------------------------------------------------------------------


class OverviewFilterQuery(StrictSchema):
    store_id: str | None = Field(default=None, max_length=64)
    owner: str | None = Field(default=None, max_length=64)
    # Selected categories must all apply (8088: ``f.cats.every``).
    cats: list[Category] = Field(default_factory=list, max_length=13)
    keyword: str | None = Field(default=None, max_length=100)
    only_issue: bool = True


# Same choices as the shared report table (REPORT_TABLE_PAGE_SIZE_OPTIONS).
PAGE_SIZES = (50, 100, 200, 500, 1000)
# Server-side sort whitelist (column key → row field); default = 8088 problem priority.
type OverviewSort = Literal[
    "daily", "wm_available", "supply", "cover", "oos_days", "n30", "gap_days"
]


class OverviewItemsQuery(OverviewFilterQuery):
    page: int = Field(default=1, ge=1)
    # Plain int + membership check: a ``Literal[50, ...]`` never matches the query string "50",
    # which made every real list request fail with 422 (fix 2026-11-04).
    page_size: int = 50
    sort_by: OverviewSort | None = None
    sort_order: Literal["asc", "desc"] = "desc"

    @field_validator("page_size")
    @classmethod
    def _page_size_allowed(cls, value: int) -> int:
        if value not in PAGE_SIZES:
            raise ValueError("page_size must be one of 50/100/200/500/1000")
        return value


# --- fragments -------------------------------------------------------------------------------


class IssueOut(StrictSchema):
    label: str
    level: str
    detail: str


class StoreShareOut(StrictSchema):
    id: str
    name: str
    sales30: int = 0
    available: int = 0
    intransit: int = 0


class OverviewItemRow(StrictSchema):
    """One ItemID (multiple stores merged); segments are mutually exclusive."""

    item_id: str
    sku: str
    msku: str
    name: str
    owner: str
    stores: list[StoreShareOut]
    listing: str
    tags: list[str]
    daily: float
    n30: int
    n_window: int | None = None
    oos_days: int | None
    no_stock_90: bool
    supply: int
    wm_available: int
    seg: dict[str, int]
    dom_lock: int
    sellout: str | None
    gap_days: int | None
    resume: str | None
    next_date: str | None
    lead_total: float
    lead_p: float | None = None
    lead_avg: float | None
    cycle_days: int | None = None
    suggest: int
    suggest_raw: int
    capped: bool
    box: int
    cover: int | None
    over: str | None
    stale: bool
    risk: bool
    oos: bool
    low_days: bool
    listing_bad: bool
    dom_over_qty: int
    dom_max: int | None
    overseas_total: int
    overseas_alloc: int
    purchase: int
    boxed: int | None
    is_draft: bool
    draft_id: str
    draft_text: str
    issues: list[IssueOut]
    sc_flags: list[IssueOut]
    exec_flags: list[IssueOut]
    main: str
    level: str
    cats: list[str]
    sort_cat: str


class OverviewItemDetail(OverviewItemRow):
    batches: list[dict[str, Any]]
    dom_rows: list[dict[str, Any]]
    plans_recent: list[dict[str, Any]]


# --- responses -------------------------------------------------------------------------------


class OverviewKpi(StrictSchema):
    items: int
    listing_bad: int
    oos: int
    risk: int
    over1: int
    over2: int
    stale: int
    supply_chain: int
    execution: int
    no_stock_90: int
    low_days: int
    overseas: int
    drafts: int
    normal: int
    low_supply: int
    overdue: int
    box_missing: int


class UnattributedOut(StrictSchema):
    kind: str
    why: str
    qty: int


class OverviewSummaryData(StrictSchema):
    data_date: str
    source: str
    source_note: str
    kpi: OverviewKpi
    params: dict[str, int]
    parity_with_8088: dict[str, dict[str, int]]
    unattributed: list[UnattributedOut]
    overseas_total: int


class OverviewItemListData(StrictSchema):
    items: list[OverviewItemRow]
    # Per category, over the rows matching every filter except ``cats`` (category buttons).
    category_counts: dict[str, int] = Field(default_factory=dict)


class OverviewFilterOptionsData(StrictSchema):
    stores: list[dict[str, str]]
    owners: list[str]
    categories: list[str]


class WarehouseOut(StrictSchema):
    name: str
    warehouse_class: str
    valid: int
    lock: int
    total: int
    onway: int
    skus: int
    age_avg: int | None = None
    age_max: int | None = None
    age_bands: dict[str, int] = Field(default_factory=dict)


class OverviewWarehouseData(StrictSchema):
    warehouses: list[WarehouseOut]
    overseas_total: int


class OverviewRuleParam(StrictSchema):
    key: str
    value: int


class OverviewRulesData(StrictSchema):
    rule_version: str
    editable: bool = False
    params: list[OverviewRuleParam]


class OverviewExportData(StrictSchema):
    """Everything the 5-sheet Excel needs (built in the browser like 8088)."""

    data_date: str
    source_note: str
    params: dict[str, int]
    store_summary: list[dict[str, Any]]
    items: list[OverviewItemRow]
    ops_heads: list[str]
    ops_rows: list[list[Any]]
    warehouses: list[WarehouseOut]


class OverviewReadMeta(StrictSchema):
    source: Literal["pmc_overview_snapshot_8088"] = "pmc_overview_snapshot_8088"
    source_objects: list[str]
    data_date: str
    rule_version: str
    draft_mode: str
    page: int | None = None
    page_size: int | None = None
    total: int | None = None
