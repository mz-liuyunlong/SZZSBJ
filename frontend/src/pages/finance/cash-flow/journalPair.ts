/** 手动配对（rocky 11-05）：候选怎么排、怎么把几笔配成一对 / 取消配对。组件在 LineActions、JournalBatch。 */
import { asLive, cashErrorText, postLineEvent, type LiveCashLine } from "@/pages/finance/cash-flow/journalApi";
import type { CashLine } from "@/pages/finance/localFinData";

export const PAIR_DAYS = 15;
const dayGap = (a: string, b: string) => Math.abs(new Date(a).getTime() - new Date(b).getTime()) / 86_400_000;
/** 搜索用的文字：账户名、金额（带不带千分位都行）、摘要、备注、对方、日期。 */
const searchText = (line: CashLine, accountName: string) => {
  const amount = Math.abs(line.amt ?? 0);
  return [accountName, line.acct, amount.toFixed(2), amount.toLocaleString("en-US", { minimumFractionDigits: 2 }), String(line.amt ?? ""), line.sum, line.memo, line.party ?? "", line.date].join(" ").toLowerCase();
};

/** 手动配对的候选：另一个账户、一出一进、还没配对、没剔除；按金额差、日期差排。
 * 不搜索时只列 15 天内的前 30 笔；输入关键词后不限日期，在全部流水里按账户 / 金额 / 摘要 / 备注 / 对方搜（空格隔开的几个词都要命中），最多 50 笔。 */
export function pairCandidates(line: CashLine, all: CashLine[], keyword = "", accountName: (acct: string) => string = (acct) => acct) {
  const amount = line.amt ?? 0;
  const words = keyword.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return all
    .filter((other) => other.id !== line.id && other.acct !== line.acct && !other.pair && other.cat !== "X01" && !other.excl && asLive(other) && (other.amt ?? 0) * amount < 0)
    .filter((other) => (words.length ? words.every((word) => searchText(other, accountName(other.acct)).includes(word.replace(/,/g, "")) || searchText(other, accountName(other.acct)).includes(word)) : dayGap(other.date, line.date) <= PAIR_DAYS))
    .map((other) => ({ line: other, diff: other.cur === line.cur ? Math.abs(Math.abs(other.amt ?? 0) - Math.abs(amount)) : Number.POSITIVE_INFINITY, days: dayGap(other.date, line.date) }))
    .sort((a, b) => a.diff - b.diff || a.days - b.days)
    .slice(0, words.length ? 50 : 30);
}

/** 把几笔配成一对（各发一次 pair，同一个配对号）；已终审的要先撤销终审。返回失败原因，全成功返回空数组。 */
export async function pairLines(lines: LiveCashLine[], kind: "pair" | "unpair", reason?: string) {
  const pairId = `M${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`.toUpperCase();
  const failed: string[] = [];
  for (const line of lines) {
    try {
      await postLineEvent(line, kind, kind === "pair" ? { payload: { pair_id: pairId } } : { reason });
    } catch (error) {
      failed.push(`${line.date} ${line.id.split(":").pop()}：${cashErrorText(error)}`);
    }
  }
  return failed;
}
