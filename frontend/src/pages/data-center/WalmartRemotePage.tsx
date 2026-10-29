import { Button, Card, Form, Input, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { backendRequest } from "@/api/backendApi";
import type { NavigationPage } from "@/config/navigation";

interface StoreChoice {
  source_account_ref: string;
  store_id: string;
  store_code: string;
  display_name: string;
  route_ready: boolean;
}

type JobStatus = "queued" | "running" | "succeeded" | "failed" | "needs_review";

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
  const [stores, setStores] = useState<StoreChoice[]>([]);
  const [storesError, setStoresError] = useState<string>();
  const [messageApi, holder] = message.useMessage();

  useEffect(() => {
    let mounted = true;
    void backendRequest<StoreChoice[]>("/api/integrations/walmart-remote/stores")
      .then((response) => { if (mounted) setStores(response.data); })
      .catch((error: unknown) => { if (mounted) setStoresError(error instanceof Error ? error.message : "店铺列表不可用"); });
    return () => { mounted = false; };
  }, []);

  const reloadJobs = async () => {
    try {
      const response = await backendRequest<RemoteJob[]>(
        "/api/integrations/walmart-remote/jobs?limit=50&offset=0",
      );
      setJobs(response.data);
    } catch (error) {
      void messageApi.error(error instanceof Error ? error.message : "任务列表加载失败");
    }
  };

  useEffect(() => {
    let mounted = true;
    void backendRequest<RemoteJob[]>("/api/integrations/walmart-remote/jobs?limit=50")
      .then((response) => { if (mounted) setJobs(response.data); })
      .catch(() => { /* Page may be disabled before server-side rollout. */ });
    return () => { mounted = false; };
  }, []);

  const create = async (values: { store: string; operations: string[]; requestKey: string }) => {
    const chosen = stores.find((store) => store.store_id === values.store && store.route_ready);
    if (!chosen) return;
    setLoading(true);
    try {
      const response = await backendRequest<RemoteJob>("/api/integrations/walmart-remote/jobs", {
        method: "POST",
        body: JSON.stringify({
          source_account_ref: chosen.source_account_ref,
          store_id: chosen.store_id,
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

  const recover = async (job: RemoteJob) => {
    setLoading(true);
    try {
      await backendRequest<RemoteJob>(
        `/api/integrations/walmart-remote/jobs/${encodeURIComponent(job.id)}/recover`,
        { method: "POST" },
      );
      void messageApi.success("只回收任务已提交，不会重新调用 Walmart");
      await reloadJobs();
    } catch (error) {
      void messageApi.error(error instanceof Error ? error.message : "只回收提交失败");
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
      {storesError && <Typography.Text type="danger">{storesError}</Typography.Text>}
      <Card title="创建手动采集任务" style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline" onFinish={(values) => void create(values)}
          initialValues={{ operations: ["wfs_inventory"] }}>
          <Form.Item name="store" label="店铺" rules={[{ required: true }]}>
            <Select style={{ width: 145 }} options={stores.map((s) => ({ value: s.store_id, label: s.store_code, disabled: !s.route_ready }))} />
          </Form.Item>
          <Form.Item name="operations" label="只读接口" rules={[{ required: true }]}>
            <Select mode="multiple" style={{ minWidth: 250 }} options={operations} />
          </Form.Item>
          <Form.Item name="requestKey" label="任务编号"
            rules={[{ required: true, pattern: /^[a-zA-Z0-9_-]{8,128}$/ }]}>
            <Input style={{ width: 195 }} placeholder="自定义唯一任务编号" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} disabled={!stores.some((s) => s.route_ready)}>提交任务</Button>
          </Form.Item>
        </Form>
      </Card>
      <Card title="采集任务历史" extra={<Button size="small" onClick={() => void reloadJobs()}>刷新列表</Button>}>
        <Table dataSource={jobs} rowKey="id" pagination={{ pageSize: 10 }} scroll={{ x: 900 }}
          columns={[
            { title: "店铺", dataIndex: "store_code", width: 100 },
            { title: "操作", dataIndex: "operations", render: (v: string[]) => v.join("、") },
            { title: "状态", dataIndex: "status", width: 110,
              render: (v: JobStatus) => <Tag color={v === "succeeded" ? "green" : v === "failed" ? "red" : "blue"}>{v}</Tag> },
            { title: "校验文件", dataIndex: "files_verified", width: 90, render: (v: number | null) => v ?? "—" },
            { title: "错误码", dataIndex: "error_code", width: 190, render: (v: string | null) => v ?? "—" },
            { title: "创建时间", dataIndex: "created_at", width: 190 },
            { title: "操作", width: 100, render: (_: unknown, record: RemoteJob) => <Space><Button size="small" onClick={() => void refresh(record)}>刷新</Button>{record.status === "needs_review" && <Button size="small" disabled={loading} onClick={() => void recover(record)}>只回收</Button>}</Space> },
          ]}
        />
      </Card>
    </div>
  );
}
