import type { BoardFreshness } from "./shipmentBoardTypes";

const fmt = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", dateStyle: "short", timeStyle: "short" });

export function freshnessText(f?: BoardFreshness | null): { text: string; stale: boolean } {
  if (!f || !f.source_observed_at) return { text: "领星数据尚未同步到看板", stale: true };
  const hours = Math.round((Date.now() - new Date(f.source_observed_at).getTime()) / 36e5);
  const coverage = f.coverage_start && f.coverage_end ? `，覆盖 ${f.coverage_start} ～ ${f.coverage_end}` : "";
  return { text: `领星数据时间 ${fmt.format(new Date(f.source_observed_at))}（${hours} 小时前${coverage}）`, stale: f.stale };
}
