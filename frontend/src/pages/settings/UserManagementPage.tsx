/** User-management No-API page shell using local acceptance data only. */
import { PlusOutlined } from "@ant-design/icons";
import { Button, Modal, Typography, message } from "antd";
import { useMemo, useState, type Key } from "react";
import PageShell from "@/components/page/PageShell";
import { REPORT_TABLE_DEFAULT_PAGE_SIZE, normalizeReportTablePageSize } from "@/components/report-table/pagination";
import type { NavigationPage } from "@/config/navigation";
import UserFormModal from "@/pages/settings/components/UserFormModal";
import UserManagementTable from "@/pages/settings/components/UserManagementTable";
import UserManagementToolbar from "@/pages/settings/components/UserManagementToolbar";
import UserRoleModal from "@/pages/settings/components/UserRoleModal";
import { userManagementMockData } from "@/pages/settings/userManagementMockData";
import {
  defaultUserColumnWidths,
  type UserFormValues,
  type UserManagementFilters,
  type UserManagementRow,
  type UserRoleName,
} from "@/pages/settings/userManagementTypes";
import "@/pages/settings/UserManagementPage.css";

const createInitialFilters = (): UserManagementFilters => ({ keyword: "" });

interface UserManagementPageProps {
  page: NavigationPage;
}

function UserManagementPage({ page }: UserManagementPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [users, setUsers] = useState<UserManagementRow[]>(userManagementMockData);
  const [filters, setFilters] = useState(createInitialFilters);
  const [columnWidths, setColumnWidths] = useState(defaultUserColumnWidths);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserManagementRow>();
  const [roleUser, setRoleUser] = useState<UserManagementRow>();

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const filteredUsers = useMemo(() => {
    const keyword = filters.keyword.trim().toLocaleLowerCase();
    return users.filter((user) => (
      (!filters.status || user.status === filters.status)
      && (!filters.role || user.roles.includes(filters.role))
      && (!keyword
        || user.username.toLocaleLowerCase().includes(keyword)
        || user.realName.toLocaleLowerCase().includes(keyword)
        || user.phone.toLocaleLowerCase().includes(keyword))
    ));
  }, [filters, users]);

  const updateFilters = (nextFilters: UserManagementFilters) => {
    setFilters(nextFilters);
    resetPageAndSelection();
  };

  const resetFilters = () => {
    setFilters(createInitialFilters());
    resetPageAndSelection();
  };

  const openCreateModal = () => {
    setEditingUser(undefined);
    setFormOpen(true);
  };

  const openEditModal = (user: UserManagementRow) => {
    setEditingUser(user);
    setFormOpen(true);
  };

  const saveUser = (values: UserFormValues) => {
    const normalized: Omit<UserManagementRow, "id" | "createdAt" | "lastLoginAt"> = {
      username: values.username.trim(),
      realName: values.realName.trim(),
      phone: values.phone?.trim() || "-",
      email: values.email?.trim() || "-",
      status: values.status,
      roles: values.roles,
    };

    if (editingUser) {
      setUsers((current) => current.map((user) => (
        user.id === editingUser.id ? { ...user, ...normalized } : user
      )));
      void messageApi.success("用户已保存");
    } else {
      const createdUser: UserManagementRow = {
        id: `user-${Date.now()}`,
        ...normalized,
        createdAt: "2026-09-13 04:08",
        lastLoginAt: "-",
      };
      setUsers((current) => [createdUser, ...current]);
      void messageApi.success("用户已新增");
    }
    setFormOpen(false);
    setEditingUser(undefined);
    resetPageAndSelection();
  };

  const saveRoles = (userId: string, roles: UserRoleName[]) => {
    setUsers((current) => current.map((user) => (
      user.id === userId ? { ...user, roles } : user
    )));
    setRoleUser(undefined);
    void messageApi.success("角色已更新");
  };

  const confirmAction = (title: string, content: string, onOk: () => void) => {
    Modal.confirm({
      title,
      content,
      okText: "确认",
      cancelText: "取消",
      onOk,
    });
  };

  const resetPassword = (user: UserManagementRow) => {
    confirmAction("重置密码", `确认将 ${user.username} 的密码重置为系统默认密码？`, () => {
      void messageApi.success("密码已重置");
    });
  };

  const toggleStatus = (user: UserManagementRow) => {
    const nextStatus = user.status === "启用" ? "停用" : "启用";
    confirmAction(`${nextStatus}用户`, `确认${nextStatus} ${user.username}？`, () => {
      setUsers((current) => current.map((item) => (
        item.id === user.id ? { ...item, status: nextStatus } : item
      )));
      void messageApi.success("状态已更新");
    });
  };

  const deleteUser = (user: UserManagementRow) => {
    confirmAction("删除用户", `确认删除 ${user.username}？删除后不可恢复。`, () => {
      setUsers((current) => current.filter((item) => item.id !== user.id));
      setSelectedRowKeys((current) => current.filter((key) => key !== user.id));
      void messageApi.success("用户已删除");
    });
  };

  return (
    <PageShell page={page}>
      {messageContextHolder}
      <div className="settings-management user-management">
        <section className="settings-management__page-card">
          <div className="settings-management__page-head">
            <div>
              <Typography.Title level={4}>用户管理</Typography.Title>
              <Typography.Text type="secondary">
                仅保留必要账号管理：新增用户、设置角色、重置密码、停用/启用、删除。
              </Typography.Text>
            </div>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>新增用户</Button>
          </div>
          <UserManagementToolbar filters={filters} onChange={updateFilters} onReset={resetFilters} />
          <UserManagementTable
            rows={filteredUsers}
            columnWidths={columnWidths}
            currentPage={currentPage}
            pageSize={pageSize}
            selectedRowKeys={selectedRowKeys}
            onColumnWidthChange={(key, width) => setColumnWidths((current) => ({ ...current, [key]: width }))}
            onCurrentPageChange={setCurrentPage}
            onPageSizeChange={(nextPageSize) => {
              setPageSize(normalizeReportTablePageSize(nextPageSize));
              resetPageAndSelection();
            }}
            onSelectionChange={setSelectedRowKeys}
            onEdit={openEditModal}
            onSetRole={setRoleUser}
            onResetPassword={resetPassword}
            onToggleStatus={toggleStatus}
            onDelete={deleteUser}
            onBulkDisable={() => void messageApi.info("批量停用接口待接入")}
          />
        </section>
      </div>
      <UserFormModal
        open={formOpen}
        editingUser={editingUser}
        onCancel={() => {
          setFormOpen(false);
          setEditingUser(undefined);
        }}
        onSubmit={saveUser}
      />
      <UserRoleModal user={roleUser} onCancel={() => setRoleUser(undefined)} onSubmit={saveRoles} />
    </PageShell>
  );
}

export default UserManagementPage;
