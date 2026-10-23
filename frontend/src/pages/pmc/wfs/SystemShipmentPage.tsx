/** Written approval record for creating Walmart shipments. Preview only. */
import type { ProColumns } from "@ant-design/pro-components";
import { Button, Card, Input, Select, Space, Steps, Tag, Typography, message } from "antd";
import { useMemo, useState } from "react";
import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import type { NavigationPage } from "@/config/navigation";
import WfsFrame from "./WfsFrame";
import WfsTable from "./WfsTable";
import { WFS_STORES, shipmentStatusLabel, systemShipmentRows, type SystemShipmentRow } from "./wfsMock";

const preview = (text: string) => message.info(text);

export default function SystemShipmentPage({ page }: { page: NavigationPage }) {
  const [store, setStore] = useState<string>();
  const [status, setStatus] = useState<SystemShipmentRow["status"] | "">("");
  const [keyword, setKeyword] = useState("");
  const rows = useMemo(() => systemShipmentRows.filter((row) => (
    (!store || row.store === store)
    && (!status || row.status === status)
    && (!keyword || `${row.draft} ${row.plan} ${row.systemNo}`.toLowerCase().includes(keyword.trim().toLowerCase()))
  )), [keyword, status, store]);
  const count = (key: SystemShipmentRow["status"]) => systemShipmentRows.filter((row) => row.status === key).length;
  const cards: ManagementStatCardItem<SystemShipmentRow["status"] | "walmart">[] = [
    { key: "pending", title: "待批准", value: count("pending"), subtitle: "书面批准后才可执行", unit: "单", tone: "warning", icon: <span>批</span> },
    { key: "approved", title: "已批准待执行", value: count("approved"), subtitle: "等待建货件和取箱唛", unit: "单", tone: "normal", icon: <span>执</span> },
    { key: "executed", title: "已执行", value: count("executed"), subtitle: "执行结果回写本页", unit: "单", tone: "success", icon: <span>完</span> },
    { key: "failed", title: "执行失败", value: count("failed"), subtitle: "失败保留原因，不自动重试", unit: "单", tone: "danger", icon: <span>败</span> },
    { key: "walmart", title: "在 Walmart", value: rows.filter((row) => row.status === "executed").length, subtitle: "示例中已有货件号的行", unit: "单", tone: "normal", icon: <span>货</span> },
  ];
  const columns: ProColumns<SystemShipmentRow>[] = [
    { title: "草稿", dataIndex: "draft", render: (_, row) => <Space direction="vertical" size={0}><span>{row.draft}</span><Typography.Text type="secondary">{row.receivedAt}</Typography.Text></Space> },
    { title: "操作类型", dataIndex: "action", render: (_, row) => <Space direction="vertical" size={0}><span>{row.action}</span><Typography.Text type="secondary">POST inbound-shipments ×1 · GET 回读 · 箱唛 ×1</Typography.Text></Space> },
    { title: "店铺", dataIndex: "store" },
    { title: "计划号 / 货件", dataIndex: "plan", render: (_, row) => <Space direction="vertical" size={0}><span>{row.plan}</span><Typography.Text type="secondary">{row.systemNo}</Typography.Text><span>{row.summary}</span></Space> },
    { title: "状态", dataIndex: "status", render: (_, row) => <Space><Tag color="success">{shipmentStatusLabel[row.status]}</Tag><Tag color="orange">{row.badge}</Tag></Space> },
    { title: "执行结果", dataIndex: "result", width: 360 },
    { title: "操作", valueType: "option", render: () => <Button size="small" onClick={() => preview("前端预览不会取消计划或改数量")}>取消</Button> },
  ];
  return (
    <WfsFrame page={page}>
      <Card>
        <Steps
          size="small"
          current={3}
          items={[
            { title: "货件草稿", description: "来自待发货打包单" },
            { title: "批准", description: "本页记录书面批准" },
            { title: "执行", description: "建货件并取箱唛" },
            { title: "结果", description: "箱唛 PDF 与写入记录回本页" },
          ]}
        />
        <Typography.Paragraph type="secondary" style={{ margin: "12px 0 0" }}>
          撤销只包括取消计划和改数量。运单号填写在领星 WFS 货件，不在本页提交。批准按权限校验，不写死具体人员。
        </Typography.Paragraph>
      </Card>
      <ManagementStatCards
        ariaLabel="系统货件统计"
        cards={cards}
        activeKey={status}
        onCardClick={(key) => setStatus(key === "walmart" ? "executed" : key)}
      />
      <Card>
        <Space wrap>
          <Select allowClear placeholder="全部店铺" style={{ width: 240 }} value={store} onChange={setStore}
            options={WFS_STORES.map((item) => ({ value: item, label: item }))} />
          <Select
            style={{ width: 160 }}
            value={status}
            onChange={setStatus}
            options={[
              { value: "", label: `全部 ${systemShipmentRows.length}` },
              { value: "pending", label: `待批准 ${count("pending")}` },
              { value: "approved", label: `待执行 ${count("approved")}` },
              { value: "executed", label: `已执行 ${count("executed")}` },
              { value: "failed", label: `失败 ${count("failed")}` },
            ]}
          />
          <Input.Search allowClear placeholder="草稿号 / 计划号 / 货件号" style={{ width: 260 }} onSearch={setKeyword} />
          <Button onClick={() => { setStore(undefined); setStatus(""); setKeyword(""); }}>重置</Button>
        </Space>
      </Card>
      <WfsTable label="系统货件表格" columns={columns} rows={rows} />
    </WfsFrame>
  );
}
