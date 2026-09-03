import { useState, useEffect, useCallback, useRef, cloneElement } from "react";
import ClearanceCenter from "./ClearanceCenter";
import PmcCenter from "./PmcCenter";
import { ItemIdLink } from "./ItemIdLink";

function isItemIdColumn(col: string): boolean {
  const norm = col.replace(/\s/g, "").toLowerCase();
  return norm === "商品id" || norm === "itemid";
}


// ── 类型 ──────────────────────────────────────────────────────────────────────

interface SheetMeta {
  sheet_id: string;
  sheet_name: string;
  total: number;
  latest_sync_time: string | null;
}

interface SheetData {
  sheet_id: string;
  sheet_name: string;
  columns: string[];
  rows: Record<string, string>[];
  total: number;
  page: number;
  page_size: number;
  latest_sync_time: string | null;
  totals?: Record<string, string> | null; // 合计行（2026-07-17 领星式，筛选全量口径）
}

interface SyncTask {
  sync_task_id: string;
  sheet_id: string;
  sheet_name: string;
  status: string;
  row_count: number;
  inserted_count: number;
  updated_count: number;
  skipped_count: number;
  started_at: string;
  finished_at: string | null;
  error_message: string | null;
}

interface CsConfigRow {
  config_type: string;
  config_key: string;
  config_value: string;
  description: string;
  enabled: number;
}

interface AppliedFilters {
  keyword: string;
  sku: string;
  msku: string;
  itemId: string;
  store: string;
  owner: string;
  stockStatus: string;
  productStage: string;
  costStatus: string;
  dateStart: string;
  dateEnd: string;
  grossMin: string;
  grossMax: string;
  adMin: string;
  adMax: string;
  wfsFeeStatus: string;
  pmCostStatus: string;
  productStatus: string;
  manualLifecycle: string;
  profitLevel: string;
  gptLink: string;
  adSpendMin: string;
  adSpendMax: string;
  clicksMin: string;
  clicksMax: string;
  testDaysMin: string;
  testDaysMax: string;
  logFilled: string;   // 运营日志已填/未填（2026-07-15）
  wfsStock: string;    // WFS库存 有/无
}

type SortDirection = "" | "asc" | "desc";

interface TabSortState {
  field: string;
  order: SortDirection;
}

const DEFAULT_FILTERS: AppliedFilters = {
  keyword: "", sku: "", msku: "", itemId: "", store: "", owner: "",
  stockStatus: "", productStage: "", costStatus: "",
  dateStart: "", dateEnd: "",
  grossMin: "", grossMax: "",
  adMin: "", adMax: "",
  wfsFeeStatus: "", pmCostStatus: "", productStatus: "", manualLifecycle: "", profitLevel: "", gptLink: "",
  adSpendMin: "", adSpendMax: "",
  clicksMin: "", clicksMax: "",
  testDaysMin: "", testDaysMax: "",
  logFilled: "", wfsStock: "",
};

// V1.1: 负责人筛选"缺负责人"哨兵值，需和后端 MISSING_OWNER_SENTINEL 保持一致
const MISSING_OWNER_SENTINEL = "__missing__";
const WFS_FEE_STATUS_OPTIONS = [
  { value: "", label: "全部" },
  { value: "missing", label: "缺WFS配送费" },
  { value: "filled", label: "已填写" },
];
const PRODUCT_STATUS_OPTIONS = [
  { value: "", label: "全部（不含归档）" },
  { value: "active", label: "在用" },
  { value: "inactive_candidate", label: "停用候选" },
  { value: "inactive", label: "停用" },
  { value: "archived", label: "归档" },
  { value: "all", label: "全部（含归档）" },
];

const ORDER_PROFIT_SHEET_ID = "order_profit_daily";
const CS_TEST_SHEET_ID = "cs_test_analysis";
const PRODUCT_MANAGEMENT_SHEET_ID = "product_management";
const OPERATION_LOG_SHEET_ID = "operation_log";

// 保留完整列表：后端历史接口/RAW数据仍然可用，只是不再从这个数组里渲染入口。
// V1.2：产品管理 Tab V1.2 —— 前端 allowlist 隐藏旧 Tab（当日数据/ItemID负责人/近期利润广告/同步任务），
// 不删除下面这几个 sheetId 对应的后端调用能力，仅隐藏页面入口，方便回滚和历史排查。
const SHEET_TABS = [
  { sheetId: "<REDACTED_FEISHU_SHEET_ID>", label: "当日数据" },
  { sheetId: "<REDACTED_FEISHU_SHEET_ID>", label: "每日销售明细" },
  { sheetId: "<REDACTED_FEISHU_SHEET_ID>", label: "ItemID负责人" },
  { sheetId: "<REDACTED_FEISHU_SHEET_ID>", label: "近期利润广告" },
  { sheetId: ORDER_PROFIT_SHEET_ID, label: "订单利润 Beta" },
  { sheetId: CS_TEST_SHEET_ID, label: "CS测品分析 Beta" },
  { sheetId: PRODUCT_MANAGEMENT_SHEET_ID, label: "产品管理" },
  { sheetId: OPERATION_LOG_SHEET_ID, label: "运营日志" },
  { sheetId: "<REDACTED_FEISHU_SHEET_ID>", label: "清货中心" },
  { sheetId: "<REDACTED_FEISHU_SHEET_ID>", label: "AI智能PMC" },
  { sheetId: "<REDACTED_FEISHU_SHEET_ID>", label: "同步任务" },
];

// V1.2: Tab 展示 allowlist。飞书 <REDACTED_FEISHU_SHEET_ID> 已停止人工更新，降级为历史镜像/排查对账，
// "当日数据""ItemID负责人""近期利润广告""同步任务" 四个入口不再展示，但对应后端接口保留。
const VISIBLE_SHEET_IDS = new Set([
  "<REDACTED_FEISHU_SHEET_ID>",
  ORDER_PROFIT_SHEET_ID,
  CS_TEST_SHEET_ID,
  PRODUCT_MANAGEMENT_SHEET_ID,
  OPERATION_LOG_SHEET_ID,
  "__clearance__",
  "__pmc__",
]);
// 2026-07-20 帮助中心/下载：Tab → 帮助文章 page_key（dim_page_help.page_key）
const PAGE_HELP_KEYS: Record<string, string> = {
  <REDACTED_FEISHU_SHEET_ID>: "profit_daily_detail",
  [ORDER_PROFIT_SHEET_ID]: "profit_order",
  [CS_TEST_SHEET_ID]: "profit_cs_test",
  [PRODUCT_MANAGEMENT_SHEET_ID]: "profit_product_mgmt",
  [OPERATION_LOG_SHEET_ID]: "profit_operation_log",
};

// 2026-07-21 领星式工具栏图标（刷新/帮助/下载/列配置）
const ICON_BTN = {
  background: "none", border: "none", cursor: "pointer", padding: "5px",
  borderRadius: "6px", color: "#6b7280", display: "inline-flex", alignItems: "center",
} as const;
const IconRefresh = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
  </svg>
);
const IconHelp = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" /><line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);
const IconDownload = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);
const IconColumns = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

const VISIBLE_SHEET_TABS = SHEET_TABS.filter((tab) => VISIBLE_SHEET_IDS.has(tab.sheetId));

const PRODUCT_STAGE_OPTIONS = ["常规产品", "新品期", "清货产品"];
const COST_STATUS_OPTIONS = ["完整", "缺采购成本", "缺头程成本", "缺WFS配送费"];
const CS_DATA_STATUS_OPTIONS = ["正常", "缺首次广告日期", "缺广告数据", "缺库存数据"];
const DASH_EMPTY_COLUMNS = new Set([
  "产品类型", "利润等级", "生命周期", "系统生命周期", "人工生命周期", "经营库存状态",
  "库存周转天数", "广告状态", "问题标签", "上架时间", "状态日期",
]);
const CS_TEST_COLUMNS = [
  "店铺", "商品ID", "MSKU", "SKU", "负责人",
  "首次广告日期", "测品结束日期", "测品天数", "非WFS库存",
  "累计销量", "有销量天数", "日均销量", "累计销售额（$）",
  "累计广告费（$）", "广告费占比", "广告曝光", "广告点击",
  "CTR", "CPC", "CVR", "ACOS", "自然订单数", "自然订单比例",
  "广告订单数", "广告销售额（$）", "测款成本", "数据状态", "预警原因",
];
const PRODUCT_MANAGEMENT_COLUMNS = [
  "店铺ID", "店铺名称", "负责人", "ItemID", "MSKU", "SKU",
  "产品名称", "产品类型", "产品状态", "上架时间", "系统生命周期",
  "人工生命周期", "近90天销量", "当前库存", "在途库存", "近30天广告费", "停用原因",
  "产品成本（¥）", "头程运费（¥）", "WFS配送费（$）", "操作",
];
const REGULAR_LIFECYCLE_OPTIONS = ["新品期", "上升期", "稳定期", "清货期"];
const CS_LIFECYCLE_OPTIONS = ["测品期", "测品结束"];
// 人工生命周期筛选下拉（常规+CS 全部人工可选值；__unset__=未设置）
const MANUAL_LIFECYCLE_FILTER_OPTIONS = [
  { value: "", label: "全部" },
  { value: "新品期", label: "新品期" },
  { value: "上升期", label: "上升期" },
  { value: "稳定期", label: "稳定期" },
  { value: "清货期", label: "清货期" },
  { value: "__unset__", label: "未设置" },
];

const DATE_QUICK_OPTIONS = [
  { label: "今天", days: 1 },
  { label: "近5天", days: 5 },
  { label: "近7天", days: 7 },
  { label: "近15天", days: 15 },
  { label: "近30天", days: 30 },
  { label: "本月", days: -1 },
];

// 运营日志 Tab 专用日期快捷选项（days=-2 是"昨天"的特殊标记，含义是
// 相对 businessAvailableDate() 再往前一天的单独一天，而不是"近N天"区间）
const OPERATION_LOG_DATE_QUICK_OPTIONS = [
  { label: "今天", days: 1 },
  { label: "昨天", days: -2 },
  { label: "近3天", days: 3 },
  { label: "近5天", days: 5 },
];

const PAGE_SIZE_OPTIONS = [50, 100, 200]; // 2026-07-17 统一广告库查看器交互
const COLUMN_ORDER_STORAGE_KEY = "feishuRawSales.columnOrder.v1";
const VISIBLE_COLUMNS_STORAGE_KEY = "feishuRawSales.visibleColumns.v1";
const PINNED_COLUMNS_STORAGE_KEY = "feishuRawSales.pinnedColumns.v1"; // 固定列（左冻结，2026-07-17）
const MAX_PINNED_COLUMNS = 7; // 领星同款上限
const DEFAULT_PIN_COL_WIDTH = 140; // 固定列启用时未拖宽列的默认宽
// 固定列布局下的列宽预设（长文本列加宽，其余走默认；用户拖宽后以 colWidths 为准）
const PIN_WIDTH_PRESETS: Record<string, number> = {
  "品名": 230, "系统运营日志": 340, "运营日志": 300, "问题标签": 200, "店铺": 170, "标题": 230,
};
// 各Tab默认固定列（仿领星：左侧信息区固定、数据区滚动；仅在用户未保存过固定配置时生效）
const DEFAULT_PINNED_BY_TAB: Record<string, string[]> = {
  "<REDACTED_FEISHU_SHEET_ID>": ["SKU", "MSKU", "品名"],
  [ORDER_PROFIT_SHEET_ID]: ["店铺", "商品ID", "MSKU"],
  [CS_TEST_SHEET_ID]: ["店铺", "商品ID", "MSKU"],
  [OPERATION_LOG_SHEET_ID]: ["负责人", "Item ID", "MSKU"],
};

// 合并搜索框字段选项（2026-07-17 领星式：字段下拉+单一输入框）
const SEARCH_FIELD_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "keyword", label: "关键词" },
  { value: "sku", label: "SKU" },
  { value: "msku", label: "MSKU" },
  { value: "itemId", label: "商品ID" },
];
const EMPTY_SORT_STATE: TabSortState = { field: "", order: "" };
const SORTABLE_COLUMNS_BY_TAB: Record<string, Record<string, string>> = {
  <REDACTED_FEISHU_SHEET_ID>: {
    "日期": "date",
    "今日销售额（$）": "sales_amount",
    "今日销售额": "sales_amount",
    "今日销量": "sales_qty",
    "订单量": "order_count",
  },
  [ORDER_PROFIT_SHEET_ID]: {
    "累计销售额（$）": "total_sales_amount",
    "累计销量": "total_sales_qty",
    "累计毛利润（$）": "total_gross_profit",
    "毛利率": "gross_margin_pct",
    "累计广告费（$）": "total_ad_spend",
    "广告占比": "ad_ratio_pct",
  },
  [CS_TEST_SHEET_ID]: {
    "首次广告日期": "first_ad_date",
    "测品天数": "test_days",
    "累计广告费（$）": "total_ad_spend",
    "广告点击": "clicks",
    "累计销售额（$）": "total_sales_amount",
    "累计销量": "total_sales_qty",
    "非WFS库存": "non_wfs_inventory",
    "测品结束日期": "test_end_date",
    "有销量天数": "sales_days",
    "日均销量": "avg_daily_sales_qty",
    "广告费占比": "ad_ratio_pct",
    "广告曝光": "impressions",
    "CTR": "ctr_pct",
    "CPC": "cpc",
    "CVR": "cvr_pct",
    "ACOS": "acos_pct",
    "自然订单数": "natural_orders",
    "自然订单比例": "natural_order_ratio_pct",
    "广告订单数": "ad_orders",
    "广告销售额（$）": "ad_sales",
    "测款成本": "test_cost",
  },
  [PRODUCT_MANAGEMENT_SHEET_ID]: {
    "店铺名称": "store_name",
    "负责人": "owner",
    "产品类型": "product_type",
    "上架时间": "launch_date",
    "系统生命周期": "system_lifecycle",
    "人工生命周期": "lifecycle",
    "WFS配送费（$）": "wfs_delivery_fee",
    "产品成本（¥）": "purchase_cost",
    "头程运费（¥）": "first_mile_shipping_cost",
  },
  [OPERATION_LOG_SHEET_ID]: {
    "日期": "log_date",
    "销量(近30天)": "qty_30d",
    "销售额(近30天)$": "sales_30d",
    "毛利润(近30天)$": "gross_profit_30d",
    "毛利率(近30天)": "profit_rate_30d",
    "广告费(近30天)$": "ad_spend_30d",
    "广告占比(近30天)": "ad_ratio_30d",
    "WFS库存": "wfs_stock",
  },
};

// ── 工具 ──────────────────────────────────────────────────────────────────────

function readStringArrayMap(key: string): Record<string, string[]> {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const result: Record<string, string[]> = {};
    for (const [tab, value] of Object.entries(parsed)) {
      if (Array.isArray(value) && value.every((item) => typeof item === "string")) {
        result[tab] = value;
      }
    }
    return result;
  } catch {
    return {};
  }
}

function writeStringArrayMap(key: string, value: Record<string, string[]>) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {}
}

// GPT分析 紧跟 ItemID：两列绑定为一对、一起挪动（2026-07-27 需求方）。非产品管理Tab无GPT分析列时为空操作。
function glueGptAfterItemId(cols: string[]): string[] {
  const PAIRS: Array<[string, string]> = [["ItemID", "GPT分析"], ["系统生命周期", "人工生命周期"]];
  let out = cols;
  for (const [a, b] of PAIRS) {
    if (!out.includes(a) || !out.includes(b)) continue;
    out = out.filter((c) => c !== b);
    out.splice(out.indexOf(a) + 1, 0, b);
  }
  return out;
}

function reconcileProductManagementColumns(columns: string[]): string[] {
  const next: string[] = [];
  for (const col of columns) {
    if (col === "生命周期" || col === "系统建议") {
      for (const replacement of ["系统生命周期", "人工生命周期"]) {
        if (!next.includes(replacement)) next.push(replacement);
      }
    } else if (!next.includes(col)) {
      next.push(col);
    }
  }
  return glueGptAfterItemId(next);
}

function reconcileVisibleColumns(tab: string, visible: string[] | undefined, actualColumns: string[]): string[] | undefined {
  if (!visible) return undefined;
  let next = tab === PRODUCT_MANAGEMENT_SHEET_ID ? reconcileProductManagementColumns(visible) : visible;
  next = next.filter((col) => actualColumns.includes(col));
  if (tab === PRODUCT_MANAGEMENT_SHEET_ID) {
    for (const col of ["ItemID", "GPT分析", "系统生命周期", "人工生命周期"]) {
      if (actualColumns.includes(col) && !next.includes(col)) next.push(col);
    }
  }
  // 2026-08-22 第四单：运营日志Tab「运营提醒」更名为「系统运营日志」。
  //   老用户 localStorage 里存的是旧列名，上面那行 filter 会把它滤掉而新列名不在存量里，
  //   导致整列不显示；故照 PRODUCT_MANAGEMENT 同款做补列（顺序由 orderedColumns 决定，此处只保证不丢）。
  if (tab === OPERATION_LOG_SHEET_ID) {
    for (const col of ["系统运营日志"]) {
      if (actualColumns.includes(col) && !next.includes(col)) next.push(col);
    }
  }
  return next;
}

// 2026-08-22 第四单补丁：「系统运营日志」与「运营日志」是成对的两列，必须相邻且系统在左。
//   老用户 localStorage 里存的列顺序不含新列名，orderedColumns 只能把它追加到末尾，
//   导致两列被拆开。此处不动用户的其它顺序偏好，只把这一列强制归位到「运营日志」左侧。
function glueSysLogBeforeOpsLog(cols: string[]): string[] {
  const SYS = "系统运营日志";
  const OPS = "运营日志";
  if (!cols.includes(SYS) || !cols.includes(OPS)) return cols;
  const rest = cols.filter((c) => c !== SYS);
  const at = rest.indexOf(OPS);
  if (at < 0) return cols;
  return [...rest.slice(0, at), SYS, ...rest.slice(at)];
}

// 2026-08-22 第四单补丁2：「系统运营日志」与「运营日志」在列配置里是不可拆分的一对。
//   勾选/取消、删除、置顶、固定、拖动一律成对处理；顺序恒为「系统在前」。
const SYS_LOG_COL = "系统运营日志";
const OPS_LOG_COL = "运营日志";
function opsLogPair(col: string): string[] {
  return (col === SYS_LOG_COL || col === OPS_LOG_COL) ? [SYS_LOG_COL, OPS_LOG_COL] : [col];
}

function toDateStr(d: Date): string {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function dateNDaysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return toDateStr(d);
}

function businessAvailableDate(): string {
  return dateNDaysAgo(3);
}

function dateWindowStart(days: number): string {
  const d = new Date(`${businessAvailableDate()}T00:00:00`);
  d.setDate(d.getDate() - Math.max(0, days - 1));
  return toDateStr(d);
}

// "昨天"：相对 businessAvailableDate()（即"今天"快捷按钮对应的日期）再往前一天，单独一天
function businessAvailableDatePrevDay(): string {
  const d = new Date(`${businessAvailableDate()}T00:00:00`);
  d.setDate(d.getDate() - 1);
  return toDateStr(d);
}

function businessMonthStart(): string {
  const d = new Date(`${businessAvailableDate()}T00:00:00`);
  d.setDate(1);
  return toDateStr(d);
}

function displayCellValue(col: string, value: unknown): string {
  const text = String(value ?? "").trim();
  if (!text && DASH_EMPTY_COLUMNS.has(col)) return "-";
  return text;
}

// ── 样式 ──────────────────────────────────────────────────────────────────────

const s = {
  container:  { padding: "20px", fontFamily: "system-ui, sans-serif", color: "#1a1a2e", height: "100vh", boxSizing: "border-box" as const, background: "#f5f6fa", display: "flex", flexDirection: "column" as const, overflow: "hidden" } as React.CSSProperties,
  header:     { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" } as React.CSSProperties,
  title:      { fontSize: "20px", fontWeight: 700, color: "#1a1a2e" } as React.CSSProperties,
  syncBtn:    (loading: boolean) => ({ padding: "8px 18px", borderRadius: "8px", border: "none", cursor: loading ? "not-allowed" : "pointer", background: loading ? "#94a3b8" : "#6366f1", color: "#fff", fontWeight: 600, fontSize: "14px" } as React.CSSProperties),
  tabBar:     { display: "flex", gap: "4px", marginBottom: "16px", borderBottom: "2px solid #e5e7eb" } as React.CSSProperties,
  tab:        (active: boolean) => ({ padding: "8px 16px", cursor: "pointer", border: "none", background: "none", fontSize: "14px", fontWeight: active ? 700 : 400, color: active ? "#6366f1" : "#6b7280", borderBottom: active ? "2px solid #6366f1" : "2px solid transparent", marginBottom: "-2px", borderRadius: "4px 4px 0 0" } as React.CSSProperties),
  card:       { background: "#fff", borderRadius: "12px", padding: "16px", boxShadow: "0 1px 4px rgba(0,0,0,0.08)", marginBottom: "0", flex: 1, minHeight: 0, display: "flex", flexDirection: "column" as const } as React.CSSProperties,
  metaRow:    { display: "flex", gap: "24px", fontSize: "13px", color: "#6b7280", marginBottom: "12px" } as React.CSSProperties,
  tableWrap:  { overflow: "auto" as const, flex: 1, minHeight: 0, borderRadius: "8px", border: "1px solid #e5e7eb" },
  table:      { width: "100%", borderCollapse: "collapse" as const, fontSize: "13px" },
  th:         { padding: "8px 12px", background: "#f8fafc", borderBottom: "2px solid #e5e7eb", textAlign: "left" as const, whiteSpace: "nowrap" as const, fontWeight: 600, color: "#374151" },
  thBtn:      (active: boolean, sortable: boolean) => ({ display: "inline-flex", alignItems: "center", gap: "4px", padding: 0, border: "none", background: "transparent", color: active ? "#4f46e5" : "#374151", cursor: sortable ? "pointer" : "default", fontWeight: 600, fontSize: "13px" } as React.CSSProperties),
  sortArrow:  (active: boolean) => ({ fontSize: "11px", color: active ? "#4f46e5" : "#c4b5fd", minWidth: "10px", userSelect: "none" } as React.CSSProperties),
  td:         { padding: "7px 12px", borderBottom: "1px solid #f1f5f9", whiteSpace: "nowrap" as const, color: "#374151", maxWidth: "280px", overflow: "hidden" as const, textOverflow: "ellipsis" as const },
  pagination: { display: "flex", justifyContent: "center", gap: "8px", marginTop: "8px", alignItems: "center", flexShrink: 0 } as React.CSSProperties,
  pageBtn:    (active: boolean, disabled: boolean) => ({ padding: "5px 12px", borderRadius: "5px", border: "1px solid #e5e7eb", cursor: disabled ? "not-allowed" : "pointer", background: active ? "#6366f1" : "#fff", color: active ? "#fff" : "#374151", fontWeight: active ? 700 : 400, fontSize: "13px" } as React.CSSProperties),
  empty:      { textAlign: "center" as const, color: "#9ca3af", padding: "40px 0", fontSize: "14px" },
  statusChip: (status: string) => ({ display: "inline-block", padding: "2px 10px", borderRadius: "99px", fontSize: "12px", fontWeight: 600, background: status === "success" ? "#dcfce7" : status === "running" ? "#fef9c3" : "#fee2e2", color: status === "success" ? "#16a34a" : status === "running" ? "#ca8a04" : "#dc2626" } as React.CSSProperties),
  // 筛选区域
  filterWrap: { background: "#f8fafc", borderRadius: "8px", border: "1px solid #e5e7eb", padding: "12px 14px", marginBottom: "12px" } as React.CSSProperties,
  filterRow:  { display: "flex", gap: "8px", flexWrap: "wrap" as const, alignItems: "flex-end", marginBottom: "8px" } as React.CSSProperties,
  filterLabel:{ fontSize: "12px", color: "#6b7280", display: "block", marginBottom: "2px" } as React.CSSProperties,
  filterInput:{ padding: "6px 10px", borderRadius: "6px", border: "1px solid #e5e7eb", fontSize: "13px", width: "140px", outline: "none", background: "#fff" } as React.CSSProperties,
  filterSelect:{ padding: "6px 10px", borderRadius: "6px", border: "1px solid #e5e7eb", fontSize: "13px", width: "160px", outline: "none", background: "#fff", cursor: "pointer" } as React.CSSProperties,
  filterSmInput:{ padding: "6px 10px", borderRadius: "6px", border: "1px solid #e5e7eb", fontSize: "13px", width: "100px", outline: "none", background: "#fff" } as React.CSSProperties,
  quickBtn:   (active: boolean) => ({ padding: "5px 10px", borderRadius: "5px", border: `1px solid ${active ? "#6366f1" : "#e5e7eb"}`, background: active ? "#ede9fe" : "#fff", color: active ? "#6366f1" : "#6b7280", fontSize: "12px", cursor: "pointer", fontWeight: active ? 600 : 400 } as React.CSSProperties),
  searchBtn:  { padding: "7px 18px", borderRadius: "6px", border: "none", background: "#6366f1", color: "#fff", cursor: "pointer", fontSize: "13px", fontWeight: 600 } as React.CSSProperties,
  resetBtn:   { padding: "7px 14px", borderRadius: "6px", border: "1px solid #e5e7eb", background: "#fff", color: "#6b7280", cursor: "pointer", fontSize: "13px" } as React.CSSProperties,
  columnBtn:  { padding: "7px 14px", borderRadius: "6px", border: "1px solid #c7d2fe", background: "#eef2ff", color: "#4f46e5", cursor: "pointer", fontSize: "13px", fontWeight: 600 } as React.CSSProperties,
  columnPanel:{ marginTop: "10px", padding: "10px", border: "1px solid #e5e7eb", borderRadius: "8px", background: "#fff" } as React.CSSProperties,
  columnGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "6px" } as React.CSSProperties,
  columnItem: { display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", padding: "6px 8px", border: "1px solid #eef2f7", borderRadius: "6px", background: "#f8fafc", fontSize: "12px" } as React.CSSProperties,
  inlineSelect:{ padding: "4px 8px", borderRadius: "6px", border: "1px solid #dbe3ef", fontSize: "12px", background: "#fff", minWidth: "110px" } as React.CSSProperties,
  inlineInput: { padding: "4px 8px", borderRadius: "6px", border: "1px solid #dbe3ef", fontSize: "12px", width: "74px", background: "#fff" } as React.CSSProperties,
  miniBtn:     { padding: "4px 8px", borderRadius: "6px", border: "1px solid #c7d2fe", background: "#eef2ff", color: "#4f46e5", cursor: "pointer", fontSize: "12px", fontWeight: 600 } as React.CSSProperties,
};

// ── 领星式日期范围选择器（2026-07-17：左侧快捷 + 双月日历，自绘无依赖） ──────────

function fmtDateYmd(d: Date): string {
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// ── 领星风格多选下拉（2026-07-17：全选/搜索/仅筛选此项/取消确定）──────
function LxMultiSelect({ placeholder, options, selected, onChange, minWidth = 140 }: {
  placeholder: string;
  options: Array<{ value: string; label: string }>;
  selected: string[];
  onChange: (v: string[]) => void;
  minWidth?: number;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<string[]>(selected);
  const [kw, setKw] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => { if (open) { setPending(selected); setKw(""); } }, [open, selected]);
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const shown = options.filter(o => !kw || o.label.includes(kw) || o.value.includes(kw));
  const allChecked = shown.length > 0 && shown.every(o => pending.includes(o.value));
  const toggleAll = () => setPending(allChecked
    ? pending.filter(v => !shown.some(o => o.value === v))
    : Array.from(new Set([...pending, ...shown.map(o => o.value)])));
  const toggleOne = (v: string) =>
    setPending(prev => prev.includes(v) ? prev.filter(x => x !== v) : [...prev, v]);

  const selLabel = (v: string) => options.find(o => o.value === v)?.label ?? v;
  const label = selected.length === 0 ? placeholder :
    selected.length === 1 ? selLabel(selected[0]) :
    `${selLabel(selected[0])} 等${selected.length}项`;

  return (
    <div ref={ref} style={{ position:"relative" }}>
      <button onClick={() => setOpen(o => !o)}
        style={{ border:"1px solid #d1d5db", borderRadius:6, padding:"5px 26px 5px 10px",
          fontSize:13, background:"#fff", cursor:"pointer", minWidth, textAlign:"left", position:"relative",
          color: selected.length ? "#111" : "#9ca3af" }}>
        {label}
        <span style={{ position:"absolute", right:8, top:"50%", transform:"translateY(-50%)", color:"#9ca3af" }}>▾</span>
      </button>
      {open && (
        <div style={{ position:"absolute", top:"110%", left:0, background:"#fff",
          border:"1px solid #e2e8f0", borderRadius:8, boxShadow:"0 6px 20px rgba(0,0,0,.14)",
          zIndex:120, minWidth:230, display:"flex", flexDirection:"column" }}>
          {options.length > 8 && (
            <div style={{ padding:"8px 10px 4px" }}>
              <input placeholder="搜索…" value={kw} onChange={e => setKw(e.target.value)}
                style={{ width:"100%", boxSizing:"border-box", border:"1px solid #d1d5db",
                  borderRadius:6, padding:"5px 8px", fontSize:12 }} />
            </div>
          )}
          <div style={{ maxHeight:260, overflowY:"auto", padding:"4px 0" }}>
            <label style={{ display:"flex", alignItems:"center", gap:8, padding:"6px 12px",
              cursor:"pointer", fontSize:13, borderBottom:"1px solid #f1f5f9" }}>
              <input type="checkbox" checked={allChecked} onChange={toggleAll} />
              全选
            </label>
            {shown.map(o => (
              <div key={o.value}
                style={{ display:"flex", alignItems:"center", gap:8, padding:"6px 12px", fontSize:13 }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLElement).style.background = "#f0f7ff";
                  const only = (e.currentTarget as HTMLElement).querySelector("[data-only]") as HTMLElement | null;
                  if (only) only.style.visibility = "visible";
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLElement).style.background = "transparent";
                  const only = (e.currentTarget as HTMLElement).querySelector("[data-only]") as HTMLElement | null;
                  if (only) only.style.visibility = "hidden";
                }}>
                <input type="checkbox" checked={pending.includes(o.value)} onChange={() => toggleOne(o.value)}
                  style={{ cursor:"pointer" }} />
                <span style={{ flex:1, cursor:"pointer", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}
                  onClick={() => toggleOne(o.value)}>{o.label}</span>
                <span data-only style={{ visibility:"hidden", color:"#2563eb", fontSize:12, cursor:"pointer", flexShrink:0 }}
                  onClick={() => setPending([o.value])}>仅筛选此项</span>
              </div>
            ))}
            {shown.length === 0 && <div style={{ padding:"10px 12px", fontSize:12, color:"#94a3b8" }}>无匹配项</div>}
          </div>
          <div style={{ display:"flex", gap:8, justifyContent:"flex-end", padding:"8px 10px",
            borderTop:"1px solid #f1f5f9" }}>
            <button onClick={() => setOpen(false)}
              style={{ padding:"4px 14px", border:"1px solid #d1d5db", borderRadius:6, background:"#fff",
                cursor:"pointer", fontSize:12 }}>取消</button>
            <button onClick={() => { onChange(pending); setOpen(false); }}
              style={{ padding:"4px 14px", border:"none", borderRadius:6, background:"#2563eb",
                color:"#fff", cursor:"pointer", fontSize:12, fontWeight:600 }}>确定</button>
          </div>
        </div>
      )}
    </div>
  );
}

function DateRangePicker({ start, end, quickOptions, activeQuick, onQuick, onRange }: {
  start: string; end: string;
  quickOptions: Array<{ days: number; label: string }>;
  activeQuick: number | null;
  onQuick: (days: number) => void;
  onRange: (start: string, end: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [viewMonth, setViewMonth] = useState<Date>(() => {
    const base = end ? new Date(`${end}T00:00:00`) : new Date();
    return new Date(base.getFullYear(), base.getMonth() - 1, 1); // 左月=结束月的上一月
  });
  const [pendStart, setPendStart] = useState<string>("");
  const wrapRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) { setOpen(false); setPendStart(""); }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const pickDay = (ymd: string) => {
    if (!pendStart) { setPendStart(ymd); return; }
    const s = pendStart <= ymd ? pendStart : ymd;
    const e = pendStart <= ymd ? ymd : pendStart;
    setPendStart("");
    setOpen(false);
    onRange(s, e);
  };

  const renderMonth = (base: Date) => {
    const y = base.getFullYear();
    const m = base.getMonth();
    const firstDow = new Date(y, m, 1).getDay();
    const daysInMonth = new Date(y, m + 1, 0).getDate();
    const cells: Array<string | null> = [];
    for (let i = 0; i < firstDow; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) cells.push(fmtDateYmd(new Date(y, m, d)));
    const inRange = (ymd: string) => {
      const s = pendStart || start;
      const e = pendStart ? "" : end;
      if (pendStart) return ymd === pendStart;
      return s && e && ymd >= s && ymd <= e;
    };
    const isEdge = (ymd: string) => ymd === (pendStart || start) || (!pendStart && ymd === end);
    return (
      <div style={{ width: "224px" }}>
        <div style={{ textAlign: "center", fontSize: "13px", fontWeight: 600, color: "#374151", marginBottom: "4px" }}>
          {y} 年 {m + 1} 月
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 32px)", fontSize: "12px", color: "#9ca3af", textAlign: "center" }}>
          {["日", "一", "二", "三", "四", "五", "六"].map((w) => <span key={w} style={{ padding: "2px 0" }}>{w}</span>)}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 32px)" }}>
          {cells.map((ymd, i) => ymd === null
            ? <span key={`e${i}`} />
            : (
              <button key={ymd} type="button" onClick={() => pickDay(ymd)}
                style={{ border: "none", cursor: "pointer", fontSize: "12px", padding: "5px 0",
                  borderRadius: isEdge(ymd) ? "50%" : 0,
                  background: isEdge(ymd) ? "#6366f1" : inRange(ymd) ? "#eef2ff" : "transparent",
                  color: isEdge(ymd) ? "#fff" : "#374151" }}>
                {Number(ymd.slice(8))}
              </button>
            ))}
        </div>
      </div>
    );
  };

  const nextMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 1);
  return (
    <span ref={wrapRef} style={{ position: "relative", display: "inline-flex" }}>
      <button type="button" onClick={() => setOpen((v) => !v)}
        style={{ display: "inline-flex", alignItems: "center", gap: "6px", padding: "6px 10px",
          borderRadius: "6px", border: "1px solid #e5e7eb", background: "#fff", fontSize: "13px",
          color: start || end ? "#374151" : "#9ca3af", cursor: "pointer", whiteSpace: "nowrap" }}>
        {start || "开始日期"} <span style={{ color: "#9ca3af" }}>-</span> {end || "结束日期"} <span>📅</span>
      </button>
      {open && (
        <div style={{ position: "absolute", top: "110%", left: 0, zIndex: 60, background: "#fff",
          border: "1px solid #e5e7eb", borderRadius: "10px", boxShadow: "0 8px 24px rgba(0,0,0,0.15)",
          display: "flex", padding: "10px" }}>
          <div style={{ width: "88px", borderRight: "1px solid #f1f5f9", paddingRight: "6px", marginRight: "10px" }}>
            {quickOptions.map((opt) => (
              <div key={opt.days}
                onClick={() => { setOpen(false); setPendStart(""); onQuick(opt.days); }}
                style={{ padding: "6px 8px", fontSize: "12px", cursor: "pointer", borderRadius: "5px",
                  color: activeQuick === opt.days ? "#4f46e5" : "#374151",
                  background: activeQuick === opt.days ? "#eef2ff" : "transparent" }}>
                {opt.label}
              </div>
            ))}
          </div>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "2px" }}>
              <button type="button" style={{ border: "none", background: "none", cursor: "pointer", color: "#6b7280" }}
                onClick={() => setViewMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() - 1, 1))}>‹</button>
              <span style={{ fontSize: "11px", color: "#94a3b8", alignSelf: "center" }}>
                {pendStart ? `已选起点 ${pendStart}，请选结束日` : "点选开始日与结束日"}
              </span>
              <button type="button" style={{ border: "none", background: "none", cursor: "pointer", color: "#6b7280" }}
                onClick={() => setViewMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 1))}>›</button>
            </div>
            <div style={{ display: "flex", gap: "14px" }}>
              {renderMonth(viewMonth)}
              {renderMonth(nextMonth)}
            </div>
          </div>
        </div>
      )}
    </span>
  );
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

export default function FeishuRawSalesData({ initialTab, embedded, onNavigate }: { initialTab?: string; embedded?: boolean; onNavigate?: (key: string) => void } = {}) {
  const [activeTab, setActiveTab]     = useState(initialTab || "<REDACTED_FEISHU_SHEET_ID>");
  const [exporting, setExporting]     = useState(false); // 2026-07-20 下载导出中
  const [pageSize, setPageSize]       = useState(50); // 每页条数（50/100/200，同广告库查看器）
  const [sheetMetas, setSheetMetas]   = useState<SheetMeta[]>([]);
  const [sheetData, setSheetData]     = useState<SheetData | null>(null);
  const [syncTasks, setSyncTasks]     = useState<SyncTask[]>([]);
  // 2026-07-24 CS规则面板已移除（需求方拍板）：state/请求/渲染块一并清理，后端接口保留
  const [page, setPage]               = useState(1);
  const [loading, setLoading]         = useState(false);
  const [storeOptions, setStoreOptions] = useState<string[]>([]);
  const [ownerOptions, setOwnerOptions] = useState<string[]>([]);
  const [profitLevelOptions, setProfitLevelOptions] = useState<string[]>([]);
  const [productFeeDrafts, setProductFeeDrafts] = useState<Record<string, string>>({});
  const [productLifecycleDrafts, setProductLifecycleDrafts] = useState<Record<string, string>>({});
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchMsg, setBatchMsg] = useState("");
  const [productSavingKey, setProductSavingKey] = useState("");
  const [productMessage, setProductMessage] = useState("");
  const [opLogDrafts, setOpLogDrafts] = useState<Record<string, string>>({});
  const [opLogSavingId, setOpLogSavingId] = useState("");
  const [opLogMsg, setOpLogMsg] = useState<{ id: string; msg: string }>({ id: "", msg: "" });
  // 2026-07-24 CS测品分析「预警原因」页面编辑
  const [csReasonDrafts, setCsReasonDrafts] = useState<Record<string, string>>({});
  const [csReasonSavingId, setCsReasonSavingId] = useState("");
  const [csReasonMsg, setCsReasonMsg] = useState<{ id: string; msg: string }>({ id: "", msg: "" });
  const [reminderModal, setReminderModal] = useState<{ title: string; text: string } | null>(null);
  const [productOperatorName, setProductOperatorName] = useState("");
  // 2026-07-23 GPT分析链接编辑弹窗（ItemID维度；不允许清空只能替换；仅保存有修改的链接）
  const [gptLinkModal, setGptLinkModal] = useState<{ itemId: string; msku: string; kw: string; ads: string; kwOrig: string; adsOrig: string } | null>(null);
  const [gptLinkSaving, setGptLinkSaving] = useState(false);
  const [gptLinkMsg, setGptLinkMsg] = useState("");

  // 表单输入状态（未提交）
  const [inpKeyword, setInpKeyword]   = useState("");
  const [inpSku,     setInpSku]       = useState("");
  const [inpMsku,    setInpMsku]      = useState("");
  const [inpItemId,  setInpItemId]    = useState("");
  // 2026-07-17 领星式多选：店铺/负责人输入态改数组，filters 层保持逗号串（后端已支持CSV多值）
  const [inpStore,   setInpStore]     = useState<string[]>([]);
  const [inpOwner,   setInpOwner]     = useState<string[]>([]);
  const [inpStockStatus, setInpStockStatus] = useState("");
  const [inpProductStage, setInpProductStage] = useState("");
  const [inpCostStatus, setInpCostStatus] = useState("");
  const [inpWfsFeeStatus, setInpWfsFeeStatus] = useState("");
  const [inpPmCostStatus, setInpPmCostStatus] = useState("");
  const [inpProductStatus, setInpProductStatus] = useState("");
  const [inpManualLifecycle, setInpManualLifecycle] = useState("");
  const [inpProfitLevel, setInpProfitLevel] = useState("");
  const [inpGptLink, setInpGptLink] = useState("");
  const [inpLogFilled, setInpLogFilled] = useState("");
  const [inpWfsStock, setInpWfsStock] = useState("");
  const [inpDateStart, setInpDateStart] = useState("");
  const [inpDateEnd,   setInpDateEnd]   = useState("");
  const [inpGrossMin,  setInpGrossMin]  = useState("");
  const [inpGrossMax,  setInpGrossMax]  = useState("");
  const [inpAdMin,     setInpAdMin]     = useState("");
  const [inpAdMax,     setInpAdMax]     = useState("");
  const [inpAdSpendMin, setInpAdSpendMin] = useState("");
  const [inpAdSpendMax, setInpAdSpendMax] = useState("");
  const [inpClicksMin,  setInpClicksMin]  = useState("");
  const [inpClicksMax,  setInpClicksMax]  = useState("");
  const [inpTestDaysMin, setInpTestDaysMin] = useState("");
  const [inpTestDaysMax, setInpTestDaysMax] = useState("");
  const [activeQuick,  setActiveQuick]  = useState<number | null>(null);

  // 已提交的筛选条件（触发数据加载）
  const [filters, setFilters] = useState<AppliedFilters>(DEFAULT_FILTERS);
  const [showColumnConfig, setShowColumnConfig] = useState(false);
  const [showMoreFilters, setShowMoreFilters] = useState(false); // 更多筛选浮层（2026-07-17）
  const [searchField, setSearchField] = useState("keyword");     // 合并搜索：字段
  const [searchText, setSearchText] = useState("");              // 合并搜索：内容
  const [pinnedColumnsByTab, setPinnedColumnsByTab] = useState<Record<string, string[]>>(
    () => readStringArrayMap(PINNED_COLUMNS_STORAGE_KEY),
  );
  const dragColIdxRef = useRef<number | null>(null); // 列配置拖拽
  const [cfgSelected, setCfgSelected] = useState<string[]>([]); // 列配置弹窗工作副本（顺序=列顺序）
  const [cfgPins, setCfgPins] = useState<string[]>([]);
  const [columnOrderByTab, setColumnOrderByTab] = useState<Record<string, string[]>>(
    () => readStringArrayMap(COLUMN_ORDER_STORAGE_KEY),
  );
  const [visibleColumnsByTab, setVisibleColumnsByTab] = useState<Record<string, string[]>>(
    () => readStringArrayMap(VISIBLE_COLUMNS_STORAGE_KEY),
  );
  const [sortByTab, setSortByTab] = useState<Record<string, TabSortState>>({});
  // 2026-07-15：列宽拖拽（会话内生效）与 行列高亮（点单元格，仿WPS，再点取消）
  const [colWidths, setColWidths] = useState<Record<string, Record<string, number>>>({});
  const [hlCell, setHlCell] = useState<{ tab: string; row: number; col: number } | null>(null);
  const resizeRef = useRef<{ tab: string; col: string; startX: number; startW: number } | null>(null);

  useEffect(() => {
    function onMove(e: MouseEvent) {
      const r = resizeRef.current;
      if (!r) return;
      const w = Math.max(60, r.startW + (e.clientX - r.startX));
      setColWidths((prev) => ({ ...prev, [r.tab]: { ...(prev[r.tab] ?? {}), [r.col]: w } }));
    }
    function onUp() { resizeRef.current = null; document.body.style.cursor = ""; }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    return () => { document.removeEventListener("mousemove", onMove); document.removeEventListener("mouseup", onUp); };
  }, []);

  // 列宽拖拽把手可见化（Google 风格：常显浅灰竖条，悬停变蓝加粗全高）
  useEffect(() => {
    if (typeof document === "undefined" || document.getElementById("lx-colresize-css")) return;
    const st = document.createElement("style");
    st.id = "lx-colresize-css";
    st.textContent =
      ".lx-colresize{position:absolute;top:0;right:-4px;width:9px;height:100%;cursor:col-resize;user-select:none;z-index:3;display:flex;align-items:center;justify-content:center}" +
      ".lx-colresize::after{content:'';width:2px;height:56%;background:#dadce0;border-radius:1px;transition:background .12s,height .12s,width .12s}" +
      ".lx-colresize:hover::after{background:#1a73e8;width:3px;height:100%}";
    document.head.appendChild(st);
  }, []);

  // 防止初次渲染时重复请求
  const prevTabRef = useRef<string>("");
  const currentSort = sortByTab[activeTab] ?? EMPTY_SORT_STATE;

  // ── 数据加载 ─────────────────────────────────────────────────────────────────

  const loadMetas = useCallback(async () => {
    try {
      const res = await fetch("/api/feishu-raw-sales/sheets");
      setSheetMetas(await res.json());
    } catch {}
  }, []);

  const loadFilterOptions = useCallback(async (sheetId: string) => {
    setStoreOptions([]);
    setOwnerOptions([]);
    setProfitLevelOptions([]);
    try {
      const res = await fetch(`/api/feishu-raw-sales/filter-options?sheet_id=${sheetId}`);
      const data = await res.json();
      setStoreOptions(data.stores ?? []);
      setProfitLevelOptions(data.profit_levels ?? []);
      if (sheetId === PRODUCT_MANAGEMENT_SHEET_ID) {
        // V1.1: 负责人下拉框改为读取"数据库里所有有飞书ID的有效人员"，不再从当前产品 distinct
        const ownerRes = await fetch("/api/feishu-raw-sales/product-management/owner-options");
        const ownerData = await ownerRes.json();
        const owners = (ownerData.owners ?? []) as { owner_name: string }[];
        setOwnerOptions(owners.map((o) => o.owner_name).filter(Boolean));
      } else {
        setOwnerOptions(data.owners ?? []);
      }
    } catch {}
  }, []);

  const loadSheetData = useCallback(async (
    sheetId: string,
    pg: number,
    f: AppliedFilters,
    sort: TabSortState,
    ps: number,
  ) => {
    setLoading(true);
    try {
      const p = new URLSearchParams({
        sheet_id:  sheetId,
        page:      String(pg),
        page_size: String(ps),
        keyword:       f.keyword,
        sku:           f.sku,
        msku:          f.msku,
        item_id:       f.itemId,
        store_name:    f.store,
        owner:         f.owner,
        profit_level:  f.profitLevel,
        gpt_link_status: f.gptLink,
        stock_status:  f.stockStatus,
        product_stage: f.productStage,
        cost_status:   f.costStatus,
        date_start:    f.dateStart,
        date_end:      f.dateEnd,
        gross_margin_min: f.grossMin,
        gross_margin_max: f.grossMax,
        ad_ratio_min:  f.adMin,
        ad_ratio_max:  f.adMax,
        wfs_fee_status: f.wfsFeeStatus,
        pm_cost_status: f.pmCostStatus,
        product_management_status: f.productStatus,
        manual_lifecycle: f.manualLifecycle,
        ad_spend_min:  f.adSpendMin,
        ad_spend_max:  f.adSpendMax,
        clicks_min:    f.clicksMin,
        clicks_max:    f.clicksMax,
        test_days_min: f.testDaysMin,
        test_days_max: f.testDaysMax,
        sort_field:    sort.field,
        sort_order:    sort.order,
        log_filled:    f.logFilled,
        wfs_stock:     f.wfsStock,
      });
      const endpoint = sheetId === ORDER_PROFIT_SHEET_ID
        ? "order-profit"
        : sheetId === CS_TEST_SHEET_ID
          ? "cs-test-analysis"
          : sheetId === PRODUCT_MANAGEMENT_SHEET_ID
            ? "product-management"
            : sheetId === OPERATION_LOG_SHEET_ID
              ? "operation-log"
              : "data";
      const res = await fetch(`/api/feishu-raw-sales/${endpoint}?${p}`);
      const data = await res.json();
      if (data.error || !res.ok) {
        console.error("[feishu-data] 接口错误:", data.error);
        setSheetData(null);
      } else if (data.sheet_id !== sheetId) {
        console.warn("[feishu-data] 忽略过期响应:", { requested: sheetId, received: data.sheet_id });
      } else {
        setSheetData(data);
      }
    } catch {
      setSheetData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // ── 数据下载（2026-07-20）：密码授权（dim_access_password）→ 审计留痕 → 全量CSV ──
  const handleExport = useCallback(async () => {
    if (activeTab === "__tasks__") return;
    const password = window.prompt("请输入下载密码：");
    if (!password) return;
    setExporting(true);
    try {
      const pageKey = PAGE_HELP_KEYS[activeTab] ?? activeTab;
      const vRes = await fetch("/api/help/export-verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: password.trim(), page_key: pageKey, filters: JSON.stringify(filters) }),
      });
      const vData = await vRes.json();
      if (!vRes.ok || !vData.token) {
        alert(vData.error || "下载密码校验失败");
        return;
      }
      const f = filters;
      const sort = currentSort;
      const p = new URLSearchParams({
        sheet_id:  activeTab,
        page:      "1",
        page_size: String(vData.max_rows ?? 50000),
        export_token: String(vData.token),
        keyword:       f.keyword,
        sku:           f.sku,
        msku:          f.msku,
        item_id:       f.itemId,
        store_name:    f.store,
        owner:         f.owner,
        profit_level:  f.profitLevel,
        gpt_link_status: f.gptLink,
        stock_status:  f.stockStatus,
        product_stage: f.productStage,
        cost_status:   f.costStatus,
        date_start:    f.dateStart,
        date_end:      f.dateEnd,
        gross_margin_min: f.grossMin,
        gross_margin_max: f.grossMax,
        ad_ratio_min:  f.adMin,
        ad_ratio_max:  f.adMax,
        wfs_fee_status: f.wfsFeeStatus,
        pm_cost_status: f.pmCostStatus,
        product_management_status: f.productStatus,
        manual_lifecycle: f.manualLifecycle,
        ad_spend_min:  f.adSpendMin,
        ad_spend_max:  f.adSpendMax,
        clicks_min:    f.clicksMin,
        clicks_max:    f.clicksMax,
        test_days_min: f.testDaysMin,
        test_days_max: f.testDaysMax,
        sort_field:    sort.field,
        sort_order:    sort.order,
        log_filled:    f.logFilled,
        wfs_stock:     f.wfsStock,
      });
      const endpoint = activeTab === ORDER_PROFIT_SHEET_ID
        ? "order-profit"
        : activeTab === CS_TEST_SHEET_ID
          ? "cs-test-analysis"
          : activeTab === PRODUCT_MANAGEMENT_SHEET_ID
            ? "product-management"
            : activeTab === OPERATION_LOG_SHEET_ID
              ? "operation-log"
              : "data";
      const res = await fetch(`/api/feishu-raw-sales/${endpoint}?${p}`);
      const data = await res.json();
      if (data.error || !res.ok) {
        alert("导出失败: " + (data.error ?? res.status));
        return;
      }
      const rows: Array<Record<string, string>> = data.rows ?? [];
      if (rows.length === 0) {
        alert("当前筛选无数据可导出");
        return;
      }
      const columns: string[] = (data.columns?.length ? data.columns : Object.keys(rows[0])) as string[];
      const esc = (v: unknown) => {
        const sv = v === null || v === undefined ? "" : String(v);
        return /[",\n]/.test(sv) ? `"${sv.replace(/"/g, '""')}"` : sv;
      };
      const csv = "\uFEFF" + [columns.map(esc).join(","), ...rows.map((r) => columns.map((c) => esc(r[c])).join(","))].join("\n");
      const label = SHEET_TABS.find((t) => t.sheetId === activeTab)?.label ?? activeTab;
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${label}_${f.dateStart || "全部"}~${f.dateEnd || ""}_${rows.length}行.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      alert("导出失败: " + String(e));
    } finally {
      setExporting(false);
    }
  }, [activeTab, filters, currentSort]);

  const loadSyncTasks = useCallback(async () => {
    try {
      const res = await fetch("/api/feishu-raw-sales/sync-tasks");
      setSyncTasks(await res.json());
    } catch {}
  }, []);

  

  // ── Effects ───────────────────────────────────────────────────────────────────

  useEffect(() => { loadMetas(); }, [loadMetas]);

  // V1.2: 兜底 fallback —— 如果当前 activeTab 不在展示 allowlist 里（旧 Tab 已隐藏），
  // 自动切回产品管理，避免出现"隐藏了入口但状态仍停留在旧 Tab"的情况。
  useEffect(() => {
    if (!VISIBLE_SHEET_IDS.has(activeTab)) {
      handleTabChange(PRODUCT_MANAGEMENT_SHEET_ID);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // Tab 变化时加载筛选选项
  useEffect(() => {
    if (activeTab !== "__tasks__" && activeTab !== "__clearance__" && activeTab !== "__pmc__" && activeTab !== prevTabRef.current) {
      prevTabRef.current = activeTab;
      loadFilterOptions(activeTab);
    }
  }, [activeTab, loadFilterOptions]);

  // 数据加载（tab + page + filters 变化时）
  useEffect(() => {
    if (activeTab === "__tasks__") {
      loadSyncTasks();
    } else if (activeTab === "__clearance__" || activeTab === "__pmc__") {
      /* 组件自加载 */
    } else {
      loadSheetData(activeTab, page, filters, currentSort, pageSize);
    }
  }, [activeTab, page, filters, currentSort, pageSize, loadSheetData]);

  useEffect(() => {
    writeStringArrayMap(COLUMN_ORDER_STORAGE_KEY, columnOrderByTab);
  }, [columnOrderByTab]);

  useEffect(() => {
    writeStringArrayMap(VISIBLE_COLUMNS_STORAGE_KEY, visibleColumnsByTab);
  }, [visibleColumnsByTab]);

  useEffect(() => {
    writeStringArrayMap(PINNED_COLUMNS_STORAGE_KEY, pinnedColumnsByTab);
  }, [pinnedColumnsByTab]);

  // 列配置弹窗打开时装载当前配置（visibleColumns 每次渲染新引用，仅以打开动作为触发）
  useEffect(() => {
    if (!showColumnConfig) return;
    const base = glueSysLogBeforeOpsLog(visibleColumnsByTab[activeTab] ?? actualColumns);
    setCfgSelected(base);
    setCfgPins((pinnedColumnsByTab[activeTab] ?? DEFAULT_PINNED_BY_TAB[activeTab] ?? []).filter((c) => base.includes(c)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showColumnConfig, activeTab]);

  useEffect(() => { setSelectedKeys(new Set()); setBatchMsg(""); }, [activeTab, page, pageSize]);

  // ── 事件处理 ──────────────────────────────────────────────────────────────────

  function getDefaultFiltersForTab(sheetId: string): AppliedFilters {
    const tabsWithDefaultDate = ["<REDACTED_FEISHU_SHEET_ID>", ORDER_PROFIT_SHEET_ID, CS_TEST_SHEET_ID, OPERATION_LOG_SHEET_ID];
    if (!tabsWithDefaultDate.includes(sheetId)) return DEFAULT_FILTERS;
    const date = businessAvailableDate();
    return { ...DEFAULT_FILTERS, dateStart: date, dateEnd: date };
  }

  function syncInputsFromFilters(f: AppliedFilters, quick: number | null) {
    setInpKeyword(f.keyword); setInpSku(f.sku); setInpMsku(f.msku); setInpItemId(f.itemId);
    // 合并搜索框回填：取第一个非空字段
    if (f.sku) { setSearchField("sku"); setSearchText(f.sku); }
    else if (f.msku) { setSearchField("msku"); setSearchText(f.msku); }
    else if (f.itemId) { setSearchField("itemId"); setSearchText(f.itemId); }
    else { setSearchField("keyword"); setSearchText(f.keyword); }
    setInpStore(f.store.split(",").map((x) => x.trim()).filter(Boolean));
    setInpOwner(f.owner.split(",").map((x) => x.trim()).filter(Boolean));
    setInpStockStatus(f.stockStatus); setInpProductStage(f.productStage); setInpCostStatus(f.costStatus);
    setInpDateStart(f.dateStart); setInpDateEnd(f.dateEnd);
    setInpGrossMin(f.grossMin); setInpGrossMax(f.grossMax); setInpAdMin(f.adMin); setInpAdMax(f.adMax);
    setInpWfsFeeStatus(f.wfsFeeStatus); setInpPmCostStatus(f.pmCostStatus); setInpProductStatus(f.productStatus); setInpProfitLevel(f.profitLevel); setInpGptLink(f.gptLink);
    setInpManualLifecycle(f.manualLifecycle);
    setInpAdSpendMin(f.adSpendMin); setInpAdSpendMax(f.adSpendMax);
    setInpClicksMin(f.clicksMin); setInpClicksMax(f.clicksMax);
    setInpTestDaysMin(f.testDaysMin); setInpTestDaysMax(f.testDaysMax);
    setInpLogFilled(f.logFilled); setInpWfsStock(f.wfsStock);
    setActiveQuick(quick);
  }

  function handleTabChange(sheetId: string) {
    setActiveTab(sheetId);
    setPage(1);
    setSortByTab((prev) => ({ ...prev, [sheetId]: EMPTY_SORT_STATE }));
    const nextFilters = getDefaultFiltersForTab(sheetId);
    syncInputsFromFilters(nextFilters, nextFilters.dateStart ? 1 : null);
    setFilters(nextFilters);
  }

  function resetInputs() {
    setInpKeyword(""); setInpSku(""); setInpMsku(""); setInpItemId("");
    setSearchField("keyword"); setSearchText("");
    setInpStore([]); setInpOwner([]);
    setInpStockStatus(""); setInpProductStage(""); setInpCostStatus("");
    setInpDateStart(""); setInpDateEnd("");
    setInpGrossMin(""); setInpGrossMax(""); setInpAdMin(""); setInpAdMax("");
    setInpWfsFeeStatus(""); setInpProductStatus(""); setInpProfitLevel(""); setInpGptLink(""); setInpManualLifecycle("");
    setInpAdSpendMin(""); setInpAdSpendMax("");
    setInpClicksMin(""); setInpClicksMax("");
    setInpTestDaysMin(""); setInpTestDaysMax("");
    setInpLogFilled(""); setInpWfsStock("");
    setActiveQuick(null);
  }

  /** 合并搜索框：按所选字段派生四个搜索参数（其余置空），后端接口不变 */
  function derivedSearch() {
    const t = searchText.trim();
    return {
      keyword: searchField === "keyword" ? t : "",
      sku:     searchField === "sku" ? t : "",
      msku:    searchField === "msku" ? t : "",
      itemId:  searchField === "itemId" ? t : "",
    };
  }

  function handleSearch() {
    const ds = derivedSearch();
    setFilters({
      keyword:   ds.keyword,
      sku:       ds.sku,
      msku:      ds.msku,
      itemId:    ds.itemId,
      store:     inpStore.join(","),
      owner:     inpOwner.join(","),
      stockStatus: inpStockStatus,
      productStage: inpProductStage,
      costStatus: inpCostStatus,
      dateStart: inpDateStart,
      dateEnd:   inpDateEnd,
      grossMin:  inpGrossMin,
      grossMax:  inpGrossMax,
      adMin:     inpAdMin,
      adMax:     inpAdMax,
      wfsFeeStatus: inpWfsFeeStatus,
      pmCostStatus: inpPmCostStatus,
      productStatus: inpProductStatus,
      manualLifecycle: inpManualLifecycle,
      profitLevel: inpProfitLevel,
      gptLink: inpGptLink,
      adSpendMin: inpAdSpendMin,
      adSpendMax: inpAdSpendMax,
      clicksMin:  inpClicksMin,
      clicksMax:  inpClicksMax,
      testDaysMin: inpTestDaysMin,
      testDaysMax: inpTestDaysMax,
      logFilled:  inpLogFilled,
      wfsStock:   inpWfsStock,
    });
    setPage(1);
  }

  function handleReset() {
    const nextFilters = getDefaultFiltersForTab(activeTab);
    if (nextFilters.dateStart) {
      syncInputsFromFilters(nextFilters, 1);
    } else {
      resetInputs();
    }
    setSortByTab((prev) => ({ ...prev, [activeTab]: EMPTY_SORT_STATE }));
    setFilters(nextFilters);
    setPage(1);
  }

  function handleHeaderSort(column: string) {
    const field = SORTABLE_COLUMNS_BY_TAB[activeTab]?.[column];
    if (!field) return;
    const prev = sortByTab[activeTab] ?? EMPTY_SORT_STATE;
    let next: TabSortState;
    // 2026-07-15 需求：升序→降序→取消
    if (prev.field !== field) {
      next = { field, order: "asc" };
    } else if (prev.order === "asc") {
      next = { field, order: "desc" };
    } else {
      next = EMPTY_SORT_STATE;
    }
    setSortByTab((state) => ({ ...state, [activeTab]: next }));
    setPage(1);
  }

  function renderHeaderCell(column: string) {
    if (column === "__select__") {
      const keys = (currentSheetData?.rows ?? []).map(getProductRowKey);
      const allSel = keys.length > 0 && keys.every((k) => selectedKeys.has(k));
      return (
        <th key="__select__" style={{ ...s.th, position: "sticky" as const, top: 0, zIndex: 3, textAlign: "center" as const }}>
          <input type="checkbox" checked={allSel} onChange={(e) => setSelectedKeys((prev) => {
            const n = new Set(prev);
            if (e.target.checked) keys.forEach((k) => n.add(k)); else keys.forEach((k) => n.delete(k));
            return n;
          })} style={{ cursor: "pointer", width: 15, height: 15, accentColor: "#4f46e5" }} />
        </th>
      );
    }
    const field = SORTABLE_COLUMNS_BY_TAB[activeTab]?.[column];
    const sortable = Boolean(field);
    const active = sortable && currentSort.field === field && Boolean(currentSort.order);
    const arrow = !sortable ? "" : !active ? "⇅" : currentSort.order === "desc" ? "↓" : "↑";
    const width = colWidths[activeTab]?.[column];
    const thStyle: React.CSSProperties = {
      ...s.th, position: "sticky", top: 0, zIndex: 3, // 表头吸顶（数据区内滚动，2026-07-17）
      ...(width ? { width, minWidth: width, maxWidth: width } : {}),
    };
    return (
      <th key={column} style={thStyle}>
        <button
          type="button"
          style={s.thBtn(active, sortable)}
          onClick={() => sortable && handleHeaderSort(column)}
        >
          <span>{column}</span>
          {arrow && <span style={s.sortArrow(active)}>{arrow}</span>}
        </button>
        <span
          onMouseDown={(e) => {
            e.preventDefault(); e.stopPropagation();
            const th = (e.currentTarget as HTMLElement).parentElement as HTMLElement;
            resizeRef.current = { tab: activeTab, col: column, startX: e.clientX, startW: th.getBoundingClientRect().width };
            document.body.style.cursor = "col-resize";
          }}
          className="lx-colresize"
        />
      </th>
    );
  }

  function handleQuickDate(days: number) {
    const isYesterday = days === -2;
    const end = isYesterday ? businessAvailableDatePrevDay() : businessAvailableDate();
    const start = days === -1 ? businessMonthStart() : isYesterday ? end : dateWindowStart(days);
    setInpDateStart(start);
    setInpDateEnd(end);
    setActiveQuick(days);
    // 直接应用
    const dsq = derivedSearch();
    setFilters((prev) => ({
      ...prev,
      dateStart: start,
      dateEnd:   end,
      keyword:   dsq.keyword,
      sku:       dsq.sku,
      msku:      dsq.msku,
      itemId:    dsq.itemId,
      store:     inpStore.join(","),
      owner:     inpOwner.join(","),
      stockStatus: inpStockStatus,
      productStage: inpProductStage,
      costStatus: inpCostStatus,
      grossMin:  inpGrossMin,
      grossMax:  inpGrossMax,
      adMin:     inpAdMin,
      adMax:     inpAdMax,
    }));
    setPage(1);
  }

  /** 日历选定范围：与快捷按钮同语义，立即应用（2026-07-17 领星式日期控件） */
  function applyDateRange(start: string, end: string) {
    setInpDateStart(start);
    setInpDateEnd(end);
    setActiveQuick(null);
    const dsr = derivedSearch();
    setFilters((prev) => ({
      ...prev,
      dateStart: start,
      dateEnd:   end,
      keyword:   dsr.keyword,
      sku:       dsr.sku,
      msku:      dsr.msku,
      itemId:    dsr.itemId,
      store:     inpStore.join(","),
      owner:     inpOwner.join(","),
      stockStatus: inpStockStatus,
      productStage: inpProductStage,
      costStatus: inpCostStatus,
      grossMin:  inpGrossMin,
      grossMax:  inpGrossMax,
      adMin:     inpAdMin,
      adMax:     inpAdMax,
    }));
    setPage(1);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") handleSearch();
  }

  function getProductRowKey(row: Record<string, string>): string {
    return [
      row._platform || "walmart",
      row._store_id || row["店铺ID"] || "",
      row._item_id || row["ItemID"] || "",
      row._msku || row["MSKU"] || "",
    ].join("|");
  }

  function getProductPayload(row: Record<string, string>) {
    return {
      platform: row._platform || "walmart",
      store_id: row._store_id || row["店铺ID"] || "",
      store_name: row._store_name || row["店铺名称"] || "",
      item_id: row._item_id || row["ItemID"] || "",
      msku: row._msku || row["MSKU"] || "",
      sku: row._sku || row["SKU"] || "",
    };
  }

  async function saveProductOwner(row: Record<string, string>, owner: string) {
    const nextOwner = owner.trim();
    if (!nextOwner) return;
    const key = `${getProductRowKey(row)}|owner`;
    setProductSavingKey(key);
    setProductMessage("");
    try {
      const res = await fetch("/api/feishu-raw-sales/product-management/update-owner", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...getProductPayload(row), owner: nextOwner }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
      setProductMessage("负责人已更新");
      await loadSheetData(PRODUCT_MANAGEMENT_SHEET_ID, page, filters, sortByTab[PRODUCT_MANAGEMENT_SHEET_ID] ?? EMPTY_SORT_STATE, pageSize);
      await loadMetas();
      await loadFilterOptions(PRODUCT_MANAGEMENT_SHEET_ID);
    } catch (err) {
      setProductMessage(`负责人更新失败：${String(err)}`);
    } finally {
      setProductSavingKey("");
    }
  }

  // 2026-07-23 GPT分析链接：单条保存（版本表 append，后端校验 http(s) 前缀）
  async function saveGptLinkOne(itemId: string, linkType: "keyword" | "ads", url: string): Promise<void> {
    const res = await fetch("/api/feishu-raw-sales/product-management/update-gpt-link", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platform: "walmart", item_id: itemId, link_type: linkType, url }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
  }

  async function saveGptLinkModal() {
    if (!gptLinkModal || gptLinkSaving) return;
    const kw = gptLinkModal.kw.trim();
    const ads = gptLinkModal.ads.trim();
    if (!kw && gptLinkModal.kwOrig) { setGptLinkMsg("关键词链接不允许清空，只能替换为新链接"); return; }
    if (!ads && gptLinkModal.adsOrig) { setGptLinkMsg("广告链接不允许清空，只能替换为新链接"); return; }
    const kwChanged = kw !== "" && kw !== gptLinkModal.kwOrig;
    const adsChanged = ads !== "" && ads !== gptLinkModal.adsOrig;
    if (!kwChanged && !adsChanged) { setGptLinkMsg("链接未修改，无需保存"); return; }
    if ((kwChanged && !/^https?:\/\//.test(kw)) || (adsChanged && !/^https?:\/\//.test(ads))) {
      setGptLinkMsg("链接必须以 http(s):// 开头"); return;
    }
    setGptLinkSaving(true);
    setGptLinkMsg("");
    try {
      if (kwChanged) await saveGptLinkOne(gptLinkModal.itemId, "keyword", kw);
      if (adsChanged) await saveGptLinkOne(gptLinkModal.itemId, "ads", ads);
      setGptLinkModal(null);
      setProductMessage("GPT分析链接已保存（新生成的运营日志起使用新链接）");
      await loadSheetData(PRODUCT_MANAGEMENT_SHEET_ID, page, filters, sortByTab[PRODUCT_MANAGEMENT_SHEET_ID] ?? EMPTY_SORT_STATE, pageSize);
    } catch (err) {
      setGptLinkMsg(`保存失败：${String(err)}`);
    } finally {
      setGptLinkSaving(false);
    }
  }

  // 任务H-Stage3：运营日志行内编辑保存（仅 system_base 且未锁定行；只写 log_content）
  async function saveOperationLog(row: Record<string, string>, contentOverride?: string) {
    const id = row._id;
    if (!id) return;
    const val = contentOverride ?? (opLogDrafts[id] ?? row["运营日志"] ?? "");
    setOpLogSavingId(id);
    setOpLogMsg({ id: "", msg: "" });
    try {
      const res = await fetch("/api/feishu-raw-sales/operation-log/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: Number(id), log_content: val }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
      setOpLogDrafts((prev) => { const n = { ...prev }; delete n[id]; return n; });
      setOpLogMsg({ id, msg: "已保存" });
      await loadSheetData(OPERATION_LOG_SHEET_ID, page, filters, sortByTab[OPERATION_LOG_SHEET_ID] ?? EMPTY_SORT_STATE, pageSize);
    } catch (err) {
      setOpLogMsg({ id, msg: `保存失败：${String(err)}` });
    } finally {
      setOpLogSavingId("");
    }
  }

  // 2026-07-24 CS测品分析「预警原因」保存：写 biz_cs_test_alert.reason（≥15字）→ 消警 → 重载
  async function saveCsAlertReason(row: Record<string, string>) {
    const alertId = row._cs_alert_id;
    if (!alertId) return;
    const val = (csReasonDrafts[alertId] ?? row["预警原因"] ?? "").trim();
    if (val.length < 15) { setCsReasonMsg({ id: alertId, msg: `原因需不少于15字（当前${val.length}）` }); return; }
    setCsReasonSavingId(alertId);
    setCsReasonMsg({ id: "", msg: "" });
    try {
      const res = await fetch("/api/feishu-raw-sales/cs-test/save-alert-reason", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ alert_id: Number(alertId), reason: val }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
      setCsReasonDrafts((prev) => { const n = { ...prev }; delete n[alertId]; return n; });
      setCsReasonMsg({ id: alertId, msg: "已保存" });
      await loadSheetData(CS_TEST_SHEET_ID, page, filters, sortByTab[CS_TEST_SHEET_ID] ?? EMPTY_SORT_STATE, pageSize);
    } catch (err) {
      setCsReasonMsg({ id: alertId, msg: `保存失败：${String(err)}` });
    } finally {
      setCsReasonSavingId("");
    }
  }

  async function saveProductWfsFee(row: Record<string, string>) {
    const rowKey = getProductRowKey(row);
    const key = `${rowKey}|fee`;
    const fee = (productFeeDrafts[rowKey] ?? row["WFS配送费（$）"] ?? "").trim();
    setProductSavingKey(key);
    setProductMessage("");
    try {
      const res = await fetch("/api/feishu-raw-sales/product-management/update-wfs-fee", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...getProductPayload(row), delivery_fee: fee }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
      setProductMessage("WFS配送费已更新");
      setProductFeeDrafts((prev) => {
        const next = { ...prev };
        delete next[rowKey];
        return next;
      });
      await loadSheetData(PRODUCT_MANAGEMENT_SHEET_ID, page, filters, sortByTab[PRODUCT_MANAGEMENT_SHEET_ID] ?? EMPTY_SORT_STATE, pageSize);
      await loadMetas();
    } catch (err) {
      setProductMessage(`WFS配送费更新失败：${String(err)}`);
    } finally {
      setProductSavingKey("");
    }
  }

  async function saveProductStatus(row: Record<string, string>, nextStatus: "archived" | "active" | "inactive") {
    const rowKey = getProductRowKey(row);
    const key = `${rowKey}|status`;
    if (nextStatus === "archived") {
      // 2026-07-25 归档门槛前端预检（与后端一致：库存 < 5 且 无在途）；库存取列表「当前库存/在途库存」列
      // 2026-07-30 UNPUBLISHED(已下架)豁免库存门槛（与后端 e37f74a 一致）
      const isUnpublished = String(row._walmart_publish_status ?? "").toUpperCase() === "UNPUBLISHED";
      const curStock = Number(String(row["当前库存"] ?? "").replace(/[,\s]/g, "")) || 0;
      const curInbound = Number(String(row["在途库存"] ?? "").replace(/[,\s]/g, "")) || 0;
      if (!isUnpublished && (curStock >= 5 || curInbound > 0)) {
        const parts: string[] = [];
        if (curStock >= 5) parts.push(`当前库存 ${curStock}（需 < 5）`);
        if (curInbound > 0) parts.push(`在途 ${curInbound}（需为 0）`);
        setProductMessage(`无法归档：${parts.join("、")}；仅库存 < 5 且无在途的产品可归档`);
        return;
      }
    }
    if (nextStatus === "archived" && !window.confirm("确认归档该产品？归档后默认列表将隐藏该产品，历史数据不会删除。")) {
      return;
    }
    if (nextStatus === "inactive" && !window.confirm("确认将该停用候选设为停用？该操作为人工确认。")) {
      return;
    }
    setProductSavingKey(key);
    setProductMessage("");
    try {
      const res = await fetch("/api/feishu-raw-sales/product-management/update-status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...getProductPayload(row),
          product_management_status: nextStatus,
          reason:
            nextStatus === "archived"
              ? "人工归档"
              : nextStatus === "inactive"
                ? "人工确认停用"
                : "人工恢复在用",
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
      setProductMessage(
        nextStatus === "archived"
          ? "已归档"
          : nextStatus === "inactive"
            ? "已确认停用"
            : "已恢复在用",
      );
      await loadSheetData(PRODUCT_MANAGEMENT_SHEET_ID, page, filters, sortByTab[PRODUCT_MANAGEMENT_SHEET_ID] ?? EMPTY_SORT_STATE, pageSize);
      await loadMetas();
    } catch (err) {
      setProductMessage(`产品状态更新失败：${String(err)}`);
    } finally {
      setProductSavingKey("");
    }
  }

  async function saveProductLifecycle(row: Record<string, string>) {
    const rowKey = getProductRowKey(row);
    const key = `${rowKey}|lifecycle`;
    const operatorName = productOperatorName.trim();
    const currentManual = (row.manual_lifecycle_stage || "").trim();
    const draftValue = productLifecycleDrafts[rowKey] ?? currentManual;
    const nextLifecycle = draftValue === "__clear__" ? "" : draftValue.trim();
    if (nextLifecycle === currentManual) {
      setProductMessage("生命周期未变化，无需保存");
      return;
    }
    // 2026-07-14 需求：操作人不再强制填写；留空时以 admin_ui 落库（审计字段保持非空）
    setProductSavingKey(key);
    setProductMessage("");
    try {
      const res = await fetch("/api/feishu-raw-sales/product-management/update-lifecycle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...getProductPayload(row),
          manual_lifecycle_stage: nextLifecycle || null,
          operator_name: operatorName || "admin_ui",
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
      // 2026-07-20 批①：设为清货期走审批制，后端返回 pending_approval
      setProductMessage(data.pending_approval
        ? (data.message || "清货申请已提交，待审批通过后生效")
        : nextLifecycle ? "生命周期人工值已更新" : "生命周期人工值已清除");
      setProductLifecycleDrafts((prev) => {
        const next = { ...prev };
        delete next[rowKey];
        return next;
      });
      await loadSheetData(PRODUCT_MANAGEMENT_SHEET_ID, page, filters, sortByTab[PRODUCT_MANAGEMENT_SHEET_ID] ?? EMPTY_SORT_STATE, pageSize);
      await loadMetas();
    } catch (err) {
      setProductMessage(`生命周期更新失败：${String(err)}`);
    } finally {
      setProductSavingKey("");
    }
  }

  // ── 批量操作（复用单条接口循环；权限沿用单条门禁）──
  const selectedRows = () => (currentSheetData?.rows ?? []).filter((r) => selectedKeys.has(getProductRowKey(r)));
  async function batchRunOnSelected(perRow: (row: Record<string, string>) => Promise<"ok" | "skip" | "fail">, label: string) {
    const rows = selectedRows();
    if (!rows.length) return;
    setBatchBusy(true); setBatchMsg("");
    let ok = 0, skip = 0, fail = 0;
    for (const r of rows) {
      try { const res = await perRow(r); if (res === "ok") ok++; else if (res === "skip") skip++; else fail++; } catch { fail++; }
    }
    setSelectedKeys(new Set());
    await loadSheetData(PRODUCT_MANAGEMENT_SHEET_ID, page, filters, sortByTab[PRODUCT_MANAGEMENT_SHEET_ID] ?? EMPTY_SORT_STATE, pageSize);
    await loadMetas();
    setBatchBusy(false);
    setBatchMsg(`${label}：成功 ${ok}${skip ? ` · 跳过 ${skip}` : ""}${fail ? ` · 失败 ${fail}` : ""}`);
  }
  async function batchAssignOwner(owner: string) {
    await batchRunOnSelected(async (r) => {
      const res = await fetch("/api/feishu-raw-sales/product-management/update-owner", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...getProductPayload(r), owner }) });
      const d = await res.json().catch(() => ({})); return (res.ok && !d.error) ? "ok" : "fail";
    }, `批量认领负责人「${owner}」`);
  }
  async function batchLifecycle(stage: string) {
    const rows = selectedRows();
    const hasCs = rows.some((r) => r["产品类型"] === "CS测品");
    const hasReg = rows.some((r) => r["产品类型"] !== "CS测品");
    if (hasCs && hasReg) { setBatchMsg("CS测品与常规产品生命周期不同，请分开批量调整"); return; }
    await batchRunOnSelected(async (r) => {
      const res = await fetch("/api/feishu-raw-sales/product-management/update-lifecycle", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...getProductPayload(r), manual_lifecycle_stage: stage, operator_name: productOperatorName.trim() || "admin_ui" }) });
      const d = await res.json().catch(() => ({})); return (res.ok && !d.error) ? "ok" : "fail";
    }, `批量调整生命周期「${stage}」`);
  }
  async function batchArchive() {
    const rows = selectedRows();
    const stockOf = (r: Record<string, string>) => Number(String(r["当前库存"] ?? "").replace(/[,\s]/g, "")) || 0;
    const inboundOf = (r: Record<string, string>) => Number(String(r["在途库存"] ?? "").replace(/[,\s]/g, "")) || 0;
    const isUnpub = (r: Record<string, string>) => String(r._walmart_publish_status ?? "").toUpperCase() === "UNPUBLISHED";
    const eligible = rows.filter((r) => isUnpub(r) || (stockOf(r) < 5 && inboundOf(r) === 0));
    const blocked = rows.length - eligible.length;
    if (!eligible.length) { setBatchMsg(`无可归档产品（仅库存<5且无在途可归档；${blocked} 个不符合）`); return; }
    if (!window.confirm(`确认批量归档 ${eligible.length} 个产品？${blocked ? `（另有 ${blocked} 个因库存/在途不符将跳过）` : ""} 历史数据不删除。`)) return;
    const eligibleKeys = new Set(eligible.map(getProductRowKey));
    await batchRunOnSelected(async (r) => {
      if (!eligibleKeys.has(getProductRowKey(r))) return "skip";
      const res = await fetch("/api/feishu-raw-sales/product-management/update-status", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...getProductPayload(r), product_management_status: "archived", reason: "人工归档(批量)" }) });
      const d = await res.json().catch(() => ({})); return (res.ok && !d.error) ? "ok" : "fail";
    }, "批量归档");
  }

  function renderDataCell(row: Record<string, string>, col: string) {
  if (col === "__select__") {
    const k = getProductRowKey(row);
    return (
      <td key="__select__" style={{ ...s.td, textAlign: "center" as const }} onClick={(e) => e.stopPropagation()}>
        <input type="checkbox" checked={selectedKeys.has(k)} onChange={() => setSelectedKeys((prev) => {
          const n = new Set(prev); if (n.has(k)) n.delete(k); else n.add(k); return n;
        })} style={{ cursor: "pointer", width: 15, height: 15, accentColor: "#4f46e5" }} />
      </td>
    );
  }
  if (isItemIdColumn(col)) {
    const idText = displayCellValue(col, row[col]);
    // 2026-07-23 GPT分析链接：运营日志 Tab 的 ItemID 后带跳转按钮（按该行生成时刻的链接版本，改链接不改历史）
    if (isOperationLogTab) {
      const gptKwLink = String(row["_kw_link"] ?? "");
      const gptAdsLink = String(row["_ads_link"] ?? "");
      return (
        <td key={col} style={{ ...s.td, whiteSpace: "nowrap" as const }} title={idText}>
          <ItemIdLink itemId={idText} />
          {gptKwLink && (
            <a href={gptKwLink} target="_blank" rel="noreferrer"
              style={{ marginLeft: "5px", fontSize: "11px", padding: "1px 7px", borderRadius: "9px", background: "#eef2ff", color: "#4f46e5", border: "1px solid #c7d2fe", textDecoration: "none", whiteSpace: "nowrap" as const }}>
              🔍 关键词
            </a>
          )}
          {gptAdsLink && (
            <a href={gptAdsLink} target="_blank" rel="noreferrer"
              style={{ marginLeft: "4px", fontSize: "11px", padding: "1px 7px", borderRadius: "9px", background: "#ecfdf5", color: "#059669", border: "1px solid #a7f3d0", textDecoration: "none", whiteSpace: "nowrap" as const }}>
              📈 广告
            </a>
          )}
        </td>
      );
    }
    return <td key={col} style={s.td} title={idText}><ItemIdLink itemId={idText} /></td>;
  }
    // 运营日志 Tab 分支必须在通用 early return 之前，否则编辑单元格不可达（2026-07-09 A1/A2 修复）
    if (isOperationLogTab) {
      const text = displayCellValue(col, row[col]);
      if (col === "系统运营日志") {
        const REMINDER_PREVIEW_LEN = 60;
        // 红字（核对不一致）排在最前；本版红字与普通文本共用同一条 60 字截断规则，不做特殊保护。
        const red = String(row["_sys_red"] ?? "").trim();
        const full = red && text ? `${red}　${text}` : (red || text);
        const isLong = full.length > REMINDER_PREVIEW_LEN;
        const cut = isLong ? full.slice(0, REMINDER_PREVIEW_LEN) + "…" : full;
        const redShown = cut.slice(0, Math.min(red.length, cut.length));
        const restShown = cut.slice(redShown.length);
        return (
          <td key={col} style={{ ...s.td, maxWidth: "420px", minWidth: "320px", whiteSpace: "normal" as const, wordBreak: "break-word" as const, overflow: "visible" as const, textOverflow: "clip" as const }}>
            {redShown && <span style={{ color: "#dc2626", fontWeight: 700 }}>{redShown}</span>}
            {restShown || (redShown ? "" : "-")}
            {isLong && (
              <button
                style={{ marginLeft: "6px", padding: "1px 8px", fontSize: "11px", color: "#4f46e5", background: "#eef2ff", border: "1px solid #c7d2fe", borderRadius: "4px", cursor: "pointer", whiteSpace: "nowrap" as const }}
                onClick={() => setReminderModal({ title: `系统运营日志 · ${row["MSKU"] || ""} / ${row["Item ID"] || row["ItemID"] || ""} · ${row["日期"] || ""}`, text: full })}
              >
                查看全部
              </button>
            )}
          </td>
        );
      }
      if (col === "运营日志") {
        const wideStyle = { ...s.td, maxWidth: "340px", minWidth: "260px", whiteSpace: "normal" as const, wordBreak: "break-word" as const };
        if (row._editable !== "1") return <td key={col} style={wideStyle} title={text}>{text || "-"}</td>;
        const rid = row._id;
        const saving = opLogSavingId === rid;
        const draft = opLogDrafts[rid] ?? text;
        const taStyle = { width: "100%", minHeight: "48px", padding: "4px 8px", borderRadius: "6px", border: "1px solid #dbe3ef", fontSize: "12px", resize: "vertical", boxSizing: "border-box" } as React.CSSProperties;
        return (
          <td key={col} style={wideStyle}>
            <textarea style={taStyle} value={draft} disabled={saving}
              onChange={(e) => setOpLogDrafts((prev) => ({ ...prev, [rid]: e.target.value }))} />
            <div style={{ marginTop: "4px", display: "flex", gap: "8px", alignItems: "center" }}>
              <button style={s.searchBtn} disabled={saving} onClick={() => saveOperationLog(row)}>{saving ? "保存中…" : "保存"}</button>
              <button
                style={{ padding: "4px 10px", fontSize: "12px", background: "#f1f5f9", color: "#475569", border: "1px solid #dbe3ef", borderRadius: "6px", cursor: "pointer", whiteSpace: "nowrap" as const }}
                disabled={saving}
                onClick={() => { setOpLogDrafts((prev) => ({ ...prev, [rid]: "今日无运营" })); saveOperationLog(row, "今日无运营"); }}
              >今日无运营</button>
              {opLogMsg.id === rid && opLogMsg.msg && (
                <span style={{ fontSize: "11px", color: opLogMsg.msg.startsWith("保存失败") ? "#dc2626" : "#16a34a" }}>{opLogMsg.msg}</span>
              )}
            </div>
          </td>
        );
      }
      return <td key={col} style={s.td} title={text}>{text}</td>;
    }
    if (isCsTestTab && col === "预警原因") {
      const editable = row._cs_alert_editable === "1";
      const cellText = displayCellValue(col, row[col]);
      if (!editable) return <td key={col} style={s.td} title="该产品当前无预警">{cellText || "—"}</td>;
      const rid = row._cs_alert_id;
      const saving = csReasonSavingId === rid;
      const draft = csReasonDrafts[rid] ?? (row["预警原因"] ?? "");
      const taStyle = { width: "100%", minHeight: "48px", padding: "4px 8px", borderRadius: "6px", border: "1px solid #dbe3ef", fontSize: "12px", resize: "vertical", boxSizing: "border-box" } as React.CSSProperties;
      return (
        <td key={col} style={{ ...s.td, maxWidth: "320px", minWidth: "240px", whiteSpace: "normal" as const, wordBreak: "break-word" as const }}>
          <textarea style={taStyle} value={draft} disabled={saving} placeholder="填写预警原因（≥15字），保存即消警"
            onChange={(e) => setCsReasonDrafts((prev) => ({ ...prev, [rid]: e.target.value }))} />
          <div style={{ marginTop: "4px", display: "flex", gap: "8px", alignItems: "center" }}>
            <button style={s.searchBtn} disabled={saving} onClick={() => saveCsAlertReason(row)}>{saving ? "保存中…" : "保存"}</button>
            {csReasonMsg.id === rid && csReasonMsg.msg && (
              <span style={{ fontSize: "11px", color: (csReasonMsg.msg.startsWith("保存失败") || csReasonMsg.msg.includes("需不少于")) ? "#dc2626" : "#16a34a" }}>{csReasonMsg.msg}</span>
            )}
          </div>
        </td>
      );
    }
    if (!isProductManagementTab) {
      const text = displayCellValue(col, row[col]);
      return <td key={col} style={s.td} title={text}>{text}</td>;
    }

    const rowKey = getProductRowKey(row);
    if (col === "负责人") {
      const currentOwner = row[col] || "";
      const saving = productSavingKey === `${rowKey}|owner`;
      return (
        <td key={col} style={s.td} title={currentOwner}>
          <select
            style={s.inlineSelect}
            value={currentOwner}
            disabled={saving}
            onChange={(e) => saveProductOwner(row, e.target.value)}
          >
            <option value="">未分配</option>
            {[currentOwner, ...ownerOptions]
              .filter((v) => v && v.trim())
              .filter((v, i, arr) => arr.indexOf(v) === i)
              .map((owner) => (
                <option key={owner} value={owner}>{owner}</option>
              ))}
          </select>
        </td>
      );
    }

    if (col === "WFS配送费（$）") {
      const saving = productSavingKey === `${rowKey}|fee`;
      const value = productFeeDrafts[rowKey] ?? row[col] ?? "";
      const isCsProduct = String(row["MSKU"] ?? "").startsWith("CS");
      return (
        <td key={col} style={s.td} title={row[col] ?? ""}>
          <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <input
              style={s.inlineInput}
              type="number"
              step="0.01"
              value={value}
              disabled={saving || isCsProduct}
              onChange={(e) => setProductFeeDrafts((prev) => ({ ...prev, [rowKey]: e.target.value }))}
            />
            <button
              style={{ ...s.miniBtn, cursor: saving ? "not-allowed" : "pointer", opacity: saving ? 0.6 : 1 }}
              disabled={saving}
              onClick={() => saveProductWfsFee(row)}
            >
              保存
            </button>
            {row["wfs_fee_auto"] && (
              <span
                style={{ fontSize: "11px", color: "#166534", background: "#dcfce7", borderRadius: "4px", padding: "1px 6px", whiteSpace: "nowrap" }}
                title="结算口径自动费率（每月25日刷新），利润计算以此为准；输入框为人工兜底值"
              >
                生效{row["wfs_fee_auto"]}（自动）
              </span>
            )}
          </span>
        </td>
      );
    }

    // 2026-07-23 GPT分析链接：原"操作"空列改名"GPT分析"（对齐样板图），渲染 🔍/📈 图标（已配置亮色/未配置灰色，点击弹窗编辑）
    if (col === "GPT分析") {
      const gptKwCur = String(row["gpt_link_keyword"] ?? "");
      const gptAdsCur = String(row["gpt_link_ads"] ?? "");
      const gptItemId = row._item_id || row["ItemID"] || "";
      const openGptModal = () => {
        setGptLinkMsg("");
        setGptLinkModal({ itemId: gptItemId, msku: String(row["MSKU"] ?? ""), kw: gptKwCur, ads: gptAdsCur, kwOrig: gptKwCur, adsOrig: gptAdsCur });
      };
      return (
        <td key={col} style={s.td}>
          <span style={{ display: "inline-flex", gap: "4px" }}>
            <button title={gptKwCur ? "关键词分析：已配置，点击修改" : "关键词分析：未配置，点击填写"} onClick={openGptModal}
              style={{ width: "26px", height: "22px", borderRadius: "5px", cursor: "pointer", fontSize: "12px", lineHeight: 1, border: gptKwCur ? "1px solid #6366f1" : "1px solid #d1d5db", background: gptKwCur ? "#eef2ff" : "#fff", opacity: gptKwCur ? 1 : 0.45 }}>🔍</button>
            <button title={gptAdsCur ? "广告分析：已配置，点击修改" : "广告分析：未配置，点击填写"} onClick={openGptModal}
              style={{ width: "26px", height: "22px", borderRadius: "5px", cursor: "pointer", fontSize: "12px", lineHeight: 1, border: gptAdsCur ? "1px solid #10b981" : "1px solid #d1d5db", background: gptAdsCur ? "#ecfdf5" : "#fff", opacity: gptAdsCur ? 1 : 0.45 }}>📈</button>
          </span>
        </td>
      );
    }

    if (col === "产品状态") {
      const statusLabel = row["产品状态"] || "在用";
      return (
        <td key={col} style={s.td} title={row.product_management_status_reason || ""}>
          {statusLabel}
        </td>
      );
    }

    if (col === "系统生命周期") {
      const manual = (row.manual_lifecycle_stage || "").trim();
      const system = (row.system_lifecycle_stage || row[col] || "").trim();
      const text = system || "-";
      const highlight = row.lifecycle_highlight || "none";
      const isDifferent = Boolean(manual && manual !== system);
      const highlightColor = highlight === "red" ? "#b91c1c" : highlight === "blue" ? "#1d4ed8" : undefined;
      const highlightTitle = highlight === "red"
        ? (row.manual_lifecycle_system_snapshot ? "系统判断已变化，请人工复核" : "历史人工值无系统基线，建议重新确认")
        : highlight === "blue"
          ? "人工主动覆盖系统，系统还未变化"
          : text;
      return (
        <td
          key={col}
          style={{ ...s.td, color: highlightColor, fontWeight: isDifferent ? 700 : undefined }}
          title={isDifferent ? `${highlightTitle} / 人工生命周期：${manual}` : text}
        >
          {text}
        </td>
      );
    }

    if (col === "人工生命周期") {
      const saving = productSavingKey === `${rowKey}|lifecycle`;
      const currentManual = (row.manual_lifecycle_stage || "").trim();
      const system = (row.system_lifecycle_stage || "").trim();
      const displayValue = row.manual_lifecycle_display || currentManual || system || "-";
      const value = productLifecycleDrafts[rowKey] ?? (currentManual || system);
      const nextLifecycle = value === "__clear__" ? "" : value.trim();
      const changed = nextLifecycle !== currentManual;
      const lifecycleOptions = row["产品类型"] === "CS测品" ? CS_LIFECYCLE_OPTIONS : REGULAR_LIFECYCLE_OPTIONS;
      const titleParts = [
        currentManual ? `人工生命周期：${currentManual}` : `未设置人工生命周期，默认显示系统值：${system || "-"}`,
        row.manual_lifecycle_system_snapshot ? `确认时系统值：${row.manual_lifecycle_system_snapshot}` : "",
        row.manual_lifecycle_by ? `操作人：${row.manual_lifecycle_by}` : "",
        row.manual_lifecycle_at ? `时间：${row.manual_lifecycle_at}` : "",
      ].filter(Boolean);
      return (
        <td key={col} style={s.td} title={titleParts.join(" / ")}>
          <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <select
              style={s.inlineSelect}
              value={value || "__clear__"}
              disabled={saving}
              onChange={(e) => setProductLifecycleDrafts((prev) => ({ ...prev, [rowKey]: e.target.value }))}
            >
              <option value="__clear__">清除人工值</option>
              {lifecycleOptions.map((stage) => (
                <option key={stage} value={stage}>{stage}</option>
              ))}
            </select>
            <button
              style={{ ...s.miniBtn, cursor: saving || !changed ? "not-allowed" : "pointer", opacity: saving || !changed ? 0.6 : 1 }}
              disabled={saving || !changed}
              onClick={() => saveProductLifecycle(row)}
            >
              保存
            </button>
            <span style={{ color: currentManual && currentManual !== system ? "#1d4ed8" : undefined, fontWeight: currentManual && currentManual !== system ? 700 : undefined }}>
              {displayValue}
            </span>
            {String(row.clearance_pending) === "true" && (
              <span style={{ background: "#fef3c7", color: "#92400e", fontSize: "11px", padding: "1px 6px", borderRadius: "8px", whiteSpace: "nowrap" }}>
                清货审批中
              </span>
            )}
          </span>
        </td>
      );
    }

    if (col === "操作") {
      const isArchived = row.product_management_status === "archived";
      const isInactiveCandidate = row.product_management_status === "inactive_candidate";
      const isInactive = row.product_management_status === "inactive";
      const saving = productSavingKey === `${rowKey}|status`;
      return (
        <td key={col} style={s.td}>
          <span style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
            {isInactiveCandidate && (
              <button
                style={{ ...s.miniBtn, cursor: saving ? "not-allowed" : "pointer", opacity: saving ? 0.6 : 1 }}
                disabled={saving}
                onClick={() => saveProductStatus(row, "inactive")}
              >
                确认停用
              </button>
            )}
            {(isInactiveCandidate || isInactive) && (
              <button
                style={{ ...s.miniBtn, cursor: saving ? "not-allowed" : "pointer", opacity: saving ? 0.6 : 1 }}
                disabled={saving}
                onClick={() => saveProductStatus(row, "active")}
              >
                恢复在用
              </button>
            )}
            <button
              style={{ ...s.miniBtn, cursor: saving ? "not-allowed" : "pointer", opacity: saving ? 0.6 : 1 }}
              disabled={saving}
              onClick={() => saveProductStatus(row, isArchived ? "active" : "archived")}
            >
              {isArchived ? "取消归档" : "归档"}
            </button>
          </span>
        </td>
      );
    }

    const text = displayCellValue(col, row[col]);
    return <td key={col} style={s.td} title={text}>{text}</td>;
  }

  const currentSheetData = sheetData?.sheet_id === activeTab ? sheetData : null;
  const actualColumns = currentSheetData?.columns?.length
    ? currentSheetData.columns
    : activeTab === CS_TEST_SHEET_ID
      ? CS_TEST_COLUMNS
      : activeTab === PRODUCT_MANAGEMENT_SHEET_ID
        ? PRODUCT_MANAGEMENT_COLUMNS
      : [];
  const storedOrder = columnOrderByTab[activeTab] ?? [];
  const reconciledStoredOrder = activeTab === PRODUCT_MANAGEMENT_SHEET_ID
    ? reconcileProductManagementColumns(storedOrder)
    : storedOrder;
  const orderedColumns = glueSysLogBeforeOpsLog(glueGptAfterItemId([
    ...reconciledStoredOrder.filter((col) => actualColumns.includes(col)),
    ...actualColumns.filter((col) => !reconciledStoredOrder.includes(col)),
  ]));
  const storedVisible = reconcileVisibleColumns(activeTab, visibleColumnsByTab[activeTab], actualColumns);
  const visibleColumns = orderedColumns.filter((col) => storedVisible
    ? storedVisible.includes(col)
    : !(activeTab === PRODUCT_MANAGEMENT_SHEET_ID && (col === "产品名称" || col === "利润等级")));

  useEffect(() => {
    if (activeTab === "__tasks__" || activeTab === "__clearance__" || activeTab === "__pmc__" || actualColumns.length === 0) return;
    setColumnOrderByTab((prev) => {
      const oldOrder = prev[activeTab] ?? [];
      const reconciledOldOrder = activeTab === PRODUCT_MANAGEMENT_SHEET_ID
        ? reconcileProductManagementColumns(oldOrder)
        : oldOrder;
      const nextOrder = [
        ...reconciledOldOrder.filter((col) => actualColumns.includes(col)),
        ...actualColumns.filter((col) => !reconciledOldOrder.includes(col)),
      ];
      if (nextOrder.join("\u0001") === oldOrder.join("\u0001")) return prev;
      return { ...prev, [activeTab]: nextOrder };
    });
    setVisibleColumnsByTab((prev) => {
      const oldVisible = prev[activeTab];
      const reconciledVisible = reconcileVisibleColumns(activeTab, oldVisible, actualColumns);
      if (reconciledVisible) {
        if (reconciledVisible.join("\u0001") === oldVisible?.join("\u0001")) return prev;
        return { ...prev, [activeTab]: reconciledVisible };
      }
      return { ...prev, [activeTab]: actualColumns };
    });
  }, [activeTab, actualColumns.join("\u0001")]);

  // 固定列（左冻结，2026-07-17 领星式）：固定列归组在前；nth-child CSS 生成 sticky 偏移
  const activePinnedCols = (pinnedColumnsByTab[activeTab] ?? DEFAULT_PINNED_BY_TAB[activeTab] ?? []).filter((c) => visibleColumns.includes(c));
  const baseRenderCols = activePinnedCols.length
    ? [...visibleColumns.filter((c) => activePinnedCols.includes(c)), ...visibleColumns.filter((c) => !activePinnedCols.includes(c))]
    : visibleColumns;
  const renderCols = activeTab === PRODUCT_MANAGEMENT_SHEET_ID ? ["__select__", ...baseRenderCols] : baseRenderCols;
  const pinColWidth = (col: string) => col === "__select__" ? 40 : (colWidths[activeTab]?.[col] ?? PIN_WIDTH_PRESETS[col] ?? DEFAULT_PIN_COL_WIDTH);
  // 逐格内联 sticky（与广告库查看器同方案，2026-07-17 替换 nth-child CSS 根治表头错位）
  const pinnedSet = new Set(activePinnedCols);
  if (activeTab === PRODUCT_MANAGEMENT_SHEET_ID) pinnedSet.add("__select__");
  const pinLeftMap: Record<string, number> = {};
  {
    let leftAcc = 0;
    for (const col of renderCols) {
      if (pinnedSet.has(col)) { pinLeftMap[col] = leftAcc; leftAcc += pinColWidth(col); }
    }
  }
  const pinnedCellStyle = (col: string, isHeader: boolean): React.CSSProperties => (
    pinnedSet.has(col)
      ? { position: "sticky", left: pinLeftMap[col], zIndex: isHeader ? 5 : 2,
          background: isHeader ? "#f8fafc" : "#fff",
          boxShadow: "2px 0 4px -2px rgba(0,0,0,0.12)" }
      : {}
  );
  const withPinned = (el: React.ReactElement | null, col: string, isHeader: boolean) => {
    if (!el || !pinnedSet.has(col)) return el;
    const prevStyle = (el.props as { style?: React.CSSProperties }).style ?? {};
    return cloneElement(el, { style: { ...prevStyle, ...pinnedCellStyle(col, isHeader) } } as never);
  };

  // 是否有任何筛选条件被应用
  const hasActiveFilters = Object.values(filters).some((v) => v !== "");

  const totalPages = currentSheetData?.total ? Math.ceil(currentSheetData.total / pageSize) : 1;
  const currentMeta = sheetMetas.find((m) => m.sheet_id === activeTab);
  const isOrderProfitTab = activeTab === ORDER_PROFIT_SHEET_ID;
  const isCsTestTab = activeTab === CS_TEST_SHEET_ID;
  const isProductManagementTab = activeTab === PRODUCT_MANAGEMENT_SHEET_ID;
  const isOperationLogTab = activeTab === OPERATION_LOG_SHEET_ID;

  // ── 筛选区 UI ─────────────────────────────────────────────────────────────────

  // ── 列配置（领星式：拖拽排序/置顶/固定≤7左冻结/删除，2026-07-17） ──────────────
  function applyColumnConfig() {
    const ordered = glueSysLogBeforeOpsLog(glueGptAfterItemId([
      ...cfgSelected.filter((c) => cfgPins.includes(c)),
      ...cfgSelected.filter((c) => !cfgPins.includes(c)),
    ]));
    setColumnOrderByTab((prev) => ({
      ...prev,
      [activeTab]: [...ordered, ...actualColumns.filter((c) => !ordered.includes(c))],
    }));
    setVisibleColumnsByTab((prev) => ({ ...prev, [activeTab]: ordered }));
    setPinnedColumnsByTab((prev) => ({ ...prev, [activeTab]: cfgPins.filter((c) => ordered.includes(c)) }));
    setShowColumnConfig(false);
  }

  const cfgOrderedSelected = glueSysLogBeforeOpsLog(glueGptAfterItemId([
    ...cfgSelected.filter((c) => cfgPins.includes(c)),
    ...cfgSelected.filter((c) => !cfgPins.includes(c)),
  ]));

  const searchFieldOptions = SEARCH_FIELD_OPTIONS.filter((o) => !(isOperationLogTab && o.value === "sku"));

  // 更多筛选浮层：各Tab低频筛选（原第2~4行控件平移，状态与后端参数不变）
  const moreFiltersPanel = (
    <div style={{ position: "absolute", top: "110%", left: 0, zIndex: 50, background: "#fff",
      border: "1px solid #e5e7eb", borderRadius: "10px", boxShadow: "0 8px 24px rgba(0,0,0,0.14)",
      padding: "12px 14px", minWidth: "460px" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 14px" }}>
        {isOperationLogTab && (
          <>
            <div><span style={s.filterLabel}>利润等级</span>
              <select style={{ ...s.filterSelect, width: "100%" }} value={inpProfitLevel} onChange={(e) => setInpProfitLevel(e.target.value)}>
                <option value="">全部利润等级</option>
                {profitLevelOptions.map((lv) => <option key={lv} value={lv}>{lv}</option>)}
              </select></div>
            <div><span style={s.filterLabel}>运营日志</span>
              <select style={{ ...s.filterSelect, width: "100%" }} value={inpLogFilled} onChange={(e) => setInpLogFilled(e.target.value)}>
                <option value="">全部</option><option value="1">已填写</option><option value="0">未填写</option>
              </select></div>
            <div><span style={s.filterLabel}>WFS库存</span>
              <select style={{ ...s.filterSelect, width: "100%" }} value={inpWfsStock} onChange={(e) => setInpWfsStock(e.target.value)}>
                <option value="">全部</option><option value="has">有库存</option><option value="none">无库存</option>
              </select></div>
            <div><span style={s.filterLabel}>产品类型</span>
              <select style={{ ...s.filterSelect, width: "100%" }} value={inpProductStage} onChange={(e) => setInpProductStage(e.target.value)}>
                <option value="">全部类型</option><option value="常规产品">常规产品</option><option value="CS测品">CS测品</option>
              </select></div>
            <div><span style={s.filterLabel}>广告占比(近30天)最小 (%)</span>
              <input style={{ ...s.filterInput, width: "100%" }} value={inpAdMin} onChange={(e) => setInpAdMin(e.target.value)} onKeyDown={handleKeyDown} placeholder="如 5" /></div>
            <div><span style={s.filterLabel}>广告占比(近30天)最大 (%)</span>
              <input style={{ ...s.filterInput, width: "100%" }} value={inpAdMax} onChange={(e) => setInpAdMax(e.target.value)} onKeyDown={handleKeyDown} placeholder="如 30" /></div>
          </>
        )}
        {(isOrderProfitTab || isCsTestTab) && (
          <>
            <div><span style={s.filterLabel}>库存状态</span>
              <select style={{ ...s.filterSelect, width: "100%" }} value={inpStockStatus} onChange={(e) => setInpStockStatus(e.target.value)}>
                <option value="">全部库存</option><option value="有库存">有库存</option><option value="无库存">无库存</option>
              </select></div>
            <div><span style={s.filterLabel}>{isCsTestTab ? "数据状态" : "成本状态"}</span>
              <select style={{ ...s.filterSelect, width: "100%" }} value={inpCostStatus} onChange={(e) => setInpCostStatus(e.target.value)}>
                <option value="">{isCsTestTab ? "全部数据状态" : "全部成本状态"}</option>
                {(isCsTestTab ? CS_DATA_STATUS_OPTIONS : COST_STATUS_OPTIONS).map((status) => (
                  <option key={status} value={status}>{status}</option>
                ))}
              </select></div>
          </>
        )}
        {isOrderProfitTab && (
          <div><span style={s.filterLabel}>产品阶段</span>
            <select style={{ ...s.filterSelect, width: "100%" }} value={inpProductStage} onChange={(e) => setInpProductStage(e.target.value)}>
              <option value="">全部阶段</option>
              {PRODUCT_STAGE_OPTIONS.map((stage) => <option key={stage} value={stage}>{stage}</option>)}
            </select></div>
        )}
        {(activeTab === "<REDACTED_FEISHU_SHEET_ID>" || isOrderProfitTab) && (
          <>
            <div><span style={s.filterLabel}>毛利率最小值 (%)</span>
              <input style={{ ...s.filterInput, width: "100%" }} type="number" placeholder="如 10" value={inpGrossMin}
                onChange={(e) => setInpGrossMin(e.target.value)} onKeyDown={handleKeyDown} /></div>
            <div><span style={s.filterLabel}>毛利率最大值 (%)</span>
              <input style={{ ...s.filterInput, width: "100%" }} type="number" placeholder="如 30" value={inpGrossMax}
                onChange={(e) => setInpGrossMax(e.target.value)} onKeyDown={handleKeyDown} /></div>
          </>
        )}
        {(activeTab === "<REDACTED_FEISHU_SHEET_ID>" || isOrderProfitTab || isCsTestTab) && (
          <>
            <div><span style={s.filterLabel}>广告占比最小值 (%)</span>
              <input style={{ ...s.filterInput, width: "100%" }} type="number" placeholder="如 5" value={inpAdMin}
                onChange={(e) => setInpAdMin(e.target.value)} onKeyDown={handleKeyDown} /></div>
            <div><span style={s.filterLabel}>广告占比最大值 (%)</span>
              <input style={{ ...s.filterInput, width: "100%" }} type="number" placeholder="如 30" value={inpAdMax}
                onChange={(e) => setInpAdMax(e.target.value)} onKeyDown={handleKeyDown} /></div>
          </>
        )}
        {isCsTestTab && (
          <>
            <div><span style={s.filterLabel}>累计广告费最小值 ($)</span>
              <input style={{ ...s.filterInput, width: "100%" }} type="number" placeholder="如 100" value={inpAdSpendMin}
                onChange={(e) => setInpAdSpendMin(e.target.value)} onKeyDown={handleKeyDown} /></div>
            <div><span style={s.filterLabel}>累计广告费最大值 ($)</span>
              <input style={{ ...s.filterInput, width: "100%" }} type="number" placeholder="如 500" value={inpAdSpendMax}
                onChange={(e) => setInpAdSpendMax(e.target.value)} onKeyDown={handleKeyDown} /></div>
            <div><span style={s.filterLabel}>广告点击最小值</span>
              <input style={{ ...s.filterInput, width: "100%" }} type="number" placeholder="如 50" value={inpClicksMin}
                onChange={(e) => setInpClicksMin(e.target.value)} onKeyDown={handleKeyDown} /></div>
            <div><span style={s.filterLabel}>广告点击最大值</span>
              <input style={{ ...s.filterInput, width: "100%" }} type="number" placeholder="如 500" value={inpClicksMax}
                onChange={(e) => setInpClicksMax(e.target.value)} onKeyDown={handleKeyDown} /></div>
            <div><span style={s.filterLabel}>测品天数最小值 (天)</span>
              <input style={{ ...s.filterInput, width: "100%" }} type="number" placeholder="如 7" value={inpTestDaysMin}
                onChange={(e) => setInpTestDaysMin(e.target.value)} onKeyDown={handleKeyDown} /></div>
            <div><span style={s.filterLabel}>测品天数最大值 (天)</span>
              <input style={{ ...s.filterInput, width: "100%" }} type="number" placeholder="如 60" value={inpTestDaysMax}
                onChange={(e) => setInpTestDaysMax(e.target.value)} onKeyDown={handleKeyDown} /></div>
          </>
        )}
        {isProductManagementTab && (
          <>
            <div><span style={s.filterLabel}>产品类型</span>
              <select style={{ ...s.filterSelect, width: "100%" }} value={inpProductStage} onChange={(e) => setInpProductStage(e.target.value)}>
                <option value="">全部类型</option><option value="常规产品">常规产品</option><option value="CS测品">CS测品</option>
              </select></div>
            <div><span style={s.filterLabel}>WFS配送费状态</span>
              <select style={{ ...s.filterSelect, width: "100%" }} value={inpWfsFeeStatus} onChange={(e) => setInpWfsFeeStatus(e.target.value)}>
                {WFS_FEE_STATUS_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
              </select></div>
            <div><span style={s.filterLabel}>成本状态</span>
              <select style={{ ...s.filterSelect, width: "100%" }} value={inpPmCostStatus} onChange={(e) => setInpPmCostStatus(e.target.value)}>
                <option value="">全部成本状态</option>
                <option value="missing_purchase">缺产品成本</option>
                <option value="missing_first_mile">缺头程运费</option>
              </select></div>
            <div><span style={s.filterLabel}>产品状态</span>
              <select style={{ ...s.filterSelect, width: "100%" }} value={inpProductStatus} onChange={(e) => setInpProductStatus(e.target.value)}>
                {PRODUCT_STATUS_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
              </select></div>
            <div><span style={s.filterLabel}>人工生命周期</span>
              <select style={{ ...s.filterSelect, width: "100%" }} value={inpManualLifecycle} onChange={(e) => setInpManualLifecycle(e.target.value)}>
                {MANUAL_LIFECYCLE_FILTER_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
              </select></div>
            <div><span style={s.filterLabel}>利润等级</span>
              <select style={{ ...s.filterSelect, width: "100%" }} value={inpProfitLevel} onChange={(e) => setInpProfitLevel(e.target.value)}>
                <option value="">全部利润等级</option>
                {profitLevelOptions.map((lv) => <option key={lv} value={lv}>{lv}</option>)}
              </select></div>
            <div><span style={s.filterLabel}>GPT分析</span>
              <select style={{ ...s.filterSelect, width: "100%" }} value={inpGptLink} onChange={(e) => setInpGptLink(e.target.value)}>
                <option value="">全部</option>
                <option value="missing_keyword">缺关键词分析链接</option>
                <option value="missing_ads">缺广告分析链接</option>
              </select></div>
          </>
        )}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "12px" }}>
        <button style={s.resetBtn} onClick={() => setShowMoreFilters(false)}>取消</button>
        <button style={s.searchBtn} onClick={() => { setShowMoreFilters(false); handleSearch(); }}>搜索</button>
      </div>
    </div>
  );

  // ── 筛选区（2026-07-17 领星式单行压缩：合并搜索框+扁平筛选+更多筛选浮层+元信息右置） ──
  const filterPanel = (
    <div style={{ ...s.filterWrap, position: "relative", padding: "8px 12px" }}>
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ display: "inline-flex" }}>
          <select style={{ ...s.filterSelect, width: "92px", borderRadius: "6px 0 0 6px" }}
            value={searchField} onChange={(e) => setSearchField(e.target.value)}>
            {searchFieldOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <input style={{ ...s.filterInput, width: "160px", borderRadius: "0 6px 6px 0", borderLeft: "none" }}
            placeholder="搜索内容…" value={searchText}
            onChange={(e) => setSearchText(e.target.value)} onKeyDown={handleKeyDown} />
        </span>
        {/* 2026-07-17 领星式多选（全选/搜索/仅筛选此项/取消确定） */}
        <LxMultiSelect placeholder="全部店铺" minWidth={150}
          options={storeOptions.map((st) => ({ value: st, label: st }))}
          selected={inpStore} onChange={setInpStore} />
        <LxMultiSelect placeholder="全部负责人" minWidth={120}
          options={[
            ...(isProductManagementTab ? [{ value: MISSING_OWNER_SENTINEL, label: "缺负责人" }] : []),
            ...ownerOptions.map((owner) => ({ value: owner, label: owner })),
          ]}
          selected={inpOwner} onChange={setInpOwner} />
        {!isProductManagementTab && !isCsTestTab && (
          <DateRangePicker
            start={inpDateStart}
            end={inpDateEnd}
            quickOptions={isOperationLogTab ? OPERATION_LOG_DATE_QUICK_OPTIONS : DATE_QUICK_OPTIONS}
            activeQuick={activeQuick}
            onQuick={handleQuickDate}
            onRange={applyDateRange}
          />
        )}
        <span style={{ position: "relative" }}>
          <button style={{ ...s.resetBtn, color: showMoreFilters ? "#4f46e5" : "#6b7280", borderColor: showMoreFilters ? "#c7d2fe" : "#e5e7eb" }}
            onClick={() => setShowMoreFilters((v) => !v)}>
            更多筛选 {showMoreFilters ? "▴" : "▾"}
          </button>
          {showMoreFilters && moreFiltersPanel}
        </span>
        <button style={s.searchBtn} onClick={() => { setShowMoreFilters(false); handleSearch(); }}>搜索</button>
        <button style={s.resetBtn} onClick={handleReset}>重置</button>

        {hasActiveFilters && <span style={{ fontSize: "12px", color: "#6366f1", fontWeight: 600 }}>●筛选生效</span>}
        {isProductManagementTab && productMessage && (
          <span style={{ fontSize: "12px", color: productMessage.includes("失败") ? "#dc2626" : "#16a34a", fontWeight: 600 }}>
            {productMessage}
          </span>
        )}
        <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", whiteSpace: "nowrap", flexShrink: 0 }}>
        <span style={{ fontSize: "12px", color: "#6b7280", whiteSpace: "nowrap" }}>
          共 <b style={{ color: "#374151" }}>{currentSheetData?.total ?? currentMeta?.total ?? "-"}</b> 行
          {" · 同步 "}{currentSheetData?.latest_sync_time ? new Date(currentSheetData.latest_sync_time).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "-"}
          {" · 第 "}<b style={{ color: "#374151" }}>{page}</b>/{totalPages} 页
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: "2px", marginLeft: "10px", flexShrink: 0 }}>
          <button style={ICON_BTN} title="刷新"
            onClick={() => loadSheetData(activeTab, page, filters, currentSort, pageSize)}><IconRefresh /></button>
          <button style={ICON_BTN} title="帮助：本页规则与数据口径"
            onClick={() => window.open(`#/help?page=${PAGE_HELP_KEYS[activeTab] ?? ""}`, "_blank")}><IconHelp /></button>
          <span style={{ width: "1px", height: "16px", background: "#e5e7eb", margin: "0 5px" }} />
          <button style={{ ...ICON_BTN, opacity: exporting ? 0.4 : 1 }} disabled={exporting} title="下载（需密码）"
            onClick={handleExport}><IconDownload /></button>
          <button style={ICON_BTN} title="列配置"
            onClick={() => setShowColumnConfig(true)}><IconColumns /></button>
          <button style={{ background: "none", border: "none", cursor: "pointer", padding: "5px 8px", borderRadius: "6px", color: "#6b7280", fontSize: "12px", whiteSpace: "nowrap" }}
            title="拖列头右边缘可调整列宽；点此恢复默认列宽"
            onClick={() => setColWidths((prev) => ({ ...prev, [activeTab]: {} }))}>列宽重置</button>
        </span>
        </span>
      </div>
      
      {showColumnConfig && activeTab !== "__tasks__" && activeTab !== "__clearance__" && activeTab !== "__pmc__" && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.4)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => setShowColumnConfig(false)}>
          <div style={{ background: "#fff", borderRadius: "12px", width: "680px", maxHeight: "78vh", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 8px 32px rgba(0,0,0,0.18)" }}
            onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid #e5e7eb", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "14px", fontWeight: 700, color: "#374151" }}>列配置</span>
              <button onClick={() => setShowColumnConfig(false)} style={{ border: "none", background: "none", fontSize: "18px", cursor: "pointer", color: "#9ca3af" }}>×</button>
            </div>
            <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
              <div style={{ flex: 1, padding: "10px 14px", overflowY: "auto" }}>
                {orderedColumns.map((col) => (
                  <label key={col} style={{ display: "flex", alignItems: "center", gap: "6px", padding: "4px 0", cursor: "pointer", fontSize: "13px" }}>
                    <input type="checkbox" checked={cfgSelected.includes(col)}
                      onChange={() => {
                        const pair = opsLogPair(col);
                        setCfgSelected((prev) => prev.includes(col)
                          ? prev.filter((c) => !pair.includes(c))
                          : [...prev.filter((c) => !pair.includes(c)), ...pair]);
                        setCfgPins((prev) => prev.filter((c) => !pair.includes(c)));
                      }} />
                    <span style={{ color: "#374151" }}>{col}</span>
                  </label>
                ))}
              </div>
              <div style={{ width: "230px", borderLeft: "1px solid #e5e7eb", padding: "10px 10px", overflowY: "auto", background: "#f8fafc" }}>
                <div style={{ fontSize: "12px", color: "#64748b", marginBottom: "2px" }}>已选 {cfgSelected.length} 列 · 拖动调顺序</div>
                <div style={{ fontSize: "11px", color: "#94a3b8", marginBottom: "6px" }}>📌最多固定{MAX_PINNED_COLUMNS}项（表格左侧冻结）</div>
                {cfgOrderedSelected.map((col, idx) => {
                  const isPin = cfgPins.includes(col);
                  return (
                    <div key={col} draggable
                      onDragStart={() => { dragColIdxRef.current = idx; }}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => {
                        const from = dragColIdxRef.current;
                        dragColIdxRef.current = null;
                        if (from === null || from === idx) return;
                        const view = [...cfgOrderedSelected];
                        const movedCol = view[from];
                        const targetCol = view[idx];
                        const pair = opsLogPair(movedCol).filter((c) => view.includes(c));
                        if (pair.length === 1) {
                          const [moved] = view.splice(from, 1);
                          view.splice(idx, 0, moved);
                          setCfgSelected(glueSysLogBeforeOpsLog(glueGptAfterItemId(view)));
                          return;
                        }
                        if (pair.includes(targetCol)) return;
                        const rest = view.filter((c) => !pair.includes(c));
                        let pos = rest.indexOf(targetCol);
                        if (pos < 0) pos = rest.length;
                        if (from < idx) pos += 1;
                        setCfgSelected(glueSysLogBeforeOpsLog(glueGptAfterItemId(
                          [...rest.slice(0, pos), ...pair, ...rest.slice(pos)])));
                      }}
                      style={{ display: "flex", alignItems: "center", gap: "4px", padding: "4px 2px", fontSize: "12px",
                        borderRadius: "4px", cursor: "grab", background: isPin ? "#eef2ff" : "transparent", borderBottom: "1px solid #f1f5f9" }}>
                      <span style={{ color: "#cbd5e1", fontSize: "13px", lineHeight: 1 }} title="拖动排序">⠿</span>
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {isPin && <span style={{ fontSize: "10px" }}>📌</span>}{col}
                      </span>
                      <span onClick={() => setCfgSelected((prev) => {
                          const pair = opsLogPair(col).filter((c) => prev.includes(c));
                          return glueSysLogBeforeOpsLog(glueGptAfterItemId([...pair, ...prev.filter((c) => !pair.includes(c))]));
                        })} title="置顶"
                        style={{ color: "#64748b", cursor: "pointer", fontSize: "12px" }}>⬆</span>
                      <span onClick={() => setCfgPins((prev) => {
                          const pairMap: Record<string, string[]> = { "ItemID": ["ItemID", "GPT分析"], "GPT分析": ["ItemID", "GPT分析"], "系统生命周期": ["系统生命周期", "人工生命周期"], "人工生命周期": ["系统生命周期", "人工生命周期"], "系统运营日志": ["系统运营日志", "运营日志"], "运营日志": ["系统运营日志", "运营日志"] };
                          const pair = (pairMap[col] ?? [col]).filter((c) => cfgSelected.includes(c));
                          if (prev.includes(col)) return prev.filter((c) => !pair.includes(c));
                          const toAdd = pair.filter((c) => !prev.includes(c));
                          if (prev.length + toAdd.length > MAX_PINNED_COLUMNS) { alert(`最多可固定${MAX_PINNED_COLUMNS}项`); return prev; }
                          return [...prev, ...toAdd];
                        })} title={isPin ? "取消固定" : "固定（左侧冻结）"}
                        style={{ color: isPin ? "#2563eb" : "#94a3b8", cursor: "pointer", fontSize: "12px" }}>📌</span>
                      <span onClick={() => {
                          const pair = opsLogPair(col);
                          setCfgSelected((prev) => prev.filter((c) => !pair.includes(c)));
                          setCfgPins((prev) => prev.filter((c) => !pair.includes(c)));
                        }} title="删除"
                        style={{ color: "#ef4444", cursor: "pointer", fontSize: "14px" }}>×</span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div style={{ padding: "10px 16px", borderTop: "1px solid #e5e7eb", display: "flex", gap: "8px", justifyContent: "flex-end" }}>
              <button style={s.resetBtn} onClick={() => { setCfgSelected(actualColumns); setCfgPins([]); }}>重置默认</button>
              <button style={s.resetBtn} onClick={() => setShowColumnConfig(false)}>取消</button>
              <button style={s.searchBtn} onClick={applyColumnConfig}>应用</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  // ── 渲染 ──────────────────────────────────────────────────────────────────────

  return (
    <div style={s.container}>
      {/* 紫色顶栏（2026-07-17 领星化：首页+Tab并入顶栏；AI问答/页面标题移除，App.tsx 该路由不再套壳） */}
      {!embedded && (
      <div style={{ background: "#6366f1", margin: "-20px -20px 12px", padding: "8px 16px",
        display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap",
        position: "sticky", top: 0, zIndex: 200 }}>
        <a href="/" style={{ background: "rgba(255,255,255,0.16)", color: "#fff", padding: "5px 14px",
          borderRadius: "6px", fontSize: "13px", textDecoration: "none", whiteSpace: "nowrap" }}>← 首页</a>
        <span style={{ width: "1px", height: "18px", background: "rgba(255,255,255,0.35)" }} />
        {VISIBLE_SHEET_TABS.map((tab) => {
          const meta = sheetMetas.find((m) => m.sheet_id === tab.sheetId);
          const active = activeTab === tab.sheetId;
          return (
            <button key={tab.sheetId}
              style={{ background: active ? "#fff" : "transparent", color: active ? "#4f46e5" : "rgba(255,255,255,0.92)",
                border: "none", borderRadius: "6px", padding: "5px 12px", fontSize: "13px",
                fontWeight: active ? 700 : 400, cursor: "pointer", whiteSpace: "nowrap" }}
              onClick={() => handleTabChange(tab.sheetId)}>
              {tab.label}
              {meta && <span style={{ marginLeft: "4px", fontSize: "11px", opacity: 0.75 }}>({meta.total})</span>}
            </button>
          );
        })}
        <button type="button"
          style={{ background: "transparent", color: "rgba(255,255,255,0.92)", border: "none",
            borderRadius: "6px", padding: "5px 12px", fontSize: "13px", cursor: "pointer", whiteSpace: "nowrap" }}
          onClick={() => { window.location.hash = "#/business-analysis"; window.location.reload(); }}>
          经营分析 ↗
        </button>
      </div>
      )}


      {/* 同步任务 Tab */}
      {activeTab === "__tasks__" && (
        <div style={s.card}>
          <div style={{ fontWeight: 600, marginBottom: "12px" }}>同步任务记录</div>
          <div style={s.tableWrap}>
            <table style={s.table}>
              <colgroup>
                {visibleColumns.map((col, ci) => (
                  <col key={col} style={{
                    ...(colWidths[activeTab]?.[col] ? { width: colWidths[activeTab][col] } : {}),
                    ...(hlCell && hlCell.tab === activeTab && hlCell.col === ci ? { background: "#eef2ff" } : {}),
                  }} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  {["任务ID", "Sheet", "状态", "总行数", "新增", "更新", "跳过", "开始时间", "完成时间", "错误信息"].map((h) => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {syncTasks.length === 0 && <tr><td colSpan={10} style={s.empty}>暂无同步记录</td></tr>}
                {syncTasks.map((t, i) => (
                  <tr key={i}>
                    <td style={s.td}><code style={{ fontSize: "11px" }}>{t.sync_task_id?.slice(0, 8)}...</code></td>
                    <td style={s.td}>{t.sheet_name ?? t.sheet_id}</td>
                    <td style={s.td}><span style={s.statusChip(t.status)}>{t.status}</span></td>
                    <td style={s.td}>{t.row_count ?? "-"}</td>
                    <td style={s.td}>{t.inserted_count}</td>
                    <td style={s.td}>{t.updated_count}</td>
                    <td style={s.td}>{t.skipped_count}</td>
                    <td style={s.td}>{t.started_at ? new Date(t.started_at).toLocaleString("zh-CN") : "-"}</td>
                    <td style={s.td}>{t.finished_at ? new Date(t.finished_at).toLocaleString("zh-CN") : "-"}</td>
                    <td style={{ ...s.td, color: "#dc2626" }}>{t.error_message ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Sheet 数据 Tab */}
      {activeTab === "__clearance__" && <ClearanceCenter onNavigate={onNavigate} />}

      {activeTab === "__pmc__" && <PmcCenter />}

      {activeTab !== "__tasks__" && activeTab !== "__clearance__" && activeTab !== "__pmc__" && (
        <div style={{ ...s.card, padding: "10px 12px" }}>
          {/* 筛选面板（元信息已并入右侧） */}
          {filterPanel}

          {isProductManagementTab && selectedKeys.size > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: "10px", background: "#1f2430", color: "#fff", borderRadius: "10px", padding: "8px 14px", margin: "0 0 10px", flexWrap: "wrap" }}>
              <span style={{ fontWeight: 700 }}>已选 {selectedKeys.size} 项</span>
              <select disabled={batchBusy} value="" onChange={(e) => { if (e.target.value) batchAssignOwner(e.target.value); e.currentTarget.value = ""; }}
                style={{ border: "none", borderRadius: "8px", padding: "6px 10px", fontSize: "12.5px", background: "#2c3240", color: "#fff", cursor: "pointer" }}>
                <option value="">批量认领负责人 ▾</option>
                {ownerOptions.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
              <select disabled={batchBusy} value="" onChange={(e) => { if (e.target.value) batchLifecycle(e.target.value); e.currentTarget.value = ""; }}
                style={{ border: "none", borderRadius: "8px", padding: "6px 10px", fontSize: "12.5px", background: "#2c3240", color: "#fff", cursor: "pointer" }}>
                <option value="">批量调整生命周期 ▾</option>
                {(() => {
                  const rs = selectedRows();
                  const hasCs = rs.some((r) => r["产品类型"] === "CS测品");
                  const hasReg = rs.some((r) => r["产品类型"] !== "CS测品");
                  if (hasCs && hasReg) return <option value="" disabled>（CS与常规不能混选，请分开）</option>;
                  return (hasCs ? CS_LIFECYCLE_OPTIONS : REGULAR_LIFECYCLE_OPTIONS).map((o) => <option key={o} value={o}>{o}</option>);
                })()}
              </select>
              <button disabled={batchBusy} onClick={batchArchive}
                style={{ border: "1px solid #5b3b3b", background: "#3a2b2b", color: "#ffb4a8", borderRadius: "8px", padding: "6px 12px", fontSize: "12.5px", cursor: "pointer" }}>批量归档</button>
              <button disabled={batchBusy} onClick={() => setSelectedKeys(new Set())}
                style={{ border: "none", background: "transparent", color: "#9aa0ab", cursor: "pointer", fontSize: "12.5px" }}>清除选择</button>
              {batchBusy && <span style={{ color: "#9aa0ab" }}>处理中…</span>}
              {!batchBusy && batchMsg && <span style={{ color: "#a7f3d0" }}>{batchMsg}</span>}
            </div>
          )}

          {/* 表格（2026-07-17 统一广告库查看器：固定布局+全列宽度+逐格冻结） */}
          <div style={s.tableWrap}>
            <table
              style={{ ...s.table, tableLayout: "fixed" as const, width: "max-content", minWidth: "100%" }}>
              <colgroup>
                {renderCols.map((col) => <col key={col} style={{ width: pinColWidth(col) }} />)}
              </colgroup>
              <thead>
                <tr>
                  {loading
                    ? <th style={s.th}>加载中...</th>
                    : renderCols.map((col) => withPinned(renderHeaderCell(col), col, true))
                  }
                </tr>
              </thead>
              <tbody>
                {!loading && !currentSheetData?.rows?.length && (
                  <tr>
                    <td colSpan={renderCols.length || 1} style={s.empty}>
                      {hasActiveFilters ? "无匹配数据，请尝试修改筛选条件" : "暂无数据，请先执行同步"}
                    </td>
                  </tr>
                )}
                {!loading && (currentSheetData?.rows ?? []).map((row, i) => (
                  <tr
                    key={i}
                    onClick={(e) => {
                      const td = (e.target as HTMLElement).closest("td");
                      if (!td) return;
                      // 交互控件内的点击不触发高亮切换
                      if ((e.target as HTMLElement).closest("button, textarea, select, input, a")) return;
                      const ci = (td as HTMLTableCellElement).cellIndex;
                      setHlCell((prev) =>
                        prev && prev.tab === activeTab && prev.row === i && prev.col === ci
                          ? null
                          : { tab: activeTab, row: i, col: ci });
                    }}
                    style={{
                      // 高亮激活时其余行透明让 colgroup 列色透出（仿WPS聚焦）；未激活恢复斑马纹
                      background: hlCell && hlCell.tab === activeTab
                        ? (hlCell.row === i ? "#eef2ff" : "transparent")
                        : i % 2 === 0 ? "#fff" : "#fafafa",
                    }}
                  >
                    {renderCols.map((col) => withPinned(renderDataCell(row, col), col, false))}
                  </tr>
                ))}
              </tbody>
              {/* 合计行（2026-07-17 领星式：当前筛选全量口径，吸底） */}
              {!loading && currentSheetData?.totals && (currentSheetData?.rows?.length ?? 0) > 0 && (
                <tfoot>
                  <tr>
                    {renderCols.map((col, ci) => (
                      <td key={col} style={{ ...s.td, position: "sticky" as const, bottom: 0,
                        background: "#eef2ff", fontWeight: 700, color: "#3730a3",
                        borderTop: "2px solid #c7d2fe", whiteSpace: "nowrap" as const,
                        ...(pinnedSet.has(col) ? { left: pinLeftMap[col], zIndex: 6 } : { zIndex: 3 }) }}>
                        {ci === 0
                          ? `总计（${currentSheetData?.total ?? 0}行）`
                          : (currentSheetData?.totals?.[col] ?? "")}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              )}
            </table>
          </div>

          {/* 分页（2026-07-17 广告库同款：每页条数+页码+跳页） */}
          <div style={s.pagination}>
            <span style={{ fontSize: "12px", color: "#6b7280" }}>每页</span>
            {PAGE_SIZE_OPTIONS.map((ps) => (
              <button key={ps} style={s.pageBtn(pageSize === ps, false)}
                onClick={() => { setPageSize(ps); setPage(1); }}>{ps}</button>
            ))}
            <span style={{ width: "12px" }} />
            <button style={s.pageBtn(false, page <= 1)} disabled={page <= 1} onClick={() => setPage(1)}>首页</button>
            <button style={s.pageBtn(false, page <= 1)} disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const start = Math.max(1, Math.min(page - 2, totalPages - 4));
              const pg = start + i;
              return pg <= totalPages ? (
                <button key={pg} style={s.pageBtn(pg === page, false)} onClick={() => setPage(pg)}>{pg}</button>
              ) : null;
            })}
            <button style={s.pageBtn(false, page >= totalPages)} disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</button>
            <button style={s.pageBtn(false, page >= totalPages)} disabled={page >= totalPages} onClick={() => setPage(totalPages)}>末页</button>
            <span style={{ fontSize: "12px", color: "#9ca3af" }}>共 {currentSheetData?.total ?? 0} 条</span>
            <span style={{ fontSize: "12px", color: "#9ca3af" }}>跳至</span>
            <input type="number" min={1} max={totalPages} defaultValue={page}
              style={{ ...s.filterInput, width: "64px", padding: "4px 8px" }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  const v = Number((e.target as HTMLInputElement).value);
                  if (v >= 1 && v <= totalPages) setPage(v);
                }
              }} />
            <span style={{ fontSize: "12px", color: "#9ca3af" }}>页</span>
          </div>
        </div>
      )}
      {gptLinkModal && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => { if (!gptLinkSaving) setGptLinkModal(null); }}
        >
          <div
            style={{ background: "#fff", borderRadius: "12px", padding: "20px 24px", width: "540px", maxWidth: "92%", boxShadow: "0 20px 50px rgba(0,0,0,0.25)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <div style={{ fontSize: "14px", fontWeight: 700, color: "#111827" }}>GPT 分析链接 ｜ ItemID {gptLinkModal.itemId}{gptLinkModal.msku ? `（${gptLinkModal.msku}）` : ""}</div>
              <button style={{ padding: "2px 10px", fontSize: "12px", border: "1px solid #e5e7eb", borderRadius: "6px", background: "#f9fafb", cursor: "pointer" }} onClick={() => setGptLinkModal(null)}>关闭</button>
            </div>
            <div style={{ fontSize: "12px", color: "#6b7280", marginBottom: "12px" }}>粘贴 GPT 对话链接；保存后仅之后新生成的运营日志行使用新链接，已生成的日志行保留旧链接。</div>
            <div style={{ marginBottom: "10px" }}>
              <div style={{ fontSize: "12.5px", fontWeight: 600, color: "#374151", marginBottom: "4px" }}>🔍 关键词分析链接</div>
              <input
                style={{ width: "100%", padding: "7px 10px", border: "1px solid #d1d5db", borderRadius: "6px", fontSize: "12.5px", boxSizing: "border-box" as const }}
                placeholder="https://…"
                value={gptLinkModal.kw}
                onChange={(e) => setGptLinkModal((prev) => (prev ? { ...prev, kw: e.target.value } : prev))}
              />
            </div>
            <div style={{ marginBottom: "10px" }}>
              <div style={{ fontSize: "12.5px", fontWeight: 600, color: "#374151", marginBottom: "4px" }}>📈 广告分析链接</div>
              <input
                style={{ width: "100%", padding: "7px 10px", border: "1px solid #d1d5db", borderRadius: "6px", fontSize: "12.5px", boxSizing: "border-box" as const }}
                placeholder="https://…"
                value={gptLinkModal.ads}
                onChange={(e) => setGptLinkModal((prev) => (prev ? { ...prev, ads: e.target.value } : prev))}
              />
            </div>
            <div style={{ fontSize: "11.5px", color: "#b45309", background: "#fffbeb", border: "1px solid #fde68a", borderRadius: "6px", padding: "6px 10px", marginBottom: "10px" }}>
              ⚠️ 必须以 http(s):// 开头；不允许清空，只能替换为新链接；未修改的链接不会重复保存。
            </div>
            {gptLinkMsg && <div style={{ fontSize: "12px", color: "#dc2626", marginBottom: "8px" }}>{gptLinkMsg}</div>}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
              <button style={{ padding: "6px 18px", borderRadius: "6px", fontSize: "13px", border: "1px solid #d1d5db", background: "#fff", cursor: "pointer" }} disabled={gptLinkSaving} onClick={() => setGptLinkModal(null)}>取消</button>
              <button style={{ padding: "6px 18px", borderRadius: "6px", fontSize: "13px", border: "1px solid #3370ff", background: "#3370ff", color: "#fff", cursor: gptLinkSaving ? "not-allowed" : "pointer", opacity: gptLinkSaving ? 0.7 : 1 }} disabled={gptLinkSaving} onClick={saveGptLinkModal}>{gptLinkSaving ? "保存中…" : "保存"}</button>
            </div>
          </div>
        </div>
      )}
      {reminderModal && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => setReminderModal(null)}
        >
          <div
            style={{ background: "#fff", borderRadius: "12px", padding: "20px 24px", maxWidth: "640px", width: "90%", maxHeight: "72vh", display: "flex", flexDirection: "column", boxShadow: "0 20px 50px rgba(0,0,0,0.25)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <div style={{ fontSize: "14px", fontWeight: 600, color: "#111827" }}>{reminderModal.title}</div>
              <button
                style={{ padding: "2px 10px", fontSize: "12px", border: "1px solid #e5e7eb", borderRadius: "6px", background: "#f9fafb", cursor: "pointer" }}
                onClick={() => setReminderModal(null)}
              >
                关闭
              </button>
            </div>
            <div style={{ overflowY: "auto", fontSize: "13px", lineHeight: 1.8, color: "#374151", whiteSpace: "pre-wrap" as const, wordBreak: "break-word" as const }}>
              {reminderModal.text}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
