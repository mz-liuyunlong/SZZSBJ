/** 物流总览（8088 pmc-logistics TabOverview）：一行一张 SP 发货单，筛选 / 分页在服务端。
 * Rocky 2026-11-04：发货单号、运单号分两列；多个运单号只显示第 1 个 + 省略号，鼠标移上去显示全部；最后一列「详情」。 */
import { Select, Tag, Tooltip, Typography } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import type { NavigationPage } from "@/config/navigation";
import WfsQueryPage from "../wfs/WfsQueryPage";
import LogisticsDrawer from "./LogisticsDrawer";
import { getOverview, type OverviewCard, type OverviewRow } from "./logisticsApi";
import { ARR_SRC, SP_SEARCH_TYPES, fmt, money, type SpFilters } from "./logisticsFormat";
import { PAGE_SIZE, logisticsKey, useLogisticsOptions } from "./logisticsQueries";
import { DataDayNotice, SignGap, SpFilterSelects, StageTag } from "./logisticsShared";
import "./logistics.css";

const { Text } = Typography;

interface Filters extends SpFilters {
  stage?: string;
  card: OverviewCard;
}

const initial = (): Filters => ({ keyword: "", field: "sp", card: "all" });

export default function LogisticsOverviewPage({ page, scope }: { page: NavigationPage; scope: string }) {
  const [filters, setFilters] = useState(initial);
  const [pg, setPg] = useState({ page: 1, size: PAGE_SIZE });
  const [open, setOpen] = useState<string>();
  const opts = useLogisticsOptions(scope);
  const params = { ...filters, page: pg.page, page_size: pg.size };
  const q = useQuery({
    queryKey: logisticsKey(scope, "overview", params),
    queryFn: ({ signal }) => getOverview(params, signal),
    retry: false,
    placeholderData: keepPreviousData,
  });
  const data = q.data?.data;
  const sum = data?.summary;
  const options = opts.data?.data;
  const today = options?.today ?? "";
  const commit = (next: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...next }));
    setPg((p) => ({ ...p, page: 1 }));
  };
  const cnt = (k: OverviewCard) => sum?.cards[k] ?? 0;

  const columns: ProColumns<OverviewRow & { id: string }>[] = [
    {
      title: "发货单号", width: 200, fixed: "left",
      render: (_, s) => (
        <span>
          <a>{s.code}</a><br />
          <Text type="secondary">{s.status} · {s.created} · {s.creator}</Text>
        </span>
      ),
    },
    {
      title: "运单号", width: 210,
      render: (_, s) => (s.tracking.length === 0
        ? <Tag color="warning" bordered={false}>运单号缺失</Tag>
        : s.tracking.length === 1
          ? <span>{s.tracking[0]}</span>
          : (
            <Tooltip title={<div>{s.tracking.map((t) => <div key={t}>{t}</div>)}</div>} placement="right">
              <span className="logi-tracking-more" aria-label={`运单号 ${s.tracking.length} 个`}>
                {s.tracking[0]}<Text type="secondary"> … 共 {s.tracking.length} 个</Text>
              </span>
            </Tooltip>
          )),
    },
    { title: "当前阶段", width: 120, render: (_, s) => <StageTag stage={s.stage} /> },
    { title: "物流商 · 渠道", width: 210, render: (_, s) => <span>{s.provider || `ID ${s.provider_id}`}<br /><Text type="secondary">{s.channel || `ID ${s.channel_id}`}{s.method ? ` · ${s.method}` : ""}</Text></span> },
    { title: "目的仓 · 地区", width: 110, render: (_, s) => <span>{s.fc || "—"}<br /><Text type="secondary">{s.region}</Text></span> },
    { title: "店铺", width: 200, render: (_, s) => s.stores.join(" / ") || "—" },
    { title: "总箱数", width: 90, align: "right", render: (_, s) => <span>{fmt(s.boxes)}{!s.cargo_count && <><br /><Tag color="warning" bordered={false}>未关联货件</Tag></>}</span> },
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
    {
      title: "操作", width: 80, fixed: "right",
      render: (_, s) => <a onClick={(e) => { e.stopPropagation(); setOpen(s.code); }}>详情</a>,
    },
  ];

  const header = (
    <>
      <DataDayNotice options={options} error={opts.error ?? q.error} />
      <ManagementStatCards<OverviewCard>
        ariaLabel="物流总览统计"
        activeKey={filters.card}
        onCardClick={(card) => commit({ card: card === filters.card ? "all" : card })}
        cards={[
          { key: "all", title: "发货单（07-01 起）", value: cnt("all"), unit: "张", tone: "normal", icon: <span>单</span>, subtitle: `已发货 ${sum?.shipped ?? 0}` },
          { key: "transit", title: "在途（未签收）", value: cnt("transit"), unit: "张", tone: "normal", icon: <span>途</span>, subtitle: "已发货且未完成" },
          { key: "soon", title: "即将超时", value: cnt("soon"), unit: "张", tone: "warning", icon: <span>!</span>, subtitle: `剩 ≤ ${options?.rules.remind_before ?? 3} 天` },
          { key: "over", title: "已超合同时效", value: cnt("over"), unit: "张", tone: "danger", icon: <span>超</span>, subtitle: `可索赔合计 ${money(sum?.penalty_total ?? 0, "CNY")}` },
          { key: "signed", title: "物流已签收待 Walmart", value: cnt("signed"), unit: "张", tone: "warning", icon: <span>签</span>, subtitle: "众壹签收完成，Walmart 未收货" },
          { key: "miss", title: "数据缺失提醒", value: cnt("miss"), unit: "张", tone: "normal", icon: <span>缺</span>, subtitle: "费用 / 预计时间 / 运单号" },
          { key: "month", title: "本月发货", value: cnt("month"), unit: "张", tone: "normal", icon: <span>月</span>, subtitle: sum?.month_start ? `${sum.month_start} 起` : "—" },
        ]}
      />
    </>
  );

  return (
    <>
      <WfsQueryPage<OverviewRow & { id: string }>
        page={page}
        helpHref="/help/pmc-logistics.html"
        title={`物流总览（${data?.total ?? 0} / ${sum?.all ?? 0} 张 · ${fmt(sum?.qty ?? 0)} 件 · ${fmt(sum?.boxes ?? 0)} 箱）`}
        tableLabel="物流总览表格"
        emptyText={q.isFetching ? "正在加载" : "当前条件下暂无数据"}
        searchAriaLabel="搜索物流总览"
        inputAriaLabel="搜索物流总览关键字"
        inputPlaceholder="输入关键字"
        typeAriaLabel="物流总览搜索类型"
        typeOptions={SP_SEARCH_TYPES}
        searchType={filters.field}
        keyword={filters.keyword}
        onSearch={(keyword, field) => commit({ keyword, field: field as SpFilters["field"] })}
        onReset={() => { setFilters(initial()); setPg({ page: 1, size: PAGE_SIZE }); }}
        filters={(
          <>
            <SpFilterSelects options={options} filters={filters} commit={commit} />
            <Select allowClear aria-label="当前阶段" className="report-filter-select" placeholder="当前阶段" style={{ width: 150 }}
              value={filters.stage} options={(options?.stages ?? []).map((s) => ({ value: s, label: `${s}（${options?.stage_counts[s] ?? 0}）` }))} onChange={(stage) => commit({ stage })} />
          </>
        )}
        aboveToolbar={header}
        loading={q.isFetching}
        loadingLabel="正在加载物流总览，请稍候"
        columns={columns}
        scrollX={3260}
        rows={(data?.items ?? []).map((s) => ({ ...s, id: s.code }))}
        total={data?.total ?? 0}
        current={pg.page}
        pageSize={pg.size}
        onPageChange={(p, size) => setPg({ page: p, size })}
        onRowClick={(s) => setOpen(s.code)}
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
