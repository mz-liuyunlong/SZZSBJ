/** 回款对账列配置（照日记账）：店铺在左、审核状态 + 审核在右，固定；「操作 · 详情」始终在最右。只记在本浏览器。 */
import type { RuntimeColumnGroup } from "@/components/report-table/RuntimeColumnConfigDrawer";
import { readUserPreference, writeUserPreference } from "@/shared/preferences/userPreferenceCache";

export const RECON_COLUMN_PREF_KEY = "finance-payout-recon:columns";
export const RECON_COLUMN_PREF_VERSION = 2;
export const RECON_FIXED_KEYS = ["code", "review"];
export const RECON_DEFAULT_KEYS = ["code", "payDate", "org", "payee", "cycle", "payable", "arrived", "diff", "arrivedAt", "state", "caseNo", "nextAt", "follow", "review"];
export const RECON_COLUMN_GROUPS: RuntimeColumnGroup[] = [
  { title: "账单", fields: [{ key: "code", title: "店铺" }, { key: "payDate", title: "账单日" }, { key: "org", title: "收款机构" }, { key: "payee", title: "收款账户" }, { key: "account", title: "入账账户（日记账）" }, { key: "cycle", title: "账期" }] },
  { title: "金额", fields: [{ key: "payable", title: "应付" }, { key: "arrived", title: "到账" }, { key: "diff", title: "差额" }, { key: "arrivedAt", title: "到账时间" }, { key: "method", title: "配对方式" }] },
  { title: "回款与跟进", fields: [{ key: "state", title: "回款状态" }, { key: "caseNo", title: "Case 编号" }, { key: "nextAt", title: "下次跟进" }, { key: "follow", title: "最新跟进" }] },
  { title: "审核", fields: [{ key: "review", title: "审核状态 + 审核按钮（固定右侧）" }] },
];

export const readReconColumns = () => {
  const stored = readUserPreference<string[]>("anonymous", RECON_COLUMN_PREF_KEY, RECON_COLUMN_PREF_VERSION);
  return stored?.length ? stored : RECON_DEFAULT_KEYS;
};
export const writeReconColumns = (keys: string[]) => writeUserPreference("anonymous", RECON_COLUMN_PREF_KEY, RECON_COLUMN_PREF_VERSION, keys);
