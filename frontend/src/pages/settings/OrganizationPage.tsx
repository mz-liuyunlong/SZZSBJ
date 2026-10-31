import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Empty, Input, Modal, Space, Spin, Table, Tree, Typography, message } from "antd";
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
  const [notice, noticeContext] = message.useMessage();

  const confirmSync = async () => {
    if (!canSync || syncing) return;
    setSyncing(true);
    try {
      const result = await backendRequest<SyncPreview>(
        "/api/settings/organization/sync-preview",
      );
      const preview = result.data;
      Modal.confirm({
        title: "确认同步飞书组织架构？",
        content: `本次包含 ${preview.department_count} 个部门、${preview.employee_count} 名员工。仅更新组织快照，不创建账号或更改角色权限。`,
        okText: "确认写入",
        cancelText: "取消",
        onOk: async () => {
          try {
            await backendRequest("/api/settings/organization/sync-apply", {
              method: "POST",
              body: JSON.stringify({ expected_hash: preview.snapshot_hash }),
            });
            const saved = await backendRequest<DirectoryPreview>(
              "/api/settings/organization/snapshot",
            );
            setData(saved.data);
            void notice.success("飞书组织架构已同步到快照");
          } catch {
            void notice.error("同步失败或数据已变化，请重新预览。");
          }
        },
      });
    } catch {
      void notice.error("无法预览飞书组织，请检查授权和应用配置。");
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    let alive = true;
    void backendRequest<DirectoryPreview>("/api/settings/organization/snapshot")
      .then(response => { if (alive) setData(response.data); })
      .catch(() => { if (alive) setError("组织架构读取失败：请确认已授权部门数据范围，并检查组织同步状态。"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

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
    </Spin>
  </div>;
}
