/** 回款对账页面显示用的状态文字和小工具（口径：Rocky 2026-11-10）。 */
import dayjs from "dayjs";
import type { PayState, ReconRow, ReviewStage } from "./reconApi";

export const PAY_STATE: Record<PayState, { color: string; text: string; tip: string }> = {
  paid: { color: "green", text: "已打款", tip: "日记账里配上了这一期的到账，金额差在 ±0.01 以内" },
  mismatch: { color: "red", text: "打款异常 · 金额不符", tip: "配上了到账，但和应付差超过 ±0.01；要跟进" },
  unpaid: { color: "red", text: "打款异常 · 未到账", tip: "账单日过了 7 天还没配上到账；要跟进" },
  waiting: { color: "gold", text: "等到账", tip: "账单日后 7 天内，还没配上到账" },
  not_due: { color: "default", text: "未到账单日", tip: "还没到这一期的账单日" },
  no_pay: { color: "default", text: "不需打款", tip: "这一期不可付或应付 ≤ 0，沃尔玛不打款" },
  voided: { color: "red", text: "账单作废", tip: "这一期的明细在领星全部被删除或作废，请核实" },
};

export const REVIEW_TAG: Record<ReviewStage, { color: string; text: string }> = {
  todo: { color: "default", text: "待初审" },
  ok1: { color: "blue", text: "待终审" },
  rej2: { color: "volcano", text: "终审驳回 · 待初审" },
  ok2: { color: "green", text: "已终审" },
};

export const isFirstPending = (stage: ReviewStage) => stage === "todo" || stage === "rej2";
/** 配上了到账的期次才审核。 */
export const isMatched = (row: ReconRow) => Boolean(row.matchId);

export const n2 = (value: number | null | undefined) =>
  value == null || !Number.isFinite(value) ? "—" : value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const timeText = (iso: string | null | undefined) => (iso ? dayjs(iso).format("YYYY-MM-DD HH:mm") : "—");

export const VOIDED_ARRIVAL_TEXT = "到账流水已作废，请撤销配对";
