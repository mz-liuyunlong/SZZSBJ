/** Display-only labels and formatters shared by the board table and the detail Modal (no business math). */
import { Tag, Typography } from "antd";
import type {
  PurchaseBoardItemIdSource,
  PurchaseBoardRow,
  PurchaseStageCode,
  SkuCycleSample,
  SkuCycleSource,
} from "@/pages/pmc/purchase-board/purchaseBoardTypes";

export const EMPTY = <Typography.Text type="secondary">—</Typography.Text>;

export const stageLabels: Record<PurchaseStageCode, { label: string; color: string }> = {
  S1: { label: "待审批", color: "default" },
  S2: { label: "待下单", color: "gold" },
  S3: { label: "已下单未到货", color: "blue" },
  S4: { label: "部分到货", color: "geekblue" },
  S9: { label: "已到货", color: "green" },
  S0: { label: "已作废", color: "default" },
  UNKNOWN: { label: "状态未知", color: "default" },
};

export const itemIdSourceLabels: Record<PurchaseBoardItemIdSource, string> = {
  from_system_plan: "系统计划",
  from_plan_remark: "计划备注",
  from_packing_slip: "打包单",
  pending_packing_slip: "待打包单",
  unresolved: "待处理",
};

export const skuCycleSourceLabels: Record<SkuCycleSource, string> = {
  samples: "近 5 单样本",
  baseline_mix: "基准 + 样本",
  lingxing_default: "领星默认交期",
  no_baseline: "无基准",
};

export const exclusionLabels: Record<NonNullable<SkuCycleSample["exclusion"]>, string> = {
  auto_short: "自动剔除（<2 天）",
  manual: "人工剔除",
  before_baseline: "基准日前",
  outside_window: "窗口外",
};

/** Purchase cycle in days; values under 2 days are excluded from SKU samples by rule. */
export function purchaseCycleText(days: number | null) {
  if (days === null) return EMPTY;
  if (days < 2) {
    return (
      <Typography.Text type="secondary">
        {days} 天 <Tag>已剔除</Tag>
      </Typography.Text>
    );
  }
  return <span>{days} 天</span>;
}

export function progressText(row: Pick<PurchaseBoardRow, "quantityReceived" | "quantityAllocated" | "progressRatio">) {
  const ratio = row.progressRatio === null ? "" : ` (${(row.progressRatio * 100).toFixed(0)}%)`;
  return `${row.quantityReceived} / ${row.quantityAllocated}${ratio}`;
}

export const currencySign = (code: string | null) => (code === "USD" ? "$" : "¥");

/** Maps envelope errors to user-facing copy; never exposes internals. */
export function purchaseBoardErrorText(reason: unknown) {
  const error = reason as { status?: number; code?: string; message?: string } | undefined;
  const code = error?.code ?? error?.message ?? "";
  if (error?.status === 401 || code === "UNAUTHORIZED") return "当前账号未登录或授权已过期，请重新登录后查看采购看板。";
  if (code === "DATA_SCOPE_DENIED") return "当前账号没有可访问的数据范围，请联系管理员配置账号范围。";
  if (error?.status === 403 || code === "FORBIDDEN") return "当前账号没有采购看板查看权限（pmc:purchase:read）。";
  if (error?.status === 404 || code === "NOT_FOUND") return "未找到该采购单，或它不在当前账号范围内。";
  if (error?.status === 422 || code === "VALIDATION_ERROR") return "筛选条件不合法，请检查区间与搜索类型后重试。";
  if (code) return `采购看板加载失败：${code}`;
  return "采购看板加载失败，请稍后重试。";
}
