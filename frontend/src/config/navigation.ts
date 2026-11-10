/**
 * Navigation template.
 *
 * This file is a project bootstrap template, not runtime code inside the rule pack.
 *
 * When the frontend project is created, copy this file to:
 *
 *   frontend/src/config/navigation.ts
 *
 * After copying, frontend/src/config/navigation.ts becomes the single source of truth for:
 * - Sidebar menu
 * - React Router route registration
 * - Breadcrumb
 * - Tabbar
 * - Page permission keys
 * - Page help links
 *
 * Rules:
 * - Do not hand-code menus inside page components.
 * - Do not create another navigation config.
 * - Do not put emoji into title.
 * - Icon can only be configured through the icon field.
 * - New pages must be added here first.
 */

import {
  AppstoreOutlined,
  BarChartOutlined,
  CustomerServiceOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  DollarOutlined,
  InboxOutlined,
  RobotOutlined,
  ScheduleOutlined,
  SettingOutlined,
  ShoppingCartOutlined,
  ShoppingOutlined,
  SoundOutlined,
} from '@ant-design/icons';
import { createElement, type ReactElement } from 'react';

export type PageStatus =
  | 'planned'
  | 'building'
  | 'testing'
  | 'ready'
  | 'disabled'
  | 'hidden';

export type PageSource = 'pending' | 'legacy_mysql' | 'new_postgres' | 'cache' | 'openapi' | 'mixed';
export type MigrationMode = 'pending' | 'legacy' | 'iframe' | 'rewrite' | 'native';

export interface PageTab {
  key: string;
  title: string;
}

export interface PageAction {
  key: string;
  title: string;
  permissionKey: string;
  highRisk?: boolean;
}

export interface PageHelp {
  enabled: boolean;
  title: string;
  helpUrl: string;
  openInNewTab: true;
}

export interface NavigationPage {
  sidebarSection?: string;
  description?: string;
  showWhenDisabled?: boolean;
  /** Preserve existing IAM page grants when one page becomes multiple navigation entries. */
  viewPermissionKey?: string;
  key: string;
  title: string;
  path: string;
  phase: number;
  status: PageStatus;
  source: PageSource;
  sourceTables: string[];
  readOnly: boolean;
  migrationMode: MigrationMode;
  permissionKey: string;
  actions?: PageAction[];
  tabs?: PageTab[];
  help: PageHelp;
}

export interface NavigationGroup {
  key: string;
  title: string;
  icon: ReactElement;
  children: NavigationPage[];
  sidebarSections?: { key: string; title: string }[];
}

const defaults = {
  phase: 1,
  status: 'planned' as PageStatus,
  source: 'pending' as PageSource,
  sourceTables: [] as string[],
  readOnly: false,
  migrationMode: 'pending' as MigrationMode,
};

const page = (
  groupKey: string,
  key: string,
  title: string,
  path: string,
  extra: Partial<NavigationPage> = {},
): NavigationPage => ({
  key: `${groupKey}_${key}`,
  title,
  path,
  ...defaults,
  permissionKey: `${groupKey}.${key}.view`,
  help: {
    enabled: true,
    title: `${title}使用说明`,
    helpUrl: `/help/${groupKey}/${key}`,
    openInNewTab: true,
  },
  ...extra,
});

export const navigation: NavigationGroup[] = [
  {
    key: 'dashboard',
    title: '工作台',
    icon: createElement(DashboardOutlined, { 'aria-hidden': true }),
    children: [
      page('dashboard', 'today_sales', '工作台', '/dashboard', {
        status: 'testing',
        readOnly: true,
        migrationMode: 'native',
      }),
      page('dashboard', 'today_profit', '今日利润', '/dashboard/today-profit'),
      page('dashboard', 'ad_spend', '广告花费', '/dashboard/ad-spend'),
      page('dashboard', 'refund_rate', '退款率', '/dashboard/refund-rate'),
      page('dashboard', 'inventory_alert', '库存预警', '/dashboard/inventory-alert'),
      page('dashboard', 'review_alert', 'Review预警', '/dashboard/review-alert'),
      page('dashboard', 'ads_alert', '广告异常', '/dashboard/ads-alert'),
      page('dashboard', 'listing_alert', 'Listing异常', '/dashboard/listing-alert'),
      page('dashboard', 'wfs_alert', 'WFS异常', '/dashboard/wfs-alert'),
      page('dashboard', 'todo', '待办任务', '/dashboard/todo'),
    ],
  },
  {
    key: 'products',
    title: '产品',
    icon: createElement(AppstoreOutlined, { 'aria-hidden': true }),
    children: [
      page('products', 'product_management', '产品管理', '/products/management'),
      page('products', 'listing_management', 'Listing管理', '/products/listing-management'),
      page('products', 'clearance_center', '清货中心', '/products/clearance-center', {
        status: 'testing', readOnly: true, migrationMode: 'native',
        viewPermissionKey: 'page:products:product-management:view',
      }),
      page('products', 'claim_center', '认领中心', '/products/claim-center'),
      page('products', 'new_product_analysis', '新品表现', '/products/new-product-analysis', {
        status: 'testing', migrationMode: 'native', source: 'pending',
      }),
      // Mock-only tracking reuses existing new-product view access.
      // Do not grant write permissions or publish a new backend permission catalog here.
      page('products', 'launch_tracking', '打品跟踪', '/products/launch-tracking', {
        status: 'testing', migrationMode: 'native', source: 'pending',
        viewPermissionKey: 'page:products:new-product-analysis:view',
      }),
      page('products', 'lifecycle', '产品生命周期', '/products/lifecycle'),
      page('products', 'grade', '产品等级', '/products/grade'),
    ],
  },
  {
    key: 'sales',
    title: '销售',
    icon: createElement(ShoppingCartOutlined, { 'aria-hidden': true }),
    children: [
      page('sales', 'daily_sales', '每日销售', '/sales/daily-sales'),
      page('sales', 'order_profit', '订单利润', '/sales/order-profit'),
      page('sales', 'review_dashboard', 'Review看板', '/sales/review-dashboard'),
      page('sales', 'restock_suggestion', '补货建议', '/sales/restock-suggestion'),
      page('sales', 'shipping_plan', '发货计划', '/sales/shipping-plan'),
      page('sales', 'trend', '销售趋势', '/sales/trend'),
    ],
  },
  {
    key: 'ads',
    title: '广告',
    icon: createElement(SoundOutlined, { 'aria-hidden': true }),
    children: [
      page('ads', 'overview', '广告总览', '/ads/overview'),
      page('ads', 'campaigns', '广告活动', '/ads/campaigns'),
      page('ads', 'keyword_library', '词库', '/ads/keyword-library'),
      page('ads', 'keyword_rank', '关键词排名', '/ads/keyword-rank'),
      page('ads', 'negative_keywords', '否定关键词', '/ads/negative-keywords'),
      page('ads', 'search_terms', '搜索词', '/ads/search-terms'),
      page('ads', 'ai_optimization_log', 'AI优化记录', '/ads/ai-optimization-log'),
      page('ads', 'bid_adjustment_log', '调价记录', '/ads/bid-adjustment-log'),
      page('ads', 'operation_log', '操作日志', '/ads/operation-log'),
    ],
  },
  {
    key: 'aftersales',
    title: '售后',
    icon: createElement(CustomerServiceOutlined, { 'aria-hidden': true }),
    children: [
      page('aftersales', 'refund_management', '退款管理', '/aftersales/refund-management'),
      page('aftersales', 'return_management', '退货管理', '/aftersales/return-management'),
      page('aftersales', 'customer_messages', '客户消息', '/aftersales/customer-messages'),
      page('aftersales', 'case_management', 'Case管理', '/aftersales/case-management'),
      page('aftersales', 'claims', '索赔/赔付', '/aftersales/claims'),
      page('aftersales', 'negative_feedback', '负面反馈', '/aftersales/negative-feedback'),
      page('aftersales', 'statistics', '售后统计', '/aftersales/statistics'),
    ],
  },
  {
    key: 'warehouse',
    title: '仓库',
    icon: createElement(InboxOutlined, { 'aria-hidden': true }),
    children: [
      page('warehouse', 'inventory_detail', '库存明细', '/warehouse/inventory-detail'),
      page('warehouse', 'inventory_alert', '库存预警', '/warehouse/inventory-alert'),
      page('warehouse', 'wfs_fee_alert', 'WFS费用异常', '/warehouse/wfs-fee-alert'),
      page('warehouse', 'storage_fee', '仓储费', '/warehouse/storage-fee'),
      page('warehouse', 'inbound_transport', '入库运输', '/warehouse/inbound-transport'),
      page('warehouse', 'removal_disposal', '移除/弃置', '/warehouse/removal-disposal'),
      page('warehouse', 'pmc_dashboard', 'PMC看板', '/warehouse/pmc-dashboard'),
      page('warehouse', 'inbound_difference', '入库差异', '/warehouse/inbound-difference'),
      page('warehouse', 'inventory_age', '库存库龄', '/warehouse/inventory-age'),
    ],
  },
  {
    key: 'finance',
    title: '财务',
    icon: createElement(DollarOutlined, { 'aria-hidden': true }),
    sidebarSections: [{ key: 'finance-cash', title: '资金流水' }, { key: 'finance-settings', title: '财务设置' }],
    children: [
      // 2026-11-02 财务菜单按业务（Rocky）确认的 Demo 10 个标签重排；新增页面的导航与权限点待负责人批准（PR-D），本地预览先行。
      page('finance', 'profit_center', '经营总览', '/finance/profit-center'),
      page('finance', 'sku_cash_profit', '现金利润', '/finance/sku-cash-profit'),
      page('finance', 'settlement_profit', '结算利润', '/finance/settlement-profit'),
      page('finance', 'settlement_reconciliation', '回款对账', '/finance/settlement-reconciliation'),
      page('finance', 'performance_report', '财务报表', '/finance/performance-report'),
      page('finance', 'balance_sheet', '资产负债表', '/finance/balance-sheet'),
      page('finance', 'cash_accounts', '账户总览（按月）', '/finance/cash/accounts', {
        sidebarSection: 'finance-cash', status: 'building', readOnly: true, viewPermissionKey: 'page:finance:cash-flow:view',
      }),
      // 2026-11-04 Rocky：「日记账（初审·终审）」改名「日记账」；资金异常并入日记账显示，去掉「异常」页。
      page('finance', 'cash_journal', '日记账', '/finance/cash/journal', {
        sidebarSection: 'finance-cash', status: 'building', readOnly: false, viewPermissionKey: 'page:finance:cash-flow:view',
      }),
      // 2026-11-05 Rocky：新增账户在页面上做（含现金这种手工录入的账户），不用再改配置文件。
      page('finance', 'cash_account_admin', '账户管理', '/finance/cash/account-admin', {
        sidebarSection: 'finance-cash', status: 'building', readOnly: false, viewPermissionKey: 'page:finance:cash-flow:view',
      }),
      page('finance', 'cash_stock', '备货资金', '/finance/cash/stock', {
        sidebarSection: 'finance-cash', status: 'building', readOnly: true, viewPermissionKey: 'page:finance:cash-flow:view',
      }),
      // 2026-11-05 Rocky：这次上线新增汇率页面，只读，读领星月汇率。接口只给超管，所以不沿用资金流水的页面权限：
      // 用自己的权限点 page:finance:fx-rates:view，这个权限点不分配给任何角色，只有超管（*）能看到入口和打开页面。
      page('finance', 'fx_rates', '资金 汇率', '/finance/fund-settings/fx-rates', {
        sidebarSection: 'finance-settings', status: 'building', readOnly: true, viewPermissionKey: 'page:finance:fx-rates:view',
      }),
      page('finance', 'cost_exception', '成本异常处理', '/finance/cost-exception'),
      page('finance', 'settings', '口径与设置', '/finance/settings'),
      page('finance', 'data_import', '数据导入', '/finance/data-import', {
        status: 'building', readOnly: true,
        tabs: [{ key: 'tasks', title: '导入任务' }, { key: 'templates', title: '导入模板' }, { key: 'history', title: '导入历史' }, { key: 'failures', title: '失败记录' }],
      }),
    ],
  },
  {
    key: 'operations',
    title: '运营',
    icon: createElement(ScheduleOutlined, { 'aria-hidden': true }),
    children: [
      page('operations', 'log', '运营日志', '/operations/log'),
      page('operations', 'plan', '运营计划', '/operations/plan'),
      page('operations', 'todo', '运营待办', '/operations/todo'),
      page('operations', 'calendar', '运营日历', '/operations/calendar'),
      page('operations', 'promotion_center', '推广中心', '/operations/promotion-center', {
        tabs: [{ key: 'evaluation', title: '测评' }, { key: 'order_brushing', title: '刷单' }],
      }),
    ],
  },
  {
    key: 'purchase',
    title: '采购',
    icon: createElement(ShoppingOutlined, { 'aria-hidden': true }),
    children: [
      page('purchase', 'plan', '采购计划', '/purchase/plan'),
      page('purchase', 'order', '采购单', '/purchase/order'),
    ],
  },
  {
    // PMC group approved by Rocky 2026-09-24 (PRP pmc-purchase-board §2, option A); owner review in PR.
    sidebarSections: [{ key: 'pmc-domestic', title: '国内仓' }, { key: 'pmc-wfs', title: 'WFS' }],
    key: 'pmc',
    title: 'PMC',
    icon: createElement(DeploymentUnitOutlined, { 'aria-hidden': true }),
    children: [
      page('pmc', 'purchase_board', '采购看板', '/pmc/purchase-board', {
        status: 'testing',
        source: 'new_postgres',
        migrationMode: 'native',
        sourceTables: ['dws_purchase_board', 'dws_purchase_sku_cycle', 'dws_purchase_pending', 'dwd_purchase_plan'],
        readOnly: true,
        // Backend permission key (docs/api/pmc-purchase-api.md); the frontend does not enforce it.
        permissionKey: 'pmc:purchase:read',
      }),
      page('pmc', 'logistics', '物流', '/pmc/logistics', { readOnly: true }),
      page('pmc', 'domestic_batches', '批次看板', '/pmc/domestic/batches', {
        sidebarSection: 'pmc-domestic', status: 'testing', source: 'new_postgres', migrationMode: 'native',
        sourceTables: ['mart_domestic_inbound_batch_board', 'gov_domestic_board_publications'],
        permissionKey: 'pmc:domestic-batch:read', viewPermissionKey: 'page:pmc:domestic-warehouse-board:view', readOnly: true,
      }),
      page('pmc', 'packing_approval', '打包单审批', '/pmc/domestic/packing-approval', {
        sidebarSection: 'pmc-domestic', status: 'testing', source: 'new_postgres', migrationMode: 'native',
        viewPermissionKey: 'page:pmc:domestic-warehouse-board:view',
      }),
      page('pmc', 'packing_warehouse', '打包单（仓库）', '/pmc/domestic/packing-warehouse', {
        sidebarSection: 'pmc-domestic', status: 'testing', source: 'new_postgres', migrationMode: 'native',
        viewPermissionKey: 'page:pmc:domestic-warehouse-board:view',
      }),
      page('pmc', 'wfs_pending_packing', '待发货打包单', '/pmc/wfs/pending-packing', {
        sidebarSection: 'pmc-wfs', status: 'disabled', showWhenDisabled: true,
        viewPermissionKey: 'page:pmc:wfs:view',
      }),
      page('pmc', 'wfs_shipments', '系统货件', '/pmc/wfs/shipments', {
        sidebarSection: 'pmc-wfs', description: '写入 Walmart', status: 'disabled', showWhenDisabled: true,
        viewPermissionKey: 'page:pmc:wfs:view',
      }),
    ],
  },
  {
    key: 'ai_center',
    title: 'AI中心',
    icon: createElement(RobotOutlined, { 'aria-hidden': true }),
    children: [
      page('ai_center', 'assistant', 'AI助手', '/ai-center/assistant'),
      page('ai_center', 'ads_optimization', '广告优化', '/ai-center/ads-optimization'),
      page('ai_center', 'keyword_launch', '关键词投放', '/ai-center/keyword-launch', { status: 'testing', source: 'pending' }),
      page('ai_center', 'image_generation', '图片生成', '/ai-center/image-generation'),
      page('ai_center', 'copywriting', '文案生成', '/ai-center/copywriting'),
      page('ai_center', 'product_research', '智能选品', '/ai-center/product-research'),
      page('ai_center', 'competitor_analysis', '竞品分析', '/ai-center/competitor-analysis'),
    ],
  },
  {
    key: 'data_center',
    title: '数据中心',
    icon: createElement(DatabaseOutlined, { 'aria-hidden': true }),
    children: [
      page('data_center', 'approval_workspace', '审批工作台', '/data-center/approval-workspace', {
        tabs: [{ key: 'pending', title: '待审批' }, { key: 'approved', title: '已审批' }, { key: 'rejected', title: '驳回记录' }],
      }),
      page('data_center', 'walmart_monitoring', '沃尔玛监控', '/data-center/walmart-monitoring', {
        tabs: [{ key: 'product', title: '商品监控' }, { key: 'price', title: '价格监控' }, { key: 'listing', title: 'Listing监控' }, { key: 'seller', title: '跟卖监控' }],
      }),
      page('data_center', 'alert_center', '预警中心', '/data-center/alert-center', {
        tabs: [{ key: 'rules', title: '预警规则' }, { key: 'messages', title: '预警消息' }],
      }),
      page('data_center', 'data_import', '数据导入', '/data-center/data-import', {
        tabs: [{ key: 'tasks', title: '导入任务' }, { key: 'templates', title: '导入模板' }, { key: 'history', title: '导入历史' }, { key: 'failed', title: '失败记录' }],
      }),
      page('data_center', 'data_export', '数据导出', '/data-center/data-export', {
        tabs: [{ key: 'tasks', title: '导出任务' }, { key: 'history', title: '导出历史' }],
      }),
      page('data_center', 'walmart_remote', '沃尔玛采集', '/data-center/walmart-remote'),
      page('data_center', 'task_center', '任务中心', '/data-center/task-center', {
        tabs: [{ key: 'sync', title: '同步任务' }, { key: 'schedule', title: '定时任务' }, { key: 'history', title: '历史记录' }, { key: 'failed', title: '失败记录' }],
      }),
      page('data_center', 'api_docs', 'API文档', '/data-center/api-docs', {
        source: 'openapi',
        migrationMode: 'native',
        permissionKey: 'data_center.api_docs.view',
        tabs: [{ key: 'api-list', title: '接口列表' }, { key: 'openapi', title: 'OpenAPI' }, { key: 'error-codes', title: '错误码' }, { key: 'permissions', title: '权限说明' }],
      }),
      page('data_center', 'documentation', '文档', '/data-center/documentation', {
        status: 'hidden',
      }),
    ],
  },
  {
    key: 'statistics',
    title: '统计',
    icon: createElement(BarChartOutlined, { 'aria-hidden': true }),
    children: [
      page('statistics', 'business_overview', '经营总览', '/statistics/business-overview'),
      page('statistics', 'account_health', '账号健康', '/statistics/account-health'),
      page('statistics', 'product_performance', '产品表现', '/statistics/product-performance'),
      page('statistics', 'return_analysis', '退货分析', '/statistics/return-analysis'),
      page('statistics', 'sales_analysis', '销售分析', '/statistics/sales-analysis'),
      page('statistics', 'profit_analysis', '利润分析', '/statistics/profit-analysis'),
      page('statistics', 'ads_analysis', '广告分析', '/statistics/ads-analysis'),
      page('statistics', 'inventory_analysis', '库存分析', '/statistics/inventory-analysis'),
    ],
  },
  {
    key: 'settings',
    title: '设置',
    icon: createElement(SettingOutlined, { 'aria-hidden': true }),
    children: [
      page('settings', 'user_management', '用户管理', '/settings/user-management', {
        tabs: [{ key: 'users', title: '用户列表' }, { key: 'roles', title: '分配角色' }, { key: 'org', title: '组织架构' }, { key: 'data-scope', title: '用户数据范围' }],
      }),
      page('settings', 'fee_rules', '费用规则', '/settings/fee-rules'),
      page('settings', 'role_management', '角色管理', '/settings/role-management', {
        tabs: [{ key: 'roles', title: '角色列表' }, { key: 'pages', title: '页面权限' }, { key: 'actions', title: '动作权限' }, { key: 'data-scope', title: '数据权限' }, { key: 'high-risk', title: '高危动作' }, { key: 'changes', title: '权限变更记录' }],
      }),
      page('settings', 'business_config', '业务配置', '/settings/business-config'),
      page('settings', 'system_config', '系统配置', '/settings/system-config', {
        tabs: [{ key: 'base', title: '基础配置' }, { key: 'integrations', title: '集成配置' }, { key: 'notifications', title: '通知规则' }, { key: 'feature-flags', title: '功能开关' }],
      }),
      page('settings', 'logs', '日志', '/settings/logs', {
        tabs: [{ key: 'operation', title: '操作日志' }, { key: 'system', title: '系统日志' }, { key: 'api', title: '接口日志' }, { key: 'permission', title: '权限变更日志' }, { key: 'fee-rule', title: '费用规则日志' }],
      }),
      page('settings', 'personal_center', '个人中心', '/settings/personal-center', {
        status: 'hidden',
      }),
    ],
  },
];


/** Old container URLs redirect without registering a page or restoring a legacy top tab. */
export const navigationRedirects: Readonly<Record<string, string>> = {
  '/dashboard/today-sales': '/dashboard',
  '/pmc/domestic-warehouse-board': '/pmc/domestic/batches',
};
