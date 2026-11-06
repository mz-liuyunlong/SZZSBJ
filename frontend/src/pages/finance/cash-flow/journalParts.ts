/** 拆分行在日记账表格里显示成子行（rocky 11-05：手续费要在列表里看得到）。
 * 子行带着原行的账户、对方；摘要没单独填就沿用原行的；类别、摘要、备注都能在子行上改。 */
import type { CashLine } from "@/pages/finance/localFinData";

export type PartRow = CashLine & { partOf: string; partIndex: number; fee?: string; parentSum: string; ownSum: boolean };
export type JournalRow = CashLine & { children?: PartRow[] };

export const isPartRow = (row: CashLine): row is PartRow => "partOf" in row;

/** 有拆分的流水带上子行（id = 流水 id#p 行号）。 */
export function withPartRows(rows: CashLine[]): JournalRow[] {
  return rows.map((line) => (line.parts?.length
    ? { ...line, children: line.parts.map((part, index): PartRow => ({ ...line, id: `${line.id}#p${index + 1}`, amt: part.amt, cny: null, bal: null, cat: part.cat, parts: undefined, flags: [], partOf: line.id, partIndex: index, fee: part.fee, sum: part.sum ?? line.sum, memo: part.memo ?? "", parentSum: line.sum, ownSum: Boolean(part.sum) })) }
    : line));
}

/** 类别筛选：整笔类别或任一拆分行类别命中都算。 */
export const lineHasCat = (line: CashLine, code: string) => line.cat === code || Boolean(line.parts?.some((part) => part.cat === code));

/** 备注列里的拆分说明（rocky 11-05）：「拆分 2 行：-9,986.80 T02 / -13.20 手续费 F01」。 */
export function splitSummary(line: CashLine) {
  const parts = line.parts ?? [];
  const money = (value: number) => value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `拆分 ${parts.length} 行：${parts.map((part) => `${money(part.amt)} ${part.fee ? "手续费 " : ""}${part.cat || "待分类"}`).join(" / ")}`;
}
