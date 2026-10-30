/** M2: Lingxing-published WFS cargos (truth) joined with this system's creation facts. */
import { Alert, Checkbox, Segmented, Select, Tag, Typography } from "antd";
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

type StatKey = "" | "all" | "s0" | "s1" | "s2" | "s3" | "pending" | "test";

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
      : filters.status !== undefined
        ? (`s${filters.status}` as StatKey)
        : "all";
  const onStatClick = (key: StatKey) => {
    const next: ShipmentBoardFilters = { ...filters, status: undefined, sync: undefined, only_test: false };
    if (key.startsWith("s")) next.status = Number(key.slice(1));
    if (key === "pending") next.sync = "PENDING";
    if (key === "test") next.only_test = true;
    commitFilters(next);
  };

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
          { key: "test", title: "测试货件", value: stats?.test ?? "—", unit: "张", tone: "normal", icon: <span>测</span>, subtitle: "business_test" },
        ]}
        activeKey={activeStat}
        onCardClick={onStatClick}
      />
    </>
  );

  const shipmentColumns: ProColumns<ShipmentBoardRow>[] = [
    { title: "货件号", width: 150, fixed: "left", render: (_, r) => <span>{r.shipment_id}<br /><span className="wfs-pending__sub">{r.inbound_order_id ?? "—"}</span></span> },
    { title: "店铺", width: 200, render: (_, r) => r.store_name ?? r.store_id },
    {
      title: "状态",
      width: 170,
      render: (_, r) => (
        <span>
          <Tag color={r.lingxing_sync_status === "PENDING" ? "error" : STATUS_TONE[String(r.status)] ?? "default"}>{r.status_label}</Tag>
          {r.label_state && <Tag>{labelText[r.label_state] ?? r.label_state}</Tag>}
          {r.business_test && <Tag color="purple">测试</Tag>}
        </span>
      ),
    },
    { title: "PK", width: 140, render: (_, r) => r.pk ?? <span className="wfs-pending__sub">人工 / 外部</span> },
    { title: "SKU · 品名", width: 190, render: (_, r) => <span>{r.sku ?? "—"}{r.sku_count > 1 ? ` 等 ${r.sku_count} 个` : ""}<br /><span className="wfs-pending__sub">{r.product_name ?? "—"}</span></span> },
    { title: "申报 / 发出", width: 110, render: (_, r) => `${num(r.declared_units)} / ${num(r.shipped_units)}` },
    { title: "Received / 破损", width: 120, render: (_, r) => `${num(r.received_units)} / ${num(r.damaged_units)}` },
    { title: "物流", width: 160, render: (_, r) => <span>{r.logistics_code ?? "—"}<br /><span className="wfs-pending__sub">{r.shipping_codes[0] ?? "—"}{r.shipping_codes.length > 1 ? ` +${r.shipping_codes.length - 1}` : ""}</span></span> },
    { title: "实际发货", width: 100, render: (_, r) => r.actual_delivery_date ?? "—" },
    // Lingxing SP field names (verified in the Lingxing UI 2026-10-30): arrival_time = 到货时间,
    // expected_arrival_time = 预计到港时间.
    { title: "到货 / 预计到港", width: 130, render: (_, r) => `${r.arrival_date ?? "—"} / ${r.expected_arrival_date ?? "—"}` },
    { title: "开始收货", width: 130, render: (_, r) => time(r.to_receive_at) },
    { title: "创建时间", width: 130, render: (_, r) => time(r.created_at) },
  ];

  const productColumns: ProColumns<ProductBoardRow>[] = [
    { title: "店铺", width: 200, render: (_, r) => r.store_name ?? r.store_id },
    { title: "MSKU", dataIndex: "msku", width: 150 },
    { title: "SKU · 品名", width: 220, render: (_, r) => <span>{r.sku ?? "—"}<br /><span className="wfs-pending__sub">{r.product_name ?? "—"}</span></span> },
    { title: "GTIN", dataIndex: "gtin", width: 150 },
    { title: "货件数", dataIndex: "shipments", width: 90 },
    { title: "申报", width: 90, render: (_, r) => num(r.declared_units) },
    { title: "发出", width: 90, render: (_, r) => num(r.shipped_units) },
    { title: "Received", width: 100, render: (_, r) => num(r.received_units) },
    { title: "破损", width: 80, render: (_, r) => num(r.damaged_units) },
    { title: "在途（未收）", width: 110, render: (_, r) => num(r.in_transit_units) },
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
            : "当前条件下暂无产品；产品维度来自领星货件商品行"}
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
        scrollX={isShipment ? 1900 : 1300}
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
            <Checkbox checked={filters.only_test} onChange={(e) => commitFilters({ ...filters, only_test: e.target.checked })}>只看测试货件</Checkbox>
            {freshness.stale && <Typography.Text type="warning">数据可能过期</Typography.Text>}
          </>
        )}
      />
      {drawerId && <ShipmentBoardDrawer rowId={drawerId} scope={scope} onClose={() => setDrawerId(undefined)} />}
    </>
  );
}
