/** 到货预测（8088 pmc-logistics TabForecast）：已发货、货件未关闭的 店铺 × MSKU，按预计可售日分段。
 * 每行关联物流信息：发货单号 / 货件单号 / 运单号，可按这三种单号分别搜索（Rocky 2026-11-04）。
 * 计算在服务端（app/modules/pmc_logistics/forecast.py），筛选 / 分页在服务端。 */
import { Button, Drawer, Select, Table, Tag, Typography } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import type { NavigationPage } from "@/config/navigation";
import WfsQueryPage from "../wfs/WfsQueryPage";
import { LogisticsInlineDetail } from "./LogisticsDrawer";
import { getForecast, type BucketKey, type ForecastLine, type ForecastRow } from "./logisticsApi";
import { ARR_SRC, fmt } from "./logisticsFormat";
import { PAGE_SIZE, logisticsKey, useLogisticsOptions } from "./logisticsQueries";
import { DataDayNotice, StageTag } from "./logisticsShared";
import "./logistics.css";

const { Text } = Typography;

const BUCKETS: { k: BucketKey; l: string }[] = [
  { k: "bOver", l: "已过预计可售日未上架" },
  { k: "b15", l: "15 天内可售" },
  { k: "b30", l: "15–30 天可售" },
  { k: "b60", l: "30–60 天可售" },
  { k: "b60p", l: "超过 60 天可售" },
  { k: "bNone", l: "无预计日期" },
];

type Card = BucketKey | "total" | "arrived";
type SearchField = "sku" | "sp" | "cargo" | "track";
const SEARCH_TYPES: { value: SearchField; label: string }[] = [
  { value: "sku", label: "SKU/MSKU/GTIN/ItemID" },
  { value: "sp", label: "发货单号" },
  { value: "cargo", label: "货件单号" },
  { value: "track", label: "运单号" },
];
const PLACEHOLDER: Record<SearchField, string> = {
  sku: "SKU / MSKU / GTIN / ItemID / 品名",
  sp: "发货单号",
  cargo: "WFS 货件单号",
  track: "运单号",
};

/** 一组单号：最多显示 2 个，其余折成「+N」（悬停看全部）。 */
function Numbers({ label, values, onClick }: { label: string; values: string[]; onClick?: (v: string) => void }) {
  if (!values.length) return <div><Text type="secondary">{label} —</Text></div>;
  const shown = values.slice(0, 2);
  return (
    <div className="logi-nowrap" title={values.join("\n")}>
      <Text type="secondary">{label} </Text>
      {shown.map((v, i) => (
        <Fragment key={v}>{i > 0 && "、"}{onClick ? <a onClick={(e) => { e.stopPropagation(); onClick(v); }}>{v}</a> : <span>{v}</span>}</Fragment>
      ))}
      {values.length > 2 && <Text type="secondary"> +{values.length - 2}</Text>}
    </div>
  );
}

interface Filters {
  bucket?: Card;
  store?: string;
  region?: string;
  owner?: string;
  keyword: string;
  field: SearchField;
}

const initial = (): Filters => ({ keyword: "", field: "sku" });
const num = (v: number) => (v ? <span className="logi-num">{fmt(v)}</span> : <Text type="secondary">—</Text>);

export default function LogisticsForecastPage({ page, scope }: { page: NavigationPage; scope: string }) {
  const [filters, setFilters] = useState(initial);
  const [pg, setPg] = useState({ page: 1, size: PAGE_SIZE });
  const [detail, setDetail] = useState<ForecastRow>();
  // 明细里展开的行（发货单号-货件）：点发货单号就地展开 / 收起，不再弹第二层（Rocky 2026-11-04）
  const [expanded, setExpanded] = useState<string[]>([]);
  const lineKey = (x: ForecastLine) => `${x.code}-${x.cargo}`;
  const toggle = (key: string) => setExpanded((ks) => (ks.includes(key) ? ks.filter((k) => k !== key) : [...ks, key]));
  const openDetail = (r: ForecastRow, code?: string) => {
    setDetail(r);
    setExpanded(code ? r.lines.filter((x) => x.code === code).map(lineKey) : []);
  };
  const opts = useLogisticsOptions(scope);
  const options = opts.data?.data;
  const params = { ...filters, page: pg.page, page_size: pg.size };
  const q = useQuery({
    queryKey: logisticsKey(scope, "forecast", params),
    queryFn: ({ signal }) => getForecast(params, signal),
    retry: false,
    placeholderData: keepPreviousData,
  });
  const data = q.data?.data;
  const sum = data?.summary;
  const commit = (next: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...next }));
    setPg((p) => ({ ...p, page: 1 }));
  };

  const columns: ProColumns<ForecastRow & { id: string }>[] = [
    { title: "店铺", dataIndex: "store", width: 210, fixed: "left" },
    { title: "SKU / MSKU", width: 170, fixed: "left", render: (_, r) => <span><b>{r.sku}</b><br /><Text type="secondary">{r.msku}</Text></span> },
    {
      title: "ItemID", width: 120,
      render: (_, r) => (r.item_id
        ? <a href={`https://www.walmart.com/ip/${r.item_id}`} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{r.item_id}</a>
        : <Text type="secondary">—</Text>),
    },
    { title: "负责人", width: 100, render: (_, r) => r.owner || <Text type="secondary">—</Text> },
    { title: "GTIN", dataIndex: "gtin", width: 140, render: (_, r) => r.gtin || "—" },
    { title: "品名", dataIndex: "name", width: 200, ellipsis: true },
    {
      title: "关联物流（发货单 / 货件 / 运单）", width: 300,
      render: (_, r) => (
        <div className="logi-numbers">
          <Numbers label="发货单" values={r.codes} onClick={(code) => openDetail(r, code)} />
          <Numbers label="货件" values={r.cargos} />
          <Numbers label="运单" values={r.trackings} />
        </div>
      ),
    },
    { title: "未可售合计", width: 100, align: "right", render: (_, r) => (r.total ? <b>{fmt(r.total)}</b> : <Text type="secondary">—</Text>) },
    ...BUCKETS.filter((b) => b.k !== "bNone" || (sum?.bNone ?? 0) > 0).map((b): ProColumns<ForecastRow & { id: string }> => ({
      title: b.l, width: b.k === "bOver" ? 160 : 118, align: "right",
      render: (_, r) => (b.k === "bOver" && r.bOver ? <Text type="danger">{fmt(r.bOver)}</Text> : num(r[b.k])),
    })),
    { title: "其中：已签收未上架", width: 140, align: "right", render: (_, r) => num(r.signedNP) },
    {
      title: "已到·收货中：发货 / 签收 / 上架", width: 210, align: "right",
      render: (_, r) => (r.aShip
        ? <span>{fmt(r.aShip)} / {fmt(r.aSign)} / {r.aShelf > r.aSign ? <Text type="warning">{fmt(r.aShelf)}</Text> : fmt(r.aShelf)}
          {r.anom > 0 && <><br /><Tag color="warning" bordered={false}>未签收已上架 {r.anom}</Tag></>}
          {r.aSign !== r.aShelf && r.anom === 0 && <><br /><Text type="secondary">签收≠上架 {r.aSign - r.aShelf > 0 ? "+" : ""}{fmt(r.aSign - r.aShelf)}</Text></>}
        </span>
        : <Text type="secondary">—</Text>),
    },
    { title: "下一批预计到仓", width: 120, render: (_, r) => r.nextArr || "—" },
    { title: "下一批预计可售", width: 120, render: (_, r) => r.nextSell || "—" },
    { title: "货件行", width: 80, align: "right", render: (_, r) => r.lines.length },
    { title: "操作", width: 80, fixed: "right", render: () => <a>明细</a> },
  ];

  const t = (k: keyof NonNullable<typeof sum>) => fmt((sum?.[k] as number | undefined) ?? 0);
  const lineColumns = [
    {
      title: "发货单号", render: (_: unknown, x: ForecastLine) => (
        <a onClick={() => toggle(lineKey(x))} aria-expanded={expanded.includes(lineKey(x))}>{x.code}</a>
      ),
    },
    { title: "货件单号", render: (_: unknown, x: ForecastLine) => x.cargo || "—" },
    {
      title: "运单号", render: (_: unknown, x: ForecastLine) => (x.tracking.length
        ? <span>{x.tracking.map((t) => <div key={t}>{t}</div>)}<Text type="secondary">{x.provider}</Text></span>
        : <span><Text type="secondary">无运单号</Text>{x.provider && <><br /><Text type="secondary">{x.provider}</Text></>}</span>),
    },
    { title: "阶段", render: (_: unknown, x: ForecastLine) => <StageTag stage={x.stage} /> },
    { title: "目的仓", render: (_: unknown, x: ForecastLine) => `${x.fc} ${x.region}` },
    { title: "发货 / 签收 / 上架", align: "right" as const, render: (_: unknown, x: ForecastLine) => <span>{fmt(x.ship)} / {fmt(x.sign)} / {x.sign === 0 && x.shelf > 0 ? <Text type="warning">{fmt(x.shelf)}</Text> : fmt(x.shelf)}</span> },
    { title: "分段", render: (_: unknown, x: ForecastLine) => <Tag bordered={false} color={x.bucket === "已到·收货中" ? "success" : x.bucket === "已过预计可售日未上架" ? "error" : "processing"}>{x.bucket}</Tag> },
    {
      title: "到仓日", render: (_: unknown, x: ForecastLine) => (x.arr
        ? <span>{x.arr} <Tag bordered={false} color={x.arrReal ? "success" : "processing"}>{x.arrReal ? "实际" : "预计"}</Tag><br /><Text type="secondary">{ARR_SRC[x.arrSrc] ?? x.arrSrc}</Text></span>
        : "—"),
    },
    {
      title: "可售日", render: (_: unknown, x: ForecastLine) => (x.sell
        ? <span>{x.sell} <Tag bordered={false} color={x.sellReal ? "success" : "processing"}>{x.sellReal ? "首批上架" : "预计"}</Tag></span>
        : "—"),
    },
    { title: "距可售", align: "right" as const, render: (_: unknown, x: ForecastLine) => (x.days == null ? "—" : x.days >= 0 ? `${x.days} 天` : <Text type="danger">已过 {-x.days} 天</Text>) },
  ];

  return (
    <>
      <WfsQueryPage<ForecastRow & { id: string }>
        page={page}
        helpHref="/help/pmc-logistics.html"
        title={`到货预测 · 产品维度（${data?.total ?? 0} 行，按未可售件数排序）`}
        tableLabel="到货预测表格"
        emptyText={q.isFetching ? "正在加载" : "当前条件下暂无在途产品"}
        searchAriaLabel="搜索到货预测"
        inputAriaLabel="搜索到货预测关键字"
        inputPlaceholder={PLACEHOLDER[filters.field]}
        typeAriaLabel="到货预测搜索类型"
        typeOptions={SEARCH_TYPES}
        searchType={filters.field}
        keyword={filters.keyword}
        onSearch={(keyword, field) => commit({ keyword, field: field as SearchField })}
        onReset={() => { setFilters(initial()); setPg({ page: 1, size: PAGE_SIZE }); }}
        filters={(
          <>
            <Select allowClear showSearch aria-label="店铺" className="report-filter-select" placeholder="全部店铺" style={{ width: 220 }}
              value={filters.store} options={options?.stores} optionFilterProp="label" onChange={(store) => commit({ store })} />
            <Select allowClear aria-label="目的地区" className="report-filter-select" placeholder="目的地区" style={{ width: 110 }}
              value={filters.region} options={(options?.regions ?? []).map((r) => ({ value: r, label: r }))} onChange={(region) => commit({ region })} />
            <Select allowClear showSearch aria-label="负责人" className="report-filter-select" placeholder="负责人" style={{ width: 130 }}
              value={filters.owner} options={(options?.owners ?? []).map((o) => ({ value: o, label: o }))} onChange={(owner) => commit({ owner })} />
          </>
        )}
        aboveToolbar={(
          <>
            <DataDayNotice options={options} error={opts.error ?? q.error} />
            <ManagementStatCards<Card | "">
              ariaLabel="到货预测统计"
              activeKey={filters.bucket ?? ""}
              onCardClick={(k) => commit({ bucket: k === filters.bucket || !k ? undefined : k })}
              cards={[
                { key: "total", title: "已发货未可售（件）", value: sum?.total ?? 0, unit: "件", tone: "normal", icon: <span>件</span>, subtitle: `产品行 ${sum?.products ?? 0} · 其中已签收未上架 ${t("signedNP")}` },
                { key: "bOver", title: "已过预计可售日未上架", value: sum?.bOver ?? 0, unit: "件", tone: "danger", icon: <span>!</span>, subtitle: "追物流 / Walmart" },
                { key: "b15", title: "15 天内可售", value: sum?.b15 ?? 0, unit: "件", tone: "normal", icon: <span>15</span>, subtitle: "按预计可售日" },
                { key: "b30", title: "15–30 天可售", value: sum?.b30 ?? 0, unit: "件", tone: "normal", icon: <span>30</span>, subtitle: "按预计可售日" },
                { key: "b60", title: "30–60 天可售", value: sum?.b60 ?? 0, unit: "件", tone: "warning", icon: <span>60</span>, subtitle: "按预计可售日" },
                { key: "b60p", title: "超过 60 天可售", value: sum?.b60p ?? 0, unit: "件", tone: "warning", icon: <span>60+</span>, subtitle: sum?.bNone ? `无预计日期 ${t("bNone")}` : "按预计可售日" },
                { key: "arrived", title: "已到·收货中（发货件数）", value: sum?.aShip ?? 0, unit: "件", tone: "normal", icon: <span>到</span>, subtitle: `签收 ${t("aSign")} · 上架 ${t("aShelf")} · 未签收已上架 ${sum?.anom ?? 0} 行` },
              ]}
            />
          </>
        )}
        headExtra={(
          <Text type="secondary">
            到仓日有实际取实际（众壹签收 / Walmart 签收取早），没有实际取最新预计；可售日 = 到仓日 + {sum?.buffer ?? 10} 天；已有 ≥1 件上架 = 首批上架日（进「已到·收货中」）。
          </Text>
        )}
        loading={q.isFetching}
        loadingLabel="正在加载到货预测，请稍候"
        columns={columns}
        scrollX={2600}
        rows={(data?.items ?? []).map((r) => ({ ...r, id: r.key }))}
        total={data?.total ?? 0}
        current={pg.page}
        pageSize={pg.size}
        onPageChange={(p, size) => setPg({ page: p, size })}
        onRowClick={(r) => openDetail(r)}
      />
      <Drawer
        open={!!detail}
        width={1200}
        onClose={() => { setDetail(undefined); setExpanded([]); }}
        title={detail && <span>{detail.store} · <b>{detail.sku}</b> <Text type="secondary">{detail.msku}</Text></span>}
      >
        {detail && (
          <Table<ForecastLine>
            size="small"
            pagination={false}
            rowKey={lineKey}
            dataSource={detail.lines}
            columns={lineColumns}
            expandable={{
              expandedRowKeys: expanded,
              onExpand: (_, x) => toggle(lineKey(x)),
              columnTitle: "发货单详情",
              columnWidth: 96,
              expandIcon: ({ expanded: isOpen, record, onExpand }) => (
                <Button size="small" type="link" onClick={(e) => onExpand(record, e)}>{isOpen ? "收起" : "展开"}</Button>
              ),
              expandedRowRender: (x) => (
                <LogisticsInlineDetail
                  code={x.code}
                  scope={scope}
                  buffer={options?.rules.wm_receive_buffer ?? 10}
                  deliveredNotSigned={options?.rules.delivered_not_signed ?? 2}
                />
              ),
            }}
          />
        )}
      </Drawer>
    </>
  );
}
