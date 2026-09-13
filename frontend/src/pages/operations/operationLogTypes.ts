export type OperationLogDatePreset =
  | "today"
  | "yesterday"
  | "last7"
  | "last30"
  | "thisMonth"
  | "lastMonth"
  | "thisYear"
  | "lastYear"
  | "custom";

export type OperationLogSearchField = "productId" | "sku" | "productName" | "store" | "owner" | "date";
export type OperationLogSystemFilter = "all" | "has" | "missing";
export type OperationLogStatus = "待提交" | "草稿" | "已保存" | "缺记录";
export type OperationLogWorkType =
  | "广告调整"
  | "Listing优化"
  | "销售价调整"
  | "无需调整"
  | "系统日志核对"
  | "其他";

export interface OperationLogSystemRecord {
  id: string;
  time: string;
  productId: string;
  owner: string;
  type: string;
  object: string;
  before: string;
  after: string;
  source: "领星" | "Walmart后台";
  detail: string;
}

export interface OperationLogRow {
  id: string;
  date: string;
  productId: string;
  sku: string;
  productName: string;
  store: string;
  owner: string;
  workType: OperationLogWorkType;
  conversionRate: number;
  adRatio?: number;
  salePrice: number;
  keywordEntryStatus: "ok" | "missing";
  adEntryStatus: "ok" | "missing";
  systemLogCount: number;
  manualLog: string;
  status: OperationLogStatus;
}

export interface OperationLogFilters {
  datePreset: OperationLogDatePreset;
  dateRange: [string, string];
  owners: string[];
  stores: string[];
  workTypes: OperationLogWorkType[];
  systemLog: OperationLogSystemFilter;
  searchField: OperationLogSearchField;
  keyword: string;
  batchValues?: string[];
}

export interface OperationLogColumnField {
  key: string;
  title: string;
}

export interface OperationLogLinkFormValues {
  entryType: "keyword" | "ad";
  entryName: string;
  entryUrl: string;
  note: string;
}

export interface OperationLogBatchWriteValues {
  productIds: string[];
  workTypes: OperationLogWorkType[];
  observeDays: string;
  writeMode: "append" | "onlyBlank" | "replace";
  logText: string;
}

export const OPERATION_LOG_REFERENCE_DATE = "2026-09-13";

const formatIsoDate = (date: Date) => date.toISOString().slice(0, 10);

const shiftIsoDate = (dateText: string, offsetDays: number) => {
  const date = new Date(`${dateText}T00:00:00`);
  date.setDate(date.getDate() + offsetDays);
  return formatIsoDate(date);
};

export const createOperationLogDateRange = (preset: OperationLogDatePreset): [string, string] => {
  const endDate = OPERATION_LOG_REFERENCE_DATE;

  if (preset === "today") return [endDate, endDate];
  if (preset === "yesterday") {
    const yesterday = shiftIsoDate(endDate, -1);
    return [yesterday, yesterday];
  }
  if (preset === "last7") return [shiftIsoDate(endDate, -6), endDate];
  if (preset === "last30") return [shiftIsoDate(endDate, -29), endDate];
  if (preset === "thisMonth") return ["2026-09-01", "2026-09-30"];
  if (preset === "lastMonth") return ["2026-08-01", "2026-08-31"];
  if (preset === "thisYear") return ["2026-01-01", "2026-12-31"];
  if (preset === "lastYear") return ["2025-01-01", "2025-12-31"];

  return [endDate, endDate];
};

export const createOperationLogInitialFilters = (): OperationLogFilters => ({
  datePreset: "today",
  dateRange: createOperationLogDateRange("today"),
  owners: [],
  stores: [],
  workTypes: [],
  systemLog: "all",
  searchField: "productId",
  keyword: "",
});

export const operationLogWorkTypes: OperationLogWorkType[] = [
  "广告调整",
  "Listing优化",
  "销售价调整",
  "无需调整",
  "系统日志核对",
  "其他",
];

export const operationLogColumnFields: OperationLogColumnField[] = [
  { key: "index", title: "#" },
  { key: "date", title: "日期" },
  { key: "productIdShortcut", title: "商品ID / 快捷入口" },
  { key: "productName", title: "商品名称" },
  { key: "store", title: "店铺" },
  { key: "owner", title: "运营" },
  { key: "workType", title: "工作类型" },
  { key: "conversionRate", title: "转化率" },
  { key: "adRatio", title: "广告占比" },
  { key: "salePrice", title: "销售价" },
  { key: "systemLogs", title: "系统日志" },
  { key: "manualLog", title: "运营日志，可直接填写" },
  { key: "status", title: "状态" },
  { key: "actions", title: "操作" },
];

export const fixedOperationLogColumnKeys = ["index", "date", "productIdShortcut"];

export const defaultOperationLogColumnWidths: Record<string, number> = {
  index: 54,
  date: 116,
  productIdShortcut: 246,
  productName: 180,
  store: 108,
  owner: 96,
  workType: 128,
  conversionRate: 96,
  adRatio: 96,
  salePrice: 98,
  systemLogs: 110,
  manualLog: 360,
  status: 104,
  actions: 96,
};

export const filterOperationLogRows = (
  rows: OperationLogRow[],
  filters: OperationLogFilters,
): OperationLogRow[] => {
  const [startDate, endDate] = filters.dateRange;
  const keyword = filters.keyword.trim().toLocaleLowerCase();
  const batchValues = filters.batchValues?.map((item) => item.trim().toLocaleLowerCase()).filter(Boolean) ?? [];

  return rows.filter((row) => {
    const target = String(row[filters.searchField]).toLocaleLowerCase();
    const searchableValues = [
      row.productId,
      row.sku,
      row.productName,
      row.store,
      row.owner,
      row.date,
      row.workType,
    ].map((value) => value.toLocaleLowerCase());

    return row.date >= startDate
      && row.date <= endDate
      && (filters.owners.length === 0 || filters.owners.includes(row.owner))
      && (filters.stores.length === 0 || filters.stores.includes(row.store))
      && (filters.workTypes.length === 0 || filters.workTypes.includes(row.workType))
      && (filters.systemLog === "all"
        || (filters.systemLog === "has" && row.systemLogCount > 0)
        || (filters.systemLog === "missing" && row.systemLogCount === 0))
      && (!keyword || target.includes(keyword))
      && (batchValues.length === 0
        || batchValues.some((item) => searchableValues.some((value) => value.includes(item) || item.includes(value))));
  });
};

export const createSystemDraft = (records: OperationLogSystemRecord[]) => {
  if (records.length === 0) return "系统未抓到调整记录，待人工确认。";

  return records
    .map((record) => `${record.time} ${record.type}：${record.object} ${record.before} → ${record.after}，调整人：${record.owner}`)
    .join("；");
};
