export type WfsFeeAlertCurrency = "USD" | "CNY";
export type WfsFeeAlertDatePreset = "today" | "last7" | "last30" | "last90" | "custom";
export type WfsFeeAlertCaseStatus = "未开Case" | "已开Case" | "跟进中" | "待归档审核" | "已追回" | "已归档" | "驳回" | "已关闭";
export type WfsFeeAlertPriority = "高" | "中" | "低";
export type WfsFeeAlertSearchField = "sku" | "msku" | "productId" | "productName";

export interface WfsFeeAlertRow {
  id: string;
  imageLabel: string;
  imageSymbol: string;
  sku: string;
  msku: string;
  store: string;
  owner: string;
  productId: string;
  productName: string;
  category: string;
  orders: number;
  units: number;
  chargedFee: number;
  standardFee: number;
  productUnitWfsFee: number | null;
  unitCharged: number;
  unitStandard: number;
  overFee: number;
  unitOverFee: number;
  recoveredAmount: number;
  status: WfsFeeAlertCaseStatus;
  caseNo: string;
  reason: string;
  discoveredAt: string;
  caseOpenedAt: string;
  nextFollowAt: string;
  level: WfsFeeAlertPriority;
  latestFollow: string;
  followLog?: string;
  followCount?: number;
  lastFollowBy?: string | null;
  lastFollowAt?: string | null;
}

export interface WfsFeeAlertFilters {
  datePreset: WfsFeeAlertDatePreset;
  dateRange: [string, string];
  currency: WfsFeeAlertCurrency;
  stores: string[];
  owners: string[];
  statuses: string[];
  reasons: string[];
  searchField: WfsFeeAlertSearchField;
  keyword: string;
}

export interface WfsFeeAlertFollowFormValues {
  status: WfsFeeAlertCaseStatus;
  caseNo: string;
  recoveredAmount: number;
  nextFollowAt?: string;
  latestFollow: string;
}

export interface WfsFeeAlertColumnField {
  key: string;
  title: string;
}

export const WFS_FEE_ALERT_USD_TO_CNY_RATE = 6.6;
export const WFS_FEE_ALERT_REFERENCE_DATE = new Date().toISOString().slice(0, 10);

const formatIsoDate = (date: Date) => date.toISOString().slice(0, 10);

const shiftIsoDate = (dateText: string, offsetDays: number) => {
  const date = new Date(`${dateText}T00:00:00`);
  date.setDate(date.getDate() + offsetDays);
  return formatIsoDate(date);
};

export const createWfsFeeAlertDateRange = (preset: WfsFeeAlertDatePreset): [string, string] => {
  const endDate = WFS_FEE_ALERT_REFERENCE_DATE;
  if (preset === "today") return [endDate, endDate];
  if (preset === "last7") return [shiftIsoDate(endDate, -6), endDate];
  if (preset === "last90") return [shiftIsoDate(endDate, -89), endDate];
  return [shiftIsoDate(endDate, -29), endDate];
};

export const wfsFeeAlertColumnFields: WfsFeeAlertColumnField[] = [
  { key: "image", title: "图片" },
  { key: "productIdName", title: "商品ID/品名" },
  { key: "skuMsku", title: "SKU/MSKU" },
  { key: "store", title: "店铺" },
  { key: "owner", title: "负责人" },
  { key: "orders", title: "受影响销量" },
  { key: "productUnitWfsFee", title: "单件WFS费用" },
  { key: "unitCharged", title: "单价实收费用" },
  { key: "chargedFee", title: "实收费用" },
  { key: "standardFee", title: "人工配送费测算" },
  { key: "overFee", title: "预计追回" },
  { key: "unitOverFee", title: "单件多收" },
  { key: "reason", title: "异常原因" },
  { key: "level", title: "优先级" },
  { key: "status", title: "Case状态" },
  { key: "caseNo", title: "Case编号" },
  { key: "caseOpenedAt", title: "立案时间" },
  { key: "nextFollowAt", title: "下次跟进" },
  { key: "recoveredAmount", title: "已追回金额" },
  { key: "latestFollow", title: "最新跟进" },
  { key: "actions", title: "操作" },
];

export const fixedWfsFeeAlertColumnKeys = ["image", "productIdName", "skuMsku"];

export const createWfsFeeAlertInitialFilters = (): WfsFeeAlertFilters => ({
  datePreset: "custom",
  dateRange: ["", ""],
  currency: "USD",
  stores: [],
  owners: [],
  statuses: [],
  reasons: [],
  searchField: "sku",
  keyword: "",
});

export const formatWfsMoney = (value: number, currency: WfsFeeAlertCurrency) => {
  const converted = currency === "CNY" ? value * WFS_FEE_ALERT_USD_TO_CNY_RATE : value;
  const symbol = currency === "CNY" ? "¥" : "$";
  return `${symbol}${converted.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

export const getPendingWfsAmount = (row: WfsFeeAlertRow) => Math.max(row.overFee - row.recoveredAmount, 0);

export const filterWfsFeeAlertRows = (
  rows: WfsFeeAlertRow[],
  filters: WfsFeeAlertFilters,
) => {
  const keyword = filters.keyword.trim().toLocaleLowerCase();
  const [startDate, endDate] = filters.dateRange;

  return rows.filter((row) => {
    const target = String(row[filters.searchField]).toLocaleLowerCase();
    return (!startDate || row.discoveredAt >= startDate)
      && (!endDate || row.discoveredAt <= endDate)
      && (filters.stores.length === 0 || filters.stores.includes(row.store))
      && (filters.owners.length === 0 || filters.owners.includes(row.owner))
      && (filters.statuses.length === 0 || filters.statuses.includes(row.status))
      && (filters.reasons.length === 0 || filters.reasons.includes(row.reason))
      && (!keyword || target.includes(keyword));
  });
};

export const getWfsFeeAlertSummary = (rows: WfsFeeAlertRow[]) => {
  const totalOverFee = rows.reduce((total, row) => total + row.overFee, 0);
  const totalRecoveredAmount = rows.reduce((total, row) => total + row.recoveredAmount, 0);
  const openedCaseCount = rows.filter((row) => row.caseNo).length;
  return {
    alertSkuCount: rows.length,
    totalOverFee,
    totalRecoveredAmount,
    pendingAmount: Math.max(totalOverFee - totalRecoveredAmount, 0),
    openedCaseCount,
    unopenedCaseCount: rows.length - openedCaseCount,
    followDueCount: rows.filter((row) => row.nextFollowAt !== "-" && row.status !== "已追回" && row.status !== "已关闭" && row.status !== "已归档").length,
  };
};
