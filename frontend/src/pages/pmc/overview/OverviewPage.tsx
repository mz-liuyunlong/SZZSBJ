/**
 * PMC 总看板 (PRP pmc-overview, read-only), laid out after 8088 `features/pmc-overview`.
 *
 * 12 stat cards (click = quick filter), ItemID main table, detail drawer, warehouse tab,
 * read-only rules tab and a 5-sheet Excel. All numbers come from `/api/pmc/overview/*`;
 * the page does no business math. 5173 source = one 8088 data-day snapshot (shown in the
 * header), so the page says which data day it is and never falls back to sample data.
 */
import { Alert, Button, Card, Drawer, Dropdown, Input, Select, Space, Switch, Table, Tabs, Tag, Tooltip, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useState, type ReactNode } from "react";
import PageShell from "@/components/page/PageShell";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import { WalmartItemLink } from "@/components/report-table/cells";
import type { NavigationPage } from "@/config/navigation";
import { getOverviewExport, overviewErrorText } from "@/pages/pmc/overview/overviewApi";
import {
  addDays,
  CAT_COLOR,
  coverFallback,
  domAvailable,
  fmt,
  fmt1,
  KIND,
  PARAM_DOC,
  poOutstanding,
} from "@/pages/pmc/overview/overviewDisplay";
import {
  useOverviewItemQuery,
  useOverviewItemsQuery,
  useOverviewOptionsQuery,
  useOverviewRulesQuery,
  useOverviewSummaryQuery,
  useOverviewWarehousesQuery,
} from "@/pages/pmc/overview/overviewQueries";
import {
  createInitialOverviewFilters,
  OVERVIEW_CATEGORIES,
  OVERVIEW_PAGE_SIZES,
  type OverviewCategory,
  type OverviewFilters,
  type OverviewItemDetail,
  type OverviewItemRow,
  type OverviewKpi,
  type OverviewPageSize,
  type OverviewSummary,
} from "@/pages/pmc/overview/overviewTypes";
import { downloadOverviewWorkbook } from "@/pages/pmc/overview/overviewWorkbook";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import "@/pages/pmc/overview/OverviewPage.css";

const Muted = ({ children }: { children: ReactNode }) => <Typography.Text type="secondary">{children}</Typography.Text>;

type CardKey = "all" | OverviewCategory;

const mark = (text: string) => <span className="management-stat-card__mark">{text}</span>;

function buildCards(k: OverviewKpi | undefined, p: Record<string, number>): ManagementStatCardItem<CardKey>[] {
  const v = (pick: (x: OverviewKpi) => number) => (k ? pick(k) : "—");
  const card = (
    key: CardKey, title: string, value: number | string, subtitle: string, icon: string,
    tone: ManagementStatCardItem["tone"],
  ): ManagementStatCardItem<CardKey> => ({ key, title, value, subtitle, tone, icon: mark(icon), layout: "leading" });
  return [
    card("all", "ItemID 总数", v((x) => x.items), k ? `正常 ${fmt(k.normal)} · 草稿 ${fmt(k.drafts)}${k.listing_bad ? ` · Listing 异常 ${fmt(k.listing_bad)}` : ""}` : "", "品", "normal"),
    card("已断货", "已断货", v((x) => x.oos), `日销 > 0 且 WFS 可售 < ${p.instockMin ?? 5}`, "断", "danger"),
    card("断货风险", "断货风险", v((x) => x.risk), "卖完前下一批到不了", "!", "danger"),
    card("供应链异常", "供应链异常", v((x) => x.supply_chain), "超期未上架 / 查验 / 采购超期 / 缺箱规", "链", "warning"),
    card("执行异常", "执行异常", v((x) => x.execution), `国内仓 > ${p.domesticDays ?? 7} 天 / 审批·下单超时`, "执", "warning"),
    card("海外仓可补", "海外仓可补", v((x) => x.overseas), "先补海外仓，再看差额", "海", "normal"),
    card("库存过剩", "库存过剩", v((x) => x.over1), `覆盖 ${p.over1 ?? 120}–${p.over2 ?? 150} 天`, "剩", "normal"),
    card("严重过剩", "严重过剩", v((x) => x.over2), `覆盖 > ${p.over2 ?? 150} 天`, "重", "warning"),
    card("滞销", "滞销", v((x) => x.stale), `有货 ≥ ${p.salesMinDays ?? 14} 天销量 0`, "滞", "normal"),
    card("近 90 天无库存", "近 90 天无库存", v((x) => x.no_stock_90), k ? `有库存不足 30 天 ${fmt(k.low_days)}` : "", "无", "normal"),
    card("超期未上架", "超期未上架", v((x) => x.overdue), "已过预计可售日", "期", "warning"),
    card("缺默认箱规", "缺默认箱规", v((x) => x.box_missing), "已发过货仍无箱规", "箱", "warning"),
  ];
}

const activeCardOf = (f: OverviewFilters): CardKey | "" => {
  if (!f.cats.length && !f.onlyIssue) return "all";
  return f.cats.length === 1 ? f.cats[0] : "";
};

function mainColumns(salesMinDays: number): ColumnsType<OverviewItemRow> {
  return [
    { title: "ItemID", key: "item_id", width: 118, fixed: "left", render: (_, r) => <WalmartItemLink itemId={r.item_id} /> },
    { title: "SKU / 品名", key: "sku", width: 190, fixed: "left", render: (_, r) => <div><b>{r.sku}</b><br /><Muted>{r.name}</Muted></div> },
    { title: "MSKU", key: "msku", width: 120, render: (_, r) => r.msku ? <span className="pmc-overview__mono">{r.msku}</span> : <Muted>—</Muted> },
    {
      title: "店铺", key: "stores", width: 150,
      render: (_, r) => r.stores.length ? (
        <Tooltip title={r.stores.map((s) => `${s.name}：销 ${s.sales30} · 可售 ${s.available} · 在途 ${s.intransit}`).join("\n")}>
          <span>{r.stores[0].name.split("-")[0]}{r.stores.length > 1 && <Tag bordered={false} style={{ marginLeft: 4 }}>+{r.stores.length - 1} 店</Tag>}</span>
        </Tooltip>
      ) : <Muted>—</Muted>,
    },
    { title: "负责人", key: "owner", width: 80, render: (_, r) => r.owner || <Muted>—</Muted> },
    {
      title: "主要问题", key: "main", width: 230,
      render: (_, r) => r.issues.length
        ? <div><Tag color={CAT_COLOR[r.main] ?? r.level} bordered={false}>{r.main}</Tag><Muted>{r.issues[0].detail}</Muted></div>
        : <Tag color="green" bordered={false}>正常</Tag>,
    },
    { title: "采购未到", key: "po", width: 80, align: "right", render: (_, r) => fmt(poOutstanding(r)) },
    { title: "国内仓 可用/锁定", key: "dom", width: 110, align: "right", render: (_, r) => `${fmt(domAvailable(r))} / ${fmt(r.dom_lock)}` },
    { title: "已发货未可售", key: "shipped", width: 100, align: "right", render: (_, r) => fmt(r.seg.shipped ?? 0) },
    { title: "已到·收货中", key: "receiving", width: 95, align: "right", render: (_, r) => fmt(r.seg.receiving ?? 0) },
    { title: "WFS 可售", key: "wfs", width: 85, align: "right", render: (_, r) => <span className={r.oos ? "pmc-overview__neg" : ""}>{fmt(r.wm_available)}</span> },
    { title: "全链路供应", key: "supply", width: 95, align: "right", render: (_, r) => <b>{fmt(r.supply)}</b> },
    { title: "日销", key: "daily", width: 70, align: "right", render: (_, r) => fmt1(r.daily) },
    { title: "有库存天数", key: "n30", width: 90, align: "right", render: (_, r) => <span className={r.n30 < 30 ? "pmc-overview__warn" : ""}>{r.n30}</span> },
    { title: "断货天数", key: "oos_days", width: 80, align: "right", render: (_, r) => r.oos_days === null ? <Muted>90+</Muted> : r.oos_days > 0 ? <b className="pmc-overview__neg">{r.oos_days}</b> : <Muted>0</Muted> },
    { title: "能卖到", key: "sellout", width: 100, render: (_, r) => r.sellout ? <span className={r.risk || r.oos ? "pmc-overview__neg" : ""}>{r.sellout}</span> : <Muted>{r.daily > 0 ? "400 天+" : "—"}</Muted> },
    { title: "下一批可售", key: "next", width: 100, render: (_, r) => r.next_date || <Muted>—</Muted> },
    { title: "预计断货天数", key: "gap", width: 100, align: "right", render: (_, r) => r.gap_days !== null ? <b className="pmc-overview__neg">{r.gap_days}</b> : <Muted>{r.sellout ? "无来货" : "—"}</Muted> },
    { title: "覆盖天数", key: "cover", width: 85, align: "right", render: (_, r) => r.cover !== null ? <span className={r.over === "严重过剩" ? "pmc-overview__warn" : ""}>{fmt(r.cover)}</span> : <Muted>{coverFallback(r, salesMinDays)}</Muted> },
    { title: "补货状态", key: "draft", width: 200, render: (_, r) => r.is_draft ? r.draft_text : <Muted>{r.draft_text}</Muted> },
    { title: "全部提示", key: "issues", width: 260, render: (_, r) => <Space size={[4, 4]} wrap>{r.issues.slice(1).map((i) => <Tag key={i.label} color={i.level} bordered={false}>{i.label}</Tag>)}</Space> },
  ];
}

const KV = ({ k, v }: { k: string; v: ReactNode }) => (
  <div className="pmc-overview__kv"><span>{k}</span><strong>{v === null || v === undefined || v === "" ? "—" : v}</strong></div>
);

function ItemDrawer({ r, today, p, onClose }: { r: OverviewItemDetail; today: string; p: Record<string, number>; onClose: () => void }) {
  const batches = r.batches.filter((b) => b.qty > 0);
  const domesticDays = p.domesticDays ?? 7;
  const salesMinDays = p.salesMinDays ?? 14;
  return (
    <Drawer open width="min(960px, calc(100vw - 24px))" onClose={onClose}
      title={<span><WalmartItemLink itemId={r.item_id} /> · {r.sku} · {r.name} <Tag color={CAT_COLOR[r.main] ?? "green"} bordered={false}>{r.main}</Tag></span>}>
      <h4>店铺分布</h4>
      <Table size="small" pagination={false} rowKey="id" dataSource={r.stores} columns={[
        { title: "店铺", dataIndex: "name" },
        { title: "近 30 天销量", dataIndex: "sales30", align: "right", render: fmt },
        { title: "WFS 可售", dataIndex: "available", align: "right", render: fmt },
        { title: "在途（该店铺发起）", dataIndex: "intransit", align: "right", render: fmt },
      ]} />
      <h4>断货时间线</h4>
      <div className="pmc-overview__kv-grid">
        <KV k="日销" v={r.no_stock_90 ? "近 90 天无库存" : `${fmt1(r.daily)} 件/天（最近 ${r.n30} 个有货日，回看 ${r.n_window ?? "—"} 天）`} />
        <KV k="断货天数" v={r.oos_days === null ? "90 天以上" : r.oos_days > 0 ? `${r.oos_days} 天（最后有货日 ${addDays(today, -r.oos_days - 1)}）` : "未断货"} />
        <KV k="全链路有效供应" v={`${fmt(r.supply)} 件`} />
        <KV k="现有可售能卖到" v={r.sellout ?? (r.daily > 0 ? "400 天内不断货" : "无销量")} />
        <KV k="下一批预计可售" v={r.next_date ?? "无来货"} />
        <KV k="预计断货天数" v={r.gap_days !== null ? `${r.gap_days} 天（${r.resume} 恢复）` : r.sellout ? "之后无来货" : "—"} />
        <KV k="库存覆盖天数" v={r.cover !== null ? `${fmt(r.cover)} 天 · ${r.over}` : coverFallback(r, salesMinDays)} />
        <KV k="提前期" v={`${fmt1(r.lead_total)} 天（采购交期 ${fmt1(r.lead_p)}）`} />
        <KV k="补货周期" v={`${r.cycle_days ?? "—"} 天`} />
      </div>
      <h4>供应链批次（互斥口径，按预计可售日）</h4>
      <Table size="small" pagination={false} rowKey={(b) => `${b.kind}-${b.date}-${b.note}-${b.qty}`} dataSource={batches}
        rowClassName={(b) => (b.overdue ? "pmc-overview__row-hl" : "")}
        columns={[
          { title: "状态", width: 120, render: (_, b) => <Tag bordered={false}>{KIND[b.kind] ?? b.kind}</Tag> },
          { title: "件数", dataIndex: "qty", width: 80, align: "right", render: fmt },
          { title: "预计可售日", dataIndex: "date", width: 110, render: (v: string | undefined) => (v === today ? "现在（收货中）" : v || "—") },
          { title: "说明", render: (_, b) => <span>{b.store && r.stores.length > 1 ? <Muted>【{b.store}】</Muted> : null}{b.note}{b.overdue && <Tag color="red" bordered={false} style={{ marginLeft: 6 }}>已过可售日</Tag>}{b.inspected && <Tag color="volcano" bordered={false}>查验</Tag>}</span> },
        ]} />
      {r.dom_rows.length > 0 && <>
        <h4>国内仓批次在仓天数（惠州）</h4>
        <Table size="small" pagination={false} rowKey="batch" dataSource={r.dom_rows}
          rowClassName={(b) => (b.age > domesticDays ? "pmc-overview__row-hl" : "")}
          columns={[
            { title: "批次", dataIndex: "batch", render: (v: string) => <span className="pmc-overview__mono">{v}</span> },
            { title: "入库日", dataIndex: "in_date" },
            { title: "在仓天数", dataIndex: "age", align: "right", render: (v: number) => <span className={v > domesticDays ? "pmc-overview__warn" : ""}>{v} 天</span> },
            { title: "余额件数", dataIndex: "qty", align: "right", render: fmt },
          ]} />
      </>}
      <h4>异常与提示</h4>
      {r.issues.length === 0 ? <Muted>无异常</Muted> : r.issues.map((i) => <div key={i.label} className="pmc-overview__note"><Tag color={i.level} bordered={false}>{i.label}</Tag>{i.detail}</div>)}
      <h4>补货</h4>
      <div className="pmc-overview__formula">
        <div>建议量 = 日销 {fmt1(r.daily)} ×（提前期 {fmt1(r.lead_total)} + 补货周期 {r.cycle_days ?? "—"}{p.safety ? ` + 安全 ${p.safety}` : ""}）− 有效供应 {fmt(r.supply)} = <b>{fmt(r.suggest)}</b> 件</div>
        {r.overseas_alloc > 0 && <div>扣海外仓 <b>{fmt(r.overseas_alloc)}</b> 件（同 SKU 海外仓共 {fmt(r.overseas_total)} 件，断货最早的 ItemID 先用；海外仓 → WFS 人工处理）</div>}
        {r.suggest > 0 && <div>国内采购 = {fmt(r.purchase)} 件{r.boxed ? ` → 按默认箱规 ${r.box} 件/箱取整 = ${fmt(r.boxed)} 件` : ""}{r.purchase < (p.minQty ?? 50) ? `（< ${p.minQty ?? 50} 件不出草稿）` : ""}</div>}
        <div>{r.is_draft && <Tag color="cyan" bordered={false} className="pmc-overview__mono">{r.draft_id}</Tag>}<b>{r.draft_text}</b>{r.is_draft && <Muted> · 草稿以「自动补货」页为准（本页只读）</Muted>}</div>
      </div>
      <h4>运营日志</h4>
      <Alert type="info" showIcon message="运营日志模块未建，后续讨论；上线后这里显示该 ItemID 的运营判断、处理与跟进记录。" />
    </Drawer>
  );
}

function WarehouseTab() {
  const query = useOverviewWarehousesQuery(true);
  if (query.error) return <Alert type="error" showIcon message={overviewErrorText(query.error)} />;
  const data = query.data;
  return (
    <div>
      <div className="pmc-overview__shell-head"><b>仓库分布</b><Muted>领星仓库库存明细（全量）；只列国内仓 / 海外仓且有库存的仓；在仓天数按批次入库日</Muted></div>
      <Table size="small" loading={query.isPending} pagination={false} rowKey="name" dataSource={data?.warehouses ?? []} columns={[
        { title: "仓库", dataIndex: "name" },
        { title: "分类", dataIndex: "warehouse_class", render: (v: string) => <Tag bordered={false} color={v === "海外仓" ? "blue" : "default"}>{v}</Tag> },
        { title: "可用", dataIndex: "valid", align: "right", render: fmt },
        { title: "锁定", dataIndex: "lock", align: "right", render: fmt },
        { title: "在库合计", dataIndex: "total", align: "right", render: fmt },
        { title: "调拨在途", dataIndex: "onway", align: "right", render: fmt },
        { title: "有库存 SKU", dataIndex: "skus", align: "right" },
        { title: "在仓天数 平均 / 最长", key: "age", render: (_, w) => w.age_avg !== null ? `${w.age_avg} / ${w.age_max} 天` : <Muted>—</Muted> },
        { title: "在仓天数分布", key: "bands", render: (_, w) => Object.keys(w.age_bands).length ? Object.entries(w.age_bands).map(([k, v]) => `${k} ${fmt(v)}`).join(" · ") : <Muted>—</Muted> },
      ]} />
      {data && <Alert style={{ marginTop: 12 }} type="warning" showIcon message={`海外仓 ${fmt(data.overseas_total)} 件不计入 ItemID 主表与覆盖天数。`} />}
    </div>
  );
}

function RulesTab() {
  const query = useOverviewRulesQuery(true);
  if (query.error) return <Alert type="error" showIcon message={overviewErrorText(query.error)} />;
  const values = new Map((query.data?.params ?? []).map((x) => [x.key, x.value]));
  return (
    <div>
      <Alert type="info" showIcon style={{ marginBottom: 12 }}
        message={`一期只读（PRP D5）：规则版本 ${query.data?.rule_version ?? "—"}；要改参数走规则版本，不在本页改。`} />
      <div className="pmc-overview__set-grid">
        {PARAM_DOC.map((d) => d.length === 1
          ? <div key={d[0]} className="pmc-overview__shell-head pmc-overview__set-group"><b>{d[0]}</b></div>
          : <div key={d[0]} className="pmc-overview__set-row"><div><b>{d[1]}</b><br /><Muted>{d[2]}</Muted></div><strong>{values.get(d[0]) ?? "—"}</strong></div>)}
      </div>
    </div>
  );
}

function Footer({ s, overseasItems }: { s: OverviewSummary; overseasItems: number }) {
  const byKind = Object.fromEntries(s.unattributed.map((x) => [x.kind, x.qty]));
  return (
    <div className="pmc-overview__foot">
      <b>未归属到 ItemID（不计入任何一行）</b>：采购计划 {fmt(byKind.plan ?? 0)} · 采购单待到货 {fmt(byKind.po ?? 0)} · 待下单 {fmt(byKind.po_pending ?? 0)} · 国内仓 {fmt(byKind.domestic ?? 0)} · 已发货货件 {fmt(byKind.shipped ?? 0)} 件（原因：{s.unattributed.map((x) => `${KIND[x.kind] ?? x.kind} ${fmt(x.qty)} 件 ${x.why}`).join("；")}）。
      <b>海外仓</b>（不计入全流程库存，按 SKU 单独统计）：{fmt(s.overseas_total)} 件；本轮可先补 WFS 的 ItemID {fmt(overseasItems)} 个。
    </div>
  );
}

interface OverviewPageProps {
  page: NavigationPage;
  preferenceScope?: string;
}

function OverviewPage({ page, preferenceScope = "anonymous" }: OverviewPageProps) {
  const [messageApi, holder] = message.useMessage();
  const stateKey = `pmc-overview:${preferenceScope}`;
  const [filters, setFilters] = usePageStateCache(`${stateKey}:filters`, createInitialOverviewFilters);
  const [keywordDraft, setKeywordDraft] = useState(filters.keyword);
  const [currentPage, setCurrentPage] = usePageStateCache(`${stateKey}:page`, 1);
  const [pageSize, setPageSize] = usePageStateCache<OverviewPageSize>(`${stateKey}:pageSize`, 50);
  const [tab, setTab] = usePageStateCache(`${stateKey}:tab`, "main");
  const [openId, setOpenId] = useState<string>();
  const [exporting, setExporting] = useState(false);

  const summaryQuery = useOverviewSummaryQuery();
  const itemsQuery = useOverviewItemsQuery(filters, currentPage, pageSize);
  const optionsQuery = useOverviewOptionsQuery();
  const detailQuery = useOverviewItemQuery(openId);

  const summary = summaryQuery.data;
  const p = summary?.params ?? {};
  const salesMinDays = p.salesMinDays ?? 14;
  const total = itemsQuery.data?.total ?? 0;
  const pageError = summaryQuery.error ?? itemsQuery.error;

  const commit = (next: Partial<OverviewFilters>) => {
    setFilters({ ...filters, ...next });
    setCurrentPage(1);
  };
  const toggleCard = (key: CardKey) => {
    if (key === "all") commit({ cats: [], onlyIssue: false });
    else commit({ cats: filters.cats.includes(key) ? filters.cats.filter((c) => c !== key) : [key], onlyIssue: true });
  };
  const reset = () => {
    setKeywordDraft("");
    commit(createInitialOverviewFilters());
  };

  const download = async (all: boolean) => {
    setExporting(true);
    const hide = messageApi.loading("正在生成 Excel…", 0);
    try {
      const data = await getOverviewExport(all ? undefined : filters);
      downloadOverviewWorkbook(data, all);
      void messageApi.success(`已下载（${fmt(data.items.length)} 个 ItemID）`);
    } catch (reason) {
      void messageApi.error(overviewErrorText(reason));
    } finally {
      hide();
      setExporting(false);
    }
  };

  return (
    <PageShell page={page}>
      {holder}
      <div className="pmc-overview">
        <Card size="small" className="pmc-overview__page-card">
          <RequestLoadingOverlay spinning={summaryQuery.isPending && !pageError} label="正在加载总看板，请稍候" />
          <div className="pmc-overview__title-row">
            <div>
              <h1>PMC 总看板</h1>
              <p>看全局 → 发现问题 → 给出提示。按 ItemID 汇总采购、国内仓、在途、WFS 和销量，提示断货、过剩、供应链 / 执行异常；业务操作回各模块。</p>
            </div>
            <div className="pmc-overview__meta">
              {summary && <div>数据日 <b>{summary.data_date}</b> · <Tag color="gold" bordered={false}>8088 数据日快照（过渡，每周刷新）</Tag></div>}
              {summary && <Muted>{summary.source_note.split("；")[0]}</Muted>}
              <Dropdown disabled={!summary || exporting} menu={{
                items: [
                  { key: "all", label: `下载全部（${fmt(summary?.kpi.items)} 个 ItemID）` },
                  { key: "filtered", label: `下载当前筛选（${fmt(total)} 个 ItemID）` },
                ],
                onClick: ({ key }) => void download(key === "all"),
              }}>
                <Button type="primary" loading={exporting}>下载 Excel ▾</Button>
              </Dropdown>
            </div>
          </div>

          {pageError && <Alert className="pmc-overview__error" type={(pageError as { status?: number }).status === 503 ? "warning" : "error"} showIcon message={overviewErrorText(pageError)} />}

          <ManagementStatCards<CardKey | "">
            ariaLabel="总看板统计"
            className="pmc-overview__cards"
            cards={buildCards(summary?.kpi, p)}
            activeKey={activeCardOf(filters)}
            onCardClick={(key) => key && toggleCard(key)}
          />

          <Tabs activeKey={tab} onChange={setTab} items={[
            {
              key: "main",
              label: <span>ItemID 主表 <Tag bordered={false}>{fmt(total)}</Tag></span>,
              children: (
                <div>
                  <div className="pmc-overview__toolbar">
                    <Select allowClear placeholder="全部店铺" value={filters.storeId} style={{ width: 230 }}
                      options={(optionsQuery.data?.stores ?? []).map((s) => ({ value: s.id, label: s.name }))}
                      onChange={(v?: string) => commit({ storeId: v })} />
                    <Select allowClear showSearch placeholder="负责人" value={filters.owner} style={{ width: 130 }}
                      options={(optionsQuery.data?.owners ?? []).map((x) => ({ value: x, label: x }))}
                      onChange={(v?: string) => commit({ owner: v })} />
                    <Select mode="multiple" allowClear placeholder="快捷筛选：问题类型" value={filters.cats} style={{ minWidth: 260, flex: "1 1 260px" }}
                      maxTagCount="responsive" options={OVERVIEW_CATEGORIES.map((c) => ({ value: c, label: c }))}
                      onChange={(v: OverviewCategory[]) => commit({ cats: v })} />
                    <Input.Search allowClear placeholder="ItemID / SKU / MSKU / 品名 / 草稿号" value={keywordDraft} style={{ width: 240 }}
                      onChange={(e) => setKeywordDraft(e.target.value)} onSearch={(v) => commit({ keyword: v })} />
                    <span className="pmc-overview__switch">只看有问题的 <Switch size="small" checked={filters.onlyIssue} onChange={(v) => commit({ onlyIssue: v })} /></span>
                    <Button onClick={reset}>重置</Button>
                  </div>
                  <div className="pmc-overview__shell-head"><b>ItemID 主表</b><Muted>一行 = 一个 ItemID（多店铺合并）；各段互斥可相加，不含海外仓；默认只显示有问题的，按问题优先级排序；点行看详情</Muted></div>
                  <Table<OverviewItemRow>
                    size="small"
                    rowKey="item_id"
                    sticky
                    loading={itemsQuery.isFetching}
                    dataSource={itemsQuery.data?.rows ?? []}
                    columns={mainColumns(salesMinDays)}
                    scroll={{ x: 2600 }}
                    rowClassName={(r) => (r.oos || r.risk ? "pmc-overview__row-risk" : "")}
                    onRow={(r) => ({ onClick: () => setOpenId(r.item_id), style: { cursor: "pointer" } })}
                    locale={{ emptyText: pageError ? overviewErrorText(pageError) : "无符合条件的 ItemID" }}
                    pagination={{
                      current: currentPage,
                      pageSize,
                      total,
                      showSizeChanger: true,
                      pageSizeOptions: OVERVIEW_PAGE_SIZES.map(String),
                      showTotal: (t) => `共 ${fmt(t)} 个 ItemID`,
                      onChange: (nextPage, nextSize) => {
                        if (nextSize !== pageSize) {
                          setPageSize(nextSize as OverviewPageSize);
                          setCurrentPage(1);
                        } else setCurrentPage(nextPage);
                      },
                    }}
                  />
                  {summary && <Footer s={summary} overseasItems={summary.kpi.overseas} />}
                </div>
              ),
            },
            { key: "wh", label: "仓库分布", children: tab === "wh" ? <WarehouseTab /> : null },
            { key: "rules", label: "规则设置", children: tab === "rules" ? <RulesTab /> : null },
          ]} />

          <div className="pmc-overview__foot">
            <b>口径</b>：主表各段 = 自动补货互斥口径（可相加、不含海外仓）；下载的「店铺 × SKU 明细」= 运营数据表分段口径（可重叠、不要跨段相加）。
            <b>未接入</b>：Walmart 数据列（购物车 / 价格 / 质量分等，需 Walmart 报表接入另行审批）；归档；草稿审批状态；运营日志。本页只读，不调用领星 / Walmart。
          </div>
        </Card>
        {openId && detailQuery.data && summary && (
          <ItemDrawer r={detailQuery.data} today={summary.data_date} p={p} onClose={() => setOpenId(undefined)} />
        )}
        {openId && detailQuery.error && (
          <Alert type="error" showIcon closable onClose={() => setOpenId(undefined)} message={overviewErrorText(detailQuery.error)} />
        )}
      </div>
    </PageShell>
  );
}

export default OverviewPage;
