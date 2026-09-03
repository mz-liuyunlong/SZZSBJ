/**
 * pmcRule.ts - AI智能PMC 补货建议规则（批④，2026-07-21 需求方定稿，纯函数）
 * 目标库存天数默认 70（与清货清尾线 60 为两个独立参数）
 * 清货期产品：没有任何补货建议（需求方明确）
 */

export interface ReplenishInput {
  stock: number;       // WFS 最新库存
  inbound: number;     // 在途
  purchased: number;   // 未完结采购在途 Σ(计划-已收)
  daily7: number;      // 近7数据日日均销量
  isClearance: boolean;
  targetDays?: number; // 默认 70
}

export interface ReplenishResult {
  qty: number;          // 建议补货量（≤0 表示不需补）
  label: string;        // 展示文案，空=无建议
  daysToSell: number | null; // 可卖天数（库存/日销），日销0为 null
}

export function replenishSuggestion(inp: ReplenishInput): ReplenishResult {
  const targetDays = inp.targetDays && inp.targetDays > 0 ? inp.targetDays : 70;
  const daysToSell = inp.daily7 > 0 ? Math.round(inp.stock / inp.daily7) : null;
  if (inp.isClearance) return { qty: 0, label: "", daysToSell };
  if (inp.daily7 <= 0) return { qty: 0, label: "", daysToSell };
  const deficit = Math.ceil(inp.daily7 * targetDays - inp.stock - inp.inbound - inp.purchased);
  if (deficit <= 0) {
    const covered = Math.round((inp.stock + inp.inbound + inp.purchased) / inp.daily7);
    return { qty: 0, label: `暂不需补（含在途/采购约可卖 ${covered} 天）`, daysToSell };
  }
  if (inp.stock <= 0) return { qty: deficit, label: `立即补 ${deficit} 件（断货，${targetDays}天目标）`, daysToSell };
  return { qty: deficit, label: `建议补 ${deficit} 件（${targetDays}天目标）`, daysToSell };
}

/** 风险分层（PMC 列表徽标） */
export function riskLevel(stock: number, daily7: number, isClearance: boolean): string {
  if (isClearance) return "清货中";
  if (stock <= 0) return daily7 > 0 ? "已断货" : "无库存";
  if (daily7 <= 0) return "无动销";
  const days = stock / daily7;
  if (days <= 7) return "≤7天";
  if (days <= 14) return "≤14天";
  if (days > 90) return "积压";
  return "健康";
}
