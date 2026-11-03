/** 异常与提醒（8088 pmc-logistics TabAlerts）：一行一条异常，筛选 / 分页在服务端。
 * 8088 的「处理状态 / 负责人 / 记录 / 通知」是演示内存态，一期只读不做（PRP #298）。 */
import { Select, Typography } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import type { NavigationPage } from "@/config/navigation";
import WfsQueryPage from "../wfs/WfsQueryPage";
import LogisticsDrawer from "./LogisticsDrawer";
import { getAlerts, type AlertRow, type Sev } from "./logisticsApi";
import { SP_SEARCH_TYPES, type SpFilters } from "./logisticsFormat";
import { PAGE_SIZE, logisticsKey, useLogisticsOptions } from "./logisticsQueries";
import { DataDayNotice, SevTag, SpFilterSelects, StageTag } from "./logisticsShared";
import "./logistics.css";

const { Text } = Typography;

interface Filters extends SpFilters {
  type?: string;
  sev?: Sev;
}

const initial = (): Filters => ({ keyword: "", field: "sp" });

const CARDS: { type: string; icon: string; tone: "danger" | "warning" | "normal" }[] = [
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

export default function LogisticsAlertsPage({ page, scope }: { page: NavigationPage; scope: string }) {
  const [filters, setFilters] = useState(initial);
  const [pg, setPg] = useState({ page: 1, size: PAGE_SIZE });
  const [open, setOpen] = useState<string>();
  const opts = useLogisticsOptions(scope);
  const options = opts.data?.data;
  const params = { ...filters, page: pg.page, page_size: pg.size };
  const q = useQuery({
    queryKey: logisticsKey(scope, "alerts", params),
    queryFn: ({ signal }) => getAlerts(params, signal),
    retry: false,
    placeholderData: keepPreviousData,
  });
  const data = q.data?.data;
  const commit = (next: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...next }));
    setPg((p) => ({ ...p, page: 1 }));
  };

  const columns: ProColumns<AlertRow>[] = [
    { title: "严重度", width: 70, render: (_, e) => <SevTag sev={e.sev} /> },
    { title: "类型", width: 200, render: (_, e) => <b>{e.type}</b> },
    { title: "发货单", width: 170, render: (_, e) => <a>{e.code}</a> },
    { title: "阶段", width: 120, render: (_, e) => <StageTag stage={e.stage} /> },
    { title: "物流商 · 渠道 · 地区", width: 230, render: (_, e) => <span>{e.provider}<br /><Text type="secondary">{e.channel} · {e.fc} {e.region}</Text></span> },
    { title: "店铺", width: 200, render: (_, e) => e.stores.join(" / ") || "—" },
    { title: "说明", width: 420, render: (_, e) => <span className="logi-wrap">{e.desc}</span> },
    { title: "发现", width: 110, render: (_, e) => e.since || "—" },
  ];

  return (
    <>
      <WfsQueryPage<AlertRow>
        page={page}
        helpHref="/help/pmc-logistics.html"
        title={`异常与提醒（${data?.total ?? 0} / ${data?.summary.all ?? 0} 条）`}
        tableLabel="物流异常表格"
        emptyText={q.isFetching ? "正在加载" : "当前条件下暂无异常"}
        searchAriaLabel="搜索物流异常"
        inputAriaLabel="搜索物流异常关键字"
        inputPlaceholder="输入关键字"
        typeAriaLabel="物流异常搜索类型"
        typeOptions={SP_SEARCH_TYPES}
        searchType={filters.field}
        keyword={filters.keyword}
        onSearch={(keyword, field) => commit({ keyword, field: field as SpFilters["field"] })}
        onReset={() => { setFilters(initial()); setPg({ page: 1, size: PAGE_SIZE }); }}
        filters={(
          <>
            <Select allowClear aria-label="异常类型" className="report-filter-select" placeholder="异常类型" style={{ width: 220 }}
              value={filters.type} options={(options?.alert_types ?? []).map((t) => ({ value: t, label: t }))} onChange={(type) => commit({ type })} />
            <Select allowClear aria-label="严重度" className="report-filter-select" placeholder="严重度" style={{ width: 100 }}
              value={filters.sev} options={[{ value: "high", label: "高" }, { value: "mid", label: "中" }, { value: "low", label: "低" }]} onChange={(sev) => commit({ sev })} />
            <SpFilterSelects options={options} filters={filters} commit={commit} />
          </>
        )}
        aboveToolbar={(
          <>
            <DataDayNotice options={options} error={opts.error ?? q.error} />
            <ManagementStatCards<string>
              ariaLabel="物流异常统计"
              activeKey={filters.type ?? ""}
              onCardClick={(type) => commit({ type: type === filters.type ? undefined : type })}
              cards={CARDS.map((c) => ({
                key: c.type,
                title: c.type,
                value: data?.summary.types[c.type] ?? 0,
                unit: "条",
                tone: c.tone,
                icon: <span>{c.icon}</span>,
                subtitle: `阈值见「时效与阈值设置」`,
              }))}
            />
          </>
        )}
        loading={q.isFetching}
        loadingLabel="正在加载物流异常，请稍候"
        columns={columns}
        scrollX={1520}
        rows={data?.items ?? []}
        total={data?.total ?? 0}
        current={pg.page}
        pageSize={pg.size}
        onPageChange={(p, size) => setPg({ page: p, size })}
        onRowClick={(e) => setOpen(e.code)}
      />
      {open && (
        <LogisticsDrawer
          code={open}
          scope={scope}
          buffer={options?.rules.wm_receive_buffer ?? 10}
          deliveredNotSigned={options?.rules.delivered_not_signed ?? 2}
          onClose={() => setOpen(undefined)}
        />
      )}
    </>
  );
}
