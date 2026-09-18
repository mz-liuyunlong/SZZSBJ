/** Types and shared helpers for the no-API product-ID order-profit acceptance page. */
import dayjs from "dayjs";
import "dayjs/locale/zh-cn";

dayjs.locale("zh-cn");

export type OrderProfitPlatform = "Walmart" | "TEMU" | "Amazon";
export type OrderProfitCurrency = "USD" | "CNY";
export type OrderProfitCostStatus = "已完成" | "待补齐" | "异常" | "部分缺失";
export type OrderProfitDatePreset = "today" | "week" | "month" | "year" | "custom";

export interface OrderProfitSourceRecord {
  id: string;
  date: string;
  store: string;
  owner: string;
  msku: string;
  productId: string;
  sku: string;
  productName: string;
  platform: OrderProfitPlatform;
  currency: OrderProfitCurrency;
  salesVolume: number;
  orderCount: number;
  salesAmount: number;
  refundAmount: number;
  adSpend: number;
  wfsDeliveryFee: number | null;
  commission: number;
  purchaseCost: number | null;
  firstLegCost: number | null;
  storageFee: number | null;
  costStatus: OrderProfitCostStatus;
}

export interface OrderProfitRow {
  id: string;
  productId: string;
  productName: string;
  sku: string;
  msku: string;
  platform: OrderProfitPlatform;
  store: string;
  owner: string;
  currency: OrderProfitCurrency;
  salesVolume: number;
  orderCount: number;
  salesAmount: number;
  refundAmount: number;
  adSpend: number;
  adRatio: number | null;
  wfsDeliveryFee: number | null;
  commission: number;
  purchaseCost: number | null;
  firstLegCost: number | null;
  storageFee: number | null;
  totalCost: number | null;
  orderProfit: number | null;
  averageProfitPerOrder: number | null;
  profitMargin: number | null;
  roi: number | null;
  costStatus: OrderProfitCostStatus;
  sevenDayDates: string[];
  sevenDaySales: number[];
}

export interface OrderProfitColumnField {
  key: string;
  title: string;
}

export const orderProfitColumnFields: OrderProfitColumnField[] = [
  { key: "image", title: "图片" },
  { key: "analysis", title: "分析" },
  { key: "productIdName", title: "商品ID/品名" },
  { key: "skuMsku", title: "SKU/MSKU" },
  { key: "platform", title: "平台" },
  { key: "store", title: "店铺" },
  { key: "owner", title: "负责人" },
  { key: "salesVolume", title: "销量" },
  { key: "orderCount", title: "订单量" },
  { key: "salesAmount", title: "销售额" },
  { key: "refundAmount", title: "退款额" },
  { key: "adSpend", title: "广告费" },
  { key: "adRatio", title: "广告占比" },
  { key: "wfsDeliveryFee", title: "WFS配送费" },
  { key: "commission", title: "佣金" },
  { key: "purchaseCost", title: "采购成本" },
  { key: "firstLegCost", title: "头程成本" },
  { key: "storageFee", title: "仓储费" },
  { key: "totalCost", title: "总成本" },
  { key: "orderProfit", title: "订单利润" },
  { key: "averageProfitPerOrder", title: "平均利润/单" },
  { key: "profitMargin", title: "利润率" },
  { key: "roi", title: "ROI" },
  { key: "costStatus", title: "成本状态" },
  { key: "actions", title: "操作" },
];

export const fixedOrderProfitColumnKeys = [
  "image",
  "analysis",
  "productIdName",
];

/** Acceptance-only display rate; replace with approved daily FX data when the API is implemented. */
export const MOCK_USD_TO_CNY_RATE = 6.6;

export const dateRangeForPreset = (
  preset: Exclude<OrderProfitDatePreset, "custom">,
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

const priority: Record<OrderProfitCostStatus, number> = {
  异常: 4,
  部分缺失: 3,
  待补齐: 2,
  已完成: 1,
};

const aggregateKey = (record: OrderProfitSourceRecord) => [
  record.productId,
  record.msku,
  record.store,
  record.owner,
].join("\u001f");

export const aggregateOrderProfitRows = (records: OrderProfitSourceRecord[]): OrderProfitRow[] => {
  const buckets = new Map<string, OrderProfitSourceRecord[]>();

  for (const record of records) {
    const key = aggregateKey(record);
    const bucket = buckets.get(key) ?? [];
    bucket.push(record);
    buckets.set(key, bucket);
  }

  return Array.from(buckets.values()).map((bucket) => {
    const base = bucket[0];
    const salesVolume = bucket.reduce((total, row) => total + row.salesVolume, 0);
    const orderCount = bucket.reduce((total, row) => total + row.orderCount, 0);
    const salesAmount = bucket.reduce((total, row) => total + row.salesAmount, 0);
    const refundAmount = bucket.reduce((total, row) => total + row.refundAmount, 0);
    const adSpend = bucket.reduce((total, row) => total + row.adSpend, 0);
    const sumOptional = (key: "wfsDeliveryFee" | "purchaseCost" | "firstLegCost" | "storageFee") => (
      bucket.some((row) => row[key] == null)
        ? null
        : bucket.reduce((total, row) => total + (row[key] ?? 0), 0)
    );
    const wfsDeliveryFee = sumOptional("wfsDeliveryFee");
    const commission = bucket.reduce((total, row) => total + row.commission, 0);
    const purchaseCost = sumOptional("purchaseCost");
    const firstLegCost = sumOptional("firstLegCost");
    const storageFee = sumOptional("storageFee");
    const totalCost = wfsDeliveryFee != null
      && purchaseCost != null
      && firstLegCost != null
      && storageFee != null
      ? adSpend + wfsDeliveryFee + commission + purchaseCost + firstLegCost + storageFee
      : null;
    const orderProfit = totalCost == null ? null : salesAmount - totalCost;
    const status = bucket.reduce((current, row) => (
      priority[row.costStatus] > priority[current] ? row.costStatus : current
    ), base.costStatus);
    const latestDate = bucket.reduce((latest, row) => row.date > latest ? row.date : latest, base.date);
    const trendDates = Array.from({ length: 7 }, (_, index) => dayjs(latestDate)
      .subtract(6 - index, "day")
      .format("YYYY-MM-DD"));
    const sevenDaySales = trendDates.map((date) => bucket
      .filter((row) => row.date === date)
      .reduce((total, row) => total + row.salesVolume, 0));

    return {
      id: `order-profit-${aggregateKey(base)}`,
      productId: base.productId,
      productName: base.productName,
      sku: base.sku,
      msku: base.msku,
      platform: base.platform,
      store: base.store,
      owner: base.owner,
      currency: base.currency,
      salesVolume,
      orderCount,
      salesAmount,
      refundAmount,
      adSpend,
      adRatio: salesAmount ? adSpend / salesAmount * 100 : null,
      wfsDeliveryFee,
      commission,
      purchaseCost,
      firstLegCost,
      storageFee,
      totalCost,
      orderProfit,
      averageProfitPerOrder: orderProfit != null && orderCount ? orderProfit / orderCount : null,
      profitMargin: orderProfit != null && salesAmount ? orderProfit / salesAmount * 100 : null,
      roi: orderProfit != null
        && purchaseCost != null
        && firstLegCost != null
        && purchaseCost + firstLegCost > 0
        ? orderProfit / (purchaseCost + firstLegCost) * 100
        : null,
      costStatus: status,
      sevenDayDates: trendDates,
      sevenDaySales,
    };
  }).sort((left, right) => (right.orderProfit ?? Number.NEGATIVE_INFINITY)
    - (left.orderProfit ?? Number.NEGATIVE_INFINITY));
};
