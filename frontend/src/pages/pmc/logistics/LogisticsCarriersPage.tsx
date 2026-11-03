/** 货代看板（原 8088「众壹接口面板」，Rocky 2026-11-03 改名）：一行一张货代运单，来自已校验的众壹文件。
 * 新系统不调众壹接口，8088 的拉数 / 调用统计和接口清单不再展示。筛选 / 分页在服务端。 */
import { Alert, Descriptions, Drawer, Select, Spin, Switch, Table, Tag, Typography } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import type { NavigationPage } from "@/config/navigation";
import WfsQueryPage from "../wfs/WfsQueryPage";
import LogisticsDrawer from "./LogisticsDrawer";
import { getCarrierOrder, getCarriers, type CarrierOrder, type CarrierTrack } from "./logisticsApi";
import { fmt } from "./logisticsFormat";
import { PAGE_SIZE, logisticsKey, useLogisticsOptions } from "./logisticsQueries";
import { DataDayNotice } from "./logisticsShared";
import "./logistics.css";

const { Text } = Typography;

const STATUS_COLOR: Record<string, string> = {
  已签收: "success", 已到港: "cyan", 已拆柜: "cyan", 已开船: "processing", 已出库: "default", 已预报: "default",
};
const KEY_TRACKS = new Set(["签收完成", "已靠港，正在卸柜中", "已开船", "货物进入操作中心", "已装柜，货物离开操作中心"]);

interface Filters {
  status?: string;
  store?: string;
  stale: boolean;
  keyword: string;
}

const initial = (): Filters => ({ stale: false, keyword: "" });

function OrderDrawer({ number, scope, onClose, openSp }: { number: string; scope: string; onClose: () => void; openSp: (code: string) => void }) {
  const q = useQuery({
    queryKey: logisticsKey(scope, "carrier", number),
    queryFn: ({ signal }) => getCarrierOrder(number, signal),
    retry: false,
  });
  const o = q.data?.data.order;
  return (
    <Drawer open width={1000} onClose={onClose}
      title={<span>运单 {number} {o && <Tag bordered={false} color={STATUS_COLOR[o.status] ?? "default"}>{o.status}</Tag>} {o?.sp && <a onClick={() => openSp(o.sp)}>发货单 {o.sp}</a>}</span>}>
      {q.isLoading && <Spin />}
      {o && (
        <div className="logi-detail">
          <Descriptions size="small" bordered column={3} items={[
            { key: "n", label: "运单号 number", children: o.number },
            { key: "c", label: "客户单号（WFS 货件）", children: o.customerNumber || "—" },
            { key: "s", label: "服务商单号", children: o.serviceNumber || "—" },
            { key: "w", label: "重量 / 计费重 kg", children: `${fmt(o.weight)} / ${fmt(o.kg)}` },
            { key: "v", label: "体积 cbm", children: o.cbm },
            { key: "b", label: "领星箱数", children: o.sp ? fmt(o.sp_boxes) : "—" },
            { key: "st", label: "发货单 / 店铺", children: `${o.sp || "—"} / ${o.store || "—"}` },
            { key: "fc", label: "目的仓 / 地区", children: `${o.fc || "—"} / ${o.region || "—"}` },
            { key: "l", label: "最后轨迹", children: o.lastTrack || "—" },
          ]} />
          <h4>全部轨迹 <Text type="secondary">按时间倒序 · 共 {o.nTracks} 条</Text></h4>
          <Table<CarrierTrack> size="small" pagination={false} rowKey={(r) => `${r.t}-${r.cn}`} dataSource={o.tracks ?? []} columns={[
            { title: "轨迹时间", dataIndex: "t", width: 150 },
            { title: "中文轨迹", dataIndex: "cn", render: (v: string) => (KEY_TRACKS.has(v) ? <b>{v}</b> : v) },
            { title: "英文轨迹", dataIndex: "en" },
            { title: "提单号", dataIndex: "bl", width: 130, render: (v: string) => v || "—" },
          ]} />
        </div>
      )}
    </Drawer>
  );
}

export default function LogisticsCarriersPage({ page, scope }: { page: NavigationPage; scope: string }) {
  const [filters, setFilters] = useState(initial);
  const [pg, setPg] = useState({ page: 1, size: PAGE_SIZE });
  const [order, setOrder] = useState<string>();
  const [open, setOpen] = useState<string>();
  const opts = useLogisticsOptions(scope);
  const options = opts.data?.data;
  const params = { ...filters, page: pg.page, page_size: pg.size };
  const q = useQuery({
    queryKey: logisticsKey(scope, "carriers", params),
    queryFn: ({ signal }) => getCarriers(params, signal),
    retry: false,
    placeholderData: keepPreviousData,
  });
  const data = q.data?.data;
  const sum = data?.summary;
  const commit = (next: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...next }));
    setPg((p) => ({ ...p, page: 1 }));
  };

  const columns: ProColumns<CarrierOrder & { id: string }>[] = [
    { title: "运单号", width: 210, fixed: "left", render: (_, o) => <a>{o.number}</a> },
    { title: "客户单号（货件）", width: 130, render: (_, o) => o.customerNumber || "—" },
    { title: "状态", width: 90, render: (_, o) => <Tag color={STATUS_COLOR[o.status] ?? "default"} bordered={false}>{o.status}</Tag> },
    {
      title: "发货单", width: 180,
      render: (_, o) => (o.sp
        ? <span><a onClick={(e) => { e.stopPropagation(); setOpen(o.sp); }}>{o.sp}</a><br /><Text type="secondary">{o.sp_status}</Text></span>
        : <Tag color="orange" bordered={false}>未关联发货单</Tag>),
    },
    { title: "店铺", width: 200, render: (_, o) => o.store || "—" },
    { title: "目的仓", width: 100, render: (_, o) => (o.fc ? <span>{o.fc}<br /><Text type="secondary">{o.region}</Text></span> : "—") },
    { title: "计费重 kg", width: 100, align: "right", render: (_, o) => fmt(o.kg) },
    { title: "体积 cbm", width: 90, align: "right", render: (_, o) => o.cbm },
    { title: "最新轨迹", width: 360, render: (_, o) => <span className="logi-wrap">{o.trackCn || <Text type="secondary">无轨迹</Text>}<br /><Text type="secondary">{o.lastTrack} · 共 {o.nTracks} 条</Text></span> },
    {
      title: "停更", width: 90, align: "right",
      render: (_, o) => (o.staleDays == null ? "—" : o.stale ? <Tag color="red" bordered={false}>{o.staleDays} 天</Tag> : `${o.staleDays} 天`),
    },
  ];

  const missing = sum?.missing ?? [];
  return (
    <>
      <WfsQueryPage<CarrierOrder & { id: string }>
        page={page}
        helpHref="/help/pmc-logistics.html"
        title={`众壹运单（${data?.total ?? 0} / ${sum?.orders ?? 0} 张）`}
        tableLabel="货代运单表格"
        emptyText={q.isFetching ? "正在加载" : "当前条件下暂无运单"}
        searchAriaLabel="搜索货代运单"
        inputAriaLabel="搜索货代运单关键字"
        inputPlaceholder="运单号 / 货件号 / 发货单号 / 轨迹"
        typeAriaLabel="货代运单搜索类型"
        typeOptions={[{ value: "all", label: "运单 / 货件 / 发货单" }]}
        searchType="all"
        keyword={filters.keyword}
        onSearch={(keyword) => commit({ keyword })}
        onReset={() => { setFilters(initial()); setPg({ page: 1, size: PAGE_SIZE }); }}
        filters={(
          <>
            <Select allowClear aria-label="运单状态" className="report-filter-select" placeholder="运单状态" style={{ width: 150 }}
              value={filters.status} options={options?.carrier_statuses} onChange={(status) => commit({ status })} />
            <Select allowClear showSearch aria-label="店铺" className="report-filter-select" placeholder="全部店铺" style={{ width: 220 }}
              value={filters.store} options={options?.stores} optionFilterProp="label" onChange={(store) => commit({ store })} />
            <span className="logi-switch">只看停更 <Switch size="small" aria-label="只看停更" checked={filters.stale} onChange={(stale) => commit({ stale })} /></span>
          </>
        )}
        aboveToolbar={(
          <>
            <DataDayNotice options={options} error={opts.error ?? q.error} />
            <ManagementStatCards<"all" | "stale" | "missing" | "notrack">
              ariaLabel="货代看板统计"
              activeKey={filters.stale ? "stale" : "all"}
              onCardClick={(k) => commit({ stale: k === "stale" ? !filters.stale : false })}
              cards={[
                { key: "all", title: "众壹运单", value: sum?.orders ?? 0, unit: "张", tone: "normal", icon: <span>单</span>, subtitle: `关联发货单 ${sum?.linked ?? 0} · 未关联 ${sum?.unlinked ?? 0}` },
                { key: "missing", title: "应查运单 / 查不到", value: `${sum?.queried ?? 0} / ${sum?.not_found ?? 0}`, tone: sum?.not_found ? "danger" : "normal", icon: <span>!</span>, subtitle: `众壹发货单 ${sum?.zy_sps ?? 0} 张` },
                { key: "stale", title: `轨迹停更 ≥ ${sum?.stale_days ?? 7} 天`, value: sum?.stale ?? 0, unit: "张", tone: sum?.stale ? "warning" : "normal", icon: <span>停</span>, subtitle: "未签收且最后一条轨迹超过 7 天" },
                { key: "notrack", title: "无运单号", value: sum?.no_tracking ?? 0, unit: "张", tone: sum?.no_tracking ? "warning" : "normal", icon: <span>缺</span>, subtitle: "众壹发货单领星没填运单号" },
              ]}
            />
            {missing.length > 0 && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message={`没拿到数据的运单 ${missing.length} 张（查不到 = 已校验的众壹文件里没有这张运单，要核对领星运单号；无运单号 = 领星发货单缺运单号）`}
                description={(
                  <ul className="logi-missing">
                    {missing.slice(0, 10).map((x) => (
                      <li key={`${x.kind}-${x.tracking}-${x.sp}`}>
                        <Tag color={x.kind === "查不到" ? "red" : "orange"} bordered={false}>{x.kind}</Tag>
                        {x.tracking && <span>{x.tracking} · </span>}
                        <a onClick={() => setOpen(x.sp)}>{x.sp}</a> <Text type="secondary">{x.sp_status} · {x.store}</Text>
                      </li>
                    ))}
                    {missing.length > 10 && <li><Text type="secondary">另有 {missing.length - 10} 张未列出</Text></li>}
                  </ul>
                )}
              />
            )}
          </>
        )}
        headExtra={<Text type="secondary">运单状态 / 计费重 / 体积 = 众壹原值；最新轨迹 = 最新一条；停更天数 = 数据日 − 最后轨迹日</Text>}
        loading={q.isFetching}
        loadingLabel="正在加载货代运单，请稍候"
        columns={columns}
        scrollX={1600}
        rows={(data?.items ?? []).map((o) => ({ ...o, id: o.number }))}
        total={data?.total ?? 0}
        current={pg.page}
        pageSize={pg.size}
        onPageChange={(p, size) => setPg({ page: p, size })}
        onRowClick={(o) => setOrder(o.number)}
      />
      {order && <OrderDrawer number={order} scope={scope} onClose={() => setOrder(undefined)} openSp={setOpen} />}
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
