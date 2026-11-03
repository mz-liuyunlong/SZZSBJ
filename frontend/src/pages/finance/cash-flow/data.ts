/**
 * 资金流水 · 备货资金 本地预览数据读取（只读本组自己的数据目录 public/local-fin-data/cash-flow/）。
 * 数据由 features/finance/drafts/local_export/cash-flow.py 从 Demo 构建结果（PMC 每日快照）导出；该目录不提交到仓库。
 * 正式接口上线后（阶段 B），把这里的读取换成 PMC 只读接口，页面组件不变。
 */
import { useQuery } from "@tanstack/react-query";

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

export const useApprovals = () => useTabFile<ApprovalsFile>("approvals.json");
export const fsFileUrl = (name: string) => `${import.meta.env.BASE_URL}local-fin-data/${DIR}/fs-files/${encodeURIComponent(name)}`;
