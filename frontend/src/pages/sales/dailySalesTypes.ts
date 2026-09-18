/** Types for the no-API daily-sales acceptance shell. */
import dayjs from "dayjs";
import "dayjs/locale/zh-cn";

dayjs.locale("zh-cn");

export type DailySalesPlatform = "Walmart" | "TEMU" | "Amazon";
export type DailySalesCurrency = "USD" | "CNY";
export type DailySalesCostStatus = "已完成" | "待补齐" | "异常" | "部分缺失";
export type DailySalesDatePreset = "today" | "week" | "month" | "year" | "custom";

export interface DailySalesRow {
  id: string;
  date: string;
  store: string;
  owner: string;
  sevenDayDates: string[];
  sevenDaySales: number[];
  msku: string;
  productId: string;
  sku: string;
  productName: string;
  platform: DailySalesPlatform;
  currency: DailySalesCurrency;
  grossSalesVolume?: number;
  grossOrderCount?: number;
  grossSalesAmount?: number;
  sampleOrderCount?: number;
  sampleQuantity?: number;
  sampleAmount?: number;
  costQuantity?: number;
  salesVolume: number;
  orderCount: number;
  salesAmount: number;
  sampleExcludedAmount: number;
  returnCount: number;
  refundAmount: number;
  returnRate30Days: number;
  adSpend: number;
  adRatio: number;
  wfsDeliveryFee: number | null;
  wfsDeliveryUnitPrice: number | null;
  wfsExpectedFee?: number;
  wfsActualFee?: number | null;
  wfsVarianceAmount?: number | null;
  wfsVarianceRate?: number | null;
  wfsFeeSource?: string;
  commission: number | null;
  purchaseCost: number | null;
  purchaseUnitPriceCny: number | null;
  firstLegCost: number | null;
  firstLegUnitPriceCny: number | null;
  storageFee: number | null;
  storageUnitPrice: number | null;
  wfsAvailableInventory: number;
  legacyGrossProfit: number | null;
  orderProfit: number | null;
  profitMargin: number | null;
  roi: number | null;
  exchangeRate?: number;
  fxSource?: string;
  commissionSource?: string;
  purchaseCostSource?: string;
  firstLegCostSource?: string;
  storageFeeSource?: string;
  calculationWarnings?: string[];
  costStatus: DailySalesCostStatus;
  systemOperationLog: string;
  operationLog: string;
}

export interface DailySalesRefundSummary {
  quantity: number;
  amount: number;
  currency: DailySalesCurrency;
}

export interface DailySalesColumnField {
  key: string;
  title: string;
}

export const dailySalesColumnFields: DailySalesColumnField[] = [
  { key: "image", title: "图片" },
  { key: "analysis", title: "分析" },
  { key: "date", title: "日期" },
  { key: "store", title: "店铺" },
  { key: "owner", title: "负责人" },
  { key: "sevenDaySales", title: "前7天销量趋势" },
  { key: "mskuProductId", title: "MSKU/商品ID" },
  { key: "skuProductName", title: "SKU/品名" },
  { key: "platform", title: "平台" },
  { key: "salesVolume", title: "销量" },
  { key: "orderCount", title: "订单量" },
  { key: "salesAmount", title: "销售额" },
  { key: "sampleQuantity", title: "送样量" },
  { key: "sampleExcludedAmount", title: "送样金额" },
  { key: "returnCount", title: "退货量" },
  { key: "refundAmount", title: "退款额" },
  { key: "returnRate30Days", title: "退货率30天" },
  { key: "adSpend", title: "广告费" },
  { key: "adRatio", title: "广告占比" },
  { key: "wfsDeliveryFee", title: "WFS总配送费" },
  { key: "wfsDeliveryUnitPrice", title: "WFS配送单价" },
  { key: "commission", title: "佣金" },
  { key: "purchaseCost", title: "采购总成本" },
  { key: "purchaseUnitPriceCny", title: "采购单价" },
  { key: "firstLegCost", title: "头程总成本" },
  { key: "firstLegUnitPriceCny", title: "头程单价" },
  { key: "storageFee", title: "总仓储费" },
  { key: "storageUnitPrice", title: "仓储单价" },
  { key: "wfsAvailableInventory", title: "WFS可售库存" },
  { key: "orderProfit", title: "订单利润" },
  { key: "profitMargin", title: "利润率" },
  { key: "roi", title: "ROI" },
  { key: "costStatus", title: "成本状态" },
  { key: "systemOperationLog", title: "系统运营日志" },
  { key: "operationLog", title: "运营日志" },
];

export const fixedDailySalesColumnKeys = [
  "image",
  "analysis",
  "date",
];

/** Acceptance-only display rate; replace with approved daily FX data when the API is implemented. */
export const MOCK_USD_TO_CNY_RATE = 6.6;

export const dateRangeForPreset = (
  preset: Exclude<DailySalesDatePreset, "custom">,
): [string, string] => {
  const referenceDay = dayjs().subtract(1, "day");
  const start = preset === "today"
    ? referenceDay
    : preset === "week"
      ? referenceDay.startOf("week")
      : preset === "month"
        ? referenceDay.startOf("month")
        : referenceDay.startOf("year");
  return [start.format("YYYY-MM-DD"), referenceDay.format("YYYY-MM-DD")];
};
