/** 拆分行在日记账表格里显示成子行（rocky 11-05：手续费要在列表里看得到）。
 * 子行带着原行的账户、对方；摘要没单独填就沿用原行的；类别、摘要、备注都能在子行上改。 */
import type { CashLine } from "@/pages/finance/localFinData";

export type PartRow = CashLine & { partOf: string; partIndex: number; fee?: string; parentSum: string; ownSum: boolean };
export type JournalRow = CashLine & { children?: PartRow[] };

export const isPartRow = (row: CashLine): row is PartRow => "partOf" in row;

/** 拆分行的折人民币（Rocky 11-10：拆分后要看到每行折多少人民币）：和后端 journal.part_cny 同一算法——
 * 先按绝对值、以分为单位按金额比例四舍五入（.5 进位），尾差落在最后一行，最后按原行符号还原；合计等于原行。 */
export function partCny(line: CashLine): (number | null)[] {
  const parts = line.parts ?? [];
  if (line.cny == null || !line.amt || !parts.length) return parts.map(() => null);
  if (line.cur === "CNY") return parts.map((part) => part.amt);
  const sign = line.cny < 0 ? -1 : 1;
  const total = Math.round(Math.abs(line.cny) * 100);
  const whole = Math.abs(line.amt);
  let used = 0;
  return parts.map((part, index) => {
    const cents = index === parts.length - 1 ? total - used : Math.round((total * Math.abs(part.amt)) / whole);
    used += cents;
    return (sign * cents) / 100;
  });
}

/** 有拆分的流水带上子行（id = 流水 id#p 行号）。 */
export function withPartRows(rows: CashLine[]): JournalRow[] {
  return rows.map((line) => {
    if (!line.parts?.length) return line;
    const cnys = line.cur === "CNY" ? line.parts.map(() => null) : partCny(line);
    return { ...line, children: line.parts.map((part, index): PartRow => ({ ...line, id: `${line.id}#p${index + 1}`, amt: part.amt, cny: cnys[index], bal: null, cat: part.cat, parts: undefined, flags: [], partOf: line.id, partIndex: index, fee: part.fee, sum: part.sum ?? line.sum, memo: part.memo ?? "", parentSum: line.sum, ownSum: Boolean(part.sum) })) };
  });
}

/** 类别筛选：整笔类别或任一拆分行类别命中都算。 */
export const lineHasCat = (line: CashLine, code: string) => line.cat === code || Boolean(line.parts?.some((part) => part.cat === code));

/** 备注列里的拆分说明（rocky 11-05）：「拆分 2 行：-9,986.80 T02 / -13.20 手续费 F01」。 */
export function splitSummary(line: CashLine) {
  const parts = line.parts ?? [];
  const money = (value: number) => value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `拆分 ${parts.length} 行：${parts.map((part) => `${money(part.amt)} ${part.fee ? "手续费 " : ""}${part.cat || "待分类"}`).join(" / ")}`;
}

const round2 = (value: number) => Math.round(value * 100) / 100;

/** 按人民币拆（Rocky 11-10）：付美金、到账人民币的，按这笔的实际汇率（折人民币 ÷ 金额）把每行人民币换回原币；
 * 前几行四舍五入到分，最后一行取剩余，保证原币合计正好等于这笔金额。 */
export function cnyToOriginal(cnyRows: number[], total: number, totalCny: number): number[] {
  if (!cnyRows.length || !totalCny) return [];
  const rate = totalCny / total;
  const head = cnyRows.slice(0, -1).map((value) => round2(value / rate));
  return [...head, round2(total - head.reduce((sum, value) => sum + value, 0))];
}
