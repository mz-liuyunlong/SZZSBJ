/** Dense user table with permission-aware fields and operations. */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Empty, Space, Tag, Typography } from "antd";
import type { Key } from "react";
import ReportTableShell, {
  ReportTableSelectionBar,
} from "@/components/report-table/ReportTableShell";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import {
  userManagementColumnFields,
  type UserManagementRow,
  type UserStatus,
} from "@/pages/settings/userManagementTypes";

interface UserManagementTableProps {
  rows: UserManagementRow[];
  columnWidths: Record<string, number>;
  currentPage: number;
  pageSize: number;
  selectedRowKeys: Key[];
  currentUserId?: string;
  currentUserIsSuperAdmin: boolean;
  canViewPhone: boolean;
  canViewEmail: boolean;
  canEdit: boolean;
  canAssignRole: boolean;
  canResetPassword: boolean;
  canEnableDisable: boolean;
  canHardDelete: boolean;
  canConfigureDataScope: boolean;
  canBindOwners: boolean;
  onColumnWidthChange: (key: string, width: number) => void;
  onCurrentPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onSelectionChange: (keys: Key[]) => void;
  onEdit: (row: UserManagementRow) => void;
  onSetRole: (row: UserManagementRow) => void;
  onSetDataScope: (row: UserManagementRow) => void;
  onBindOwners: (row: UserManagementRow) => void;
  onResetPassword: (row: UserManagementRow) => void;
  onToggleStatus: (row: UserManagementRow) => void;
  onDelete: (row: UserManagementRow) => void;
  onBulkDisable: () => void;
}

const statusColors: Record<UserStatus, string> = {
  启用: "success",
  停用: "default",
};

const compareText = (left: string, right: string) => left.localeCompare(right, "zh-CN");

function roleColor(role: string) {
  if (role === "超级管理员") return "red";
  if (role === "管理员") return "volcano";
  if (role === "运营") return "processing";
  if (role === "采购") return "cyan";
  if (role === "仓库") return "geekblue";
  if (role === "财务") return "purple";
  return "default";
}

function createColumns(
  options: Pick<
    UserManagementTableProps,
    | "currentUserId"
    | "currentUserIsSuperAdmin"
    | "canEdit"
    | "canAssignRole"
    | "canResetPassword"
    | "canEnableDisable"
    | "canHardDelete"
    | "canConfigureDataScope"
    | "canBindOwners"
    | "onEdit"
    | "onSetRole"
    | "onSetDataScope"
    | "onBindOwners"
    | "onResetPassword"
    | "onToggleStatus"
    | "onDelete"
  >,
): ProColumns<UserManagementRow>[] {
  return [
    {
      title: "用户名",
      dataIndex: "username",
      key: "username",
      sorter: (left, right) => compareText(left.username, right.username),
      render: (_, row) => <strong>{row.username}</strong>,
    },
    {
      title: "真实姓名",
      dataIndex: "realName",
      key: "realName",
      sorter: (left, right) => compareText(left.realName, right.realName),
    },
    { title: "手机号", dataIndex: "phone", key: "phone" },
    { title: "邮箱", dataIndex: "email", key: "email" },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (_, row) => <Tag color={statusColors[row.status]}>{row.status}</Tag>,
    },
    {
      title: "角色",
      dataIndex: "roles",
      key: "roles",
      render: (_, row) => (
        <Space size={4} wrap>
          {row.roles.map((role) => (
            <Tag key={role} color={roleColor(role)}>{role}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: "领星负责人绑定",
      key: "ownerBinding",
      render: (_, row) => (
        row.ownerMappingCount === undefined ? "—" : (
          <Tag color={row.ownerMappingCount > 0 ? "success" : "warning"}>
            {row.ownerMappingCount > 0 ? `已绑定 ${row.ownerMappingCount} 组` : "未绑定"}
          </Tag>
        )
      ),
    },
    {
      title: "创建时间",
      dataIndex: "createdAt",
      key: "createdAt",
      sorter: (left, right) => compareText(left.createdAt, right.createdAt),
    },
    {
      title: "最近登录",
      dataIndex: "lastLoginAt",
      key: "lastLoginAt",
      sorter: (left, right) => compareText(left.lastLoginAt, right.lastLoginAt),
    },
    {
      title: "操作",
      key: "operation",
      fixed: "right",
      render: (_, row) => {
        const isSelf = row.id === options.currentUserId;
        const protectedSuperAdmin = row.isSuperAdmin && !options.currentUserIsSuperAdmin;
        const actions = [
          options.canEdit ? (
            <Button
              key="edit"
              type="link"
              disabled={protectedSuperAdmin}
              onClick={() => options.onEdit(row)}
            >编辑</Button>
          ) : null,
          options.canAssignRole ? (
            <Button
              key="role"
              type="link"
              disabled={protectedSuperAdmin || row.isSuperAdmin}
              onClick={() => options.onSetRole(row)}
            >设置角色</Button>
          ) : null,
          options.canConfigureDataScope ? (
            <Button
              key="data-scope"
              type="link"
              disabled={isSelf || protectedSuperAdmin || row.isSuperAdmin}
              onClick={() => options.onSetDataScope(row)}
            >数据范围</Button>
          ) : null,
          options.canBindOwners ? (
            <Button
              key="owner-binding"
              type="link"
              disabled={protectedSuperAdmin || row.status !== "启用"}
              onClick={() => options.onBindOwners(row)}
            >绑定负责人</Button>
          ) : null,
          options.canResetPassword ? (
            <Button
              key="password"
              type="link"
              disabled={protectedSuperAdmin}
              onClick={() => options.onResetPassword(row)}
            >重置密码</Button>
          ) : null,
          options.canEnableDisable ? (
            <Button
              key="status"
              type="link"
              disabled={isSelf || row.isSuperAdmin}
              onClick={() => options.onToggleStatus(row)}
            >{row.status === "启用" ? "停用" : "启用"}</Button>
          ) : null,
          options.canHardDelete && !isSelf && !row.isSuperAdmin ? (
            <Button
              key="delete"
              type="link"
              danger
              onClick={() => options.onDelete(row)}
            >删除</Button>
          ) : null,
        ].filter(Boolean);

        return actions.length > 0 ? (
          <Space size={0} className="user-management__row-actions">{actions}</Space>
        ) : (
          <Typography.Text type="secondary">-</Typography.Text>
        );
      },
    },
  ];
}

function UserManagementTable(props: UserManagementTableProps) {
  const {
    rows,
    columnWidths,
    currentPage,
    pageSize,
    selectedRowKeys,
    currentUserId,
    canViewPhone,
    canViewEmail,
    canEnableDisable,
    onColumnWidthChange,
    onCurrentPageChange,
    onPageSizeChange,
    onSelectionChange,
    onBulkDisable,
  } = props;

  const visibleFields = userManagementColumnFields.filter((field) => (
    (field.key !== "phone" || canViewPhone)
    && (field.key !== "email" || canViewEmail)
    && (field.key !== "ownerBinding" || props.canBindOwners)
  ));
  const columnMap = new Map(
    createColumns(props).map((column) => [String(column.key), column]),
  );

  const columns = visibleFields.flatMap((field) => {
    const column = columnMap.get(field.key);
    if (!column) return [];
    const width = columnWidths[field.key] ?? (Number(column.width) || 120);
    const minWidth = Math.max(
      field.key === "operation" ? 240 : 88,
      field.title.length * 14 + 32,
    );
    return [{
      ...column,
      align: "left" as const,
      width,
      onHeaderCell: () => ({
        className: "report-table-resizable-header-cell user-management__resizable-header-cell",
      }),
      title: (
        <ResizableColumnTitle
          label={field.title}
          minWidth={minWidth}
          width={width}
          onWidthChange={(nextWidth) => onColumnWidthChange(field.key, nextWidth)}
        />
      ),
    }];
  });

  const scrollX = columns.reduce((total, column) => total + Number(column.width ?? 120), 48);

  return (
    <ReportTableShell className="user-management__table" label="用户管理表格">
      <ProTable<UserManagementRow>
        columns={columns}
        dataSource={rows}
        rowKey="id"
        rowSelection={canEnableDisable ? {
          fixed: true,
          selectedRowKeys,
          onChange: onSelectionChange,
          getCheckboxProps: (row) => ({
            disabled: row.id === currentUserId || row.isSuperAdmin,
          }),
        } : false}
        search={false}
        options={false}
        toolBarRender={false}
        tableAlertRender={false}
        tableAlertOptionRender={false}
        showSorterTooltip={{ target: "sorter-icon" }}
        scroll={{ x: scrollX, y: "100%" }}
        pagination={{
          current: currentPage,
          pageSize,
          total: rows.length,
          showSizeChanger: true,
          pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS,
          showTotal: (total) => `共 ${total.toLocaleString("zh-CN")} 个用户`,
          onChange: (page, nextPageSize) => {
            onCurrentPageChange(page);
            if (nextPageSize !== pageSize) onPageSizeChange(nextPageSize);
          },
        }}
        footer={canEnableDisable ? () => (
          <ReportTableSelectionBar
            selectedCount={selectedRowKeys.length}
            actions={[{
              key: "disable",
              label: "批量停用",
              danger: true,
              onClick: onBulkDisable,
            }]}
          />
        ) : undefined}
        locale={{
          emptyText: (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配用户" />
          ),
        }}
      />
    </ReportTableShell>
  );
}

export default UserManagementTable;
