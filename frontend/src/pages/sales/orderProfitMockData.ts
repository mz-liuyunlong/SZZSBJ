/** Fixed, clearly labelled acceptance data aggregated by product ID for the no-API order-profit page. */
import dayjs from "dayjs";
import type {
  OrderProfitCostStatus,
  OrderProfitCurrency,
  OrderProfitPlatform,
  OrderProfitSourceRecord,
} from "@/pages/sales/orderProfitTypes";

const platforms: OrderProfitPlatform[] = ["Walmart", "TEMU", "Amazon"];
const owners = ["林晓", "周宁", "陈岚", "王舟"];
const stores = ["美国一店", "美国二店", "加拿大店", "验收测试店"];
const statuses: OrderProfitCostStatus[] = ["已完成", "待补齐", "异常", "部分缺失"];
const productNames = [
  "厨房密封夹",
  "硅胶收纳垫",
  "桌面理线器",
  "食品保鲜袋",
  "烘焙刮刀套装",
  "柜门挂钩",
  "包装标签纸",
  "抽屉分隔盒",
];

export const orderProfitSourceRecords: OrderProfitSourceRecord[] = Array.from({ length: 48 }, (_, productIndex) => {
  const productNumber = productIndex + 1;
  const serial = String(productNumber).padStart(3, "0");
  const productId = `PID-${300_000 + productNumber}`;
  const sku = `ORDER-PROFIT-${serial}`;
  const msku = `MSKU-PROFIT-${serial}`;
  const productName = `${productNames[productIndex % productNames.length]} ${serial}`;
  const platform = platforms[productIndex % platforms.length];
  const owner = owners[productIndex % owners.length];
  const store = stores[productIndex % stores.length];
  const currency: OrderProfitCurrency = productIndex % 5 === 0 ? "CNY" : "USD";

  return Array.from({ length: 8 }, (_, dayOffset) => {
    const date = dayjs().subtract(dayOffset, "day").format("YYYY-MM-DD");
    const salesVolume = 4 + ((productIndex + 3) * (dayOffset + 2)) % 38;
    const orderCount = Math.max(1, salesVolume - 1 - (productIndex % 4));
    const unitPrice = 16.9 + (productIndex % 9) * 1.85;
    const salesAmount = orderCount * unitPrice;
    const refundAmount = ((productIndex + dayOffset) % 7) * 4.35;
    const adSpend = salesAmount * (0.07 + (productIndex % 4) * 0.008);
    const wfsDeliveryFee = orderCount * (2.9 + (productIndex % 3) * 0.35);
    const commission = salesAmount * 0.15;
    const purchaseCost = salesAmount * (0.29 + (productIndex % 5) * 0.015);
    const firstLegCost = orderCount * (1.4 + (productIndex % 4) * 0.18);
    const storageFee = 2.8 + ((productIndex + dayOffset) % 9) * 0.42;
    const costStatus = statuses[(productIndex + dayOffset) % statuses.length];

    return {
      id: `order-profit-source-${serial}-${dayOffset}`,
      date,
      store,
      owner,
      msku,
      productId,
      sku,
      productName,
      platform,
      currency,
      salesVolume,
      orderCount,
      salesAmount,
      refundAmount,
      adSpend,
      wfsDeliveryFee,
      commission,
      purchaseCost,
      firstLegCost,
      storageFee,
      costStatus,
    };
  });
}).flat();
