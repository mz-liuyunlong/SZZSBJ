/** Dense no-API user table with fixed footer and resizable columns. */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Empty, Space, Tag } from "antd";
import type { Key } from "react";
import ReportTableShell, {
  ReportTableSelectionBar,
} from "@/components/report-table/ReportTableShell";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import {
  userManagementColumnFields,
  type UserManagementRow,
  type UserRoleName,
  type UserStatus,
} from "@/pages/settings/userManagementTypes";

interface UserManagementTableProps {
  rows: UserManagementRow[];
  columnWidths: Record<string, number>;
  currentPage: number;
  pageSize: number;
  selectedRowKeys: Key[];
  onColumnWidthChange: (key: string, width: number) => void;
  onCurrentPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onSelectionChange: (keys: Key[]) => void;
  onEdit: (row: UserManagementRow) => void;
  onSetRole: (row: UserManagementRow) => void;
  onResetPassword: (row: UserManagementRow) => void;
  onToggleStatus: (row: UserManagementRow) => void;
  onDelete: (row: UserManagementRow) => void;
  onBulkDisable: () => void;
}

const statusColors: Record<UserStatus, string> = {
  启用: "success",
  停用: "default",
};

const roleColors: Record<UserRoleName, string> = {
  AI助手: "blue",
  运营: "processing",
  采购: "cyan",
  仓库管理: "geekblue",
  财务管理: "purple",
  管理员: "volcano",
};

const compareText = (left: string, right: string) => left.localeCompare(right, "zh-CN");

function createColumns(
  onEdit: (row: UserManagementRow) => void,
  onSetRole: (row: UserManagementRow) => void,
  onResetPassword: (row: UserManagementRow) => void,
  onToggleStatus: (row: UserManagementRow) => void,
  onDelete: (row: UserManagementRow) => void,
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
          {row.roles.map((role) => <Tag key={role} color={roleColors[role]}>{role}</Tag>)}
        </Space>
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
      render: (_, row) => (
        <Space size={0} className="user-management__row-actions">
          <Button type="link" onClick={() => onEdit(row)}>编辑</Button>
          <Button type="link" onClick={() => onSetRole(row)}>设置角色</Button>
          <Button type="link" onClick={() => onResetPassword(row)}>重置密码</Button>
          <Button type="link" onClick={() => onToggleStatus(row)}>{row.status === "启用" ? "停用" : "启用"}</Button>
          <Button type="link" danger onClick={() => onDelete(row)}>删除</Button>
        </Space>
      ),
    },
  ];
}

function UserManagementTable({
  rows,
  columnWidths,
  currentPage,
  pageSize,
  selectedRowKeys,
  onColumnWidthChange,
  onCurrentPageChange,
  onPageSizeChange,
  onSelectionChange,
  onEdit,
  onSetRole,
  onResetPassword,
  onToggleStatus,
  onDelete,
  onBulkDisable,
}: UserManagementTableProps) {
  const columnMap = new Map(createColumns(
    onEdit,
    onSetRole,
    onResetPassword,
    onToggleStatus,
    onDelete,
  ).map((column) => [String(column.key), column]));

  const columns = userManagementColumnFields.flatMap((field) => {
    const column = columnMap.get(field.key);
    if (!column) return [];
    const width = columnWidths[field.key] ?? (Number(column.width) || 120);
    const minWidth = Math.max(field.key === "operation" ? 240 : 88, field.title.length * 14 + 32);
    return [{
      ...column,
      align: "left" as const,
      width,
      onHeaderCell: () => ({ className: "report-table-resizable-header-cell user-management__resizable-header-cell" }),
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
        rowSelection={{ fixed: true, selectedRowKeys, onChange: onSelectionChange }}
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
        footer={() => (
          <ReportTableSelectionBar
            selectedCount={selectedRowKeys.length}
            actions={[{
              key: "disable",
              label: "批量停用",
              danger: true,
              onClick: onBulkDisable,
            }]}
          />
        )}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配用户" /> }}
      />
    </ReportTableShell>
  );
}

export default UserManagementTable;
