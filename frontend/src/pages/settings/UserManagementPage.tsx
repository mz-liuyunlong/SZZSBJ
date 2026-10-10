import { PlusOutlined } from "@ant-design/icons";
import { Button, Input, Modal, Typography, message } from "antd";
import { useCallback, useEffect, useMemo, useState, type Key } from "react";
import PageShell from "@/components/page/PageShell";
import {
  REPORT_TABLE_DEFAULT_PAGE_SIZE,
  normalizeReportTablePageSize,
} from "@/components/report-table/pagination";
import type { NavigationPage } from "@/config/navigation";
import UserFormModal from "@/pages/settings/components/UserFormModal";
import UserManagementTable from "@/pages/settings/components/UserManagementTable";
import UserManagementToolbar from "@/pages/settings/components/UserManagementToolbar";
import UserRoleModal from "@/pages/settings/components/UserRoleModal";
import {
  createUser,
  deactivateUser,
  loadUserManagementData,
  resetUserPassword,
  updateUser,
  updateUserStatus,
} from "@/pages/settings/userManagementApi";
import {
  defaultUserColumnWidths,
  fallbackUserRoleOptions,
  type UserFormValues,
  type UserManagementFilters,
  type UserManagementRow,
  type UserRoleName,
  type UserRoleOption,
} from "@/pages/settings/userManagementTypes";
import "@/pages/settings/UserManagementPage.css";

const createInitialFilters = (): UserManagementFilters => ({ keyword: "" });

interface UserManagementPageProps {
  page: NavigationPage;
}

function UserManagementPage({ page }: UserManagementPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [users, setUsers] = useState<UserManagementRow[]>([]);
  const [roleOptions, setRoleOptions] = useState<UserRoleOption[]>(fallbackUserRoleOptions);
  const [loading, setLoading] = useState(false);
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

  const refreshUsers = useCallback(async () => {
    setLoading(true);
    try {
      const data = await loadUserManagementData();
      setUsers(data.users);
      setRoleOptions(data.roleOptions);
    } catch {
      void messageApi.error("用户/角色数据加载失败，请确认已登录管理员账号");
    } finally {
      setLoading(false);
    }
  }, [messageApi]);

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
        || user.phone.toLocaleLowerCase().includes(keyword)
        || (user.feishuName ?? "").toLocaleLowerCase().includes(keyword)
        || (user.feishuUserId ?? "").toLocaleLowerCase().includes(keyword))
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

  const saveUser = async (values: UserFormValues) => {
    try {
      if (editingUser) {
        await updateUser(editingUser.id, values, roleOptions);
        void messageApi.success("用户已保存");
      } else {
        await createUser(values, roleOptions);
        void messageApi.success("用户已新增");
      }

      setFormOpen(false);
      setEditingUser(undefined);
      resetPageAndSelection();
      await refreshUsers();
    } catch {
      void messageApi.error("保存失败，请检查账号是否重复或权限是否不足");
    }
  };

  const saveRoles = async (userId: string, roles: UserRoleName[]) => {
    const target = users.find((user) => user.id === userId);
    if (!target) return;

    try {
      await updateUser(userId, {
        username: target.username,
        realName: target.realName,
        phone: target.phone === "-" ? "" : target.phone,
        email: target.email === "-" ? "" : target.email,
        status: target.status,
        roles,
        feishuName: target.feishuName,
        feishuOpenId: target.feishuOpenId,
        feishuUserId: target.feishuUserId,
        feishuUnionId: target.feishuUnionId,
        feishuEmployeeId: target.feishuEmployeeId,
        feishuDepartmentIds: target.feishuDepartmentIds,
      }, roleOptions);
      setRoleUser(undefined);
      await refreshUsers();
      void messageApi.success("角色已更新");
    } catch {
      void messageApi.error("角色更新失败");
    }
  };

  const confirmAction = (title: string, content: string, onOk: () => void | Promise<void>) => {
    Modal.confirm({
      title,
      content,
      okText: "确认",
      cancelText: "取消",
      onOk,
    });
  };

  const resetPassword = (user: UserManagementRow) => {
    let nextPassword = "";

    Modal.confirm({
      title: "重置密码",
      content: (
        <div>
          <Typography.Paragraph>
            请输入 {user.username} 的新密码，密码至少 8 位。
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
        void messageApi.success("密码已重置");
      },
    });
  };

  const toggleStatus = (user: UserManagementRow) => {
    const nextStatus = user.status === "启用" ? "停用" : "启用";
    confirmAction(`${nextStatus}用户`, `确认${nextStatus} ${user.username}？`, async () => {
      await updateUserStatus(user.id, nextStatus === "启用");
      await refreshUsers();
      void messageApi.success("状态已更新");
    });
  };

  const deleteUser = (user: UserManagementRow) => {
    confirmAction("删除用户", `确认删除 ${user.username}？V1 将执行停用处理。`, async () => {
      await deactivateUser(user.id);
      setSelectedRowKeys((current) => current.filter((key) => key !== user.id));
      await refreshUsers();
      void messageApi.success("用户已停用");
    });
  };

  const bulkDisable = () => {
    if (selectedRowKeys.length === 0) {
      void messageApi.info("请先选择用户");
      return;
    }

    confirmAction("批量停用", `确认停用 ${selectedRowKeys.length} 个用户？`, async () => {
      await Promise.all(selectedRowKeys.map((key) => updateUserStatus(String(key), false)));
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
                真实账号管理：新增用户、设置角色、重置密码、停用/启用、删除。
              </Typography.Text>
            </div>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
              新增用户
            </Button>
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
            onBulkDisable={bulkDisable}
          />
          {loading && <Typography.Text type="secondary">正在加载真实用户数据...</Typography.Text>}
        </section>
      </div>
      <UserFormModal
        open={formOpen}
        editingUser={editingUser}
        roleOptions={roleOptions}
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
