import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Empty, Input, Modal, Select, Space, Spin, Table, Tree, Typography, message } from "antd";
import type { DataNode } from "antd/es/tree";
import { backendRequest } from "@/api/backendApi";

interface Department {
  department_id: string;
  parent_department_id: string;
  name: string;
  leader_user_id: string;
}
interface Employee {
  name: string;
  open_id: string;
  department_ids: string[];
  is_active: boolean | null;
  is_resigned: boolean | null;
  is_frozen: boolean | null;
}
interface OwnerCandidate {
  owner_ref: string;
  feishu_open_id: string | null;
  employee_name: string | null;
  is_active: boolean;
}
interface DirectoryPreview {
  departments: Department[];
  users: Employee[];
  read_only: boolean;
  last_synced_at?: string | null;
}
interface SyncPreview {
  snapshot_hash: string;
  department_count: number;
  employee_count: number;
  large_reduction: boolean;
  identity_replacement: boolean;
  removed_department_ids: string[];
  added_department_ids: string[];
  removed_employee_ids: string[];
  added_employee_ids: string[];
  department_retention_ratio: number;
  employee_retention_ratio: number;
}
interface OrganizationPageProps {
  canSync: boolean;
}

export default function OrganizationPage({ canSync }: OrganizationPageProps) {
  const [data, setData] = useState<DirectoryPreview>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [department, setDepartment] = useState<string>();
  const [search, setSearch] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [ownerCandidates, setOwnerCandidates] = useState<OwnerCandidate[]>([]);
  const [ownerSaving, setOwnerSaving] = useState<string>();
  const [notice, noticeContext] = message.useMessage();

  const confirmSync = async () => {
    if (!canSync || syncing) return;
    setSyncing(true);
    try {
      const result = await backendRequest<SyncPreview>(
        "/api/settings/organization/sync-preview",
      );
      const preview = result.data;
      await new Promise<void>((resolve) => {
        Modal.confirm({
          title: "确认同步飞书组织架构？",
          width: 560,
          content: (
            <div>
              <p>本次包含 {preview.department_count} 个部门、{preview.employee_count} 名员工。</p>
              <p>部门身份保留率：{(preview.department_retention_ratio * 100).toFixed(1)}%；员工身份保留率：{(preview.employee_retention_ratio * 100).toFixed(1)}%。</p>
              {(preview.large_reduction || preview.identity_replacement) && (
                <Alert type="warning" showIcon message="组织身份变化异常，需要明确二次确认" description="请先核实飞书应用通讯录授权范围、部门和员工身份集合。同步不会自动创建账号或分配角色。" />
              )}
              <p>新增部门 {preview.added_department_ids.length}，移除部门 {preview.removed_department_ids.length}；新增员工 {preview.added_employee_ids.length}，移除员工 {preview.removed_employee_ids.length}。</p>
            </div>
          ),
          okText: "确认写入快照",
          cancelText: "取消",
          onOk: async () => {
            try {
              await backendRequest("/api/settings/organization/sync-apply", {
                method: "POST",
                body: JSON.stringify({
                  expected_hash: preview.snapshot_hash,
                  allow_large_reduction: preview.large_reduction,
                  allow_identity_replacement: preview.identity_replacement,
                }),
              });
              const saved = await backendRequest<DirectoryPreview>(
                "/api/settings/organization/snapshot",
              );
              setData(saved.data);
              void notice.success("飞书组织架构已同步到快照");
            } catch {
              void notice.error("同步失败或数据已变化，请重新预览。");
            } finally {
              resolve();
            }
          },
          onCancel: () => resolve(),
        });
      });
    } catch {
      void notice.error("无法预览飞书组织，请检查授权和应用配置。");
    } finally {
      setSyncing(false);
    }
  };

  const reloadOwnerCandidates = async () => {
    const response = await backendRequest<OwnerCandidate[]>("/api/settings/organization/owner-candidates");
    setOwnerCandidates(response.data);
  };

  const bindOwner = async (ownerRef: string, openId: string | undefined) => {
    if (!openId) {
      await backendRequest(
        `/api/settings/organization/owner-bindings/${encodeURIComponent(ownerRef)}`,
        { method: "DELETE" },
      );
    } else {
      await backendRequest(
        `/api/settings/organization/owner-bindings/${encodeURIComponent(ownerRef)}`,
        { method: "PUT", body: JSON.stringify({ feishu_open_id: openId }) },
      );
    }
    await reloadOwnerCandidates();
    void notice.success("负责人绑定已更新");
  };

  useEffect(() => {
    let alive = true;
    void backendRequest<DirectoryPreview>("/api/settings/organization/snapshot")
      .then(response => { if (alive) setData(response.data); })
      .catch(() => { if (alive) setError("组织架构读取失败：请确认已授权部门数据范围，并检查组织同步状态。"); })
      .finally(() => { if (alive) setLoading(false); });
    if (canSync) void reloadOwnerCandidates().catch(() => {
      if (alive) void notice.error("负责人候选数据加载失败");
    });
    return () => { alive = false; };
  }, [canSync]);

  const nodes = useMemo(() => {
    const departments = data?.departments ?? [];
    const groups = new Map<string, DataNode[]>();
    for (const entry of departments) groups.set(entry.department_id, []);
    const roots: DataNode[] = [];
    for (const entry of departments) {
      const node: DataNode = { key: entry.department_id, title: entry.name,
        children: groups.get(entry.department_id) };
      const parent = groups.get(entry.parent_department_id);
      if (parent && entry.parent_department_id !== entry.department_id) parent.push(node);
      else roots.push(node);
    }
    return roots;
  }, [data]);

  const selectedUsers = useMemo(() => (data?.users ?? []).filter(user =>
    (!department || user.department_ids.includes(department))
    && (!search || user.name.toLowerCase().includes(search.toLowerCase()))
  ), [data, department, search]);

  return <div style={{ padding: 20 }}>
    {noticeContext}
    <Space style={{ marginBottom: 16 }}>
      <Typography.Title level={4} style={{ margin: 0 }}>组织架构 · 飞书</Typography.Title>
      {canSync && <Button loading={syncing} onClick={() => void confirmSync()}>
        预览并同步
      </Button>}
    </Space>
    <Alert type="info" showIcon style={{ marginBottom: 16 }}
      message="飞书组织架构"
      description="页面展示飞书应用可见的组织信息；只有超级管理员可以预览并确认同步快照。同步不会创建账号、更改角色或扩大数据权限。" />
    {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
    <Spin spinning={loading}>
      <div style={{ display: "grid", gridTemplateColumns: "280px minmax(0, 1fr)", gap: 16 }}>
        <Card title="组织部门">
          {nodes.length ? <Tree treeData={nodes} defaultExpandAll
            selectedKeys={department ? [department] : []}
            onSelect={keys => setDepartment(keys.length ? String(keys[0]) : undefined)} />
            : <Empty description="无可见部门" />}
        </Card>
        <Card title={`员工名录（${selectedUsers.length}）`} extra={
          <Input.Search allowClear placeholder="按姓名搜索" value={search}
            onChange={event => setSearch(event.target.value)} />
        }>
          <Table<Employee> rowKey="open_id" dataSource={selectedUsers} size="small"
            pagination={{ pageSize: 20 }} columns={[
              { title: "员工", dataIndex: "name" },
              { title: "飞书 Open ID", dataIndex: "open_id", ellipsis: true },
              { title: "所属部门", dataIndex: "department_ids",
                render: (ids: string[]) => ids.join("、") || "未提供" },
              { title: "状态", render: (_, record) =>
                record.is_resigned ? "已离职" : record.is_frozen ? "冻结" : "在职/未确认" },
            ]} />
        </Card>
      </div>
      {canSync && (
        <Card title="领星业务负责人绑定" style={{ marginTop: 16 }}
          extra={<Typography.Text type="secondary">仅使用已验证的业务 UID；变更会记录审计</Typography.Text>}>
          <Table<OwnerCandidate> rowKey="owner_ref" size="small"
            dataSource={ownerCandidates} pagination={{ pageSize: 10 }}
            columns={[
              { title: "领星负责人 UID", dataIndex: "owner_ref", width: 220 },
              { title: "当前飞书员工", dataIndex: "employee_name", render: value => value || "未绑定" },
              { title: "绑定飞书员工", width: 280, render: (_, row) => (
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  placeholder="选择飞书在职员工"
                  style={{ width: "100%" }}
                  loading={ownerSaving === row.owner_ref}
                  value={row.is_active ? row.feishu_open_id || undefined : undefined}
                  options={(data?.users ?? [])
                    .filter(user => user.is_active && !user.is_resigned && !user.is_frozen)
                    .map(user => ({ value: user.open_id, label: user.name }))}
                  onChange={async value => {
                    setOwnerSaving(row.owner_ref);
                    try { await bindOwner(row.owner_ref, value); }
                    catch { void notice.error("负责人绑定失败，请确认 UID 和员工状态"); }
                    finally { setOwnerSaving(undefined); }
                  }}
                />
              ) },
              { title: "状态", dataIndex: "is_active", width: 90,
                render: value => value ? "已绑定" : "未绑定" },
            ]} />
        </Card>
      )}
    </Spin>
  </div>;
}
