/** M2: Lingxing-published WFS cargos (truth) joined with this system's creation facts. */
import { Alert, Checkbox, Progress, Segmented, Select, Tag, Tooltip, Typography } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import type { NavigationPage } from "@/config/navigation";
import ShipmentBoardDrawer from "./ShipmentBoardDrawer";
import WfsQueryPage from "./WfsQueryPage";
import { boardError, boardOptions, listProducts, listShipments, shipmentSummary } from "./shipmentBoardApi";
import { freshnessText } from "./shipmentBoardFreshness";
import {
  ARRIVAL_BUCKETS,
  ETA_SOURCE_TEXT,
  STATUS_OPTIONS,
  STATUS_TONE,
  type ProductBoardRow,
  type ShipmentBoardFilters,
  type ShipmentBoardRow,
} from "./shipmentBoardTypes";
import "./PendingPackingPage.css";

const initialFilters = (): ShipmentBoardFilters => ({
  keyword: "",
  keyword_field: "shipment",
  only_test: false,
});

const labelText: Record<string, string> = { READY: "箱唛就绪", PENDING: "箱唛待取", FAILED: "箱唛失败" };
const fmt = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", dateStyle: "short", timeStyle: "short" });
const time = (v?: string | null) => (v ? fmt.format(new Date(v)) : "—");
const num = (v?: number | null) => (v === null || v === undefined ? "—" : String(v));

const SRC_TONE: Record<string, string> = { real: "success", plan: "processing", region: "processing" };
const Src = ({ k }: { k?: string | null }) =>
  k ? <Tag bordered={false} color={SRC_TONE[k] ?? "default"} style={{ marginLeft: 4 }}>{ETA_SOURCE_TEXT[k as keyof typeof ETA_SOURCE_TEXT] ?? k}</Tag> : null;
const Muted = ({ children }: { children: string }) => <span className="wfs-pending__sub">{children}</span>;
const dayDiff = (from: string, to: string) => Math.round((Date.parse(to) - Date.parse(from)) / 86400000);
const todayIso = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(new Date());

type StatKey = "" | "all" | "s0" | "s1" | "s2" | "s3" | "pending" | "test" | "exceptions" | "external";

export default function ShipmentBoardPage({ page, scope = "anonymous" }: { page: NavigationPage; scope?: string }) {
  const [view, setView] = useState<"shipment" | "product">("shipment");
  const [filters, setFilters] = useState(initialFilters);
  const [pagination, setPagination] = useState({ page: 1, size: 20 });
  const [drawerId, setDrawerId] = useState<string>();
  const [searchTick, setSearchTick] = useState(0);
  const base = useMemo(() => ["wfs-shipment-board", scope], [scope]);
  const isShipment = view === "shipment";
  const list = useQuery({
    queryKey: [...base, "list", filters, pagination, searchTick],
    queryFn: ({ signal }) => listShipments(filters, pagination.page, pagination.size, signal),
    enabled: isShipment,
    retry: false,
  });
  const products = useQuery({
    queryKey: [...base, "products", filters, pagination, searchTick],
    queryFn: ({ signal }) => listProducts(filters, pagination.page, pagination.size, signal),
    enabled: !isShipment,
    retry: false,
  });
  const summary = useQuery({
    queryKey: [...base, "summary", filters, searchTick],
    queryFn: ({ signal }) => shipmentSummary(filters, signal),
    retry: false,
  });
  const options = useQuery({
    queryKey: [...base, "options"],
    queryFn: ({ signal }) => boardOptions(signal),
    retry: false,
  });
  const rows = list.data?.data.items ?? [];
  const total = list.data?.data.total ?? 0;
  const productRows = products.data?.data.items ?? [];
  const productTotal = products.data?.data.total ?? 0;
  const stats = summary.data?.data;
  const freshness = freshnessText(stats?.freshness ?? list.data?.data.freshness);
  const loadError = isShipment ? (list.error ?? summary.error) : (products.error ?? summary.error);
  const commitFilters = (next: ShipmentBoardFilters, refetch = false) => {
    setFilters(next);
    setPagination((p) => ({ ...p, page: 1 }));
    if (refetch) setSearchTick((n) => n + 1);
  };
  const runSearch = (keyword: string, searchField: string) => {
    commitFilters({ ...filters, keyword, keyword_field: searchField as ShipmentBoardFilters["keyword_field"] }, true);
  };
  const runReset = () => {
    commitFilters(initialFilters(), true);
    setPagination({ page: 1, size: 20 });
  };
  const activeStat: StatKey = filters.sync === "PENDING"
    ? "pending"
    : filters.only_test
      ? "test"
      : filters.only_exceptions
        ? "exceptions"
        : filters.only_external
          ? "external"
          : filters.status !== undefined
            ? (`s${filters.status}` as StatKey)
            : "all";
  const onStatClick = (key: StatKey) => {
    const next: ShipmentBoardFilters = {
      ...filters, status: undefined, sync: undefined, only_test: false, only_exceptions: false, only_external: false,
    };
    if (/^s\d$/.test(key)) next.status = Number(key.slice(1));
    if (key === "pending") next.sync = "PENDING";
    if (key === "test") next.only_test = true;
    if (key === "exceptions") next.only_exceptions = true;
    if (key === "external") next.only_external = true;
    commitFilters(next);
  };
  const today = todayIso();

  const viewToggle = (
    <Segmented
      className="wfs-board__view-segment"
      value={view}
      onChange={(v) => { setView(v as "shipment" | "product"); setPagination({ page: 1, size: 20 }); }}
      options={[
        { label: "货件维度", value: "shipment" },
        { label: "产品维度", value: "product" },
      ]}
    />
  );

  const statCards = (
    <>
      {loadError && <Alert type="error" showIcon message={boardError(loadError)} style={{ marginBottom: 12 }} />}
      <div role="status" aria-label="领星数据时间">
        <Alert type={freshness.stale ? "warning" : "info"} showIcon message={freshness.text} style={{ marginBottom: 12 }} />
      </div>
      <ManagementStatCards<StatKey>
        ariaLabel="WFS货件看板统计"
        cards={[
          { key: "all", title: "货件总数", value: stats?.total ?? "—", unit: "张", tone: "normal", icon: <span>件</span>, subtitle: "领星 WFS 货件 + 本系统待同步" },
          { key: "s1", title: "在途", value: stats?.by_status?.["1"] ?? 0, unit: "张", tone: "normal", icon: <span>途</span>, subtitle: "AWAITING_DELIVERY" },
          { key: "s2", title: "收货中", value: stats?.by_status?.["2"] ?? 0, unit: "张", tone: "warning", icon: <span>收</span>, subtitle: "RECEIVING_IN_PROGRESS" },
          { key: "s3", title: "已关闭", value: stats?.by_status?.["3"] ?? 0, unit: "张", tone: "success", icon: <span>闭</span>, subtitle: `其中短收 ${stats?.received_short ?? 0} 张` },
          { key: "pending", title: "待领星同步", value: stats?.pending_lingxing_sync ?? "—", unit: "张", tone: "danger", icon: <span>同</span>, subtitle: "本系统已建、领星尚未出现" },
          { key: "exceptions", title: "有异常", value: stats?.with_exceptions ?? "—", unit: "张", tone: "danger", icon: <span>异</span>, subtitle: "8088 异常规则（WFS-RULES-20261010）" },
          { key: "external", title: "外部创建·待关联", value: stats?.external ?? "—", unit: "张", tone: "warning", icon: <span>外</span>, subtitle: "8 月起、无 SP 发货单、未取消" },
          { key: "test", title: "测试货件", value: stats?.test ?? "—", unit: "张", tone: "normal", icon: <span>测</span>, subtitle: "PMC-TEST- 或业务测试" },
        ]}
        activeKey={activeStat}
        onCardClick={onStatClick}
      />
    </>
  );

  // Columns follow the 8088 board (app-c.jsx COLS, default-visible set).
  const shipmentColumns: ProColumns<ShipmentBoardRow>[] = [
    { title: "店铺", width: 200, fixed: "left", render: (_, r) => r.store_name ?? r.store_id },
    {
      title: "Shipment ID",
      width: 170,
      fixed: "left",
      render: (_, r) => (
        <span>
          {r.shipment_id}
          {r.business_test && <Tag color="orange" bordered={false} style={{ marginLeft: 4 }}>测试</Tag>}
          <br /><span className="wfs-pending__sub">{r.inbound_order_id ?? "—"}</span>
        </span>
      ),
    },
    { title: "产品负责人", width: 130, render: (_, r) => (r.owners?.length ? r.owners.join("、") : <Muted>—</Muted>) },
    {
      title: "状态",
      width: 150,
      render: (_, r) => (
        <span>
          <Tag color={r.lingxing_sync_status === "PENDING" ? "error" : STATUS_TONE[String(r.status)] ?? "default"}>{r.status_label}</Tag>
          {r.label_state && <Tag>{labelText[r.label_state] ?? r.label_state}</Tag>}
        </span>
      ),
    },
    {
      title: "货件类型",
      width: 110,
      render: (_, r) => (r.its ?? r.its_inferred
        ? <Tooltip title="Walmart 节点代码以 T 结尾 = ITS 转运站（推算）"><Tag color="purple" bordered={false}>ITS 货件</Tag></Tooltip>
        : <Tag color="green" bordered={false}>普通 WFS</Tag>),
    },
    {
      title: "打包单 · 来源",
      width: 150,
      render: (_, r) => r.pk ?? (r.external ? <Tag color="warning" bordered={false}>外部创建·待关联</Tag> : <Muted>待关联</Muted>),
    },
    { title: "SKU · 品名", width: 190, render: (_, r) => <span>{r.sku ?? "—"}{r.sku_count > 1 ? ` 等 ${r.sku_count} 个` : ""}<br /><span className="wfs-pending__sub">{r.product_name ?? "—"}</span></span> },
    { title: "实际发货", width: 90, align: "right", render: (_, r) => (r.baseline_from === "SP" ? num(r.baseline_units) : num(r.shipped_units || null)) },
    { title: "Received", width: 90, align: "right", render: (_, r) => num(r.received_units) },
    {
      title: "Receiving 进度",
      width: 180,
      render: (_, r) => {
        const base = r.baseline_units ?? 0;
        const got = r.received_units ?? 0;
        const diff = r.diff_units ?? 0;
        return (
          <span>
            <Progress percent={base ? Math.min(100, Math.round((got / base) * 100)) : 0} size="small" showInfo={false}
              status={got > base ? "exception" : r.status === 3 ? "success" : "normal"} />
            <span className="wfs-pending__sub">{got}/{base}{r.status === 3 && diff !== 0 ? `（${diff > 0 ? "+" : ""}${diff}）` : ""}</span>
          </span>
        );
      },
    },
    { title: "Walmart FC", width: 120, render: (_, r) => (r.logistics_code ? <span>{r.logistics_code} <Muted>{r.region ?? ""}</Muted></span> : "—") },
    {
      title: "到仓日（实际 / 预计）",
      width: 200,
      render: (_, r) => (r.eta
        ? (
          <span>
            {r.eta}<Src k={r.eta_source} />
            {r.eta_passed_days && r.eta_passed_days > 0 && r.eta_source !== "real" && r.status_name === "AWAITING_DELIVERY" && !r.walmart_first_receipt
              ? <Tag color="warning" bordered={false} style={{ marginLeft: 4 }}>已过 {r.eta_passed_days} 天</Tag>
              : null}
            {r.eta_source_label ? <><br /><span className="wfs-pending__sub">{r.eta_source_label}</span></> : null}
          </span>
        )
        : <Muted>无 SP</Muted>),
    },
    {
      title: "可售日（首批上架）",
      width: 160,
      render: (_, r) => {
        if (!r.sellable_date || r.status === 4) return <Muted>—</Muted>;
        const left = dayDiff(today, r.sellable_date);
        return (
          <span>
            {r.sellable_date}<Src k={r.sellable_real ? "real" : "plan"} />
            {!r.sellable_real && r.status !== 3
              ? <><br /><span className="wfs-pending__sub">{left >= 0 ? `还有 ${left} 天` : `已过 ${-left} 天未上架`}</span></>
              : null}
          </span>
        );
      },
    },
    {
      title: "Walmart 开始收货 / 完成",
      width: 170,
      render: (_, r) => (r.walmart_first_receipt
        ? <span>{r.walmart_first_receipt}<Src k="real" /><br /><span className="wfs-pending__sub">{r.walmart_done ? `完成 ${r.walmart_last_receipt ?? ""}` : "收货中"}</span></span>
        : <Muted>未收货</Muted>),
    },
    { title: "SP 发货单", width: 170, render: (_, r) => (r.shipping_codes.length ? r.shipping_codes.join(", ") : "—") },
    { title: "实际发货时间", width: 110, render: (_, r) => r.actual_delivery_date ?? "—" },
    {
      title: "异常",
      width: 80,
      render: (_, r) => (r.exception_types?.length
        ? <Tooltip title={r.exception_types.join("；")}><Tag color="error" bordered={false}>{r.exception_types.length}</Tag></Tooltip>
        : <Muted>—</Muted>),
    },
    { title: "创建时间", width: 130, render: (_, r) => time(r.created_at) },
  ];

  const bucketCols: ProColumns<ProductBoardRow>[] = ARRIVAL_BUCKETS.map((b) => ({
    title: b.label,
    width: b.value === "overdue" ? 150 : 115,
    align: "right" as const,
    render: (_: unknown, r: ProductBoardRow) => {
      const v = r.buckets[b.value] ?? 0;
      return v ? <span className={b.value === "overdue" || b.value === "none" ? "warn-txt" : ""}>{v}</span> : <Muted>—</Muted>;
    },
  }));
  const productColumns: ProColumns<ProductBoardRow>[] = [
    { title: "店铺", width: 200, fixed: "left", render: (_, r) => r.store_name ?? r.store_id },
    { title: "Item ID", dataIndex: "item_id", width: 130 },
    { title: "MSKU", width: 140, render: (_, r) => r.mskus.join(", ") },
    { title: "SKU · 品名", width: 220, render: (_, r) => <span>{r.skus.join(", ")}<br /><span className="wfs-pending__sub">{r.product_name ?? "—"}</span></span> },
    { title: "未可售货件行", dataIndex: "shipments", width: 110, align: "right" },
    { title: "未可售合计", width: 100, align: "right", render: (_, r) => (r.in_transit_units ? <b>{r.in_transit_units}</b> : <Muted>—</Muted>) },
    ...bucketCols,
    { title: "其中：已签收未上架", width: 140, align: "right", render: (_, r) => (r.signed_not_put_units ? r.signed_not_put_units : <Muted>—</Muted>) },
    {
      title: "已到·收货中：发货 / 签收 / 上架",
      width: 220,
      align: "right",
      render: (_, r) => (r.arrived_shipped_units
        ? (
          <span>
            {r.arrived_shipped_units} / {r.arrived_signed_units} / {r.arrived_shelved_units}
            {r.signed_zero_shelved > 0 && <><br /><Tag color="warning" bordered={false}>未签收已上架 {r.signed_zero_shelved}</Tag></>}
            {r.receiving_gap_units < 0 && <><br /><span className="wfs-pending__sub">超收 {-r.receiving_gap_units}</span></>}
          </span>
        )
        : <Muted>—</Muted>),
    },
    { title: "下一批预计到仓", width: 120, render: (_, r) => r.next_eta ?? <Muted>—</Muted> },
    { title: "下一批预计可售", width: 120, render: (_, r) => r.next_sellable ?? <Muted>—</Muted> },
  ];

  return (
    <>
      <WfsQueryPage<ShipmentBoardRow | ProductBoardRow>
        page={page}
        title={isShipment ? `WFS 货件（${total} 张）` : `产品维度（${productTotal} 个）`}
        tableLabel={isShipment ? "WFS 货件表格" : "WFS 产品表格"}
        emptyText={loadError
          ? "加载失败，请重试"
          : isShipment
            ? "当前条件下暂无货件；领星同步后会出现全部 WFS 货件，本系统创建的货件在同步前显示为待领星同步"
            : "当前条件下暂无产品；产品维度只列有 Item ID、已发货未可售或已到收货中的产品"}
        searchAriaLabel="搜索WFS货件看板"
        inputAriaLabel="搜索WFS货件看板关键字"
        inputPlaceholder="按所选类型搜索"
        typeAriaLabel="WFS货件看板搜索类型"
        searchType={filters.keyword_field}
        typeOptions={[
          { value: "shipment", label: "货件号" },
          { value: "inbound", label: "入库单号" },
          { value: "shipping", label: "发货单 / 运单" },
          { value: "pk", label: "PK" },
          { value: "msku", label: "MSKU" },
          { value: "sku", label: "SKU" },
          { value: "item", label: "Item ID" },
          { value: "gtin", label: "GTIN" },
        ]}
        columns={(isShipment ? shipmentColumns : productColumns) as ProColumns<ShipmentBoardRow | ProductBoardRow>[]}
        scrollX={isShipment ? 2600 : 2200}
        keyword={filters.keyword}
        onSearch={runSearch}
        onReset={runReset}
        loading={list.isFetching || products.isFetching || summary.isFetching}
        loadingLabel="正在加载WFS货件看板，请稍候"
        rows={isShipment ? rows : productRows}
        total={isShipment ? total : productTotal}
        current={pagination.page}
        pageSize={pagination.size}
        onPageChange={(page, size) => setPagination({ page, size })}
        onRowClick={isShipment ? (row) => setDrawerId((row as ShipmentBoardRow).id) : undefined}
        aboveToolbar={statCards}
        filters={(
          <>
            {viewToggle}
            <Select allowClear showSearch aria-label="店铺" className="report-filter-select" placeholder="全部店铺" style={{ width: 220 }}
              value={filters.store_id} options={options.data?.data.stores} loading={options.isFetching} optionFilterProp="label"
              onChange={(store_id) => commitFilters({ ...filters, store_id })} />
            <Select allowClear aria-label="货件状态" className="report-filter-select" placeholder="全部状态" style={{ width: 140 }}
              value={filters.status} options={STATUS_OPTIONS}
              onChange={(status) => commitFilters({ ...filters, status, sync: undefined })} />
            <Select allowClear showSearch aria-label="产品负责人" className="report-filter-select" placeholder="全部负责人" style={{ width: 140 }}
              value={filters.owner} options={(options.data?.data.owners ?? []).map((o) => ({ value: o, label: o }))}
              onChange={(owner) => commitFilters({ ...filters, owner })} />
            <Select allowClear aria-label="可售分段" className="report-filter-select" placeholder="全部可售分段" style={{ width: 170 }}
              value={filters.arrival_bucket} options={ARRIVAL_BUCKETS}
              onChange={(arrival_bucket) => commitFilters({ ...filters, arrival_bucket })} />
            <Checkbox checked={filters.only_test} onChange={(e) => commitFilters({ ...filters, only_test: e.target.checked })}>只看测试货件</Checkbox>
            {freshness.stale && <Typography.Text type="warning">数据可能过期</Typography.Text>}
          </>
        )}
      />
      {drawerId && <ShipmentBoardDrawer rowId={drawerId} scope={scope} onClose={() => setDrawerId(undefined)} />}
    </>
  );
}
