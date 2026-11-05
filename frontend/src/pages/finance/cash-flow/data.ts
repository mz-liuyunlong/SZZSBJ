/**
 * 资金流水 · 备货资金 本地预览数据读取（只读本组自己的数据目录 public/local-fin-data/cash-flow/）。
 * 数据由 features/finance/drafts/local_export/cash-flow.py 从 Demo 构建结果（PMC 每日快照）导出；该目录不提交到仓库。
 * 正式接口上线后（阶段 B），把这里的读取换成 PMC 只读接口，页面组件不变。
 */
import { useQuery } from "@tanstack/react-query";
import type { CashAnomaly } from "@/pages/finance/localFinData";

const DIR = "cash-flow";

export async function readTabFile<T>(name: string): Promise<T> {
  const response = await fetch(`${import.meta.env.BASE_URL}local-fin-data/${DIR}/${name}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`本地预览数据 ${DIR}/${name} 不存在（先在 Mac 上运行 local_export/cash-flow.py）`);
  return response.json() as Promise<T>;
}

/** 读取本组的一个数据文件；首屏文件请控制在约 1MB 以内，明细按需再读。 */
export function useTabFile<T>(name: string, enabled = true) {
  return useQuery({
    queryKey: ["finance-local-preview", DIR, name],
    queryFn: () => readTabFile<T>(name),
    staleTime: Infinity,
    retry: false,
    enabled: import.meta.env.DEV && enabled,
  });
}

/** 发货投入：某店某发货月为备货花的钱（¥）。 */
export interface StockInvMonth { sid: string; month: string; goods: number; head: number; other: number; qty: number }
/** WFS 在仓：age 为 5 档库龄件数（0–90 / 91–180 / 181–270 / 271–365 / 365+ 天）；unit 为 0 表示找不到入库成本。 */
export interface StockWfs { sid: string; gtin: string; sku: string; item_id: string; qty: number; inbound: number; onhand: number; age: number[]; unit: number; amount: number }
export interface StockTransit { sid: string; gtin: string; sku: string; cargo: string; status: string; date: string; qty: number; unit: number; amount: number }
export interface StockDomestic { sid: string; sku: string; warehouse: string; batch: string; qty: number; unit: number; amount: number; age: number }

export interface StockFile {
  meta: { daily: string; today: string; stores: { sid: string; code: string }[]; source: string };
  inv_month: StockInvMonth[];
  wfs: StockWfs[];
  transit: StockTransit[];
  domestic: StockDomestic[];
  domestic_unassigned: { batches: number; qty: number; amount: number };
  wfs_src: Record<string, string>;
}

export const useStock = (enabled = true) => useTabFile<StockFile>("stock.json", enabled);

/* ---------------------------------------------------------------- 飞书审批单明细 + 凭证（日记账详情 / 终审用）
 * approvals.json 由 cash-flow.py 从飞书只读测试的落盘结果导出（账号只留尾号）；凭证原件副本在 fs-files/。两者都不进 Git。
 * 正式版：后端存图，按「财务 · 日记账初审 / 终审」权限给看原图。 */
export interface FsFile { name: string; src: "form" | "timeline" | "comment" | string; what: string; item: number; img: boolean; title: string; bytes?: number }
export interface FsDetail {
  serial: string; kind: string; status: string; start: string; end: string; handled: string;
  reason: string; amount: number | null; cur: string; invoice: string; pay: string; payee: string;
  account_name: string; bank: string; last4: string; items: { c: string; a: number | null }[]; files: FsFile[];
  /** 申请人姓名（通讯录换出来的；早期抽样数据可能为空）。 */
  applicant?: string;
  /** 审批记录：发起 → 各审批节点 → 办理 → 抄送，按时间顺序；files 为该步上传的文件数。 */
  records?: FsRecord[];
  comments?: { who: string; time: string; note: string }[];
}
export interface FsRecord { node: string; act: string; who: string; time: string; note: string; files: number }
export interface ApprovalsFile { meta: { src: string; ticket: string; built: string; n: number; files: number }; items: Record<string, FsDetail> }

export const useApprovals = (enabled = true) => useTabFile<ApprovalsFile>("approvals.json", enabled);
export const fsFileUrl = (name: string) => `${import.meta.env.BASE_URL}local-fin-data/${DIR}/fs-files/${encodeURIComponent(name)}`;

/* ---------------------------------------------------------------- 资金异常（并入日记账显示；Rocky 2026-11-04：异常不分等级，全部都要处理）
 * 每条带稳定编号（流水号 / 审批单号），以后作为「设置 → 业务配置中心 → 通知规则」的对象编号（object_key）去重、确认。
 * 数据提示类只是说明：灰色标签，不算异常、不发提醒。 */
export const CASH_HINT_TYPES = new Set(["期初切换", "对方账户不在日记账", "审批单在另一个飞书（不拉）"]);
export interface CashAlert extends CashAnomaly { id: string; ref: string; line?: string; serial?: string; hint: boolean }
type RawAnomaly = CashAnomaly & { line?: string; serial?: string };

/** 稳定编号：有流水号用流水号，审批单用审批单号；剔除用「日期 + 第几条」，其余用「账户 + 日期 + 金额」。 */
function alertRef(item: RawAnomaly): string {
  if (item.line) return item.line;
  if (item.serial) return item.serial;
  const n = /第 (\d+) 条/.exec(item.msg)?.[1];
  if (item.type === "剔除未命中" && n) return `剔除:${item.date}:${n}`;
  return `${item.acct || "-"}:${item.date}:${item.amt ?? ""}`;
}

export function toCashAlerts(list: CashAnomaly[]): CashAlert[] {
  return list.map((raw) => {
    const item = raw as RawAnomaly;
    const ref = alertRef(item);
    return { ...item, ref, id: `${item.type}|${ref}`, hint: CASH_HINT_TYPES.has(item.type) };
  });
}

/** 显示用的短类型名 + 处理指引（流水详情的「异常」段落用）。 */
export const ALERT_GUIDE: Record<string, { short: string; guide: string }> = {
  "内部转账未配对": { short: "未配对", guide: "在其他账户里找到对应的那笔内部调拨，配成一对；确实是外部款项就改类别。" },
  "明细合计≠流水": { short: "明细不符", guide: "核对这笔流水的明细金额，补齐或改正明细，合计要等于流水金额。" },
  "余额不连续": { short: "余额不连续", guide: "这笔之前可能漏了流水，回银行或平台后台补导出漏掉的那几行。" },
  "剔除未命中": { short: "要剔除的款没找到", guide: "剔除清单里这笔要剔除的款，在流水里没找到对应付款，或找到的金额不够扣：核对剔除清单的单号和金额，或补导这笔付款流水。" },
  "审批单未付": { short: "审批单没付款", guide: "审批已通过但关联的流水里还没有付款：核对是否关联错流水，或跟进付款。" },
  "审批单部分已付": { short: "审批单部分已付", guide: "已付金额小于申请金额：补关联剩余的付款流水，或跟进剩余付款。" },
  "审批单无付款流水": { short: "无付款流水", guide: "飞书已同意，没找到对应付款流水，多半是流水没导全，请检查导入。" },
  "审批单金额不符": { short: "审批单金额不符", guide: "已付金额大于申请金额：核对是否关联错流水，或审批单金额有误。" },
};
export const alertShort = (type: string) => ALERT_GUIDE[type]?.short ?? type;
