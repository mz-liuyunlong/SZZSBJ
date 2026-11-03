/** Formatting helpers and labels shared by the 物流看板 table and drawer (8088 app-a.jsx). */
import type { Sev } from "./logisticsApi";

const nf = new Intl.NumberFormat("zh-CN");
export const fmt = (v?: number | null) => (v == null ? "—" : nf.format(v));
export const money = (v: number, currency = "USD") =>
  `${currency === "CNY" ? "¥" : "$"}${new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v || 0)}`;

export const daysBetween = (a: string, b: string) =>
  Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86400000);

export const ARR_SRC: Record<string, string> = {
  carrier: "众壹签收",
  wm_sign: "Walmart 签收",
  carrier_est: "众壹预约派送",
  "ata+cycle": "实际到港+周期",
  "atd+voyage+cycle": "实际开船+航程+周期",
  "eta+cycle": "预计到港+周期",
  lx_arrival: "领星预计到货",
  region_total: "发货日+地区兜底",
};

export const SEV_RANK: Record<Sev, number> = { high: 0, mid: 1, low: 2 };
