/** 资金流水（账户总览 / 日记账）共用的类型、常量和纯函数；从 FinanceCashFlowPage.tsx 原样搬出。 */
import { type ProColumns } from "@ant-design/pro-components";
import { type RuntimeColumnGroup } from "@/components/report-table/RuntimeColumnConfigDrawer";
import { asLive } from "@/pages/finance/cash-flow/journalApi";
import { type CompareLine, RMB_CODES } from "@/pages/finance/cash-flow/journalParts";
import { type CashAlert, type FsDetail } from "@/pages/finance/cash-flow/data";
import { fmtMoney, type CashLine, type CashSnapshot, type FeishuApproval } from "@/pages/finance/localFinData";
import { readUserPreference } from "@/shared/preferences/userPreferenceCache";

export type CashFlowView = "accounts" | "journal" | "stock";
/* 日记账统计卡（Rocky 11-04）：只留 全部 / 待初审 / 待终审 / 异常 / 已剔除；待分类改用「类别」筛选里的「待分类」。 */
export const REVIEW_CARDS = ["all", "todo", "ok1", "alert", "excluded"] as const;
export type ReviewCard = (typeof REVIEW_CARDS)[number];
export interface JournalHandoff { account?: string; card?: ReviewCard; cats?: string[]; month?: string; alerts?: string[] }

export const HANDOFF_KEY = "finance:cash-journal:handoff";
export const OPEN_STATES = ["未付", "部分已付", "金额不符", "金额缺失"];
export const STATE_COLOR: Record<string, string> = { 已付: "green", 未付: "red", 部分已付: "orange", 金额不符: "volcano", 已取消: "default", 金额缺失: "purple", 待定: "gold" };
export const KIND_COLOR: Record<string, string> = { 对公: "blue", 对私: "orange", 现金: "orange", 平台: "purple", 其他: "gold" };
export const EMPTY = "—";

/* 关联审批单下拉的候选：流水起始月及以后发起、已审批通过、还没付清的单（Rocky 11-02 20:02：之前的单当时已在系统外付款）。 */
export const isOpenApproval = (item: FeishuApproval, data: CashSnapshot) => OPEN_STATES.includes(item.state) && item.status === "已同意" && (item.start || "") >= `${data.meta.start}-01`;
/* 待分类：没有类别、也没拆分过（拆分过的流水类别在明细里，不算待分类）。日记账卡片 / 类别筛选 / 账户总览三处同一口径。 */
export const isUncat = (line: CashLine) => !line.cat && !line.parts?.length;
export const NO_FLOW_TYPE = "审批单无付款流水";
/* 审批单全集：本期快照里的单 + 飞书只读测试拉到、不在快照里的已同意单（多是流水截止日之后的单）。 */
export function mergeFeishu(data: CashSnapshot, details: Record<string, FsDetail>): FeishuApproval[] {
  const known = new Set(data.feishu.map((item) => item.serial));
  const extra: FeishuApproval[] = Object.values(details).filter((d) => !known.has(d.serial) && d.status === "已同意" && d.amount != null)
    .map((d) => ({ serial: d.serial, kind: d.kind, status: d.status, start: d.start.slice(0, 10), end: d.end.slice(0, 10), applicant: "", reason: d.reason, amount: d.amount, cur: d.cur, pay: d.pay, payee: d.payee, bank: d.bank, last4: d.last4, items: d.items, rel: "", invoice: d.invoice, src: "飞书只读测试", cat: "", masked: false, paid: [], paid_sum: 0, cny: d.amount, state: "未付" }));
  return [...data.feishu, ...extra];
}
/* 审批单无付款流水（Rocky 11-04）：流水起始月及以后发起、飞书已同意、没有任何流水关联的单——只会是流水没导全。
   日期用飞书完成（同意）日期 end，没有时退回发起日期 start；没有账户。日记账和账户总览都用这一个函数。 */
/* Rocky 11-10：备用金核销本来就没有付款流水，不报；审批通过 15 天内也先不报，给付款留时间（超过 15 天还没对上才算异常）。 */
export const NO_FLOW_GRACE_DAYS = 15;
const NO_FLOW_KINDS_SKIPPED = ["备用金核销"];
const daysBetween = (from: string, to: string) => Math.floor((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
export function noFlowAlerts(data: CashSnapshot, approvals: FeishuApproval[], today: string = new Date().toISOString().slice(0, 10)): CashAlert[] {
  const linked = new Set(data.lines.flatMap((line) => [...line.refs, ...(line.parts ?? []).flatMap((part) => part.refs ?? [])]));
  return approvals.filter((item) => item.status === "已同意" && (item.start || "") >= `${data.meta.start}-01` && !linked.has(item.serial)
    && !NO_FLOW_KINDS_SKIPPED.some((kind) => item.kind.includes(kind))
    && !((item.end || item.start) && daysBetween((item.end || item.start).slice(0, 10), today) < NO_FLOW_GRACE_DAYS))
    .sort((a, b) => a.serial.localeCompare(b.serial))
    .map((item) => {
      const agreed = item.end || item.start || "";
      return { type: NO_FLOW_TYPE, sev: "", acct: "", date: agreed, amt: item.amount, serial: item.serial, ref: item.serial, id: `${NO_FLOW_TYPE}|${item.serial}`, hint: false,
        msg: `审批单 ${item.serial}（${item.kind}）${item.masked ? "" : ` ${fmtMoney(item.amount, item.cur)}`}${item.payee ? ` · 收款人 ${item.payee}` : ""} · 飞书 ${agreed || EMPTY} 同意` };
    });
}
/* 找不到流水的异常按当前账户、月份过滤：没有账户的，账户选「全部」时才算；月份按这条记录自己的 date（审批单 = 同意日期，要剔除的款 = 剔除记录日期）。 */
export const orphanInScope = (item: CashAlert, accounts: string[], month: string) =>
  (accounts.length === 0 || (Boolean(item.acct) && accounts.includes(item.acct))) && (!month || item.date.slice(0, 7) === month);
/** 能点「确认记为手续费」的异常类型 → 切出来的手续费层（fee_layer）。派安盈提现到账差额以后在这里加一条。 */
export const FEE_ALERT_TYPES: Record<string, string> = { "转账到账差额": "fee", "派安盈提现到账差额": "payoneer", "PingPong 付款手续费": "pingpong" };
export const isExcluded = (line: CashLine) => line.cat === "X01" || Boolean(line.excl) || Boolean(line.parts?.some((part) => part.cat === "X01"));
/* 审核：初审（财务专员）→ 终审（财务主管）。初审不通过留在专员处；终审不通过驳回到待初审，都必须填原因。 */
export type ReviewStage = "todo" | "rej1" | "ok1" | "rej2" | "ok2";
export interface ReviewMark { stage: ReviewStage; reason?: string; note?: string }
export const REVIEW_TAG: Record<ReviewStage, { color: string; text: string }> = {
  todo: { color: "default", text: "待初审" },
  rej1: { color: "red", text: "初审不通过" },
  ok1: { color: "blue", text: "待终审" },
  rej2: { color: "volcano", text: "终审驳回 · 待初审" },
  ok2: { color: "green", text: "已终审" },
};
export const baseReview = (line: CashLine): ReviewMark => {
  const live = asLive(line);
  if (live) return { stage: live.stage as ReviewStage, reason: live.stageReason, note: live.reviewNote };
  return { stage: line.ok2 ? "ok2" : line.ok ? "ok1" : "todo" };
};
export const isFirstPending = (stage: ReviewStage) => stage === "todo" || stage === "rej1" || stage === "rej2";
export const REVIEW_STAGE_OPTIONS = (Object.keys(REVIEW_TAG) as ReviewStage[]).map((stage) => ({ value: stage, label: REVIEW_TAG[stage].text }));
export const PREVIEW_ACTION_TIP = "本地预览：审核只记在本页，刷新即还原，不写库";

/* ---------------------------------------------------------------- 关联审批单：字段 + 凭证 + 与流水逐项比对（Rocky 11-03 定稿）
 * 日记账不强制匹配审批单（没有就显示「无审批单」）；审批金额和流水金额有差额，初审必须写差额说明，终审看得到。
 * 比对只用文字字段：金额、收款人 vs 对方、收款账号尾号 vs 对方账号尾号、办理完成时间 vs 付款日期；不一致标红，图片给主管目视核对。第一版不做 OCR。 */
export interface ApprovalView {
  serial: string; kind: string; status: string; state?: string; start: string; end: string; handled: string; applicant: string;
  reason: string; amount: number | null; cur: string; payee: string; bank: string; last4: string; invoice: string; pay: string;
  items: { c: string; a: number | null }[]; detail?: FsDetail; masked: boolean; known: boolean;
}
export const viewOf = (serial: string, item?: FeishuApproval, detail?: FsDetail): ApprovalView => ({
  serial,
  kind: detail?.kind || item?.kind || "",
  status: detail?.status || item?.status || "",
  state: item?.state,
  start: detail?.start || item?.start || "",
  end: detail?.end || item?.end || "",
  handled: detail?.handled || "",
  applicant: detail?.applicant || item?.applicant || "",
  reason: detail?.reason || item?.reason || "",
  amount: detail?.amount ?? item?.amount ?? null,
  cur: detail?.cur || item?.cur || "CNY",
  payee: detail?.payee || item?.payee || "",
  bank: detail?.bank || item?.bank || "",
  last4: detail?.last4 || item?.last4 || "",
  invoice: detail?.invoice || item?.invoice || "",
  pay: detail?.pay || item?.pay || "",
  items: detail?.items.length ? detail.items : item?.items ?? [],
  detail,
  masked: Boolean(item?.masked),
  known: Boolean(item || detail),
});
export const norm = (text?: string) => (text ?? "").replace(/[\s()（）·.,，、]/g, "").toLowerCase();
export const dayGap = (a: string, b: string) => Math.round(Math.abs(Date.parse(a.slice(0, 10)) - Date.parse(b.slice(0, 10))) / 86400000);
/** 精确的折人民币来源：派安盈实际汇率、人工改（和后端 journal.FX_EXACT_SOURCES 一致）。 */
const EXACT_FX = new Set(["payoneer", "manual"]);
/** 和审批单比的流水金额（Rocky 11-12：人民币审批单对美元流水，以前直接拿原币相减，差额没意义）。
 * 币种相同（CNY / CNH 算同一种；审批单没写币种按同币种）→ 原币；审批单都是人民币、流水是外币 → 流水折人民币；
 * 别的（币种不同又没折人民币、几张单币种混着）→ null，没法比。exact = 折人民币用的是精确来源。 */
export interface CompareAmount { amt: number; cur: string; converted: boolean; exact: boolean; original: { cur: string; amt: number } }
/** 拆分行 / 整笔扣拆分行已经换成人民币的（cnyFrom 有值）也算「折过来的」：exact 照样看这笔的汇率来源
 * （刘云龙 #341：拆分后用领星月汇率折的，不能当精确金额）；审批单是原币的，按换算前的原币比。 */
export function compareAmount(line: CompareLine, views: ApprovalView[]): CompareAmount | null {
  if (line.amt == null) return null;
  const curs = views.filter((view) => view.amount != null).map((view) => view.cur);
  const exact = EXACT_FX.has(asLive(line)?.fxSource ?? "");
  const from = line.cnyFrom;
  if (from && curs.length && curs.every((cur) => cur === from.cur)) {
    return { amt: Math.abs(from.amt), cur: from.cur, converted: false, exact: true, original: from };
  }
  const original = from ?? { cur: line.cur, amt: line.amt };
  const lineRmb = RMB_CODES.has(line.cur);
  const same = curs.every((cur) => !cur || cur === line.cur || (lineRmb && RMB_CODES.has(cur)));
  if (same) return { amt: Math.abs(line.amt), cur: line.cur, converted: Boolean(from), exact: from ? exact : true, original };
  if (!lineRmb && line.cny != null && curs.every((cur) => RMB_CODES.has(cur))) {
    return { amt: Math.abs(line.cny), cur: "CNY", converted: true, exact, original };
  }
  return null;
}
/** 审批金额合计 − 流水金额（取绝对值，币种按 compareAmount）；没有审批单、审批单没金额、币种没法比时为 null。 */
export const amountDiff = (line: CompareLine, views: ApprovalView[]) => {
  const amounts = views.map((view) => view.amount).filter((value): value is number => value != null);
  const base = compareAmount(line, views);
  if (!views.length || !amounts.length || base == null) return null;
  return Math.round((amounts.reduce((sum, value) => sum + value, 0) - base.amt) * 100) / 100;
};
export interface CompareRow { key: string; item: string; approval: string; line: string; ok: boolean | null; result: string }
export const compareRows = (line: CompareLine, views: ApprovalView[]): CompareRow[] => {
  const diff = amountDiff(line, views);
  const base = compareAmount(line, views);
  const original = base ? fmtMoney(Math.abs(base.original.amt), base.original.cur) : fmtMoney(line.amt == null ? null : Math.abs(line.amt), line.cur);
  const hasAmount = views.some((view) => view.amount != null);
  const amountResult = !hasAmount ? "审批单没金额"
    : diff == null ? "币种不同、流水还没折人民币，看凭证"
    : Math.abs(diff) < 0.005 ? "一致"
    : base?.converted && !base.exact ? `按系统汇率折算差 ${fmtMoney(diff, "CNY")}；约定汇率不同请先改折人民币`
    : `差额 ${fmtMoney(diff, base?.cur ?? line.cur)}`;
  const rows: CompareRow[] = [{
    key: "amt", item: "金额", approval: views.map((view) => (view.amount == null ? "没金额" : fmtMoney(view.amount, view.cur))).join(" + "),
    line: base?.converted ? `${original}（折 ${fmtMoney(base.amt, "CNY")}）` : original,
    ok: diff == null ? null : Math.abs(diff) < 0.005, result: amountResult,
  }];
  views.forEach((view) => {
    const tag = views.length > 1 ? ` · ${view.serial}` : "";
    const payeeOk = !view.payee || !line.party ? null : norm(view.payee) === norm(line.party) || norm(line.party).includes(norm(view.payee)) || norm(view.payee).includes(norm(line.party));
    rows.push({ key: `payee-${view.serial}`, item: `收款人 / 对方${tag}`, approval: view.payee || EMPTY, line: line.party || EMPTY, ok: payeeOk, result: payeeOk == null ? "缺一边，看凭证" : payeeOk ? "一致" : "不一致" });
    rows.push({ key: `last4-${view.serial}`, item: `账号尾号${tag}`, approval: view.last4 ? `…${view.last4}` : EMPTY, line: EMPTY, ok: null, result: "流水暂无对方账号（银行明细还没取这一列），看凭证" });
    const done = view.handled || view.end;
    const gap = done ? dayGap(done, line.date) : null;
    rows.push({ key: `time-${view.serial}`, item: `办理完成 / 付款日期${tag}`, approval: done || EMPTY, line: `${line.date} ${line.time ?? ""}`.trim(), ok: gap == null ? null : gap <= 1, result: gap == null ? "审批单还没办理完成" : gap <= 1 ? (gap ? "差 1 天（银行入账次日，算一致）" : "同一天") : `差 ${gap} 天` });
  });
  return rows;
};

/* 日记账列配置：日期在左、审核状态 + 审核在右，三者固定。配对 / 标记不在表格展示（Rocky 11-02 19:13），详情里只读保留。 */
export const JOURNAL_COLUMN_PREF_KEY = "finance-cash-journal:columns";
export const JOURNAL_COLUMN_PREF_VERSION = 4;
export const JOURNAL_FIXED_KEYS = ["date", "review"];
export const JOURNAL_DEFAULT_KEYS = ["date", "acct", "sum", "memo", "party", "amt", "alert", "cny", "bal", "cat", "refs", "review"];
export const JOURNAL_COLUMN_GROUPS: RuntimeColumnGroup[] = [
  { title: "流水", fields: [{ key: "date", title: "日期" }, { key: "acct", title: "账户" }, { key: "sum", title: "摘要" }, { key: "memo", title: "备注" }, { key: "party", title: "对方" }] },
  { title: "金额", fields: [{ key: "amt", title: "金额" }, { key: "cny", title: "折人民币" }, { key: "bal", title: "余额" }] },
  { title: "分类与单据", fields: [{ key: "cat", title: "类别" }, { key: "refs", title: "审批单" }, { key: "alert", title: "异常" }] },
  { title: "审核", fields: [{ key: "review", title: "审核状态 + 审核按钮（固定右侧）" }] },
];
export const readJournalColumns = () => {
  const stored = readUserPreference<string[]>("anonymous", JOURNAL_COLUMN_PREF_KEY, JOURNAL_COLUMN_PREF_VERSION);
  return stored?.length ? stored : JOURNAL_DEFAULT_KEYS;
};

export const icon = (text: string) => <span className="management-stat-card__mark">{text}</span>;
export const scrollX = <T,>(columns: ProColumns<T>[]) => columns.reduce((sum, column) => sum + Number(column.width ?? 120), 0);

/* 日记账页签可能已经开着（页签切换不重新挂载），所以除了存 sessionStorage，还发一个事件让已打开的日记账立即套用。 */
export const HANDOFF_EVENT = "finance:cash-journal:handoff";
export function writeHandoff(value: JournalHandoff) {
  try { sessionStorage.setItem(HANDOFF_KEY, JSON.stringify(value)); } catch { /* 便利功能，失败忽略 */ }
  window.dispatchEvent(new Event(HANDOFF_EVENT));
}
export function readHandoff(): JournalHandoff {
  try {
    const raw = sessionStorage.getItem(HANDOFF_KEY);
    sessionStorage.removeItem(HANDOFF_KEY);
    const value: JournalHandoff = raw ? JSON.parse(raw) : {};
    return { ...value, card: REVIEW_CARDS.includes(value.card as ReviewCard) ? value.card : undefined };
  } catch {
    return {};
  }
}
