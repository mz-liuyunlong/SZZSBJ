/** 订单审核列配置（复用 Listing 管理的列配置抽屉）：订单号在左、状态 + 操作在右固定；只记在本浏览器。 */
import type { RuntimeColumnGroup } from "@/components/report-table/RuntimeColumnConfigDrawer";
import { readUserPreference, writeUserPreference } from "@/shared/preferences/userPreferenceCache";

export const OR_COLUMN_PREF_KEY = "finance-order-review:columns";
export const OR_COLUMN_PREF_VERSION = 1;
export const OR_FIXED_KEYS = ["order", "status"];
export const OR_DEFAULT_KEYS = [
  "order", "store", "period", "item", "msku", "kind", "qty", "posted", "sales", "refund", "promotion", "commission",
  "wfsFee", "purchase", "head", "lastLeg", "source", "costTotal", "profit", "reasons", "status",
];
export const OR_COLUMN_GROUPS: RuntimeColumnGroup[] = [
  { title: "订单", fields: [
    { key: "order", title: "订单号 / 行" }, { key: "store", title: "店铺" }, { key: "period", title: "期（账单日）" },
    { key: "item", title: "ItemID" }, { key: "sku", title: "SKU" }, { key: "msku", title: "MSKU" }, { key: "gtin", title: "GTIN" },
    { key: "owner", title: "负责人" }, { key: "kind", title: "类型" }, { key: "fulfillment", title: "履约" }, { key: "qty", title: "件数" },
    { key: "posted", title: "结算时间" }, { key: "types", title: "交易类型" },
  ] },
  { title: "收入与费用（USD）", fields: [
    { key: "sales", title: "销售" }, { key: "refund", title: "退款" }, { key: "promotion", title: "促销折扣" },
    { key: "commission", title: "佣金" }, { key: "returnFee", title: "退货处理费" }, { key: "tax", title: "税费代收代缴" },
    { key: "wfsFee", title: "WFS 配送费" }, { key: "mcfFee", title: "MCF 费" }, { key: "settlement", title: "结算净额" },
  ] },
  { title: "货本（CNY）", fields: [
    { key: "purchase", title: "采购价" }, { key: "head", title: "头程" }, { key: "lastLeg", title: "尾程" },
    { key: "source", title: "成本来源" }, { key: "costTotal", title: "货本合计" }, { key: "costUsd", title: "货本（USD）" },
    { key: "fx", title: "汇率" }, { key: "profit", title: "利润（USD）" },
  ] },
  { title: "审核", fields: [
    { key: "reasons", title: "待审原因" }, { key: "version", title: "版本" }, { key: "status", title: "状态 + 操作（固定右侧）" },
  ] },
];

export const readOrderReviewColumns = () => {
  const stored = readUserPreference<string[]>("anonymous", OR_COLUMN_PREF_KEY, OR_COLUMN_PREF_VERSION);
  return stored?.length ? stored : OR_DEFAULT_KEYS;
};
export const writeOrderReviewColumns = (keys: string[]) => writeUserPreference("anonymous", OR_COLUMN_PREF_KEY, OR_COLUMN_PREF_VERSION, keys);
