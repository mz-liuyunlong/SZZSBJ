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

  sampleQuantity: number;
  sampleAmount: number | null;
  costQuantity: number;

  refundQuantity: number;
  refundAmount: number | null;
  returnRate30Days: number | null;

  adSpend: number;

  wfsDeliveryFee: number | null;
  wfsDeliveryUnitPrice: number | null;

  commission: number;

  purchaseCost: number | null;
  purchaseUnitPriceCny: number | null;

  firstLegCost: number | null;
  firstLegUnitPriceCny: number | null;

  storageFee: number | null;
  storageUnitPrice: number | null;

  wfsAvailableInventory: number;
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

  sampleQuantity: number;
  sampleAmount: number | null;

  refundQuantity: number;
  refundAmount: number | null;
  returnRate30Days: number | null;

  adSpend: number;
  adRatio: number | null;

  wfsDeliveryFee: number | null;
  wfsDeliveryUnitPrice: number | null;

  commission: number;

  purchaseCost: number | null;
  purchaseUnitPriceCny: number | null;

  firstLegCost: number | null;
  firstLegUnitPriceCny: number | null;

  storageFee: number | null;
  storageUnitPrice: number | null;

  wfsAvailableInventory: number;
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

  { key: "sampleQuantity", title: "送样量" },
  { key: "sampleAmount", title: "送样金额" },

  { key: "refundQuantity", title: "退货量" },
  { key: "refundAmount", title: "退款损失" },
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

const uniqueTextValues = (
  records: OrderProfitSourceRecord[],
  key: "sku" | "msku" | "store" | "owner",
) => Array.from(new Set(
  records
    .map((record) => String(record[key] ?? "").trim())
    .filter(Boolean),
));

const compactJoinedText = (values: string[], fallback = "-") => {
  if (values.length === 0) return fallback;
  if (values.length <= 2) return values.join(" / ");
  return `${values[0]} / ${values[1]} 等${values.length}个`;
};

const aggregateKey = (record: OrderProfitSourceRecord) => record.productId;

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
    const skuValues = uniqueTextValues(bucket, "sku");
    const mskuValues = uniqueTextValues(bucket, "msku");
    const storeValues = uniqueTextValues(bucket, "store");
    const ownerValues = uniqueTextValues(bucket, "owner");
    const salesVolume = bucket.reduce((total, row) => total + row.salesVolume, 0);
    const orderCount = bucket.reduce((total, row) => total + row.orderCount, 0);
    const salesAmount = bucket.reduce((total, row) => total + row.salesAmount, 0);

    const sampleQuantity = bucket.reduce(
      (total, row) => total + row.sampleQuantity,
      0,
    );

    const sampleAmount = bucket.some((row) => row.sampleAmount == null)
      ? null
      : bucket.reduce(
          (total, row) => total + (row.sampleAmount ?? 0),
          0,
        );

    const refundQuantity = bucket.reduce(
      (total, row) => total + row.refundQuantity,
      0,
    );

    const refundAmount = bucket.some((row) => row.refundAmount == null)
      ? null
      : bucket.reduce(
          (total, row) => total + (row.refundAmount ?? 0),
          0,
        );

    const adSpend = bucket.reduce((total, row) => total + row.adSpend, 0);

    const weightedAverage = (
      valueKey:
        | "returnRate30Days"
        | "wfsDeliveryUnitPrice"
        | "purchaseUnitPriceCny"
        | "firstLegUnitPriceCny"
        | "storageUnitPrice",
      weightKey: "salesVolume" | "costQuantity",
    ) => {
      let weightedTotal = 0;
      let totalWeight = 0;
      const fallbackValues: number[] = [];

      for (const row of bucket) {
        const value = row[valueKey];

        if (typeof value !== "number" || !Number.isFinite(value)) {
          continue;
        }

        fallbackValues.push(value);

        const weight = row[weightKey];

        if (Number.isFinite(weight) && weight > 0) {
          weightedTotal += value * weight;
          totalWeight += weight;
        }
      }

      if (totalWeight > 0) {
        return weightedTotal / totalWeight;
      }

      if (fallbackValues.length > 0) {
        return fallbackValues.reduce((sum, value) => sum + value, 0)
          / fallbackValues.length;
      }

      return null;
    };

    const returnRate30Days = weightedAverage(
      "returnRate30Days",
      "salesVolume",
    );

    const wfsDeliveryUnitPrice = weightedAverage(
      "wfsDeliveryUnitPrice",
      "salesVolume",
    );

    const purchaseUnitPriceCny = weightedAverage(
      "purchaseUnitPriceCny",
      "costQuantity",
    );

    const firstLegUnitPriceCny = weightedAverage(
      "firstLegUnitPriceCny",
      "costQuantity",
    );

    const storageUnitPrice = weightedAverage(
      "storageUnitPrice",
      "costQuantity",
    );

    // 库存是快照数据，不能把历史日期库存直接相加。
    // 每个 店铺 + SKU + MSKU 只取筛选范围内最新一天库存，再汇总。
    const latestInventoryRows = new Map<
      string,
      OrderProfitSourceRecord
    >();

    for (const row of bucket) {
      const inventoryKey = [
        row.store,
        row.sku,
        row.msku,
      ].join("::");

      const current = latestInventoryRows.get(inventoryKey);

      if (!current || row.date > current.date) {
        latestInventoryRows.set(inventoryKey, row);
      }
    }

    const wfsAvailableInventory = Array.from(
      latestInventoryRows.values(),
    ).reduce(
      (total, row) => total + row.wfsAvailableInventory,
      0,
    );
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
      sku: compactJoinedText(skuValues),
      msku: compactJoinedText(mskuValues),
      platform: base.platform,
      store: compactJoinedText(storeValues),
      owner: compactJoinedText(ownerValues),
      currency: base.currency,
      salesVolume,
      orderCount,
      salesAmount,

      sampleQuantity,
      sampleAmount,

      refundQuantity,
      refundAmount,
      returnRate30Days,

      adSpend,
      adRatio: salesAmount ? adSpend / salesAmount * 100 : null,

      wfsDeliveryFee,
      wfsDeliveryUnitPrice,

      commission,

      purchaseCost,
      purchaseUnitPriceCny,

      firstLegCost,
      firstLegUnitPriceCny,

      storageFee,
      storageUnitPrice,

      wfsAvailableInventory,
      totalCost,
      orderProfit,
      averageProfitPerOrder: orderProfit != null && orderCount ? orderProfit / orderCount : null,
      profitMargin: orderProfit != null && salesAmount ? orderProfit / salesAmount * 100 : null,
      roi: orderProfit != null
        && purchaseCost != null
        && firstLegCost != null
        && purchaseCost + firstLegCost > 0
        ? orderProfit / (purchaseCost + firstLegCost)
        : null,
      costStatus: status,
      sevenDayDates: trendDates,
      sevenDaySales,
    };
  }).sort((left, right) => (
    right.salesVolume - left.salesVolume
    || right.salesAmount - left.salesAmount
    || right.orderCount - left.orderCount
    || left.productId.localeCompare(right.productId)
  ));
};
