import { PlusOutlined } from "@ant-design/icons";
import { Alert, Button, Input, Modal, Typography, message } from "antd";
import { useCallback, useEffect, useMemo, useState, type Key } from "react";
import PageShell from "@/components/page/PageShell";
import {
  REPORT_TABLE_DEFAULT_PAGE_SIZE,
  normalizeReportTablePageSize,
} from "@/components/report-table/pagination";
import type { NavigationPage } from "@/config/navigation";
import { fetchCurrentUser } from "@/pages/auth/authApi";
import type { AuthUser } from "@/pages/auth/authTypes";
import UserFormModal from "@/pages/settings/components/UserFormModal";
import UserManagementTable from "@/pages/settings/components/UserManagementTable";
import UserManagementToolbar from "@/pages/settings/components/UserManagementToolbar";
import UserRoleModal from "@/pages/settings/components/UserRoleModal";
import {
  createUser,
  deleteUserPermanently,
  loadUserManagementData,
  resetUserPassword,
  updateUser,
  updateUserRoles,
  updateUserStatus,
} from "@/pages/settings/userManagementApi";
import {
  defaultUserColumnWidths,
  type UserFormValues,
  type UserManagementFilters,
  type UserManagementRow,
  type UserRoleName,
  type UserRoleOption,
} from "@/pages/settings/userManagementTypes";
import { hasPermission } from "@/shared/permissions/mockAccess";
import "@/pages/settings/UserManagementPage.css";

const createInitialFilters = (): UserManagementFilters => ({ keyword: "" });

interface UserManagementPageProps {
  page: NavigationPage;
}

function permitted(user: AuthUser | undefined, permission: string, legacy?: string) {
  return hasPermission(user?.permissions, permission)
    || Boolean(legacy && hasPermission(user?.permissions, legacy));
}

function UserManagementPage({ page }: UserManagementPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [users, setUsers] = useState<UserManagementRow[]>([]);
  const [roleOptions, setRoleOptions] = useState<UserRoleOption[]>([]);
  const [currentUser, setCurrentUser] = useState<AuthUser>();
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string>();
  const [filters, setFilters] = useState(createInitialFilters);
  const [columnWidths, setColumnWidths] = useState(defaultUserColumnWidths);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserManagementRow>();
  const [roleUser, setRoleUser] = useState<UserManagementRow>();

  const canCreate = permitted(
    currentUser,
    "action:settings:user-management:create",
    "settings:users:write",
  );
  const canEdit = permitted(
    currentUser,
    "action:settings:user-management:edit",
    "settings:users:write",
  );
  const canAssignRole = permitted(
    currentUser,
    "action:settings:user-management:assign-role",
    "settings:users:write",
  );
  const canResetPassword = permitted(
    currentUser,
    "action:settings:user-management:reset-password",
    "settings:users:write",
  );
  const canEnableDisable = permitted(
    currentUser,
    "action:settings:user-management:enable-disable",
    "settings:users:write",
  );
  const canViewPhone = permitted(
    currentUser,
    "field:settings:user-management:phone",
  );
  const canViewEmail = permitted(
    currentUser,
    "field:settings:user-management:email",
  );
  const canHardDelete = Boolean(currentUser?.isSuperAdmin);

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const refreshUsers = useCallback(async () => {
    setLoading(true);
    try {
      const [data, authenticatedUser] = await Promise.all([
        loadUserManagementData(),
        fetchCurrentUser(),
      ]);
      if (!authenticatedUser) throw new Error("missing current user");
      setLoadError(undefined);
      setUsers(data.users);
      setRoleOptions(data.roleOptions);
      setCurrentUser(authenticatedUser);
    } catch {
      setUsers([]);
      setRoleOptions([]);
      setLoadError("用户或可分配角色加载失败；页面不会展示本地假数据。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshUsers();
    }, 0);

    return () => window.clearTimeout(timer);
  }, [refreshUsers]);

  const filteredUsers = useMemo(() => {
    const keyword = filters.keyword.trim().toLocaleLowerCase();
    return users.filter((user) => (
      (!filters.status || user.status === filters.status)
      && (!filters.role || user.roles.includes(filters.role))
      && (!keyword
        || user.username.toLocaleLowerCase().includes(keyword)
        || user.realName.toLocaleLowerCase().includes(keyword)
        || (canViewPhone && user.phone.toLocaleLowerCase().includes(keyword))
        || (canViewEmail && user.email.toLocaleLowerCase().includes(keyword))
        || (user.feishuName ?? "").toLocaleLowerCase().includes(keyword)
        || (user.feishuUserId ?? "").toLocaleLowerCase().includes(keyword))
    ));
  }, [canViewEmail, canViewPhone, filters, users]);

  const currentUserId = currentUser ? String(currentUser.id) : undefined;
  const currentUserIsSuperAdmin = Boolean(currentUser?.isSuperAdmin);

  const isProtectedTarget = (user: UserManagementRow) => (
    user.isSuperAdmin && !currentUserIsSuperAdmin
  );

  const updateFilters = (nextFilters: UserManagementFilters) => {
    setFilters(nextFilters);
    resetPageAndSelection();
  };

  const resetFilters = () => {
    setFilters(createInitialFilters());
    resetPageAndSelection();
  };

  const openCreateModal = () => {
    if (!canCreate || !canAssignRole) return;
    setEditingUser(undefined);
    setFormOpen(true);
  };

  const openEditModal = (user: UserManagementRow) => {
    if (!canEdit || isProtectedTarget(user)) return;
    setEditingUser(user);
    setFormOpen(true);
  };

  const saveUser = async (values: UserFormValues) => {
    try {
      if (editingUser) {
        if (!canEdit || isProtectedTarget(editingUser)) return;
        await updateUser(editingUser.id, values);
        if (canAssignRole && !editingUser.isSuperAdmin) {
          await updateUserRoles(editingUser.id, values.roles, roleOptions);
        }
        void messageApi.success("用户已保存");
      } else {
        if (!canCreate || !canAssignRole) return;
        await createUser(values, roleOptions);
        void messageApi.success("用户已新增");
      }

      setFormOpen(false);
      setEditingUser(undefined);
      resetPageAndSelection();
      await refreshUsers();
    } catch {
      void messageApi.error("保存失败，请检查角色、账号或权限配置");
    }
  };

  const saveRoles = async (userId: string, roles: UserRoleName[]) => {
    const target = users.find((user) => user.id === userId);
    if (!target || !canAssignRole || target.isSuperAdmin || isProtectedTarget(target)) return;

    try {
      await updateUserRoles(userId, roles, roleOptions);
      setRoleUser(undefined);
      await refreshUsers();
      void messageApi.success("角色已更新");
    } catch {
      void messageApi.error("角色更新失败");
    }
  };

  const confirmAction = (title: string, content: string, onOk: () => Promise<void>) => {
    Modal.confirm({
      title,
      content,
      okText: "确认",
      cancelText: "取消",
      onOk,
    });
  };

  const resetPassword = (user: UserManagementRow) => {
    if (!canResetPassword || isProtectedTarget(user)) return;
    let nextPassword = "";

    Modal.confirm({
      title: "重置密码",
      content: (
        <div>
          <Typography.Paragraph>
            请输入 {user.username} 的新密码，密码至少 8 位。重置后旧会话立即失效。
          </Typography.Paragraph>
          <Input.Password
            autoComplete="new-password"
            placeholder="请输入新密码"
            onChange={(event) => {
              nextPassword = event.target.value.trim();
            }}
          />
        </div>
      ),
      okText: "确认重置",
      cancelText: "取消",
      onOk: async () => {
        if (nextPassword.length < 8) {
          void messageApi.error("密码至少 8 位");
          return Promise.reject(new Error("password too short"));
        }
        await resetUserPassword(user.id, nextPassword);
        void messageApi.success("密码已重置，旧会话已撤销");
      },
    });
  };

  const toggleStatus = (user: UserManagementRow) => {
    if (
      !canEnableDisable
      || user.id === currentUserId
      || user.isSuperAdmin
      || isProtectedTarget(user)
    ) return;
    const nextStatus = user.status === "启用" ? "停用" : "启用";
    confirmAction(`${nextStatus}用户`, `确认${nextStatus} ${user.username}？`, async () => {
      await updateUserStatus(user.id, nextStatus === "启用");
      await refreshUsers();
      void messageApi.success("状态已更新");
    });
  };

  const deleteUser = (user: UserManagementRow) => {
    if (!canHardDelete || user.id === currentUserId || user.isSuperAdmin) return;
    confirmAction(
      "永久删除用户",
      `确认永久删除 ${user.username}？此操作不可恢复。`,
      async () => {
        await deleteUserPermanently(user.id);
        setSelectedRowKeys((current) => current.filter((key) => key !== user.id));
        await refreshUsers();
        void messageApi.success("用户已删除");
      },
    );
  };

  const bulkDisable = () => {
    const targets = users.filter((user) => selectedRowKeys.includes(user.id));
    if (!canEnableDisable || targets.length === 0) {
      void messageApi.info("请先选择用户");
      return;
    }
    if (targets.some((user) => user.id === currentUserId || user.isSuperAdmin)) {
      void messageApi.warning("不能批量停用当前账号或超级管理员");
      return;
    }

    confirmAction("批量停用", `确认停用 ${targets.length} 个用户？`, async () => {
      await Promise.all(targets.map((user) => updateUserStatus(user.id, false)));
      resetPageAndSelection();
      await refreshUsers();
      void messageApi.success("批量停用完成");
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
                用户、角色选项和操作权限均来自后端真实 RBAC 数据。
              </Typography.Text>
            </div>
            {canCreate && canAssignRole && (
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
                新增用户
              </Button>
            )}
          </div>
          {loadError ? (
            <Alert type="error" showIcon message={loadError} />
          ) : (
            <>
              <UserManagementToolbar
                filters={filters}
                roleOptions={roleOptions}
                onChange={updateFilters}
                onReset={resetFilters}
              />
              <UserManagementTable
                rows={filteredUsers}
                columnWidths={columnWidths}
                currentPage={currentPage}
                pageSize={pageSize}
                selectedRowKeys={selectedRowKeys}
                currentUserId={currentUserId}
                currentUserIsSuperAdmin={currentUserIsSuperAdmin}
                canViewPhone={canViewPhone}
                canViewEmail={canViewEmail}
                canEdit={canEdit}
                canAssignRole={canAssignRole}
                canResetPassword={canResetPassword}
                canEnableDisable={canEnableDisable}
                canHardDelete={canHardDelete}
                onColumnWidthChange={(key, width) => setColumnWidths((current) => ({
                  ...current,
                  [key]: width,
                }))}
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
                onBulkDisable={bulkDisable}
              />
            </>
          )}
          {loading && <Typography.Text type="secondary">正在加载真实用户数据...</Typography.Text>}
        </section>
      </div>
      <UserFormModal
        open={formOpen}
        editingUser={editingUser}
        roleOptions={roleOptions}
        canAssignRoles={canAssignRole}
        onCancel={() => {
          setFormOpen(false);
          setEditingUser(undefined);
        }}
        onSubmit={(values) => void saveUser(values)}
      />
      <UserRoleModal
        user={roleUser}
        roleOptions={roleOptions}
        onCancel={() => setRoleUser(undefined)}
        onSubmit={(userId, roles) => void saveRoles(userId, roles)}
      />
    </PageShell>
  );
}

export default UserManagementPage;
