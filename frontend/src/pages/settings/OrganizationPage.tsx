import { useEffect, useMemo, useState } from "react";
import { Alert, Card, Empty, Input, Spin, Table, Tree, Typography } from "antd";
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
}

export default function OrganizationPage() {
  const [data, setData] = useState<DirectoryPreview>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [department, setDepartment] = useState<string>();
  const [search, setSearch] = useState("");

  useEffect(() => {
    let alive = true;
    void backendRequest<DirectoryPreview>("/api/settings/organization/preview")
      .then(response => { if (alive) setData(response.data); })
      .catch(() => { if (alive) setError("飞书通讯录读取失败。请检查飞书授权范围和应用配置。"); })
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
    <Typography.Title level={4}>组织架构 · 飞书</Typography.Title>
    <Alert type="info" showIcon style={{ marginBottom: 16 }}
      message="当前为飞书实时只读预览"
      description="部门和人员来自飞书应用可见的通讯录；这里不自动创建账号、不调整角色，也不扩大任何数据权限。" />
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
