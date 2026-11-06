/**
 * 财务板块 · 本地预览数据（阶段 A，2026-11-02）。
 *
 * 只在本地开发时读取 `public/local-fin-data/*.json`（由 features/finance/drafts/export_local_fin.py
 * 从 Demo 构建结果导出；该目录已写入 frontend/.gitignore，绝不提交）。正式接口上线后，本文件的
 * 读取函数逐个替换为 `/api/finance/*` 查询（阶段 B），页面组件不变。
 */
import { useQuery } from "@tanstack/react-query";

export interface CashAccount {
  id: string;
  name: string;
  entity?: string;
  cur: string;
  kind: string;
  stmt?: string;
  note?: string;
  open?: number | null;
  close?: number | null;
  retired?: boolean;
}

export interface CashCategory {
  code: string;
  big: string;
  name: string;
  internal?: boolean;
  salary?: boolean;
}

export interface CashPart {
  amt: number;
  cat: string;
  ref?: string;
  note?: string;
  /** 手续费行（「确认记为手续费」切出来的）：手续费层，如 fee / payoneer */
  fee?: string;
  /** 拆分行自己的摘要 / 备注（没填 = 沿用整笔的摘要，备注空着） */
  sum?: string;
  memo?: string;
}

export interface CashLine {
  id: string;
  acct: string;
  date: string;
  time?: string;
  m: string;
  cur: string;
  amt: number | null;
  cny: number | null;
  bal?: number | null;
  sum: string;
  memo: string;
  party?: string;
  refs: string[];
  cat: string;
  cat_src: string;
  pair: string;
  flags: string[];
  masked: boolean;
  ord?: number;
  stmt?: boolean;
  sub?: string;
  ok?: boolean;
  ok2?: boolean;
  note?: string;
  parts?: CashPart[];
  /** Demo 里是剔除金额；接口版只表示「有剔除」。 */
  excl?: number | boolean;
}

export interface FeishuPaid {
  line: string;
  date?: string;
  acct?: string;
  amt?: number | null;
}

export interface FeishuApproval {
  serial: string;
  kind: string;
  status: string;
  start: string;
  end: string;
  applicant: string;
  reason: string;
  amount: number | null;
  cur: string;
  pay: string;
  payee: string;
  bank: string;
  last4: string;
  items: { c: string; a: number | null }[];
  rel: string;
  invoice: string;
  src: string;
  cat: string;
  masked: boolean;
  paid: FeishuPaid[];
  paid_sum: number;
  cny: number | null;
  state: string;
  days?: number | null;
}

export interface CashFlowMonth {
  n?: number;
  open?: number | null;
  in_ext?: number | null;
  out_ext?: number | null;
  in_int?: number | null;
  out_int?: number | null;
  close?: number | null;
  sheet_close?: number | null;
}

export interface CashAnomaly {
  type: string;
  sev: string;
  acct: string;
  date: string;
  msg: string;
  amt?: number | null;
}

export interface CashSnapshot {
  meta: {
    built: string;
    start: string;
    months: string[];
    feishu_src: string[];
    fx: Record<string, [number, string]>;
    fx_months?: { month: string; rate: number | null }[];
    summary: Record<string, number>;
    bank_files?: { file?: string; note?: string; acct?: string; accts?: string[]; from?: string; to?: string; range_from?: string; range_to?: string; range_src?: string; n?: number }[];
  };
  accounts: CashAccount[];
  cats: CashCategory[];
  lines: CashLine[];
  feishu: FeishuApproval[];
  flow: { months: string[]; by_acct: Record<string, Record<string, CashFlowMonth>> };
  anomalies: CashAnomaly[];
}

export interface ImportDetail {
  t: string;
  file?: string;
  n?: number;
  from?: string;
  max_d?: string;
  range_src?: string;
  missing?: boolean;
}

export interface ImportItem {
  id: string;
  name: string;
  src_label?: string;
  who: string;
  node: string;
  next_node?: string;
  last_file?: string;
  last_at?: string;
  cover?: string;
  stale?: boolean;
  name_rule: string;
  fmt: string;
  accept: string;
  used_in: string;
  dest: string;
  detail?: ImportDetail[];
}

export interface ImportsSnapshot {
  meta: { built: string; note: string; bill_anchor?: string };
  items: ImportItem[];
}

export interface PreviewMeta {
  exported_at: string;
  source: string;
}

async function readLocal<T>(name: string): Promise<T> {
  const response = await fetch(`${import.meta.env.BASE_URL}local-fin-data/${name}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`本地预览数据 ${name} 不存在（先在 Mac 上运行 export_local_fin.py）`);
  return response.json() as Promise<T>;
}

const localQuery = <T,>(name: string) => ({
  queryKey: ["finance-local-preview", name],
  queryFn: () => readLocal<T>(name),
  staleTime: Infinity,
  retry: false,
  enabled: import.meta.env.DEV,
});

export const useCashSnapshot = () => useQuery(localQuery<CashSnapshot>("cash.json"));
export const useImportsSnapshot = () => useQuery(localQuery<ImportsSnapshot>("imports.json"));
export const usePreviewMeta = () => useQuery(localQuery<PreviewMeta>("meta.json"));

/** 账户显示名：主体 · 银行 / 平台 + 币种 + 尾号（2026-11-02 Rocky：账户要写清楚）。 */
export const accountTail = (account?: CashAccount) => account?.stmt?.match(/尾号\s*(\d{4})/)?.[1] ?? account?.stmt?.match(/…([0-9A-Za-z-]{3,6})/)?.[1] ?? "";
export const accountLabel = (account?: CashAccount) => (account ? `${account.name}（${account.cur}${accountTail(account) ? ` · 尾号 ${accountTail(account)}` : ""}）` : "");

const moneyFmt = new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const fmtMoney = (value: number | null | undefined, cur = "CNY") => {
  if (value == null || !Number.isFinite(value)) return "—";
  const symbol = cur === "USD" ? "$" : "¥";
  return `${value < 0 ? "-" : ""}${symbol}${moneyFmt.format(Math.abs(value))}`;
};
