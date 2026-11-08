from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PermissionType = Literal["page", "action", "field"]
RiskLevel = Literal["normal", "high"]


@dataclass(frozen=True, slots=True)
class PageDefinition:
    page_key: str
    name: str
    sort_order: int


@dataclass(frozen=True, slots=True)
class ModuleDefinition:
    module_key: str
    name: str
    sort_order: int
    pages: tuple[PageDefinition, ...]


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    page_key: str
    action_key: str
    name: str
    sort_order: int
    risk_level: RiskLevel = "normal"


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    page_key: str
    field_key: str
    name: str
    sort_order: int
    risk_level: RiskLevel = "normal"


@dataclass(frozen=True, slots=True)
class PermissionDefinition:
    permission_key: str
    name: str
    description: str
    permission_type: PermissionType
    module_key: str
    page_key: str
    action_key: str | None
    field_key: str | None
    risk_level: RiskLevel
    sort_order: int


def _page(module_key: str, page_key: str, name: str, sort_order: int) -> PageDefinition:
    return PageDefinition(
        page_key=f"{module_key}_{page_key}",
        name=name,
        sort_order=sort_order,
    )


def _load_navigation_modules() -> tuple[ModuleDefinition, ...]:
    """Read the generated navigation registry; no second hard-coded page list."""
    payload = json.loads(
        Path(__file__).with_name("navigation_permissions.json").read_text(encoding="utf-8")
    )
    return tuple(
        ModuleDefinition(
            module_key=module["module_key"],
            name=module["name"],
            sort_order=int(module["sort_order"]),
            pages=tuple(
                PageDefinition(
                    page_key=page["page_key"],
                    name=page["name"],
                    sort_order=int(page["sort_order"]),
                )
                for page in module["pages"]
            ),
        )
        for module in payload["modules"]
    )


MODULES: tuple[ModuleDefinition, ...] = _load_navigation_modules()

ACTIONS: tuple[ActionDefinition, ...] = (
    ActionDefinition("ai_center_keyword_launch", "manage", "维护关键词来源与分析", 10),
    ActionDefinition("ai_center_keyword_rules", "submit", "提交关键词规则裁决", 10, "high"),
    ActionDefinition("ai_center_keyword_rules", "review", "复核关键词规则裁决", 20, "high"),
    ActionDefinition("ai_center_keyword_rules", "publish", "发布关键词规则", 30, "high"),
    ActionDefinition("pmc_domestic_warehouse_board", "packing-approve", "通过打包审批", 10),
    ActionDefinition("pmc_domestic_warehouse_board", "packing-reject", "驳回打包审批", 20),
    ActionDefinition("products_product_management", "view-sync-history", "查看同步历史", 8),
    ActionDefinition("products_product_management", "view-raw-lineage", "查看数据血缘", 9, "high"),
    ActionDefinition("products_product_management", "view-operation-logs", "查看操作日志", 10),
    ActionDefinition("products_product_management", "export", "导出产品", 10),
    ActionDefinition("products_product_management", "edit_grade", "修改产品等级", 20),
    ActionDefinition("products_product_management", "recalculate_pricing", "重算定价", 30, "high"),
    ActionDefinition("products_product_management", "save_table_view", "保存表格视图", 40),
    ActionDefinition(
        "products_product_management",
        "update-pricing-rules",
        "维护定价规则",
        50,
        "high",
    ),
    ActionDefinition("products_listing_management", "export", "导出Listing", 10),
    ActionDefinition("products_listing_management", "manage_tags", "管理标签", 20),
    ActionDefinition("products_listing_management", "archive", "归档Listing", 30, "high"),
    ActionDefinition("products_listing_management", "restore", "恢复Listing", 40),
    ActionDefinition("products_listing_management", "edit_analysis_link", "编辑分析链接", 50),
    ActionDefinition(
        "products_listing_management", "edit_lifecycle", "人工修改Listing生命周期", 55, "high"
    ),
    ActionDefinition(
        "products_listing_management", "configure_rules", "配置Listing评级规则", 60, "high"
    ),
    ActionDefinition(
        "products_listing_management", "manage_followups", "处理C/D等级跟进", 70, "high"
    ),
    ActionDefinition("sales_daily_sales", "export", "导出每日销售", 10),
    ActionDefinition("sales_order_profit", "export", "导出订单利润", 10),
    ActionDefinition("warehouse_wfs_fee_alert", "mark-recovered", "确认WFS费用已追回", 30, "high"),
    ActionDefinition("operations_plan", "create", "新增运营计划", 10),
    ActionDefinition("operations_plan", "edit", "编辑运营计划", 20),
    ActionDefinition("operations_plan", "import", "导入运营计划", 30),
    ActionDefinition("pmc_purchase_board", "override", "维护采购周期覆盖", 10, "high"),
    ActionDefinition("data_center_task_center", "configure", "维护同步配置", 10),
    ActionDefinition("data_center_task_center", "execute", "执行同步任务", 20, "high"),
    ActionDefinition("settings_fee_rules", "edit", "维护费用规则", 10),
    ActionDefinition("settings_fee_rules", "recalculate", "执行规则重算", 20, "high"),
    ActionDefinition("settings_user_management", "create", "新增用户", 10),
    ActionDefinition("settings_user_management", "edit", "编辑用户", 20),
    ActionDefinition("settings_user_management", "assign_role", "设置角色", 30, "high"),
    ActionDefinition("settings_user_management", "reset_password", "重置密码", 40, "high"),
    ActionDefinition("settings_user_management", "enable_disable", "停用或启用用户", 50, "high"),
    ActionDefinition("settings_user_management", "delete", "永久删除用户", 60, "high"),
    ActionDefinition(
        "settings_user_management",
        "configure_data_scope",
        "配置用户数据权限",
        70,
        "high",
    ),
    ActionDefinition("settings_role_management", "create", "新增角色", 10),
    ActionDefinition("settings_role_management", "edit", "编辑角色", 20),
    ActionDefinition(
        "settings_role_management",
        "configure_permissions",
        "配置页面、功能和字段权限",
        30,
        "high",
    ),
    ActionDefinition(
        "settings_role_management",
        "configure_data_scope",
        "配置数据权限",
        40,
        "high",
    ),
    ActionDefinition("settings_role_management", "view_audit", "查看权限审计", 50),
    ActionDefinition("finance_cash_flow", "import", "上传资金流水", 10, "high"),
    ActionDefinition("finance_cash_flow", "void-import", "作废资金流水批次", 20, "high"),
    ActionDefinition("finance_cash_flow", "edit-journal", "审核和编辑日记账", 30, "high"),
    ActionDefinition("finance_cash_flow", "sync-approvals", "手动同步财务审批单", 40, "high"),
    ActionDefinition("finance_cash_flow", "manage-accounts", "新增及维护财务账户", 50, "high"),
    ActionDefinition("finance_fx_rates", "sync", "手动同步月汇率", 10, "high"),
    ActionDefinition("settings_business_config", "manage-connectors", "配置业务连接器与密钥", 10, "high"),
    ActionDefinition("settings_business_config", "manage-decodo", "配置 Decodo 接口", 20, "high"),
    ActionDefinition("settings_business_config", "manage-notifications", "配置通知规则", 30, "high"),

)

FIELDS: tuple[FieldDefinition, ...] = (
    FieldDefinition("products_product_management", "purchase_cost", "采购成本", 10, "high"),
    FieldDefinition("products_product_management", "logistics_cost", "物流费用", 20, "high"),
    FieldDefinition("sales_order_profit", "gross_profit", "毛利润", 10, "high"),
    FieldDefinition("sales_order_profit", "profit_margin", "利润率", 20, "high"),
    FieldDefinition("settings_user_management", "phone", "手机号", 10, "high"),
    FieldDefinition("settings_user_management", "email", "邮箱", 20, "high"),
)

MODULE_NAMES = {module.module_key: module.name for module in MODULES}
PAGE_DEFINITIONS = {
    page.page_key: (module.module_key, module.name, page)
    for module in MODULES
    for page in module.pages
}
# Keyword-rule approvals retain an internal compatibility key even though
# their old navigation page was retired. Do not grant it automatically.
PAGE_DEFINITIONS.setdefault(
    "ai_center_keyword_rules",
    ("ai_center", "AI中心", _page("ai_center", "keyword_rules", "关键词规则", 999)),
)


def _slug(value: str) -> str:
    return value.replace("_", "-")


def page_permission_key(page_key: str) -> str:
    module_key, _module_name, page = PAGE_DEFINITIONS[page_key]
    local_key = page.page_key.removeprefix(f"{module_key}_")
    return f"page:{_slug(module_key)}:{_slug(local_key)}:view"


def action_permission_key(page_key: str, action_key: str) -> str:
    module_key, _module_name, page = PAGE_DEFINITIONS[page_key]
    local_key = page.page_key.removeprefix(f"{module_key}_")
    return f"action:{_slug(module_key)}:{_slug(local_key)}:{_slug(action_key)}"


def field_permission_key(page_key: str, field_key: str) -> str:
    module_key, _module_name, page = PAGE_DEFINITIONS[page_key]
    local_key = page.page_key.removeprefix(f"{module_key}_")
    return f"field:{_slug(module_key)}:{_slug(local_key)}:{_slug(field_key)}"


def _build_permission_definitions() -> tuple[PermissionDefinition, ...]:
    definitions: list[PermissionDefinition] = []
    for module in MODULES:
        for page in module.pages:
            definitions.append(
                PermissionDefinition(
                    permission_key=page_permission_key(page.page_key),
                    name=page.name,
                    description=f"允许进入并查看「{page.name}」页面",
                    permission_type="page",
                    module_key=module.module_key,
                    page_key=page.page_key,
                    action_key=None,
                    field_key=None,
                    risk_level="normal",
                    sort_order=module.sort_order * 1000 + page.sort_order,
                )
            )
    for action in ACTIONS:
        module_key, _module_name, page = PAGE_DEFINITIONS[action.page_key]
        definitions.append(
            PermissionDefinition(
                permission_key=action_permission_key(action.page_key, action.action_key),
                name=action.name,
                description=f"{page.name}：{action.name}",
                permission_type="action",
                module_key=module_key,
                page_key=action.page_key,
                action_key=action.action_key,
                field_key=None,
                risk_level=action.risk_level,
                sort_order=action.sort_order,
            )
        )
    for field in FIELDS:
        module_key, _module_name, page = PAGE_DEFINITIONS[field.page_key]
        definitions.append(
            PermissionDefinition(
                permission_key=field_permission_key(field.page_key, field.field_key),
                name=field.name,
                description=f"{page.name}字段：{field.name}",
                permission_type="field",
                module_key=module_key,
                page_key=field.page_key,
                action_key=None,
                field_key=field.field_key,
                risk_level=field.risk_level,
                sort_order=field.sort_order,
            )
        )
    return tuple(definitions)


PERMISSION_DEFINITIONS = _build_permission_definitions()
PERMISSION_KEYS = frozenset(item.permission_key for item in PERMISSION_DEFINITIONS)

LEGACY_PERMISSION_MAPPINGS: dict[str, tuple[str, ...]] = {
    "products:read": (page_permission_key("products_product_management"),),
    "sales:daily-sales:read": (page_permission_key("sales_daily_sales"),),
    "aftersales:refund-management:read": (page_permission_key("aftersales_refund_management"),),
    "warehouse:wfs-fee-alert:read": (page_permission_key("warehouse_wfs_fee_alert"),),
    "pmc:purchase:read": (page_permission_key("pmc_purchase_board"),),
    "pmc:domestic-batch:read": (page_permission_key("pmc_domestic_warehouse_board"),),
    "operations:plan:read": (page_permission_key("operations_plan"),),
    "operations:plan:write": (
        action_permission_key("operations_plan", "create"),
        action_permission_key("operations_plan", "edit"),
        action_permission_key("operations_plan", "import"),
    ),
    "integrations:read": (page_permission_key("data_center_task_center"),),
    "integrations:update": (action_permission_key("data_center_task_center", "configure"),),
    "integrations:execute": (action_permission_key("data_center_task_center", "execute"),),
    "business-rules:read": (page_permission_key("settings_fee_rules"),),
    "business-rules:write": (action_permission_key("settings_fee_rules", "edit"),),
    "business-rules:execute": (action_permission_key("settings_fee_rules", "recalculate"),),
    "settings:users:read": (page_permission_key("settings_user_management"),),
    "settings:users:write": (
        action_permission_key("settings_user_management", "create"),
        action_permission_key("settings_user_management", "edit"),
        action_permission_key("settings_user_management", "assign_role"),
        action_permission_key("settings_user_management", "reset_password"),
        action_permission_key("settings_user_management", "enable_disable"),
    ),
    "settings:roles:read": (page_permission_key("settings_role_management"),),
    "settings:roles:write": (
        action_permission_key("settings_role_management", "create"),
        action_permission_key("settings_role_management", "edit"),
        action_permission_key("settings_role_management", "configure_permissions"),
        action_permission_key("settings_role_management", "configure_data_scope"),
        action_permission_key("settings_role_management", "view_audit"),
    ),
}
