/** Packed orders waiting for a shipment draft. Preview only. */
import type { ProColumns } from "@ant-design/pro-components";
import { Button, Card, Input, Select, Space, Tag, Typography, message } from "antd";
import { useMemo, useState } from "react";
import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import type { NavigationPage } from "@/config/navigation";
import WfsFrame from "./WfsFrame";
import WfsTable from "./WfsTable";
import { WFS_STORES, pendingPackingRows, type PendingPackingRow } from "./wfsMock";

const preview = () => message.info("前端预览不会生成货件草稿");

export default function PendingPackingPage({ page }: { page: NavigationPage }) {
  const [store, setStore] = useState<string>();
  const [keyword, setKeyword] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const rows = useMemo(() => pendingPackingRows.filter((row) => (
    (!store || row.store === store)
    && (!keyword || `${row.pk} ${row.sku} ${row.gtin} ${row.itemId}`.toLowerCase().includes(keyword.trim().toLowerCase()))
  )), [keyword, store]);
  const cards: ManagementStatCardItem[] = [
    { key: "packed", title: "已打包完成", value: rows.length, subtitle: "只列本系统打包完成的单据", unit: "单", tone: "normal", icon: <span>单</span> },
    { key: "selected", title: "已勾选", value: selected.length, subtitle: "勾选后可预览生成草稿", unit: "单", tone: "success", icon: <span>选</span> },
  ];
  const columns: ProColumns<PendingPackingRow>[] = [
    { title: "打包单", dataIndex: "pk" },
    { title: "店铺", dataIndex: "store" },
    { title: "SKU", dataIndex: "sku" },
    { title: "Item ID", dataIndex: "itemId" },
    { title: "GTIN", dataIndex: "gtin" },
    { title: "数量", dataIndex: "qty" },
    { title: "装箱", dataIndex: "boxes" },
    { title: "报关", dataIndex: "customs", render: (_, row) => <Tag color={row.customs === "报关" ? "red" : "default"}>{row.customs}</Tag> },
    { title: "打包完成", dataIndex: "packedAt" },
  ];
  return (
    <WfsFrame page={page}>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
        上游是国内仓打包单（审批、装箱、打包完成）。这里只保留已打包完成的单据，用来生成货件草稿。装箱只认本系统，不抓领星备货单装箱。
      </Typography.Paragraph>
      <ManagementStatCards ariaLabel="待发货打包单统计" cards={cards} activeKey="" onCardClick={() => undefined} />
      <Card>
        <Space wrap>
          <Select allowClear placeholder="全部店铺" style={{ width: 240 }} value={store} onChange={setStore}
            options={WFS_STORES.map((item) => ({ value: item, label: item }))} />
          <Input.Search allowClear placeholder="打包单 / SKU / GTIN / Item ID" style={{ width: 280 }} onSearch={setKeyword} />
          <Button onClick={() => { setStore(undefined); setKeyword(""); }}>重置</Button>
          <Button type="primary" disabled={selected.length === 0} onClick={preview}>生成货件草稿</Button>
        </Space>
      </Card>
      <WfsTable
        label="待发货打包单表格"
        columns={columns}
        rows={rows}
        rowSelection={{
          selectedRowKeys: selected,
          onChange: (keys) => setSelected((current) => {
            const next = keys.map(String);
            return current.length === next.length && current.every((id, index) => id === next[index]) ? current : next;
          }),
        }}
      />
    </WfsFrame>
  );
}
