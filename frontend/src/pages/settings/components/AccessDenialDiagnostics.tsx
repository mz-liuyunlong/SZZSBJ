/** Administrator-only diagnosis of actual denied IAM requests.

The backend returns only canonical route templates, permission keys and reason
codes. Raw URLs, request bodies, credentials and business record values are
never fetched or rendered.
*/
import { useState } from "react";
import { Alert, Button, Card, Input, Space, Table, Tag, Typography } from "antd";
import { backendRequest } from "@/api/backendApi";

interface DenialEvent {
  request_id: string;
  principal_id: string;
  method: string;
  route_template: string;
  denial_stage: string;
  error_code: string;
  required_permissions: string[];
  scope_reason: string | null;
  created_at: string;
}

const stageLabels: Record<string, string> = {
  permission: "缺少功能权限",
  data_scope: "数据范围拒绝",
  unspecified_forbidden: "其他拒绝",
};
const reasonLabels: Record<string, string> = {
  UNENFORCED_DIMENSION: "存在尚未启用的授权维度",
  STORE_SCOPE_NOT_ENFORCED: "该模块尚未实现店铺范围",
  ORGANIZATION_SCOPE_NOT_ENFORCED: "该模块尚未实现组织范围",
};

export default function AccessDenialDiagnostics() {
  const [requestId, setRequestId] = useState("");
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<DenialEvent[]>([]);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  const reload = async () => {
    const trimmed = requestId.trim();
    if (trimmed && !/^[A-Za-z0-9._:-]{1,128}$/.test(trimmed)) {
      setError("请求 ID 格式无效");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ limit: "50" });
      if (trimmed) params.set("request_id", trimmed);
      const result = await backendRequest<{ items: DenialEvent[]; retention_days: number }>(
        `/api/settings/rbac/access-denials?${params.toString()}`,
      );
      setItems(result.data.items);
      setLoaded(true);
    } catch {
      setError("访问拒绝记录加载失败。请确认数据表迁移已完成并检查管理员权限。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card title="403 权限拒绝诊断" size="small" style={{ marginTop: 16 }}>
      <Typography.Paragraph type="secondary">
        按响应中的 X-Request-ID 查询权限拒绝原因。只展示脱敏的路径模板、权限键及原因，不包含请求参数、令牌或业务内容。
      </Typography.Paragraph>
      <Space wrap style={{ marginBottom: 12 }}>
        <Input
          aria-label="查询拒绝请求 ID"
          style={{ width: 320 }}
          placeholder="输入请求 ID；留空查询最近 50 条"
          value={requestId}
          maxLength={128}
          onChange={event => setRequestId(event.target.value)}
          onPressEnter={() => void reload()}
          allowClear
        />
        <Button type="primary" loading={loading} onClick={() => void reload()}>
          查询
        </Button>
      </Space>
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
      <Table<DenialEvent>
        rowKey={row => `${row.request_id}-${row.created_at}-${row.route_template}`}
        size="small"
        loading={loading}
        pagination={{ pageSize: 10 }}
        dataSource={items}
        locale={{ emptyText: loaded ? "无匹配的拒绝记录" : "输入请求 ID 后查询" }}
        scroll={{ x: 1100 }}
        columns={[
          { title: "时间", dataIndex: "created_at", width: 175 },
          { title: "请求 ID", dataIndex: "request_id", width: 185,
            render: value => <Typography.Text copyable>{String(value)}</Typography.Text> },
          { title: "用户 ID", dataIndex: "principal_id", width: 95 },
          { title: "方法", dataIndex: "method", width: 70 },
          { title: "路由", dataIndex: "route_template", ellipsis: true, width: 255 },
          { title: "原因阶段", dataIndex: "denial_stage", width: 130,
            render: value => <Tag>{stageLabels[String(value)] ?? "权限拒绝"}</Tag> },
          { title: "具体原因", dataIndex: "scope_reason", width: 210,
            render: value => value ? reasonLabels[String(value)] ?? "其他范围拒绝" : "-" },
          { title: "所需权限", dataIndex: "required_permissions", width: 280,
            render: value => (value as string[]).join("、") || "-" },
        ]}
      />
    </Card>
  );
}
