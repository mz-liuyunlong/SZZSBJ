/** 物流看板（8088 pmc-logistics）：物流总览 + 异常与提醒。数据一次取回，筛选 / 分页在浏览器里做（同 8088）。 */
import { Alert, Segmented, Select, Tag, Typography } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { BackendRequestError } from "@/api/backendApi";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import type { NavigationPage } from "@/config/navigation";
import WfsQueryPage from "../wfs/WfsQueryPage";
import LogisticsDrawer from "./LogisticsDrawer";
import { getBoard, type LogisticsAlert, type LogisticsRow, type Sev } from "./logisticsApi";
import { ARR_SRC, SEV_RANK, fmt, money } from "./logisticsFormat";
import { SevTag, SignGap, StageTag } from "./logisticsShared";
import "./LogisticsPage.css";

const { Text } = Typography;

type View = "overview" | "alerts";
type Card = "all" | "transit" | "soon" | "over" | "signed" | "miss" | "month";
type SearchField = "sp" | "cargo" | "track" | "sku";

interface Filters {
  store?: string;
  provider?: string;
  channel?: string;
  region?: string;
  stage?: string;
  keyword: string;
  field: SearchField;
  card: Card;
  type?: string;
  sev?: Sev;
}

const initial = (): Filters => ({ keyword: "", field: "sp", card: "all" });

const ALERT_CARDS: { type: string; icon: string; tone: "danger" | "warning" | "normal" }[] = [
  { type: "已超合同时效", icon: "超", tone: "danger" },
  { type: "签收已超时效（可索赔）", icon: "赔", tone: "danger" },
  { type: "物流已签收 WFS 未收货", icon: "签", tone: "danger" },
  { type: "物流已签收 Walmart 未签收", icon: "WM", tone: "danger" },
  { type: "即将超时", icon: "!", tone: "warning" },
  { type: "渠道与目的地区不符", icon: "区", tone: "warning" },
  { type: "收货差异（超缓冲期）", icon: "差", tone: "warning" },
  { type: "实际费用未录入", icon: "$", tone: "normal" },
  { type: "预计到港缺失", icon: "港", tone: "normal" },
];

const searchText = (s: LogisticsRow, field: SearchField) =>
  ({
    sp: s.code,
    cargo: s.cargos.map((c) => c.code).join(" "),
    track: s.tracking.join(" "),
    sku: s.goods.map((g) => `${g.sku} ${g.msku} ${g.gtin}`).join(" "),
  })[field].toLowerCase();

function boardError(error: unknown): string {
  if (error instanceof BackendRequestError) {
    if (error.code === "WFS_BOARD_SCHEMA_NOT_READY") return "WFS 数据库结构尚未更新，请先完成迁移后重试";
    if (error.status === 401) return "登录已失效，请重新登录";
    if (error.status === 403) return "没有页面权限或店铺数据范围";
    if (error.status === 404) return "物流看板接口未就绪，请重启本地后端（8010）并确认已加载最新代码";
  }
  return "物流看板请求失败，请重试";
}

export default function LogisticsPage({ page, scope = "anonymous" }: { page: NavigationPage; scope?: string }) {
  const [view, setView] = useState<View>("overview");
  const [filters, setFilters] = useState(initial);
  const [pagination, setPagination] = useState({ page: 1, size: 50 });
  const [open, setOpen] = useState<string>();
  const q = useQuery({ queryKey: ["pmc-logistics", scope, "board"], queryFn: ({ signal }) => getBoard(signal), retry: false });
  const board = q.data?.data;
  const sps = useMemo(() => board?.rows ?? [], [board]);
  const today = board?.today ?? "";
  const monthStart = today ? `${today.slice(0, 8)}01` : "";

  const commit = (next: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...next }));
    setPagination((p) => ({ ...p, page: 1 }));
  };

  const inCard = (s: LogisticsRow, card: Card) =>
    card === "all" ? true
      : card === "transit" ? !s.done && s.status === "已发货"
      : card === "soon" ? s.soon
      : card === "over" ? s.overdue
      : card === "signed" ? s.stage === "物流签收"
      : card === "miss" ? s.missing.length > 0
      : s.t.delivery >= monthStart;

  const base = sps.filter((s) =>
    (!filters.store || s.goods.some((g) => g.store_id === filters.store))
    && (!filters.provider || s.provider_id === filters.provider)
    && (!filters.channel || s.channel_id === filters.channel)
    && (!filters.region || s.region === filters.region)
    && (!filters.stage || s.stage === filters.stage)
    && (!filters.keyword || searchText(s, filters.field).includes(filters.keyword.toLowerCase())));

  const overviewRows = base.filter((s) => inCard(s, filters.card)).map((s) => ({ ...s, id: s.code }));

  type AlertRow = LogisticsAlert & { id: string; s: LogisticsRow };
  const allAlerts: AlertRow[] = useMemo(
    () => sps
      .flatMap((s) => s.ex.map((e, i) => ({ ...e, id: `${s.code}#${e.type}#${i}`, s })))
      .sort((a, b) => SEV_RANK[a.sev] - SEV_RANK[b.sev] || (b.since || "").localeCompare(a.since || "")),
    [sps],
  );
  const baseCodes = new Set(base.map((s) => s.code));
  const alertRows = allAlerts.filter((e) => baseCodes.has(e.s.code) && (!filters.type || e.type === filters.type) && (!filters.sev || e.sev === filters.sev));

  const rows = view === "overview" ? overviewRows : alertRows;
  const pageRows = rows.slice((pagination.page - 1) * pagination.size, pagination.page * pagination.size);

  const cnt = (card: Card) => sps.filter((s) => inCard(s, card)).length;
  const rules = board?.rules;
  const penaltyTotal = sps.reduce((n, s) => n + (s.penalty || 0), 0);

  const viewToggle = (
    <Segmented
      value={view}
      onChange={(v) => { setView(v as View); setPagination((p) => ({ ...p, page: 1 })); }}
      options={[
        { label: `物流总览（${cnt("transit")} 在途）`, value: "overview" },
        { label: `异常与提醒（${allAlerts.length}）`, value: "alerts" },
      ]}
    />
  );

  const header = (
    <>
      {q.error && <Alert type="error" showIcon message={boardError(q.error)} style={{ marginBottom: 12 }} />}
      {board && (
        <div role="status" aria-label="物流数据日">
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message={`数据日 ${today}（8088 规则按数据日计算）· 领星发货单 07-01 起 ${sps.length} 张 · 众壹轨迹 ${String(board.sources.carrier_tracks ?? 0)} 张 · Walmart ${(board.sources.walmart_stores as string[] | undefined)?.length ?? 0} 店（批次 ${String(board.sources.walmart_batch || "—")}）· 只读，不调用领星 / 物流商 / Walmart 接口`}
          />
        </div>
      )}
      {view === "overview" ? (
        <ManagementStatCards<Card>
          ariaLabel="物流总览统计"
          activeKey={filters.card}
          onCardClick={(card) => commit({ card: card === filters.card ? "all" : card })}
          cards={[
            { key: "all", title: "发货单（07-01 起）", value: sps.length, unit: "张", tone: "normal", icon: <span>单</span>, subtitle: `已发货 ${sps.filter((s) => s.status === "已发货").length}` },
            { key: "transit", title: "在途（未签收）", value: cnt("transit"), unit: "张", tone: "normal", icon: <span>途</span>, subtitle: "已发货且未完成" },
            { key: "soon", title: "即将超时", value: cnt("soon"), unit: "张", tone: "warning", icon: <span>!</span>, subtitle: `剩 ≤ ${rules?.remind_before ?? 3} 天` },
            { key: "over", title: "已超合同时效", value: cnt("over"), unit: "张", tone: "danger", icon: <span>超</span>, subtitle: `可索赔合计 ${money(penaltyTotal, "CNY")}` },
            { key: "signed", title: "物流已签收待 Walmart", value: cnt("signed"), unit: "张", tone: "warning", icon: <span>签</span>, subtitle: "众壹签收完成，Walmart 未收货" },
            { key: "miss", title: "数据缺失提醒", value: cnt("miss"), unit: "张", tone: "normal", icon: <span>缺</span>, subtitle: "费用 / 预计时间 / 运单号" },
            { key: "month", title: "本月发货", value: cnt("month"), unit: "张", tone: "normal", icon: <span>月</span>, subtitle: monthStart ? `${monthStart} 起` : "—" },
          ]}
        />
      ) : (
        <ManagementStatCards<string>
          ariaLabel="物流异常统计"
          activeKey={filters.type ?? ""}
          onCardClick={(type) => commit({ type: type === filters.type ? undefined : type })}
          cards={ALERT_CARDS.map((c) => ({
            key: c.type,
            title: c.type,
            value: allAlerts.filter((e) => e.type === c.type).length,
            unit: "条",
            tone: c.tone,
            icon: <span>{c.icon}</span>,
            subtitle: "8088 规则",
          }))}
        />
      )}
    </>
  );

  const channelOptions = (board?.channels ?? []).filter((c) => !filters.provider || c.provider_id === filters.provider);
  const filterBar = (
    <>
      {viewToggle}
      <Select allowClear showSearch aria-label="店铺" className="report-filter-select" placeholder="全部店铺" style={{ width: 220 }}
        value={filters.store} options={board?.stores} optionFilterProp="label" onChange={(store) => commit({ store })} />
      <Select allowClear aria-label="物流商" className="report-filter-select" placeholder="物流商" style={{ width: 140 }}
        value={filters.provider} options={board?.providers} onChange={(provider) => commit({ provider, channel: undefined })} />
      <Select allowClear showSearch aria-label="物流渠道" className="report-filter-select" placeholder="物流渠道" style={{ width: 200 }}
        value={filters.channel} options={channelOptions} optionFilterProp="label" onChange={(channel) => commit({ channel })} />
      <Select allowClear aria-label="目的地区" className="report-filter-select" placeholder="目的地区" style={{ width: 110 }}
        value={filters.region} options={(board?.regions ?? []).map((r) => ({ value: r, label: r }))} onChange={(region) => commit({ region })} />
      {view === "overview" ? (
        <Select allowClear aria-label="当前阶段" className="report-filter-select" placeholder="当前阶段" style={{ width: 140 }}
          value={filters.stage} options={(board?.stages ?? []).map((s) => ({ value: s, label: `${s}（${board?.stage_counts[s] ?? 0}）` }))} onChange={(stage) => commit({ stage })} />
      ) : (
        <Select allowClear aria-label="严重度" className="report-filter-select" placeholder="严重度" style={{ width: 100 }}
          value={filters.sev} options={[{ value: "high", label: "高" }, { value: "mid", label: "中" }, { value: "low", label: "低" }]} onChange={(sev) => commit({ sev })} />
      )}
    </>
  );

  const overviewColumns: ProColumns<LogisticsRow & { id: string }>[] = [
    {
      title: "发货单号 · 运单号", width: 230, fixed: "left",
      render: (_, s) => (
        <span>
          <a>{s.code}</a><br />
          {s.tracking.length ? <Text type="secondary">{s.tracking.join(" / ")}</Text> : <Tag color="warning" bordered={false}>运单号缺失</Tag>}<br />
          <Text type="secondary">{s.status} · {s.created} · {s.creator}</Text>
        </span>
      ),
    },
    { title: "当前阶段", width: 120, render: (_, s) => <StageTag stage={s.stage} /> },
    { title: "物流商 · 渠道", width: 210, render: (_, s) => <span>{s.provider || `ID ${s.provider_id}`}<br /><Text type="secondary">{s.channel || `ID ${s.channel_id}`}{s.method ? ` · ${s.method}` : ""}</Text></span> },
    { title: "目的仓 · 地区", width: 110, render: (_, s) => <span>{s.fc || "—"}<br /><Text type="secondary">{s.region}</Text></span> },
    { title: "店铺", width: 200, render: (_, s) => s.stores.join(" / ") || "—" },
    { title: "总箱数", width: 90, align: "right", render: (_, s) => <span>{fmt(s.boxes)}{!s.cargos.length && <><br /><Tag color="warning" bordered={false}>未关联货件</Tag></>}</span> },
    { title: "计费重 kg", width: 110, align: "right", render: (_, s) => (s.chargeWeight ? fmt(s.chargeWeight) : <span>{fmt(s.gw)}<br /><Text type="secondary">领星毛重</Text></span>) },
    {
      title: "实际费用", width: 130, align: "right",
      render: (_, s) => (s.cost.transport || s.cost.other
        ? <span>{money(s.cost.transport + s.cost.other, s.cost.currency)}<br /><Text type="secondary">运费 {money(s.cost.transport, s.cost.currency)}</Text></span>
        : s.status === "已发货" ? <Tag color="warning" bordered={false}>未录入</Tag> : "—"),
    },
    { title: "提货 / 发货", width: 100, render: (_, s) => s.pickup || "—" },
    { title: "开船时间", width: 100, render: (_, s) => s.atd || "—" },
    { title: "到港 实际 / 预计", width: 130, render: (_, s) => <span>{s.ata || "—"}<br /><Text type="secondary">预计 {s.eta || "—"}</Text></span> },
    {
      title: "到仓 实际 / 预计", width: 170,
      render: (_, s) => (
        <span>
          {s.arrivalActual || "—"}{s.arrivalActual && <Text type="secondary"> {ARR_SRC[s.arrivalActualSrc]}</Text>}<br />
          <Text type="secondary">预计 {s.arrivalPlan || "—"}{s.arrivalPlanSrc ? ` · ${ARR_SRC[s.arrivalPlanSrc] ?? s.arrivalPlanSrc}` : ""}</Text>
        </span>
      ),
    },
    {
      title: "到仓日期（取值）", width: 140,
      render: (_, s) => (s.arrivalDate
        ? <span>{s.arrivalDate} <Tag bordered={false} color={s.arrivalSrc === "real" ? "success" : "processing"}>{s.arrivalSrc === "real" ? "实际" : s.arrivalSrc === "calc" ? "推算" : "预计"}</Tag>{s.daysToArrival != null && !s.done && <><br /><Text type="secondary">{s.daysToArrival >= 0 ? `还有 ${s.daysToArrival} 天` : `已过 ${-s.daysToArrival} 天`}</Text></>}</span>
        : "—"),
    },
    {
      title: "Walmart 开始收货 / 完成", width: 170,
      render: (_, s) => <span>{s.wmReceiptStart || s.wmFirstReceive || "—"}<br /><Text type="secondary">完成 {s.wmReceiptDone ? s.wmLastReceipt : s.wmLastReceipt ? `收货中（最近 ${s.wmLastReceipt}）` : "—"}</Text></span>,
    },
    { title: "到货 vs Walmart 签收", width: 170, render: (_, s) => <SignGap s={s} today={today} /> },
    { title: "合同时效", width: 90, align: "right", render: (_, s) => (s.ct ? `${s.ct} 天` : "无") },
    {
      title: "可售（首批上架）", width: 140,
      render: (_, s) => (s.sellableDate
        ? <span>{s.sellableDate} <Tag bordered={false} color={s.sellableSrc === "real" ? "success" : "processing"}>{s.sellableSrc === "real" ? "实际" : "预计"}</Tag>{s.sellableSrc !== "real" && s.daysToSellable != null && !["Walmart 完成", "已作废"].includes(s.stage) && <><br /><Text type="secondary">{s.daysToSellable >= 0 ? `还有 ${s.daysToSellable} 天` : `已过 ${-s.daysToSellable} 天未上架`}</Text></>}</span>
        : "—"),
    },
    { title: "可索赔", width: 100, align: "right", render: (_, s) => (s.penalty ? <Text type="danger">¥{s.penalty}</Text> : "—") },
    {
      title: "剩余 / 超时", width: 110,
      render: (_, s) => (s.remain == null ? "—"
        : s.done ? (s.usedDays != null ? `用时 ${s.usedDays} 天` : "已完成")
        : s.remain < 0 ? <Tag color="error" bordered={false}>超 {-s.remain} 天</Tag>
        : s.soon ? <Tag color="warning" bordered={false}>剩 {s.remain} 天</Tag>
        : `剩 ${s.remain} 天`),
    },
    {
      title: "缺失 / 异常", width: 220,
      render: (_, s) => (s.ex.length
        ? <span>{s.ex.slice(0, 3).map((e, i) => <Tag key={i} bordered={false} color={e.sev === "high" ? "error" : e.sev === "mid" ? "warning" : "default"}>{e.type}</Tag>)}{s.ex.length > 3 && <Text type="secondary">+{s.ex.length - 3}</Text>}</span>
        : "—"),
    },
  ];

  const alertColumns: ProColumns<AlertRow>[] = [
    { title: "严重度", width: 70, render: (_, e) => <SevTag sev={e.sev} /> },
    { title: "类型", width: 200, render: (_, e) => <b>{e.type}</b> },
    { title: "发货单", width: 170, render: (_, e) => <a>{e.s.code}</a> },
    { title: "阶段", width: 120, render: (_, e) => <StageTag stage={e.s.stage} /> },
    { title: "物流商 · 渠道 · 地区", width: 230, render: (_, e) => <span>{e.s.provider}<br /><Text type="secondary">{e.s.channel} · {e.s.fc} {e.s.region}</Text></span> },
    { title: "店铺", width: 200, render: (_, e) => e.s.stores.join(" / ") || "—" },
    { title: "说明", width: 420, render: (_, e) => <span className="logi-wrap">{e.desc}</span> },
    { title: "发现", width: 110, render: (_, e) => e.since || "—" },
  ];

  const common = {
    page,
    helpHref: "/help/pmc-logistics.html",
    emptyText: q.isFetching ? "正在加载" : "当前条件下暂无数据",
    searchAriaLabel: "搜索物流看板",
    inputAriaLabel: "搜索物流看板关键字",
    inputPlaceholder: "输入关键字",
    typeAriaLabel: "物流看板搜索类型",
    typeOptions: [
      { value: "sp", label: "发货单" },
      { value: "cargo", label: "WFS 货件" },
      { value: "track", label: "运单号" },
      { value: "sku", label: "SKU/MSKU/GTIN" },
    ],
    searchType: filters.field,
    keyword: filters.keyword,
    onSearch: (keyword: string, field: string) => commit({ keyword, field: field as SearchField }),
    onReset: () => { setFilters(initial()); setPagination({ page: 1, size: 50 }); },
    filters: filterBar,
    aboveToolbar: header,
    loading: q.isFetching,
    loadingLabel: "正在加载物流看板，请稍候",
    total: rows.length,
    current: pagination.page,
    pageSize: pagination.size,
    onPageChange: (p: number, size: number) => setPagination({ page: p, size }),
  };

  return (
    <>
      {view === "overview" ? (
        <WfsQueryPage<LogisticsRow & { id: string }>
          {...common}
          title={`物流总览（${overviewRows.length} / ${sps.length} 张 · ${fmt(overviewRows.reduce((n, s) => n + s.qty, 0))} 件 · ${fmt(overviewRows.reduce((n, s) => n + s.boxes, 0))} 箱）`}
          tableLabel="物流总览表格"
          columns={overviewColumns}
          scrollX={3100}
          rows={pageRows as (LogisticsRow & { id: string })[]}
          onRowClick={(s) => setOpen(s.code)}
        />
      ) : (
        <WfsQueryPage<AlertRow>
          {...common}
          title={`异常与提醒（${alertRows.length} / ${allAlerts.length} 条）`}
          tableLabel="物流异常表格"
          columns={alertColumns}
          scrollX={1520}
          rows={pageRows as AlertRow[]}
          onRowClick={(e) => setOpen(e.s.code)}
        />
      )}
      {open && (
        <LogisticsDrawer
          code={open}
          scope={scope}
          buffer={rules?.wm_receive_buffer ?? 10}
          deliveredNotSigned={rules?.delivered_not_signed ?? 2}
          onClose={() => setOpen(undefined)}
        />
      )}
    </>
  );
}
