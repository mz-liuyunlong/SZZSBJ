import { Collapse, Modal, Tabs, Tag, Typography } from "antd";
import { useState, type ReactNode } from "react";

// Display-only component. Keep the existing export name and props so both
// clearance table entries continue using their existing data and event flow.
export type RiskDetailLevel = "high" | "medium" | "low" | "none" | "unknown";
export type RiskDetailStatus = "hit" | "not_hit" | "insufficient" | "disabled";

export interface RuleHitDetail {
  code: string;
  name: string;
  enabled: boolean;
  status: RiskDetailStatus;
  severity: string;
  effect: string;
  actual_value: unknown;
  threshold: unknown;
  evidence: Record<string, unknown>;
  missing_fields?: string[];
  explanation?: string;
}

export interface RiskDetailPayload {
  risk?: string | null;
  rule_hits?: RuleHitDetail[];
  evaluated_at?: string | null;
  as_of_date_la?: string | null;
  rule_version?: number | null;
  time_evidence?: Record<string, unknown>;
  data_gaps?: string[];
  evaluator_reasons?: string[];
}

const levelNames: Record<RiskDetailLevel, string> = {
  high: "高风险", medium: "中风险", low: "低风险", none: "无风险", unknown: "待评估",
};
const levelColors: Record<RiskDetailLevel, string> = {
  high: "error", medium: "warning", low: "processing", none: "success", unknown: "default",
};
const statusNames: Record<RiskDetailStatus, string> = {
  hit: "已命中", not_hit: "未命中", insufficient: "证据不足", disabled: "已关闭",
};
const effectNames: Record<string, string> = {
  level: "等级判断", assisted_only: "经营辅助", protection_only: "保护条件",
  priority_only: "优先级提示", auxiliary: "辅助证据",
};
const fieldNames: Record<string, string> = {
  source: "数据来源", formula: "判断公式", wfs_available: "WFS 可售库存（件）",
  period_days: "销量统计周期（天）", units_in_period: "统计期销量（件）",
  daily_average: "日均销量", listing_start_at_utc: "Listing 实际上架日期",
  listing_days: "Listing 上架天数", first_wfs_available_date_la: "WFS 首次有库存日期（美西）",
  first_wfs_days: "首次 WFS 有库存天数", as_of_date_la: "业务基准日（美西）",
  recent_7d: "近 7 天销量", previous_7d: "前 7 天销量",
  decline_percent: "销量下降百分比", observed_days_30d: "30 天有效观察天数",
  profit_7d_usd: "近 7 天利润（USD）", profit_14d_usd: "近 14 天利润（USD）",
  profit_30d_usd: "近 30 天利润（USD）", units_sold: "30 天销量（件）",
  return_qty: "30 天退货件数", return_rate_percent: "30 天退货率（%）",
  review_count: "评论数", rating: "商品评分", coverage_days_gte: "库存覆盖阈值（天）",
  inbound_units: "在途件数", sellout_days: "预计售罄天数", sales_30d: "近 30 天销量",
  ad_ratio_7d: "近 7 天广告占比", ad_ratio_30d: "近 30 天广告占比",
  difference_percentage_points: "广告占比差（百分点）", actual: "实际值",
};
const fieldName = (key: string) => fieldNames[key] ?? key.replaceAll("_", " ");
const isPresent = (v: unknown): boolean => v !== null && v !== undefined && v !== "";

// A date-only backend value has its own calendar date; do not shift it by the
// browser's local timezone. Timestamp values elsewhere retain date-only UI.
const clearanceDateOnly = (value: string): string => value.replace(
  /(\d{4}-\d{2}-\d{2})[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?/g,
  "$1",
);

// evaluated_at is an instant with an offset; unlike as_of_date_la it must be
// formatted in the US-West timezone before the label says "(美西)".
const evaluatedDateLA = (value?: string | null): string => {
  if (!value) return "—";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  // Avoid parsing timezone-less local timestamps in the browser's timezone.
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)) return clearanceDateOnly(value);
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) return clearanceDateOnly(value);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(parsed);
  const get = (type: string) => parts.find(item => item.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
};

function display(value: unknown): string {
  if (!isPresent(value)) return "—";
  if (typeof value === "number") return Number.isFinite(value)
    ? new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 3 }).format(value) : "∞";
  if (typeof value === "string") return clearanceDateOnly(value);
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) return value.map(display).join(" / ");
  if (typeof value === "object") return Object.entries(value as Record<string, unknown>)
    .filter(([key]) => key !== "timezone")
    .map(([key, part]) => `${fieldName(key)}：${display(part)}`).join("；");
  return "—";
}

// Do not expose the technical timezone description or repeat dates already
// presented in the time-summary area.
function DataFields({ values, omit = [] }: { values?: Record<string, unknown> | null; omit?: string[] }) {
  const rows = Object.entries(values ?? {}).filter(([key]) => key !== "timezone" && !omit.includes(key));
  if (!rows.length) return <Typography.Text type="secondary" style={{ fontSize: 12 }}>暂无额外数据</Typography.Text>;
  return <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "10px 20px" }}>
    {rows.map(([key, value]) => <div key={key} style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 3 }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>{fieldName(key)}</Typography.Text>
      <Typography.Text style={{ fontSize: 13, overflowWrap: "anywhere" }}>{display(value)}</Typography.Text>
    </div>)}
  </div>;
}

const thinBorder = "1px solid var(--ant-color-border-secondary, #e9edf3)";
const quietBackground = "var(--ant-color-fill-quaternary, #f8fafc)";

function RuleHeader({ rule }: { rule: RuleHitDetail }) {
  return <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8, width: "100%", paddingRight: 8 }}>
    <Typography.Text strong style={{ fontSize: 13, overflowWrap: "anywhere" }}>{rule.name || rule.code}</Typography.Text>
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      <Typography.Text type="secondary" style={{ fontSize: 11 }}>{effectNames[rule.effect] ?? "辅助判断"}</Typography.Text>
      <Tag color={rule.status === "hit" ? (rule.severity === "high" ? "error" : "warning") : "default"}
        style={{ margin: 0 }}>{statusNames[rule.status] ?? "待核对"}</Tag>
    </span>
  </div>;
}

function RuleBody({ rule }: { rule: RuleHitDetail }) {
  const extraEvidence = Object.entries(rule.evidence ?? {}).filter(([key]) => !["formula", "source", "timezone"].includes(key));
  return <div style={{ display: "grid", gap: 13 }}>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
      <div style={{ minWidth: 0, padding: "9px 12px", border: thinBorder, borderRadius: 7 }}>
        <Typography.Text type="secondary" style={{ display: "block", fontSize: 11 }}>实际值</Typography.Text>
        <Typography.Text strong style={{ display: "block", marginTop: 4, fontSize: 14, overflowWrap: "anywhere" }}>{display(rule.actual_value)}</Typography.Text>
      </div>
      <div style={{ minWidth: 0, padding: "9px 12px", border: thinBorder, borderRadius: 7 }}>
        <Typography.Text type="secondary" style={{ display: "block", fontSize: 11 }}>当前阈值</Typography.Text>
        <Typography.Text strong style={{ display: "block", marginTop: 4, fontSize: 14, overflowWrap: "anywhere" }}>{display(rule.threshold)}</Typography.Text>
      </div>
    </div>
    <div style={{ display: "grid", gap: 7, fontSize: 12 }}>
      <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>判断逻辑：</Typography.Text>{display(rule.evidence?.formula)}</div>
      <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>数据来源：</Typography.Text>{display(rule.evidence?.source)}</div>
      <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>计算结论：</Typography.Text>{display(rule.explanation || statusNames[rule.status])}</div>
      {!!rule.missing_fields?.length && <Typography.Text type="warning" style={{ fontSize: 12 }}>
        缺失字段：{rule.missing_fields.filter(key => key !== "timezone").map(fieldName).join("、")}
      </Typography.Text>}
    </div>
    {extraEvidence.length > 0 && <div style={{ borderTop: thinBorder, paddingTop: 11 }}>
      <Typography.Text strong style={{ display: "block", marginBottom: 9, fontSize: 12 }}>原始计算证据</Typography.Text>
      <DataFields values={Object.fromEntries(extraEvidence)}/>
    </div>}
  </div>;
}

function ExpandedRule({ rule }: { rule: RuleHitDetail }) {
  return <section style={{ border: thinBorder, borderRadius: 9, padding: "13px 15px", background: "var(--ant-color-bg-container, #fff)" }}>
    <RuleHeader rule={rule}/>
    <div style={{ paddingTop: 12 }}><RuleBody rule={rule}/></div>
  </section>;
}

function TimeCard({ label, date, days }: { label: string; date: unknown; days: unknown }) {
  return <div style={{ minWidth: 0, background: quietBackground, padding: "15px 17px", borderRadius: 9 }}>
    <Typography.Text type="secondary" style={{ fontSize: 12 }}>{label}</Typography.Text>
    <div style={{ fontWeight: 600, fontSize: 18, letterSpacing: ".2px", marginTop: 5 }}>{display(date)}</div>
    <div style={{ fontSize: 12, marginTop: 8, color: "var(--ant-color-text-secondary, #727b88)" }}>
      {isPresent(days) ? `至业务基准日：${display(days)} 天` : "对应天数：未获取"}
    </div>
  </div>;
}

function TimePanel({ payload }: { payload?: RiskDetailPayload | null }) {
  const time = payload?.time_evidence ?? {};
  const alreadyShown = ["timezone", "listing_start_at_utc", "listing_days", "first_wfs_available_date_la", "first_wfs_days", "as_of_date_la"];
  const extra = Object.fromEntries(Object.entries(time).filter(([key]) => !alreadyShown.includes(key)));
  const hasExtra = Object.keys(extra).length > 0;
  const asOf = time.as_of_date_la ?? payload?.as_of_date_la;
  return <div style={{ display: "grid", gap: 18 }}>
    <section>
      <Typography.Text strong style={{ display: "block", marginBottom: 10, fontSize: 13 }}>商品时间依据</Typography.Text>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 }}>
        <TimeCard label="Listing 实际上架日期（美西）"
          date={typeof time.listing_start_at_utc === "string" ? evaluatedDateLA(time.listing_start_at_utc) : time.listing_start_at_utc}
          days={time.listing_days}/>
        <TimeCard label="WFS 首次有库存日期（美西）" date={time.first_wfs_available_date_la} days={time.first_wfs_days}/>
      </div>
      <div style={{ borderBottom: thinBorder, padding: "14px 1px 12px", display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>业务基准日（美西）</Typography.Text>
        <Typography.Text strong style={{ fontSize: 13 }}>{display(asOf)}</Typography.Text>
      </div>
    </section>
    {hasExtra && <section>
      <Typography.Text strong style={{ display: "block", marginBottom: 10, fontSize: 13 }}>其他数据依据</Typography.Text>
      <DataFields values={extra}/>
    </section>}
    <section style={{ paddingTop: hasExtra ? 8 : 0 }}>
      <Typography.Text strong style={{ display: "block", marginBottom: 7, fontSize: 13 }}>数据缺口</Typography.Text>
      {payload?.data_gaps?.length
        ? <div style={{ display: "grid", gap: 5 }}>
          {payload.data_gaps.map((gap, index) => <Typography.Text key={`${index}-${gap}`} type="secondary" style={{ fontSize: 12 }}>· {clearanceDateOnly(gap)}</Typography.Text>)}
        </div>
        : <Typography.Text type="secondary" style={{ fontSize: 12 }}>当前未报告数据缺口；单条规则的证据是否完整，以「全部规则」中对应状态为准。</Typography.Text>}
    </section>
  </div>;
}

export function ClearanceRiskPopover({ itemId, payload, fallbackLevel, sku, storeName, productName }: {
  itemId: string;
  payload?: RiskDetailPayload | null;
  fallbackLevel?: string | null;
  sku?: string | null;
  storeName?: string | null;
  productName?: string | null;
}): ReactNode {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"hits" | "all" | "time">("hits");
  const raw = payload?.risk ?? fallbackLevel ?? "unknown";
  const level: RiskDetailLevel = raw === "high" || raw === "medium" || raw === "low" || raw === "none" ? raw : "unknown";
  const rules = Array.isArray(payload?.rule_hits) ? payload.rule_hits : [];
  const hits = rules.filter(item => item.status === "hit");
  const others = rules.filter(item => item.status !== "hit");
  const startOpen = () => { setTab("hits"); setOpen(true); };
  const close = () => setOpen(false);

  return <>
    <button type="button" aria-haspopup="dialog" aria-label={`查看商品 ${itemId} 的清货风险计算详情`}
      onClick={startOpen} style={{ display: "inline-flex", padding: 0, background: "transparent", border: 0, cursor: "pointer", verticalAlign: "middle" }}>
      <Tag color={levelColors[level]} style={{ marginInlineEnd: 0, cursor: "pointer" }}>{levelNames[level]}</Tag>
    </button>
    <Modal title="清货风险计算详情" width={800} centered open={open} onCancel={close}
      footer={null} destroyOnHidden styles={{ body: { paddingTop: 0 } }}>
      <div style={{ display: "flex", flexDirection: "column", minHeight: 0, maxHeight: "min(760px, 83vh)" }}>
        <div style={{ flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, paddingBottom: 12 }}>
            <div style={{ minWidth: 0, flex: 1 }}>
              <Typography.Text strong style={{ display: "block", fontSize: 15, lineHeight: 1.5, overflowWrap: "anywhere" }}>{productName || `商品 ID：${itemId}`}</Typography.Text>
              <div style={{ display: "flex", gap: "4px 16px", flexWrap: "wrap", marginTop: 6 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>商品 ID：{itemId}</Typography.Text>
                {!!sku && <Typography.Text type="secondary" style={{ fontSize: 12 }}>SKU：{sku}</Typography.Text>}
                {!!storeName && <Typography.Text type="secondary" style={{ fontSize: 12 }}>店铺：{storeName}</Typography.Text>}
              </div>
            </div>
            <Tag color={levelColors[level]} style={{ marginInlineEnd: 0, marginTop: 2 }}>{levelNames[level]}</Tag>
          </div>
          <div style={{ borderTop: thinBorder, borderBottom: thinBorder, display: "flex", alignItems: "center", flexWrap: "wrap", padding: "10px 0", gap: "6px 0" }}>
            {[
              ["命中规则", `${hits.length} 项`],
              ["规则版本", payload?.rule_version == null ? "未确认" : `V${payload.rule_version}`],
              ["计算日期（美西）", evaluatedDateLA(payload?.evaluated_at)],
            ].map(([name, value], index) => <div key={name} style={{ display: "inline-flex", alignItems: "baseline", gap: 8, padding: index === 0 ? "0 19px 0 0" : "0 19px", borderLeft: index ? thinBorder : undefined }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>{name}</Typography.Text>
              <Typography.Text strong style={{ fontSize: 13 }}>{value}</Typography.Text>
            </div>)}
          </div>
        </div>
        <Tabs activeKey={tab} onChange={key => setTab(key as "hits" | "all" | "time")}
          style={{ flexShrink: 0, marginBottom: 0 }}
          items={[
            { key: "hits", label: `命中规则（${hits.length}）` },
            { key: "all", label: `全部规则（${rules.length}）` },
            { key: "time", label: "时间与数据" },
          ]}/>
        <div role="region" aria-label="清货风险规则核对内容"
          style={{ overflowY: "auto", maxHeight: "min(500px, 55vh)", minHeight: 50, padding: "3px 2px 9px", overscrollBehavior: "contain" }}>
          {tab === "hits" && <div style={{ display: "grid", gap: 10 }}>
            {hits.map(rule => <ExpandedRule key={`${rule.code}-${rule.status}`} rule={rule}/>)}
            {!hits.length && <Typography.Text type="secondary" style={{ fontSize: 13, padding: "14px 0" }}>
              {level === "none" ? "当前判定为无风险；可在「全部规则」中检查各项依据。" : "暂无已确认命中规则。请查看「全部规则」确认是否存在证据不足。"}
            </Typography.Text>}
            {!!payload?.evaluator_reasons?.length && <div style={{ padding: "9px 2px 3px", borderTop: thinBorder }}>
              <Typography.Text strong style={{ fontSize: 12 }}>原风险引擎说明（仅供核对）</Typography.Text>
              {payload.evaluator_reasons.map((reason, index) => <div key={`${index}-${reason}`} style={{ fontSize: 12, marginTop: 5 }}>{clearanceDateOnly(reason)}</div>)}
            </div>}
          </div>}
          {tab === "all" && <div style={{ display: "grid", gap: 10 }}>
            {!!rules.length && <Collapse size="small" defaultActiveKey={[]} style={{ background: "var(--ant-color-bg-container, #fff)" }}
              items={[...hits, ...others].map((rule, index) => ({
                key: `${index}-${rule.code}`,
                label: <RuleHeader rule={rule}/>,
                children: <RuleBody rule={rule}/>,
              }))}/>}
            {!rules.length && <Typography.Text type="secondary">服务端尚未返回逐条规则证据，不能据此判定无风险。</Typography.Text>}
          </div>}
          {tab === "time" && <TimePanel payload={payload}/>}
        </div>
        <div style={{ flexShrink: 0, borderTop: thinBorder, paddingTop: 9, marginTop: 7 }}>
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>仅查看已计算的风险依据，不会修改规则、清货申请或库存。</Typography.Text>
        </div>
      </div>
    </Modal>
  </>;
}
