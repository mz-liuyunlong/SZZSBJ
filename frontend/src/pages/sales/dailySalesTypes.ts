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
  salesVolume: number;
  orderCount: number;
  salesAmount: number;
  sampleExcludedAmount: number;
  returnCount: number;
  refundAmount: number;
  returnRate30Days: number;
  adSpend: number;
  adRatio: number;
  wfsDeliveryFee: number;
  wfsDeliveryUnitPrice: number;
  commission: number;
  purchaseCost: number;
  purchaseUnitPriceCny: number;
  firstLegCost: number;
  firstLegUnitPriceCny: number;
  storageFee: number;
  storageUnitPrice: number;
  wfsAvailableInventory: number;
  legacyGrossProfit: number;
  orderProfit: number;
  profitMargin: number;
  roi: number;
  costStatus: DailySalesCostStatus;
  systemOperationLog: string;
  operationLog: string;
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
  { key: "sampleExcludedAmount", title: "剔除送样额" },
  { key: "returnCount", title: "退货量" },
  { key: "refundAmount", title: "退款额" },
  { key: "returnRate30Days", title: "退货率30天" },
  { key: "adSpend", title: "广告费" },
  { key: "adRatio", title: "广告占比" },
  { key: "wfsDeliveryFee", title: "WFS配送费" },
  { key: "wfsDeliveryUnitPrice", title: "WFS配送单价$" },
  { key: "commission", title: "佣金" },
  { key: "purchaseCost", title: "采购成本" },
  { key: "purchaseUnitPriceCny", title: "采购单价¥" },
  { key: "firstLegCost", title: "头程成本" },
  { key: "firstLegUnitPriceCny", title: "头程单价¥" },
  { key: "storageFee", title: "仓储费" },
  { key: "storageUnitPrice", title: "仓储单价$" },
  { key: "wfsAvailableInventory", title: "WFS可售库存" },
  { key: "legacyGrossProfit", title: "毛利润(旧)" },
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
export const MOCK_USD_TO_CNY_RATE = 7.2;

export const dateRangeForPreset = (
  preset: Exclude<DailySalesDatePreset, "custom">,
): [string, string] => {
  const today = dayjs();
  const start = preset === "today"
    ? today
    : preset === "week"
      ? today.startOf("week")
      : preset === "month"
        ? today.startOf("month")
        : today.startOf("year");
  return [start.format("YYYY-MM-DD"), today.format("YYYY-MM-DD")];
};
