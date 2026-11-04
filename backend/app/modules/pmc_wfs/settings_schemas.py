"""WFS settings contracts (PRP ``PRPs/pmc-wfs-settings.md`` §5)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.modules.pmc_domestic.warehouse_schemas import Strict

Region = Literal["美西", "美中", "美东", "待定"]
Transport = Literal["LTL", "SMALL_PARCEL", "FTL"]
CarrierOpt = Literal["own", "wm"]
Reason = Field(min_length=2, max_length=500)


class RuleRow(Strict):
    rule_key: str | None = Field(default=None, max_length=64)
    node: str = Field(min_length=1, max_length=255)
    region: str = Field(min_length=1, max_length=32)
    carrier: str = Field(min_length=1, max_length=128)
    channel: str = Field(min_length=1, max_length=128)
    days: int = Field(ge=0, le=365)
    remind_days: int = Field(ge=0, le=365)
    row_effective_date: date
    notify: str = Field(default="", max_length=255)
    remark: str = Field(default="", max_length=2000)
    decided: bool


class RuleVersionOut(Strict):
    version_no: int
    effective_date: date
    reason: str
    created_by: str
    created_at: datetime


class RuleSetOut(Strict):
    version: RuleVersionOut
    rows: list[RuleRow]
    sample_rows: int  # rows still 示例 · 待定 (decided = False)


SortOrder = Literal["asc", "desc"]


class RuleRowQuery(Strict):
    """Paged rule rows of the version in force (SEARCH_FILTER_SORT_RULES: whitelisted sort)."""

    at: date | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=1000)
    keyword: str | None = Field(default=None, max_length=100)
    search_field: Literal["all", "node", "remark", "notify"] = "all"
    region: str | None = Field(default=None, max_length=32)
    decided: bool | None = None
    sort_by: Literal["row_no", "node", "days", "row_effective_date"] = "row_no"
    sort_order: SortOrder = "asc"


class RuleRowPage(Strict):
    version: RuleVersionOut
    items: list[RuleRow]
    total: int
    sample_rows: int  # whole version, not just this page
    regions: list[str]  # 下拉选项


class RuleVersionList(Strict):
    items: list[RuleVersionOut]


class RuleVersionCreate(Strict):
    effective_date: date
    reason: str = Reason
    rows: list[RuleRow] = Field(min_length=1, max_length=100)


class FcRegionOut(Strict):
    fc: str
    name: str | None
    zip: str | None
    city: str | None
    state: str | None
    address: str | None  # 地址全称（领星 distribution_addresses 整理）
    region: Region
    region_source: Literal["saved", "state"]  # saved = 本系统改过；state = 按州预填
    shipments: int
    updated_by: str | None = None
    updated_at: datetime | None = None


class FcRegionQuery(Strict):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=1000)
    keyword: str | None = Field(default=None, max_length=100)
    search_field: Literal["all", "fc", "zip", "address"] = "all"
    region: Region | None = None
    state: str | None = Field(default=None, max_length=8)
    sort_by: Literal["fc", "zip", "state", "shipments"] = "fc"
    sort_order: SortOrder = "asc"


class FcRegionList(Strict):
    items: list[FcRegionOut]
    total: int
    states: list[str]  # 下拉选项：看板上出现过的州


class FcRegionUpdate(Strict):
    region: Region
    name: str | None = Field(default=None, max_length=128)
    reason: str = Reason


class CreationDefaults(Strict):
    transport: Transport
    ship_date_offset: int = Field(ge=0, le=120)
    pallet_boxes: int = Field(ge=1, le=100)
    mixed_boxes: int = Field(ge=0, le=1000)
    carrier_opt: CarrierOpt


class CreationDefaultsOut(CreationDefaults):
    source_account_ref: str
    saved: bool  # False = 8088 默认值，本账号还没保存过
    updated_by: str | None = None
    updated_at: datetime | None = None


class CreationDefaultsUpdate(CreationDefaults):
    source_account_ref: str | None = Field(default=None, min_length=1, max_length=128)
    reason: str = Reason


class LogisticsChannelOut(Strict):
    provider_id: str | None
    provider_name: str | None
    channel_id: str
    channel_name: str | None
    method_name: str | None
    enabled: bool


class ChannelQuery(Strict):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=1000)
    keyword: str | None = Field(default=None, max_length=100)
    search_field: Literal["all", "channel_id", "channel_name", "provider"] = "all"
    provider: str | None = Field(default=None, max_length=255)
    method: str | None = Field(default=None, max_length=128)
    enabled: bool | None = None
    sort_by: Literal["provider_name", "channel_id", "channel_name"] = "provider_name"
    sort_order: SortOrder = "asc"


class LogisticsChannelList(Strict):
    items: list[LogisticsChannelOut]
    loaded: bool  # False = WFS 组尚未导入渠道文件
    total: int
    providers: list[str]  # 下拉选项
    methods: list[str]


class SettingsChangeOut(Strict):
    entity: str
    entity_key: str
    before: dict | None
    after: dict
    reason: str
    actor: str
    created_at: datetime


class SettingsChangeList(Strict):
    items: list[SettingsChangeOut]
    total: int


class ChangeQuery(Strict):
    entity: Literal["rules", "fc_region", "creation_defaults"] | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
