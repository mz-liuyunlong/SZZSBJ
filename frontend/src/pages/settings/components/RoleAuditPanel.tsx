/** Read-only IAM audit timeline; sensitive before/after payloads stay server-side. */
import { Empty, Table, Tag, Typography, type TableColumnsType } from "antd";
import dayjs from "dayjs";
import type { RoleAuditEvent } from "@/pages/settings/roleManagementTypes";

const eventLabels: Record<string, string> = {
  "role.created": "新增角色",
  "role.permissions.updated": "修改角色权限",
  "role.data-scopes.updated": "修改数据权限",
  "user.created": "新增用户",
  "user.updated": "修改用户",
  "user.roles.updated": "修改用户角色",
  "user.password.reset": "重置用户密码",
  "user.deleted": "永久删除用户",
};

interface RoleAuditPanelProps {
  events: RoleAuditEvent[];
  loading: boolean;
}

function RoleAuditPanel({ events, loading }: RoleAuditPanelProps) {
  const columns: TableColumnsType<RoleAuditEvent> = [
    {
      title: "时间",
      dataIndex: "createdAt",
      width: 168,
      render: (value: string) => dayjs(value).format("YYYY-MM-DD HH:mm:ss"),
    },
    {
      title: "操作",
      dataIndex: "eventType",
      width: 168,
      render: (value: string) => (
        <Tag color={value.includes("deleted") ? "red" : "blue"}>
          {eventLabels[value] ?? value}
        </Tag>
      ),
    },
    {
      title: "目标",
      key: "target",
      width: 220,
      render: (_, event) => (
        <Typography.Text code>
          {event.targetType}:{event.targetKey}
        </Typography.Text>
      ),
    },
    {
      title: "操作人",
      dataIndex: "actorUserId",
      width: 108,
      render: (value?: number) => value ?? "系统",
    },
    {
      title: "请求ID",
      dataIndex: "requestId",
      ellipsis: true,
      render: (value?: string) => value ? (
        <Typography.Text copyable={{ text: value }}>{value}</Typography.Text>
      ) : "-",
    },
    {
      title: "来源IP",
      dataIndex: "requestIp",
      width: 136,
      render: (value?: string) => value || "-",
    },
  ];

  return (
    <div className="role-management__permission-scroll role-management__audit-panel">
      <div className="role-management__audit-intro">
        <div>
          <Typography.Text strong>权限变更记录</Typography.Text>
          <Typography.Text type="secondary">
            仅展示操作元数据，不在前端暴露密码、Token 或完整变更载荷。
          </Typography.Text>
        </div>
      </div>
      <Table<RoleAuditEvent>
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={events}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无权限变更记录"
            />
          ),
        }}
        scroll={{ x: 900 }}
      />
    </div>
  );
}

export default RoleAuditPanel;
