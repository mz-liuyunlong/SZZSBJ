/** Display components shared by the 物流看板 table and drawer (8088 app-a.jsx). */
import { Tag, Typography } from "antd";
import type { LogisticsRow, Sev } from "./logisticsApi";
import { daysBetween } from "./logisticsFormat";

const STAGE_COLOR: Record<string, string> = {
  待发货: "default",
  已发货: "blue",
  已开船: "geekblue",
  已到港: "cyan",
  派送中: "purple",
  物流签收: "magenta",
  "Walmart 收货中": "orange",
  "Walmart 完成": "success",
  已作废: "default",
};

export const StageTag = ({ stage }: { stage: string }) => <Tag color={STAGE_COLOR[stage] ?? "default"} bordered={false}>{stage}</Tag>;

const SEV: Record<Sev, { color: string; label: string }> = {
  high: { color: "error", label: "高" },
  mid: { color: "warning", label: "中" },
  low: { color: "default", label: "低" },
};
export const SevTag = ({ sev }: { sev: Sev }) => <Tag color={SEV[sev].color} bordered={false}>{SEV[sev].label}</Tag>;

/** 物流到货（众壹签收完成）vs Walmart 签收（actualDeliveryDate / 最早 Receipt）。 */
export function SignGap({ s, today }: { s: LogisticsRow; today: string }) {
  const label = {
    none: <Typography.Text type="secondary">物流未到货</Typography.Text>,
    ok: <Tag color="success" bordered={false}>正常 · 差 {s.signGap} 天</Tag>,
    late: <Tag color="warning" bordered={false}>签收滞后 {s.signGap} 天</Tag>,
    overdue: <Tag color="error" bordered={false}>到货 {s.deliveredCarrier ? daysBetween(s.deliveredCarrier, today) : "—"} 天 Walmart 未签收</Tag>,
    waiting: <Tag color="processing" bordered={false}>等 Walmart 签收</Tag>,
    closed: <Typography.Text type="secondary">已 Closed</Typography.Text>,
    nodata: <Typography.Text type="secondary">该店铺无 Walmart 数据</Typography.Text>,
  }[s.signCheck];
  return (
    <span>
      {label}
      {s.signCheck !== "none" && <><br /><Typography.Text type="secondary">物流 {s.deliveredCarrier} · WM {s.wmSign || "—"}</Typography.Text></>}
    </span>
  );
}
