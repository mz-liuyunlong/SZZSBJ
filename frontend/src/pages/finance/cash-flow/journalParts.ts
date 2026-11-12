/** 拆分行在日记账表格里显示成子行（rocky 11-05：手续费要在列表里看得到）。
 * 子行带着原行的账户、对方；摘要没单独填就沿用原行的；类别、摘要、备注都能在子行上改。 */
import type { CashLine } from "@/pages/finance/localFinData";

export type PartRow = CashLine & { partOf: string; partIndex: number; fee?: string; parentSum: string; ownSum: boolean };
export type JournalRow = CashLine & { children?: PartRow[] };

export const isPartRow = (row: CashLine): row is PartRow => "partOf" in row;

/** 拆分行的折人民币（Rocky 11-10：拆分后要看到每行折多少人民币）：和后端 journal.part_cny 同一算法——
 * 先按绝对值、以分为单位按金额比例四舍五入（.5 进位），尾差落在最后一行，最后按原行符号还原；合计等于原行。
 * 后端 journal.part_cny 返回绝对值（approval_service._line_shares 按绝对值分摊），前端最后还原符号只用于显示。 */
export function partCny(line: CashLine): (number | null)[] {
  const parts = line.parts ?? [];
  if (line.cny == null || !line.amt || !parts.length) return parts.map(() => null);
  if (isRmb(line.cur)) return parts.map((part) => part.amt);
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
    const cnys = isRmb(line.cur) ? line.parts.map(() => null) : partCny(line);
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

/** 拆分行挂的审批单（刘云龙 #339 终审：整笔详情要看得到）。整笔已经挂了的不再列（不重复算）；
 * cny = 这一行折人民币（人民币流水就是这一行金额），用来和审批单比对。 */
/** 人民币 = CNY / CNH，两者视为同币种（刘云龙 #341：CNH 拆分后不能走外币换算）。 */
export const RMB_CODES = new Set(["CNY", "CNH"]);
export const isRmb = (cur: string) => RMB_CODES.has(cur);

export interface PartApprovalRef { ref: string; index: number; amt: number; cny: number | null }
export function partApprovalRefs(line: CashLine): PartApprovalRef[] {
  const parts = line.parts ?? [];
  const cnys = isRmb(line.cur) ? parts.map((part) => part.amt) : partCny(line);
  const seen = new Set(line.refs);
  const out: PartApprovalRef[] = [];
  parts.forEach((part, index) => {
    for (const ref of part.refs ?? []) {
      if (seen.has(ref)) continue;
      seen.add(ref);
      out.push({ ref, index, amt: part.amt, cny: cnys[index] });
    }
  });
  return out;
}

/** 详情「关联审批单（N）」的 N：整笔挂的 + 各拆分行挂的，去重。 */
export const approvalRefCount = (line: CashLine) => new Set([...line.refs, ...partApprovalRefs(line).map((item) => item.ref)]).size;

/** 比对用的「流水」：外币换成折人民币时，cnyFrom 记下换算前的币种和金额（刘云龙 #341：换算后还要知道
 * 是外币折过来的，汇率来源才不会丢——系统汇率折的不能当精确金额比）。 */
export type CompareLine = CashLine & { cnyFrom?: { cur: string; amt: number } };

/** 拆分行那张单比对用的「流水」：外币按这一行折人民币比，人民币按这一行金额比。 */
export function partCompareLine(line: CashLine, item: PartApprovalRef): CompareLine {
  if (!isRmb(line.cur) && item.cny != null) return { ...line, amt: item.cny, cur: "CNY", refs: [item.ref], cnyFrom: { cur: line.cur, amt: item.amt } };
  return { ...line, amt: item.amt, refs: [item.ref] };
}

/** 按拆分行分组的审批单（刘云龙 #339 第二轮终审）：同一行挂几张单时，这几张合起来和这一行比，不各自和整行比。 */
export interface PartApprovalGroup { index: number; refs: string[]; amt: number; cny: number | null }
export function partApprovalGroups(line: CashLine): PartApprovalGroup[] {
  const groups = new Map<number, PartApprovalGroup>();
  for (const item of partApprovalRefs(line)) {
    const group = groups.get(item.index) ?? { index: item.index, refs: [], amt: item.amt, cny: item.cny };
    group.refs.push(item.ref);
    groups.set(item.index, group);
  }
  return Array.from(groups.values());
}

/** 一组拆分行审批单比对用的「流水」：外币按这一行折人民币（缺汇率退回原币），人民币按这一行金额。 */
export function partGroupCompareLine(line: CashLine, group: PartApprovalGroup): CompareLine {
  if (!isRmb(line.cur) && group.cny != null) return { ...line, amt: group.cny, cur: "CNY", refs: group.refs, cnyFrom: { cur: line.cur, amt: group.amt } };
  return { ...line, amt: group.amt, refs: group.refs };
}

/** 整笔挂的审批单比对用的「流水」（刘云龙 #339 第二轮终审）：拆分行已经挂了单的那部分金额不算，只和剩下的比，
 * 和后端 approval_service._line_shares 的 rest 口径一致。外币按折人民币（缺汇率退回原币），人民币按原币。 */
export function wholeCompareLine(line: CashLine): CompareLine {
  const parts = line.parts ?? [];
  const taken = parts.map((part, index) => ({ part, index })).filter(({ part }) => (part.refs ?? []).length > 0);
  if (!taken.length || line.amt == null) return line;
  const sign = line.amt < 0 ? -1 : 1;
  const cents = (value: number) => Math.round(Math.abs(value) * 100);
  if (!isRmb(line.cur) && line.cny != null) {
    const cnys = partCny(line);
    const used = taken.reduce((sum, { index }) => sum + cents(cnys[index] ?? 0), 0);
    const usedOriginal = taken.reduce((sum, { part }) => sum + cents(part.amt), 0);
    return { ...line, amt: (sign * (cents(line.cny) - used)) / 100, cur: "CNY", cnyFrom: { cur: line.cur, amt: (sign * (cents(line.amt) - usedOriginal)) / 100 } };
  }
  const used = taken.reduce((sum, { part }) => sum + cents(part.amt), 0);
  return { ...line, amt: (sign * (cents(line.amt) - used)) / 100 };
}
