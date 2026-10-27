import { useEffect, useState } from "react";
import { Alert, Button, Descriptions, Drawer, Input, Select, Space, Table, Tag, Typography, message } from "antd";
import { backendRequest } from "@/api/backendApi";

interface Anomaly {
  id: string;
  run_id: string;
  source_account_ref: string;
  interface_key: string;
  business_date: string;
  error_code: string;
  store_id: string | null;
  item_id: string | null;
  msku: string | null;
  local_sku: string | null;
  platform_order_no: string | null;
  campaign_name: string | null;
  status: string;
  details: Record<string, unknown>;
  occurrence_count: number;
  owner_note: string | null;
  first_seen_at: string;
  last_seen_at: string;
}

const statusNames: Record<string, string> = {
  pending: "待核对",
  investigating: "核对中",
  fix_pending: "待修复",
  review_pending: "待复验",
  resolved: "已解决",
  dismissed: "误报关闭",
};

const guide: Record<string, string> = {
  DATA_PAGES_SEM_SPEND_UNATTRIBUTED:
    "在领星广告报表按店铺、业务日期查询 Campaign 和广告花费；核实商品归属。没有 Item ID 时不得猜测 SKU。",
  DATA_PAGES_CONFIRMED_SAMPLE_EXCEEDS_SALESTAT:
    "在领星订单查询按业务日期、店铺及订单号核对零金额、折扣、购买时间、订单行、取消状态，并与 SaleStat 对比。",
  DATA_PAGES_SAMPLE_RULE_VERSION_UNSUPPORTED:
    "核对订单的送样来源、判定规则版本及历史批准记录，不要批量重设送样标记。",
  SYNC_EXECUTION_FAILED:
    "在关联任务的执行日志核对异常堆栈；这是技术故障，不一定存在可供领星核对的订单。",
};

const display = (value: string | null | undefined) => value?.trim() || "待定位";

export default function SyncTaskAnomalyCenter() {
  const [items, setItems] = useState<Anomaly[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Anomaly | null>(null);
  const [status, setStatus] = useState<string>("all");
  const [keyword, setKeyword] = useState("");
  const [note, setNote] = useState("");
  const [nextStatus, setNextStatus] = useState("investigating");
  const [saving, setSaving] = useState(false);
  const [messageApi, contextHolder] = message.useMessage();
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const refresh = async () => {
    setLoading(true);
    try {
      const query = new URLSearchParams({ page: String(page), page_size: "20" });
      if (status !== "all") query.set("status", status);
      const result = await backendRequest<{ items: Anomaly[] }, { total?: number }>(
        `/api/integrations/sync-anomalies?${query.toString()}`
      );
      setItems(result.data.items);
      setTotal(result.meta.total ?? result.data.items.length);
    } catch {
      messageApi.error("异常列表加载失败，请检查接口权限与异常表迁移状态");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void refresh(); }, [page, status]);

  const submit = async () => {
    if (!selected || note.trim().length < 3) {
      messageApi.warning("请填写至少3个字符的核对说明");
      return;
    }
    setSaving(true);
    try {
      await backendRequest(`/api/integrations/sync-anomalies/${selected.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus, note: note.trim() }),
      });
      messageApi.success("已记录核对结论");
      setSelected(null);
      setNote("");
      await refresh();
    } catch {
      messageApi.error("保存失败，未改变异常状态");
    } finally {
      setSaving(false);
    }
  };
  const visible = items.filter(item =>
    [item.local_sku, item.msku, item.item_id, item.platform_order_no,
      item.store_id, item.campaign_name, item.error_code, item.business_date]
      .some(value => value?.toLowerCase().includes(keyword.toLowerCase()))
  );

  return (
    <section className="sync-task__card" aria-label="同步异常中心">
      {contextHolder}
      <Space wrap style={{ marginBottom: 16 }}>
        <Input.Search placeholder="搜索 SKU / Item ID / 订单号 / 店铺 / 日期" value={keyword}
          onChange={event => setKeyword(event.target.value)} style={{ width: 340 }} allowClear />
        <Select value={status} onChange={value => { setStatus(value); setPage(1); }}
          style={{ width: 140 }}
          options={[{ value: "all", label: "全部状态" },
            ...Object.entries(statusNames).map(([value, label]) => ({ value, label }))]} />
        <Button onClick={() => { void refresh(); }}>刷新异常</Button>
      </Space>
      <Table<Anomaly> size="small" rowKey="id" loading={loading}
        dataSource={visible}
        scroll={{ x: 1100 }}
        pagination={{
          current: page, pageSize: 20, total,
          onChange: value => setPage(value),
        }}
        columns={[
          { title: "业务日期", dataIndex: "business_date", width: 120 },
          { title: "店铺 ID", dataIndex: "store_id", width: 120, render: display },
          { title: "SKU / MSKU", width: 170, render: (_, row) => display(row.local_sku || row.msku) },
          { title: "订单号", dataIndex: "platform_order_no", width: 160, render: display },
          { title: "接口", dataIndex: "interface_key", width: 160 },
          { title: "异常原因", dataIndex: "error_code", width: 250 },
          { title: "状态", dataIndex: "status", width: 105,
            render: value => <Tag>{statusNames[value] ?? value}</Tag> },
          { title: "次数", dataIndex: "occurrence_count", width: 70 },
          { title: "操作", key: "view", fixed: "right", width: 90,
            render: (_, row) => <Button type="link" onClick={() => {
              setSelected(row); setNote(row.owner_note ?? ""); setNextStatus(row.status);
            }}>核对详情</Button> },
        ]}
      />
      <Drawer title="异常核对详情" width={680} open={!!selected}
        onClose={() => setSelected(null)}>
        {selected && <>
          <Alert type="warning" showIcon style={{ marginBottom: 16 }}
            message="异常不代表源接口同步失败；财务结果需独立校验" />
          <Descriptions column={1} bordered size="small" items={[
            { key: "date", label: "美国业务日期", children: selected.business_date },
            { key: "account", label: "来源账号", children: selected.source_account_ref },
            { key: "run", label: "关联任务 Run ID", children: <Typography.Text copyable>{selected.run_id}</Typography.Text> },
            { key: "store", label: "店铺 ID", children: <Typography.Text copyable>{display(selected.store_id)}</Typography.Text> },
            { key: "sku", label: "本地 SKU", children: <Typography.Text copyable>{display(selected.local_sku)}</Typography.Text> },
            { key: "msku", label: "MSKU", children: <Typography.Text copyable>{display(selected.msku)}</Typography.Text> },
            { key: "item", label: "Item ID", children: <Typography.Text copyable>{display(selected.item_id)}</Typography.Text> },
            { key: "order", label: "订单号", children: <Typography.Text copyable>{display(selected.platform_order_no)}</Typography.Text> },
            { key: "campaign", label: "Campaign", children: <Typography.Text copyable>{display(selected.campaign_name)}</Typography.Text> },
            { key: "source", label: "接口", children: selected.interface_key },
            { key: "error", label: "错误码", children: selected.error_code },
            { key: "count", label: "累计发现次数", children: selected.occurrence_count },
            { key: "last", label: "最近发现", children: selected.last_seen_at },
          ]} />
          <Typography.Title level={5} style={{ marginTop: 20 }}>领星核对指引</Typography.Title>
          <Typography.Paragraph>{guide[selected.error_code] ??
            "根据店铺、业务日期、商品与订单在领星核对来源数据；无法确认时标记待定位，不得直接修改财务数据。"}</Typography.Paragraph>
          <Typography.Title level={5}>异常证据（仅展示安全摘要）</Typography.Title>
          <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {JSON.stringify(selected.details, null, 2)}
          </pre>
          <Typography.Title level={5}>处理状态与核对记录</Typography.Title>
          <Space direction="vertical" style={{ width: "100%" }}>
            <Select value={nextStatus} onChange={setNextStatus}
              options={Object.entries(statusNames).map(([value, label]) => ({ value, label }))} />
            <Input.TextArea rows={4} value={note} onChange={event => setNote(event.target.value)}
              placeholder="填写领星核对结论、差异原因及处理依据；解决/误报关闭均须说明" />
            <Button type="primary" loading={saving} onClick={() => { void submit(); }}>保存核对记录</Button>
          </Space>
        </>}
      </Drawer>
    </section>
  );
}
