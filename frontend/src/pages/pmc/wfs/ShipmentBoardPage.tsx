/** M1: creation-backed shipment rows; Lingxing fulfillment not wired yet. */
import { Alert, Checkbox, Segmented, Select, Tag } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import type { NavigationPage } from "@/config/navigation";
import ShipmentBoardDrawer from "./ShipmentBoardDrawer";
import WfsQueryPage from "./WfsQueryPage";
import { boardError, boardOptions, listShipments, shipmentSummary } from "./shipmentBoardApi";
import type { ShipmentBoardFilters, ShipmentBoardRow } from "./shipmentBoardTypes";
import "./PendingPackingPage.css";

const initialFilters = (): ShipmentBoardFilters => ({
  keyword: "",
  keyword_field: "shipment",
  only_test: false,
});

const labelText: Record<string, string> = { READY: "箱唛就绪", PENDING: "箱唛待取", FAILED: "箱唛失败" };
const time = (v?: string) => v ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Taipei", dateStyle: "short", timeStyle: "short" }).format(new Date(v)) : "—";

type ProductRow = { id: string };

export default function ShipmentBoardPage({ page, scope = "anonymous" }: { page: NavigationPage; scope?: string }) {
  const [view, setView] = useState<"shipment" | "product">("shipment");
  const [filters, setFilters] = useState(initialFilters);
  const [pagination, setPagination] = useState({ page: 1, size: 20 });
  const [drawerId, setDrawerId] = useState<string>();
  const [searchTick, setSearchTick] = useState(0);
  const base = useMemo(() => ["wfs-shipment-board", scope], [scope]);
  const list = useQuery({
    queryKey: [...base, "list", filters, pagination, searchTick],
    queryFn: ({ signal }) => listShipments(filters, pagination.page, pagination.size, signal),
    enabled: view === "shipment",
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
  const stats = summary.data?.data;
  const loadError = view === "shipment" ? (list.error ?? summary.error) : summary.error;
  const commitFilters = (next: ShipmentBoardFilters, refetch = false) => {
    setFilters(next);
    setPagination((p) => ({ ...p, page: 1 }));
    if (refetch) setSearchTick((n) => n + 1);
  };
  const runSearch = (keyword: string, searchField: string) => {
    if (view === "product") {
      setSearchTick((n) => n + 1);
      return;
    }
    commitFilters(
      { ...filters, keyword, keyword_field: searchField as ShipmentBoardFilters["keyword_field"] },
      true,
    );
  };
  const runReset = () => {
    commitFilters(initialFilters(), true);
    setPagination({ page: 1, size: 20 });
  };

  const viewToggle = (
    <Segmented
      className="wfs-board__view-segment"
      value={view}
      onChange={(v) => setView(v as "shipment" | "product")}
      options={[
        { label: "货件维度", value: "shipment" },
        { label: "产品维度", value: "product" },
      ]}
    />
  );

  const statCards = (
    <>
      {loadError && <Alert type="error" showIcon message={boardError(loadError)} style={{ marginBottom: 12 }} />}
      <ManagementStatCards
        ariaLabel="WFS货件看板统计"
        cards={[
          { key: "total", title: "货件总数", value: stats?.total ?? "—", unit: "张", tone: "normal", icon: <span>件</span>, subtitle: "含本系统创建且已有货件号" },
          { key: "sync", title: "待领星同步", value: stats?.pending_lingxing_sync ?? "—", unit: "张", tone: "warning", icon: <span>同</span>, subtitle: "M1 履约字段尚未接入" },
          { key: "test", title: "测试货件", value: stats?.test ?? "—", unit: "张", tone: "normal", icon: <span>测</span>, subtitle: "business_test" },
        ]}
        activeKey=""
        onCardClick={() => undefined}
      />
    </>
  );

  const shipmentColumns: ProColumns<ShipmentBoardRow>[] = [
    { title: "货件号", dataIndex: "shipment_id", width: 160, fixed: "left" },
    { title: "店铺", width: 220, render: (_, r) => r.store_name ?? r.store_id },
    { title: "状态", width: 200, render: (_, r) => <span><Tag>{labelText[r.label_state] ?? r.label_state}</Tag><Tag color="default">待领星同步</Tag></span> },
    { title: "货件类型", width: 100, render: (_, r) => (r.its ? "ITS" : "WFS") },
    { title: "PK", dataIndex: "pk", width: 150 },
    { title: "SKU · 品名", width: 180, render: (_, r) => <span>{r.sku}<br /><span className="wfs-pending__sub">{r.product_name ?? "—"}</span></span> },
    { title: "Item / GTIN", width: 160, render: (_, r) => `${r.item_id ?? "—"} / ${r.gtin ?? "—"}` },
    { title: "申报", width: 80, render: () => "—" },
    { title: "实际发货", width: 90, render: () => "—" },
    { title: "Received", width: 90, render: () => "—" },
    { title: "创建时间", width: 150, render: (_, r) => time(r.created_at) },
  ];

  const productColumns: ProColumns<ProductRow>[] = [
    { title: "店铺", dataIndex: "store", width: 220 },
    { title: "Item ID", dataIndex: "itemId", width: 140 },
    { title: "MSKU", dataIndex: "msku", width: 140 },
    { title: "SKU · 品名", dataIndex: "sku", width: 200 },
  ];

  const isShipment = view === "shipment";

  return (
    <>
      <WfsQueryPage<ShipmentBoardRow | ProductRow>
        page={page}
        title={isShipment ? `WFS 货件（${total} 张）` : "产品维度（0 个）"}
        tableLabel={isShipment ? "WFS 货件表格" : "WFS 产品表格"}
        emptyText={isShipment
          ? (loadError ? "加载失败，请重试" : "当前条件下暂无货件；请先在待发货打包单完成创建")
          : "产品维度将在领星读模型接入后开放"}
        searchAriaLabel="搜索WFS货件看板"
        inputAriaLabel="搜索WFS货件看板关键字"
        inputPlaceholder={isShipment ? "按所选类型搜索" : "输入关键字"}
        typeAriaLabel="WFS货件看板搜索类型"
        searchType={isShipment ? filters.keyword_field : "sku"}
        typeOptions={isShipment ? [
          { value: "shipment", label: "Shipment" },
          { value: "pk", label: "PK" },
          { value: "msku", label: "MSKU" },
          { value: "sku", label: "SKU" },
          { value: "item", label: "Item ID" },
          { value: "gtin", label: "GTIN" },
        ] : [{ value: "sku", label: "SKU" }]}
        columns={(isShipment ? shipmentColumns : productColumns) as ProColumns<ShipmentBoardRow | ProductRow>[]}
        scrollX={isShipment ? 1680 : 1500}
        keyword={isShipment ? filters.keyword : ""}
        onSearch={runSearch}
        onReset={runReset}
        loading={list.isFetching || summary.isFetching}
        loadingLabel="正在加载WFS货件看板，请稍候"
        rows={isShipment ? rows : []}
        total={isShipment ? total : 0}
        page={pagination.page}
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
            {isShipment && (
              <Checkbox checked={filters.only_test} onChange={(e) => commitFilters({ ...filters, only_test: e.target.checked })}>只看测试货件</Checkbox>
            )}
          </>
        )}
      />
      {drawerId && <ShipmentBoardDrawer rowId={drawerId} scope={scope} onClose={() => setDrawerId(undefined)} />}
    </>
  );
}
