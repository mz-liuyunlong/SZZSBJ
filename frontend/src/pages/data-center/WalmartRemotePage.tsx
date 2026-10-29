import { Button, Card, Form, Input, Select, Space, Table, Tag, Typography, message } from "antd";
import { useState } from "react";
import { backendRequest } from "@/api/backendApi";
import type { NavigationPage } from "@/config/navigation";

const stores = [
  { code: "HK2612", id: "110704872940532224" },
  { code: "HK2613", id: "110711149541688320" },
  { code: "HK2614", id: "110711149920800256" },
  { code: "HK2615", id: "110711146247224320" },
  { code: "CN2501", id: "110687427724845056" },
  { code: "CN2502", id: "110687428693128704" },
  { code: "CN2601", id: "110687423514268160" },
  { code: "CN2602", id: "110689966555011584" },
  { code: "CN2603", id: "110704863834580480" },
] as const;

type JobStatus = "queued" | "running" | "succeeded" | "failed";

interface RemoteJob {
  id: string;
  source_account_ref: string;
  store_id: string;
  store_code: string;
  operations: string[];
  status: JobStatus;
  run_id: string | null;
  files_verified: number | null;
  error_code: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

const operations = [
  { value: "wfs_inventory", label: "WFS 在库库存" },
  { value: "inbound_shipments", label: "入库货件" },
  { value: "inbound_shipment_items", label: "货件商品明细" },
  { value: "inventory_log", label: "库存流水" },
];

export default function WalmartRemotePage({ page }: { page: NavigationPage }) {
  const [form] = Form.useForm<{ store: string; operations: string[]; requestKey: string }>();
  const [jobs, setJobs] = useState<RemoteJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [messageApi, holder] = message.useMessage();

  const create = async (values: { store: string; operations: string[]; requestKey: string }) => {
    const chosen = stores.find((store) => store.code === values.store);
    if (!chosen) return;
    setLoading(true);
    try {
      const response = await backendRequest<RemoteJob>("/api/integrations/walmart-remote/jobs", {
        method: "POST",
        body: JSON.stringify({
          source_account_ref: "primary",
          store_id: chosen.id,
          operations: values.operations,
          request_key: values.requestKey,
        }),
      });
      setJobs((existing) => [response.data, ...existing.filter((job) => job.id !== response.data.id)]);
      void messageApi.success("任务已创建，状态以服务器返回为准");
    } catch (error) {
      void messageApi.error(error instanceof Error ? error.message : "任务创建失败");
    } finally {
      setLoading(false);
    }
  };

  const refresh = async (job: RemoteJob) => {
    try {
      const response = await backendRequest<RemoteJob>(
        `/api/integrations/walmart-remote/jobs/${encodeURIComponent(job.id)}`,
      );
      setJobs((existing) => existing.map((item) => item.id === job.id ? response.data : item));
    } catch (error) {
      void messageApi.error(error instanceof Error ? error.message : "查询失败");
    }
  };

  return (
    <div style={{ padding: 20 }}>
      {holder}
      <Typography.Title level={4}>{page.title}</Typography.Title>
      <Typography.Paragraph type="secondary">
        九店固定路由采集 · 腾讯云保管长期密钥 · 子服务器执行只读 API。任务状态和错误码不包含凭证。
      </Typography.Paragraph>
      <Card title="创建手动采集任务" style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline" onFinish={(values) => void create(values)}
          initialValues={{ store: "HK2613", operations: ["wfs_inventory"] }}>
          <Form.Item name="store" label="店铺" rules={[{ required: true }]}>
            <Select style={{ width: 145 }} options={stores.map((s) => ({ value: s.code, label: s.code }))} />
          </Form.Item>
          <Form.Item name="operations" label="只读接口" rules={[{ required: true }]}>
            <Select mode="multiple" style={{ minWidth: 250 }} options={operations} />
          </Form.Item>
          <Form.Item name="requestKey" label="任务编号"
            rules={[{ required: true, pattern: /^[a-zA-Z0-9_-]{8,128}$/ }]}>
            <Input style={{ width: 195 }} placeholder="自定义唯一任务编号" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>提交任务</Button>
          </Form.Item>
        </Form>
      </Card>
      <Card title="本页任务记录" extra={<Typography.Text type="secondary">仅显示本页已创建的任务，点击刷新读取服务器状态</Typography.Text>}>
        <Table dataSource={jobs} rowKey="id" pagination={{ pageSize: 10 }} scroll={{ x: 900 }}
          columns={[
            { title: "店铺", dataIndex: "store_code", width: 100 },
            { title: "操作", dataIndex: "operations", render: (v: string[]) => v.join("、") },
            { title: "状态", dataIndex: "status", width: 110,
              render: (v: JobStatus) => <Tag color={v === "succeeded" ? "green" : v === "failed" ? "red" : "blue"}>{v}</Tag> },
            { title: "校验文件", dataIndex: "files_verified", width: 90, render: (v: number | null) => v ?? "—" },
            { title: "错误码", dataIndex: "error_code", width: 190, render: (v: string | null) => v ?? "—" },
            { title: "创建时间", dataIndex: "created_at", width: 190 },
            { title: "操作", width: 100, render: (_: unknown, record: RemoteJob) => <Space><Button size="small" onClick={() => void refresh(record)}>刷新</Button></Space> },
          ]}
        />
      </Card>
    </div>
  );
}
