/** 资金 汇率页面的数据整理，单独放一个文件方便测试。 */
import { BackendRequestError } from "@/api/backendApi";
import { cashErrorText } from "@/pages/finance/cash-flow/journalApi";

export interface FxRateRow { month: string; rate: string | number | null }
export interface FxSyncState { run_id: string | null; status: string; error_code: string | null }

export const FX_SOURCE_LABEL = "领星·月汇率（我的汇率）";
/** 页面上币种直接写中文；CNY、CNH、RMB 现阶段汇率一样，都写人民币。 */
export const FX_PAIR_LABEL = "美元→人民币";

/** 合格的汇率：正数的字符串。这里不转 Number，后端给的 10 位小数一位不丢。 */
const rateString = (rate: FxRateRow["rate"]): string | null => {
  const text = rate == null ? "" : String(rate);
  return /^\d+(\.\d+)?$/.test(text) && /[1-9]/.test(text) ? text : null;
};

/** 比较用：7.0000000000 和 7 算同一个值，只去掉写法上的 0，不做数字换算。 */
const rateKey = (rate: FxRateRow["rate"]): string | null => {
  const text = rateString(rate);
  if (text == null) return null;
  return (text.includes(".") ? text.replace(/\.?0+$/, "") : text).replace(/^0+(?=\d)/, "");
};

/** 页面显示到小数点后 2 位，第 3 位四舍五入；按字符串算，不经过浮点数。空值、0 和不是数字都显示「—」。 */
export const fxRateText = (rate: FxRateRow["rate"]): string => {
  const text = rateString(rate);
  if (text == null) return "—";
  const [whole, fraction = ""] = text.split(".");
  const digits = fraction.padEnd(3, "0");
  const cents = BigInt(whole + digits.slice(0, 2)) + BigInt(digits[2] >= "5" ? 1 : 0);
  const shown = cents.toString().padStart(3, "0");
  return `${shown.slice(0, -2)}.${shown.slice(-2)}`;
};

/** 可选年份：有数据的年份加上今年，新的在前。 */
export const fxYears = (rows: FxRateRow[], currentYear: number): number[] =>
  [...new Set([currentYear, ...rows.map((row) => Number(row.month.slice(0, 4)))])].sort((left, right) => right - left);

/** 翻页只在可选年份里走（years 新的在前）：older 是上一年，newer 是下一年；到头返回 null。 */
export const fxAdjacentYear = (years: number[], year: number, direction: "older" | "newer"): number | null =>
  years[years.indexOf(year) + (direction === "older" ? 1 : -1)] ?? null;

/** 一页一个完整年份：1 到 12 月都有一行，没数据的月份汇率为空。 */
export const fxYearRows = (rows: FxRateRow[], year: number): FxRateRow[] => {
  const byMonth = new Map(rows.map((row) => [row.month, row.rate]));
  return Array.from({ length: 12 }, (_, index) => {
    const month = `${year}-${String(index + 1).padStart(2, "0")}`;
    return { month, rate: byMonth.get(month) ?? null };
  });
};

/** 对比同步前后的月汇率：原来没有算新增，数值变了算更新，一样算未变；前后都没有不计。 */
export const diffFxRates = (before: FxRateRow[], after: FxRateRow[]) => {
  const old = new Map(before.map((row) => [row.month, rateKey(row.rate)]));
  const result = { added: 0, updated: 0, unchanged: 0 };
  after.forEach((row) => {
    const previous = old.get(row.month) ?? null;
    const current = rateKey(row.rate);
    if (previous == null && current == null) return;
    if (previous == null) result.added += 1;
    else if (previous === current) result.unchanged += 1;
    else result.updated += 1;
  });
  return result;
};

export const fxSyncDoneText = ({ added, updated, unchanged }: ReturnType<typeof diffFxRates>) =>
  `同步完成：新增 ${added} 条，更新 ${updated} 条，未变 ${unchanged} 条`;

const FAILURE_REASONS: Record<string, string> = {
  SYNC_FX_RUNTIME_NOT_AUTHORIZED: "这个环境还没开放领星接口",
  SYNC_FX_ALL_MONTHS_EMPTY: "领星所有月份都没有返回汇率",
  SYNC_FX_RESPONSE_FAILED: "领星返回了错误",
  SYNC_FX_REQUEST_FAILED: "请求领星失败，可能是网络问题，请稍后再试",
  SYNC_FX_INVALID_ROW: "领星返回的数据不合格",
  SYNC_FX_GOVERNANCE_DISABLED: "汇率同步任务已被关闭",
  SYNC_FX_EXECUTION_NOT_AUTHORIZED: "汇率同步任务已被关闭",
  SYNC_CONFIG_DISABLED: "汇率同步任务已被关闭",
  SYNC_INTERFACE_DISABLED: "汇率同步任务已被关闭",
};

/** 失败时已同步的月份会保留，只是没跑完。 */
export const fxSyncFailedText = (code: string | null): string => {
  const reason = code ? FAILURE_REASONS[code] ?? `错误代码 ${code}` : "原因未知";
  return `同步失败：${reason}。已同步的月份会保留，可以重新同步`;
};

export const FX_SYNC_SUPER_ADMIN_ONLY = "只有超级管理员能同步";

/** 后端拒绝读取（403）时说明是没有权限，不说读取失败。 */
export const fxReadDenied = (error: unknown): boolean => error instanceof BackendRequestError && error.status === 403;

export const fxSyncErrorText = (error: unknown): string => {
  if (error instanceof BackendRequestError && error.status === 403) return FX_SYNC_SUPER_ADMIN_ONLY;
  if (error instanceof BackendRequestError && error.status === 409) return "汇率同步任务还没打开，请联系管理员";
  if (error instanceof BackendRequestError && error.status === 503) return "任务队列暂时不可用，请稍后再试";
  return cashErrorText(error);
};
