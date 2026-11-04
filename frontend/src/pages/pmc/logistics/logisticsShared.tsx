/** Display components shared by the 物流 pages and drawers (8088 app-a.jsx). */
import { Alert, Select, Tag, Typography } from "antd";
import type { LogisticsOptions, LogisticsRow, Sev } from "./logisticsApi";
import { logisticsError } from "./logisticsQueries";
import { daysBetween, type SpFilters } from "./logisticsFormat";

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
export function SignGap({ s, today }: { s: Pick<LogisticsRow, "signCheck" | "signGap" | "deliveredCarrier" | "wmSign">; today: string }) {
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

/** 数据日 notice: every 物流 page computes with the publication's data day (8088 TODAY). */
export function DataDayNotice({ options, error }: { options?: LogisticsOptions; error?: unknown }) {
  if (error) return <Alert type="error" showIcon message={logisticsError(error)} style={{ marginBottom: 12 }} />;
  if (!options) return null;
  const s = options.sources;
  const stores = (s.walmart_stores as string[] | undefined)?.length ?? 0;
  return (
    <div role="status" aria-label="物流数据日">
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message={`数据日 ${options.today}（8088 规则按数据日计算）· 领星发货单 07-01 起 ${options.total} 张 · 众壹运单 ${String(s.carrier_orders ?? 0)} 张 · Walmart ${stores} 店（批次 ${String(s.walmart_batch || "—")}）· 只读，不调用领星 / 物流商 / Walmart 接口`}
      />
    </div>
  );
}

/** 店铺 / 物流商 / 物流渠道 / 目的地区 selects (8088 overview and alerts toolbar). */
export function SpFilterSelects<F extends SpFilters>({ options, filters, commit }: {
  options?: LogisticsOptions;
  filters: F;
  commit: (next: Partial<F>) => void;
}) {
  const channels = (options?.channels ?? []).filter((c) => !filters.provider || c.provider_id === filters.provider);
  return (
    <>
      <Select allowClear showSearch aria-label="店铺" className="report-filter-select" placeholder="全部店铺" style={{ width: 220 }}
        value={filters.store} options={options?.stores} optionFilterProp="label" onChange={(store) => commit({ store } as Partial<F>)} />
      <Select allowClear aria-label="物流商" className="report-filter-select" placeholder="物流商" style={{ width: 140 }}
        value={filters.provider} options={options?.providers} onChange={(provider) => commit({ provider, channel: undefined } as Partial<F>)} />
      <Select allowClear showSearch aria-label="物流渠道" className="report-filter-select" placeholder="物流渠道" style={{ width: 200 }}
        value={filters.channel} options={channels} optionFilterProp="label" onChange={(channel) => commit({ channel } as Partial<F>)} />
      <Select allowClear aria-label="目的地区" className="report-filter-select" placeholder="目的地区" style={{ width: 110 }}
        value={filters.region} options={(options?.regions ?? []).map((r) => ({ value: r, label: r }))} onChange={(region) => commit({ region } as Partial<F>)} />
    </>
  );
}
