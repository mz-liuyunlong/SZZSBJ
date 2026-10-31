from __future__ import annotations

from dataclasses import dataclass
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


MODULES: tuple[ModuleDefinition, ...] = (
    ModuleDefinition(
        "dashboard",
        "工作台",
        10,
        (
            _page("dashboard", "today_sales", "今日销售", 10),
            _page("dashboard", "today_profit", "今日利润", 20),
            _page("dashboard", "ad_spend", "广告花费", 30),
            _page("dashboard", "refund_rate", "退款率", 40),
            _page("dashboard", "inventory_alert", "库存预警", 50),
            _page("dashboard", "review_alert", "Review预警", 60),
            _page("dashboard", "ads_alert", "广告异常", 70),
            _page("dashboard", "listing_alert", "Listing异常", 80),
            _page("dashboard", "wfs_alert", "WFS异常", 90),
            _page("dashboard", "todo", "待办任务", 100),
        ),
    ),
    ModuleDefinition(
        "products",
        "产品",
        20,
        (
            _page("products", "product_management", "产品管理", 10),
            _page("products", "listing_management", "Listing管理", 20),
            _page("products", "claim_center", "认领中心", 30),
            _page("products", "new_product_analysis", "新品分析", 40),
            _page("products", "lifecycle", "产品生命周期", 50),
            _page("products", "grade", "产品等级", 60),
        ),
    ),
    ModuleDefinition(
        "sales",
        "销售",
        30,
        (
            _page("sales", "daily_sales", "每日销售", 10),
            _page("sales", "order_profit", "订单利润", 20),
            _page("sales", "review_dashboard", "Review看板", 30),
            _page("sales", "restock_suggestion", "补货建议", 40),
            _page("sales", "shipping_plan", "发货计划", 50),
            _page("sales", "trend", "销售趋势", 60),
        ),
    ),
    ModuleDefinition(
        "ads",
        "广告",
        40,
        (
            _page("ads", "overview", "广告总览", 10),
            _page("ads", "campaigns", "广告活动", 20),
            _page("ads", "keyword_library", "词库", 30),
            _page("ads", "keyword_rank", "关键词排名", 40),
            _page("ads", "negative_keywords", "否定关键词", 50),
            _page("ads", "search_terms", "搜索词", 60),
            _page("ads", "ai_optimization_log", "AI优化记录", 70),
            _page("ads", "bid_adjustment_log", "调价记录", 80),
            _page("ads", "operation_log", "操作日志", 90),
        ),
    ),
    ModuleDefinition(
        "aftersales",
        "售后",
        50,
        (
            _page("aftersales", "refund_management", "退款管理", 10),
            _page("aftersales", "return_management", "退货管理", 20),
            _page("aftersales", "customer_messages", "客户消息", 30),
            _page("aftersales", "case_management", "Case管理", 40),
            _page("aftersales", "claims", "索赔/赔付", 50),
            _page("aftersales", "negative_feedback", "负面反馈", 60),
            _page("aftersales", "statistics", "售后统计", 70),
        ),
    ),
    ModuleDefinition(
        "warehouse",
        "仓库",
        60,
        (
            _page("warehouse", "inventory_detail", "库存明细", 10),
            _page("warehouse", "inventory_alert", "库存预警", 20),
            _page("warehouse", "wfs_fee_alert", "WFS费用异常", 30),
            _page("warehouse", "storage_fee", "仓储费", 40),
            _page("warehouse", "inbound_transport", "入库运输", 50),
            _page("warehouse", "removal_disposal", "移除/弃置", 60),
            _page("warehouse", "pmc_dashboard", "PMC看板", 70),
            _page("warehouse", "inbound_difference", "入库差异", 80),
            _page("warehouse", "inventory_age", "库存库龄", 90),
        ),
    ),
    ModuleDefinition(
        "finance",
        "财务",
        70,
        (
            _page("finance", "profit_center", "利润中心", 10),
            _page("finance", "sku_cash_profit", "单品现金利润", 20),
            _page("finance", "walmart_settlement", "沃尔玛返还明细", 30),
            _page("finance", "settlement_reconciliation", "结算对账", 40),
            _page("finance", "ad_cost", "广告费用", 50),
            _page("finance", "ad_bill", "广告账单", 60),
            _page("finance", "performance_report", "业绩报表", 70),
        ),
    ),
    ModuleDefinition(
        "operations",
        "运营",
        80,
        (
            _page("operations", "log", "运营日志", 10),
            _page("operations", "plan", "运营计划", 20),
            _page("operations", "todo", "运营待办", 30),
            _page("operations", "calendar", "运营日历", 40),
            _page("operations", "promotion_center", "推广中心", 50),
        ),
    ),
    ModuleDefinition(
        "purchase",
        "采购",
        90,
        (
            _page("purchase", "plan", "采购计划", 10),
            _page("purchase", "order", "采购单", 20),
        ),
    ),
    ModuleDefinition(
        "pmc",
        "PMC",
        100,
        (
            _page("pmc", "purchase_board", "采购看板", 10),
            _page("pmc", "domestic_warehouse_board", "国内仓看板", 20),
        ),
    ),
    ModuleDefinition(
        "ai_center",
        "AI中心",
        110,
        (
            _page("ai_center", "assistant", "AI助手", 10),
            _page("ai_center", "ads_optimization", "广告优化", 20),
            _page("ai_center", "image_generation", "图片生成", 30),
            _page("ai_center", "copywriting", "文案生成", 40),
            _page("ai_center", "product_research", "智能选品", 50),
            _page("ai_center", "competitor_analysis", "竞品分析", 60),
            _page("ai_center", "keyword_rules", "关键词规则", 70),
            _page("ai_center", "keyword_launch", "关键词投放", 80),
        ),
    ),
    ModuleDefinition(
        "data_center",
        "数据中心",
        120,
        (
            _page("data_center", "approval_workspace", "审批工作台", 10),
            _page("data_center", "walmart_monitoring", "沃尔玛监控", 20),
            _page("data_center", "alert_center", "预警中心", 30),
            _page("data_center", "data_import", "数据导入", 40),
            _page("data_center", "data_export", "数据导出", 50),
            _page("data_center", "task_center", "任务中心", 60),
            _page("data_center", "walmart_remote", "沃尔玛采集", 65),
            _page("data_center", "api_docs", "API文档", 70),
        ),
    ),
    ModuleDefinition(
        "statistics",
        "统计",
        130,
        (
            _page("statistics", "business_overview", "经营总览", 10),
            _page("statistics", "account_health", "账号健康", 20),
            _page("statistics", "product_performance", "产品表现", 30),
            _page("statistics", "return_analysis", "退货分析", 40),
            _page("statistics", "sales_analysis", "销售分析", 50),
            _page("statistics", "profit_analysis", "利润分析", 60),
            _page("statistics", "ads_analysis", "广告分析", 70),
            _page("statistics", "inventory_analysis", "库存分析", 80),
        ),
    ),
    ModuleDefinition(
        "settings",
        "设置",
        140,
        (
            _page("settings", "user_management", "用户管理", 10),
            _page("settings", "organization", "组织架构", 15),
            _page("settings", "fee_rules", "费用规则", 20),
            _page("settings", "role_management", "角色管理", 30),
            _page("settings", "business_config", "业务配置", 40),
            _page("settings", "system_config", "系统配置", 50),
            _page("settings", "logs", "日志", 60),
        ),
    ),
)

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
        "products_listing_management", "configure_rules", "配置Listing评级规则", 60, "high"
    ),
    ActionDefinition(
        "products_listing_management", "manage_followups", "处理C/D等级跟进", 70, "high"
    ),
    ActionDefinition("sales_daily_sales", "export", "导出每日销售", 10),
    ActionDefinition("sales_order_profit", "export", "导出订单利润", 10),
    ActionDefinition("warehouse_wfs_fee_alert", "follow", "跟进WFS Case", 10),
    ActionDefinition("warehouse_wfs_fee_alert", "archive-request", "申请归档WFS Case", 20, "high"),
    ActionDefinition("warehouse_wfs_fee_alert", "archive-review", "审核归档WFS Case", 25, "high"),
    ActionDefinition("warehouse_wfs_fee_alert", "mark-recovered", "确认WFS费用已追回", 30, "high"),
    ActionDefinition(
        "pmc_domestic_warehouse_board", "packing-manual-create", "手工提交打包审批", 30, "high"
    ),
    ActionDefinition("pmc_domestic_warehouse_board", "packing-boxes-save", "保存仓库装箱", 40),
    ActionDefinition("pmc_domestic_warehouse_board", "packing-done", "确认打包完成", 41),
    ActionDefinition("pmc_domestic_warehouse_board", "packing-customs", "修改打包报关", 42),
    ActionDefinition("pmc_domestic_warehouse_board", "packing-note", "填写打包延迟备注", 43),
    ActionDefinition(
        "pmc_domestic_warehouse_board", "packing-unpacked-dispose", "处置未装数量", 44, "high"
    ),
    ActionDefinition("pmc_domestic_warehouse_board", "packing-rebox", "修改已完成装箱", 45, "high"),
    ActionDefinition(
        "pmc_domestic_warehouse_board", "packing-supplement-ib", "登记超发补入库单", 46, "high"
    ),
    ActionDefinition(
        "pmc_domestic_warehouse_board", "packing-supplement-sync", "校验超发补入库数据", 47, "high"
    ),
    ActionDefinition("operations_plan", "create", "新增运营计划", 10),
    ActionDefinition("operations_plan", "edit", "编辑运营计划", 20),
    ActionDefinition("operations_plan", "import", "导入运营计划", 30),
    ActionDefinition("pmc_purchase_board", "override", "维护采购周期覆盖", 10, "high"),
    ActionDefinition("data_center_task_center", "configure", "维护同步配置", 10),
    ActionDefinition("data_center_task_center", "execute", "执行同步任务", 20, "high"),
    ActionDefinition("data_center_walmart_remote", "execute", "执行沃尔玛采集", 10, "high"),
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
