/** Fixed, clearly labelled acceptance data; replace it when a real API is approved. */
import dayjs from "dayjs";
import type {
  DailySalesCostStatus,
  DailySalesCurrency,
  DailySalesPlatform,
  DailySalesRow,
} from "@/pages/sales/dailySalesTypes";

const platforms: DailySalesPlatform[] = ["Walmart", "TEMU", "Amazon"];
const owners = ["林晓", "周宁", "陈岚", "王舟"];
const stores = ["美国一店", "美国二店", "加拿大店", "验收测试店"];
const statuses: DailySalesCostStatus[] = ["已完成", "待补齐", "异常", "部分缺失"];

export const dailySalesMockData: DailySalesRow[] = Array.from({ length: 50 }, (_, index) => {
  const number = index + 1;
  const serial = String(number).padStart(3, "0");
  const platform = platforms[index % platforms.length];
  const currency: DailySalesCurrency = index % 4 === 0 ? "CNY" : "USD";
  const salesVolume = 16 + (index * 7) % 115;
  const orderCount = Math.max(1, salesVolume - 2 - (index % 5));
  const salesAmount = orderCount * (18.5 + (index % 9));
  const purchaseCost = salesAmount * (0.31 + (index % 4) * 0.02);
  const adSpend = salesAmount * (0.08 + (index % 3) * 0.01);
  const orderProfit = salesAmount - purchaseCost - adSpend - orderCount * 3.25;

  return {
    id: `daily-sales-acceptance-${serial}`,
    date: dayjs().subtract(index % 8, "day").format("YYYY-MM-DD"),
    store: stores[index % stores.length],
    owner: owners[index % owners.length],
    sevenDayDates: Array.from({ length: 7 }, (_, day) => dayjs()
      .subtract(6 - day, "day")
      .format("YYYY-MM-DD")),
    sevenDaySales: Array.from({ length: 7 }, (_, day) => 8 + ((index + 2) * (day + 3)) % 42),
    msku: `MSKU-${serial}`,
    productId: `PID-${100_000 + number}`,
    sku: `DAILY-SALES-${serial}`,
    productName: `每日销售验收商品 ${serial}`,
    platform,
    currency,
    salesVolume,
    orderCount,
    salesAmount,
    sampleExcludedAmount: salesAmount * 0.96,
    returnCount: index % 6,
    refundAmount: (index % 6) * 19.9,
    returnRate30Days: 1.2 + (index % 8) * 0.55,
    adSpend,
    adRatio: (adSpend / salesAmount) * 100,
    wfsDeliveryFee: orderCount * 3.25,
    wfsDeliveryUnitPrice: 3.25,
    commission: salesAmount * 0.15,
    purchaseCost,
    purchaseUnitPriceCny: 28 + (index % 12) * 1.5,
    firstLegCost: orderCount * 1.8,
    firstLegUnitPriceCny: 6.8 + (index % 5) * 0.4,
    storageFee: 4.2 + (index % 10) * 0.75,
    storageUnitPrice: 0.35 + (index % 4) * 0.05,
    wfsAvailableInventory: 45 + (index * 19) % 360,
    legacyGrossProfit: orderProfit + 4.5,
    orderProfit,
    profitMargin: (orderProfit / salesAmount) * 100,
    roi: (orderProfit / purchaseCost) * 100,
    costStatus: statuses[index % statuses.length],
    systemOperationLog: `验收数据 ${serial}：系统日志待接口接入`,
    operationLog: `验收数据 ${serial}：运营日志待接口接入`,
  };
});
