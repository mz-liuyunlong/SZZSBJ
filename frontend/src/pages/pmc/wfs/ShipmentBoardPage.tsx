/** Read-only WFS shipment board. Headers only until the read API is connected. */
import { Segmented, Select } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import { useState } from "react";
import type { NavigationPage } from "@/config/navigation";
import WfsQueryPage from "./WfsQueryPage";

const shipmentColumns: ProColumns<{ id: string }>[] = [
  { title: "货件号", dataIndex: "code", width: 150 },
  { title: "店铺", dataIndex: "store", width: 220 },
  { title: "状态", dataIndex: "status", width: 160 },
  { title: "货件类型", dataIndex: "type", width: 120 },
  { title: "产品负责人", dataIndex: "owner", width: 120 },
  { title: "申报", dataIndex: "declared", width: 90 },
  { title: "实际发货", dataIndex: "shipped", width: 100 },
  { title: "Received", dataIndex: "received", width: 110 },
  { title: "Walmart FC", dataIndex: "fc", width: 120 },
  { title: "到仓日", dataIndex: "arrival", width: 120 },
  { title: "可售日", dataIndex: "sellable", width: 120 },
  { title: "SP 发货单", dataIndex: "sp", width: 160 },
];

const productColumns: ProColumns<{ id: string }>[] = [
  { title: "店铺", dataIndex: "store", width: 220 },
  { title: "Item ID", dataIndex: "itemId", width: 140 },
  { title: "MSKU", dataIndex: "msku", width: 140 },
  { title: "SKU · 品名", dataIndex: "sku", width: 200 },
  { title: "未可售货件行", dataIndex: "ships", width: 120 },
  { title: "未可售合计", dataIndex: "inTransit", width: 110 },
  { title: "已到·收货中", dataIndex: "receiving", width: 180 },
  { title: "下一批预计到仓", dataIndex: "next", width: 140 },
  { title: "下一批预计可售", dataIndex: "nextSell", width: 140 },
];

export default function ShipmentBoardPage({ page }: { page: NavigationPage }) {
  const [view, setView] = useState<"shipment" | "product">("shipment");
  const [store, setStore] = useState<string>();
  const [owner, setOwner] = useState<string>();
  const [status, setStatus] = useState<string>();
  const [keyword, setKeyword] = useState("");
  const reset = () => { setStore(undefined); setOwner(undefined); setStatus(undefined); setKeyword(""); };
  return (
    <WfsQueryPage
      page={page}
      title={view === "shipment" ? "WFS 货件（0 张）" : "产品维度（0 个）"}
      tableLabel={view === "shipment" ? "WFS 货件表格" : "WFS 产品表格"}
      emptyText="当前条件下暂无货件"
      searchAriaLabel="搜索WFS货件看板"
      inputAriaLabel="搜索WFS货件看板关键字"
      inputPlaceholder="输入关键字"
      typeAriaLabel="WFS货件看板搜索类型"
      typeOptions={[
        { value: "code", label: "Shipment" },
        { value: "sp", label: "SP 发货单" },
        { value: "msku", label: "MSKU/SKU" },
        { value: "item", label: "Item ID" },
        { value: "gtin", label: "GTIN" },
      ]}
      columns={view === "shipment" ? shipmentColumns : productColumns}
      scrollX={view === "shipment" ? 1680 : 1500}
      loadingLabel="正在加载WFS货件看板，请稍候"
      keyword={keyword}
      onSearch={setKeyword}
      onReset={reset}
      filters={(
        <>
          <Segmented
            value={view}
            onChange={(value) => setView(value as "shipment" | "product")}
            options={[{ label: "货件维度", value: "shipment" }, { label: "产品维度", value: "product" }]}
          />
          <Select allowClear showSearch aria-label="店铺" className="report-filter-select" placeholder="全部店铺" style={{ width: 220 }} value={store} onChange={setStore} options={[]} />
          <Select allowClear showSearch aria-label="产品负责人" className="report-filter-select" placeholder="产品负责人" style={{ width: 150 }} value={owner} onChange={setOwner} options={[]} />
          {view === "shipment" && (
            <Select
              allowClear
              aria-label="货件状态"
              className="report-filter-select"
              placeholder="全部状态"
              style={{ width: 180 }}
              value={status}
              onChange={setStatus}
              options={[
                { value: "PENDING_SHIPMENT_DETAILS", label: "待发货详情" },
                { value: "AWAITING_DELIVERY", label: "待到仓" },
                { value: "RECEIVING_IN_PROGRESS", label: "收货中" },
                { value: "CLOSED", label: "已关闭" },
                { value: "CANCELLED", label: "已取消" },
              ]}
            />
          )}
        </>
      )}
    />
  );
}
