/** Read-only shipment board. Test shipments stay visible and out of the supply count. */
import type { ProColumns } from "@ant-design/pro-components";
import { Button, Card, Drawer, Segmented, Select, Space, Tag, Typography, message } from "antd";
import { useMemo, useState } from "react";
import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import type { NavigationPage } from "@/config/navigation";
import WfsFrame from "./WfsFrame";
import WfsTable from "./WfsTable";
import { WFS_STORES, boardRows, supplyBoardRows, type BoardRow } from "./wfsMock";

export default function ShipmentBoardPage({ page }: { page: NavigationPage }) {
  const [view, setView] = useState<"shipment" | "product">("shipment");
  const [store, setStore] = useState<string>();
  const [current, setCurrent] = useState<BoardRow>();
  const rows = useMemo(() => boardRows.filter((row) => !store || row.store === store), [store]);
  const supply = rows.filter((row) => !row.test);
  const cards: ManagementStatCardItem[] = [
    { key: "all", title: "货件", value: rows.length, subtitle: "含测试货件", unit: "票", tone: "normal", icon: <span>货</span> },
    { key: "supply", title: "计入供货", value: supply.length, subtitle: "测试货件不计入", unit: "票", tone: "success", icon: <span>供</span> },
    { key: "transit", title: "在途", value: supply.filter((row) => row.arrival === "—").length, subtitle: "示例中到仓日未知", unit: "票", tone: "warning", icon: <span>途</span> },
    { key: "test", title: "测试", value: rows.filter((row) => row.test).length, subtitle: "PMC-TEST 前缀", unit: "票", tone: "normal", icon: <span>测</span> },
  ];
  const shipmentColumns: ProColumns<BoardRow>[] = [
    { title: "店铺", dataIndex: "store" },
    { title: "Shipment ID", dataIndex: "shipmentId", render: (_, row) => <Space>{row.shipmentId}{row.test && <Tag>测试</Tag>}</Space> },
    { title: "负责人", dataIndex: "owner" },
    { title: "状态", dataIndex: "status" },
    { title: "申报", dataIndex: "declared" },
    { title: "实际发货", dataIndex: "shipped" },
    { title: "Received", dataIndex: "received" },
    { title: "FC", dataIndex: "fc" },
    { title: "到仓日", dataIndex: "arrival" },
    { title: "可售日", dataIndex: "sellable" },
    { title: "操作", valueType: "option", render: (_, row) => <Button size="small" onClick={() => setCurrent(row)}>明细</Button> },
  ];
  const productColumns: ProColumns<BoardRow>[] = [
    { title: "店铺", dataIndex: "store" },
    { title: "SKU", dataIndex: "sku" },
    { title: "GTIN", dataIndex: "gtin" },
    { title: "标题", dataIndex: "title" },
    { title: "Shipment ID", dataIndex: "shipmentId", render: (_, row) => <Space>{row.shipmentId}{row.test && <Tag>测试</Tag>}</Space> },
    { title: "申报", dataIndex: "declared" },
    { title: "Received", dataIndex: "received" },
  ];
  return (
    <WfsFrame page={page}>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
        看板读取货件状态、申报和 Received。测试货件保留「测试」标记，不计入供货、在途和异常。当前到仓日、可售日没有示例事实，显示为未知。
      </Typography.Paragraph>
      <ManagementStatCards ariaLabel="WFS 货件看板统计" cards={cards} activeKey="" onCardClick={() => undefined} />
      <Card>
        <Space wrap>
          <Segmented
            value={view}
            onChange={(value) => setView(value as "shipment" | "product")}
            options={[{ label: "货件", value: "shipment" }, { label: "产品", value: "product" }]}
          />
          <Select allowClear placeholder="全部店铺" style={{ width: 240 }} value={store} onChange={setStore}
            options={WFS_STORES.map((item) => ({ value: item, label: item }))} />
          <Button onClick={() => message.info("前端预览不会同步 Walmart")}>同步 Walmart</Button>
        </Space>
      </Card>
      <WfsTable
        label={view === "shipment" ? "WFS 货件表格" : "WFS 产品表格"}
        columns={view === "shipment" ? shipmentColumns : productColumns}
        rows={view === "shipment" ? rows : rows}
      />
      <Typography.Text type="secondary">供货口径示例 {supplyBoardRows.length} 票，已排除测试货件。</Typography.Text>
      <Drawer title={current?.shipmentId ?? "货件明细"} open={Boolean(current)} onClose={() => setCurrent(undefined)}>
        {current && (
          <Space direction="vertical">
            <span>店铺：{current.store}</span>
            <span>状态：{current.status}</span>
            <span>申报 / 实发：{current.declared} / {current.shipped}</span>
            <span>Received：{current.received}</span>
            <span>FC：{current.fc}</span>
            <span>SKU：{current.sku}</span>
            <span>GTIN：{current.gtin}</span>
          </Space>
        )}
      </Drawer>
    </WfsFrame>
  );
}
