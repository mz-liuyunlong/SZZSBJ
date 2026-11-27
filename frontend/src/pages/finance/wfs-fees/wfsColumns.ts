/** WFS 费用明细列配置（照回款对账）：店铺固定左、操作固定右；只记在本浏览器。 */
import type { RuntimeColumnGroup } from "@/components/report-table/RuntimeColumnConfigDrawer";
import { readUserPreference, writeUserPreference } from "@/shared/preferences/userPreferenceCache";

const PREF_KEY = "finance-wfs-fees:columns";
const PREF_VERSION = 1;

export const WFS_FIXED_KEYS = ["store", "actions"];
export const WFS_DEFAULT_KEYS = [
  "store", "report_date", "date_charged", "transaction_date", "fee_type", "reason_code", "po", "gtin", "item_id", "msku", "local_sku",
  "quantity", "amount", "share", "attribution", "basis", "source", "detail", "actions",
];
export const WFS_COLUMN_GROUPS: RuntimeColumnGroup[] = [
  { title: "期间", fields: [{ key: "store", title: "店铺（固定左侧）" }, { key: "report_date", title: "账单日" }, { key: "date_charged", title: "扣费日期" }, { key: "transaction_date", title: "交易日期" }] },
  { title: "费用", fields: [{ key: "fee_type", title: "费用类型" }, { key: "reason_code", title: "原因" }, { key: "po", title: "订单 / 货件号" }, { key: "quantity", title: "数量" }, { key: "amount", title: "金额（USD）" }] },
  { title: "商品", fields: [{ key: "gtin", title: "商品条码" }, { key: "item_id", title: "商品 ID" }, { key: "msku", title: "店铺 SKU" }, { key: "local_sku", title: "本地 SKU" }] },
  { title: "归属", fields: [{ key: "share", title: "分摊" }, { key: "attribution", title: "归属" }, { key: "basis", title: "依据" }, { key: "source", title: "来源" }, { key: "detail", title: "说明" }, { key: "actions", title: "操作（固定右侧）" }] },
];

export const readWfsColumns = () => {
  const stored = readUserPreference<string[]>("anonymous", PREF_KEY, PREF_VERSION);
  return stored?.length ? stored : WFS_DEFAULT_KEYS;
};
export const writeWfsColumns = (keys: string[]) => writeUserPreference("anonymous", PREF_KEY, PREF_VERSION, keys);
