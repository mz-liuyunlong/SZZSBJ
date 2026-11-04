import { Alert, Descriptions, Tag, Typography } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import type { NewProductMetrics, NewProductPeriodMetrics } from "./newProductApi";

type PeriodKey = "30" | "60" | "90";
type PeriodRow = NewProductPeriodMetrics & { key: PeriodKey };

const PERIODS: PeriodKey[] = ["30", "60", "90"];
const format = (value: number | null | undefined): string =>
  value == null ? "—" : new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 2,
  }).format(value);
const percent = (value: number | null | undefined): string =>
  value == null ? "—" : `${format(value)}%`;

const columns: ProColumns<PeriodRow>[] = [
  { title: "周期", dataIndex: "days", width: 70, render: (_, row) => `${row.days}天` },
  { title: "数据起始", dataIndex: "from", width: 120 },
  { title: "截止日（不含）", dataIndex: "to_exclusive", width: 120 },
  { title: "销量", dataIndex: "sales", width: 85, render: (_, row) => format(row.sales) },
  { title: "订单", dataIndex: "orders", width: 85, render: (_, row) => format(row.orders) },
  { title: "销售额", dataIndex: "revenue", width: 95, render: (_, row) => format(row.revenue) },
  { title: "金额币种", dataIndex: "currency_code", width: 85,
    render: (_, row) => row.currency_code ?? "币种不一致" },
  { title: "点击量", dataIndex: "clicks", width: 90, render: (_, row) => format(row.clicks) },
  { title: "SP广告费", dataIndex: "sp_ad_spend", width: 95,
    render: (_, row) => format(row.sp_ad_spend) },
  { title: "SEM费用", dataIndex: "sem_ad_spend", width: 95,
    render: (_, row) => format(row.sem_ad_spend) },
  { title: "总广告费", dataIndex: "ad_spend", width: 95, render: (_, row) => format(row.ad_spend) },
  { title: "广告归因销售额", dataIndex: "attributed_sales", width: 125,
    render: (_, row) => format(row.attributed_sales) },
  { title: "ACOS", dataIndex: "acos", width: 85, render: (_, row) => percent(row.acos) },
  { title: "CPC", dataIndex: "cpc", width: 85, render: (_, row) => format(row.cpc) },
  { title: "广告ROAS", dataIndex: "roas", width: 95, render: (_, row) => format(row.roas) },
  { title: "CVR", dataIndex: "cvr", width: 85, render: (_, row) => percent(row.cvr) },
  { title: "归因订单", dataIndex: "attributed_orders", width: 110,
    render: (_, row) => format(row.attributed_orders) },
  { title: "广告费占比", dataIndex: "ad_spend_ratio", width: 105,
    render: (_, row) => percent(row.ad_spend_ratio) },
  { title: "利润", dataIndex: "profit", width: 95, render: (_, row) => format(row.profit) },
  { title: "利润率", dataIndex: "margin", width: 95, render: (_, row) => percent(row.margin) },
  { title: "经营 ROI", dataIndex: "roi", width: 100, render: (_, row) => format(row.roi) },
  { title: "覆盖天数", dataIndex: "observed_days", width: 95 },
  { title: "完整成本天数", dataIndex: "complete_cost_days", width: 115 },
  { title: "缺失日数", dataIndex: "missing_days", width: 90,
    render: (_, row) => row.missing_days ?? "—" },
  { title: "数据问题", dataIndex: "data_issues", width: 240,
    render: (_, row) => (row.data_issues ?? []).map(code => ({
      missing_business_day_coverage: "业务日覆盖不足",
      incomplete_cost_coverage: "成本数据不完整",
      financial_currency_unverified: "财务币种未核实",
      margin_unavailable: "利润率不可计算",
      ad_spend_unavailable: "广告费缺失",
      ad_spend_currency_unverified: "SP广告费用币种未核实或与销售币种不一致",
      sem_ad_spend_currency_unverified: "SEM费用币种未核实或与销售币种不一致",
      ad_clicks_unavailable: "广告点击缺失",
      ad_coverage_unverified: "广告业务日覆盖未确认",
      attributed_acos_unavailable: "归因 ACOS 不可计算",
    } as Record<string, string>)[code] ?? code).join("、") || "—" },
  { title: "数据状态", key: "complete", width: 95,
    render: (_, row) => <Tag color={row.complete ? "success" : "warning"}>
      {row.complete ? "完整" : "数据不足"}
    </Tag> },
];

export default function NewProductMetricsPanel({ metrics }: { metrics: NewProductMetrics }) {
  const rows: PeriodRow[] = PERIODS.map(key => ({ ...metrics.periods[key], key }));
  return <>
    <Typography.Paragraph type="secondary">
      使用 {metrics.business_timezone} 业务日。周期截止日期不包含当天；金额仍需按来源币种与结算口径对账。
    </Typography.Paragraph>
    <Descriptions size="small" column={2} items={[
      { key: "sku", label: "SKU", children: metrics.sku },
      { key: "account", label: "账户", children: metrics.account },
      { key: "date", label: "数据截止（不含）", children: metrics.as_of_exclusive },
      { key: "version", label: "规则版本", children: `V${metrics.rule_version}` },
      { key: "visibility", label: "财务字段权限",
        children: metrics.financial_visibility === "restricted"
          ? "受限（服务端脱敏）"
          : metrics.financial_visibility === "authorized" ? "已授权" : "权限状态未确认" },
      { key: "start", label: "已确认观察起点", children: metrics.verified_start_date ?? "待确认" },
      { key: "available", label: "可售库存", children: format(metrics.inventory.available) },
      { key: "wfs", label: "WFS 可售", children: format(metrics.inventory.wfs_available) },
      { key: "first_order", label: "首次出单时间", children:
        metrics.order_milestones?.first_order_date ?? "日期覆盖或观察起点待确认" },
      { key: "first_order_days", label: "首次出单间隔（天）", children:
        metrics.order_milestones?.days_to_first_order ?? "—" },
      { key: "pace_7", label: "前7日销量", children:
        format(metrics.order_milestones?.sales_7d) },
      { key: "pace_10", label: "前10日销量", children:
        format(metrics.order_milestones?.sales_10d) },
      { key: "pace_20", label: "前20日销量", children:
        format(metrics.order_milestones?.sales_20d) },
      { key: "roi", label: "ROI 用途", children: "经营 ROI 采用每日销售公式；正式打品评分 ROI 尚未批准" },
      { key: "purchase", label: "候选采购区间", children:
        metrics.score.purchase_preview?.range
          ? metrics.score.purchase_preview.range.join("–") + "（仅预估，禁止自动采购）"
          : "等级尚未批准，需人工确认" },
      { key: "score", label: "系统评分状态",
        children: metrics.score.status === "evaluated"
          ? `${format(metrics.score.score)} / ${metrics.score.grade ?? "—"}`
          : (metrics.score.status === "provisional"
            ? "公式待批准（仅预览分，不生成正式评级）"
            : "数据不足，暂不出正式评分") },
      { key: "launch", label: "打品结论",
        children: metrics.launch.status === "awaiting_approved_rules"
          ? "正式规则待批准（不判定成功或失败）"
          : metrics.launch.status === "evaluated"
            ? (metrics.launch.result === "success" ? "达标" : "未达标")
            : "观察未完成或数据不足" },
    ]} />
    {(metrics.score.status !== "evaluated" || metrics.launch.status !== "evaluated") &&
      <Alert type="warning" showIcon
        message={metrics.financial_visibility === "restricted"
          ? "当前账号没有查看订单利润及利润率的完整字段权限，敏感指标和衍生结论已由服务端脱敏"
          : "指标或观察起点尚未完整验证，不生成正式评分及打品终态"}
        style={{ marginBottom: 12 }} />}
    <ReportTableShell label="真实30、60、90天经营指标">
      <ProTable<PeriodRow> rowKey="key" dataSource={rows} columns={columns}
        options={false} search={false} pagination={false} size="small" bordered
        scroll={{ x: 2200 }} />
    </ReportTableShell>
    <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
      广告费口径沿用每日销售：总广告费 = SP广告费 + SEM费用，
      利润已包含两项费用，不再重复扣除。ACOS 为 SP 归因花费 / SP 归因销售额；
      广告费占比为总广告费 / 总销售额。
      两者不能互相替代。CPC 为广告归因花费/点击，CVR 为广告归因订单/点击；
      未经归因核实和完整覆盖不可用于正式评分。经营 ROI = 利润 /
      （采购成本 + 头程成本），显示为倍数，缺失数据时留空；正式打品评分 ROI 仍待批准。
      空值表示缺少可验证数据，并不代表零。
    </Typography.Paragraph>
  </>;
}
