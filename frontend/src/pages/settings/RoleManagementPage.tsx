import { PlusOutlined } from "@ant-design/icons";
import { Alert, Button, Typography, message } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { BackendRequestError } from "@/api/backendApi";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import { fetchCurrentUser } from "@/pages/auth/authApi";
import type { AuthUser } from "@/pages/auth/authTypes";
import RoleCreateModal from "@/pages/settings/components/RoleCreateModal";
import RoleListPanel from "@/pages/settings/components/RoleListPanel";
import RolePermissionEditor from "@/pages/settings/components/RolePermissionEditor";
import {
  createRole,
  emptyRolePermissionCatalog,
  loadRoleAuditEvents,
  loadRoleDataScopes,
  loadRoleManagementData,
  permissionKeysToState,
  saveRoleDataScopes,
  saveRolePermissions,
  type RolePermissionCatalog,
} from "@/pages/settings/roleManagementApi";
import {
  type PermissionTabKey,
  type RoleAuditEvent,
  type RoleDataScopeEntry,
  type RoleFormValues,
  type RoleManagementRow,
  type RolePermissionState,
} from "@/pages/settings/roleManagementTypes";
import { hasPermission } from "@/shared/permissions/mockAccess";
import "@/pages/settings/RoleManagementPage.css";

interface RoleManagementPageProps {
  page: NavigationPage;
}

const clonePermissions = (permissions: RolePermissionState) => ({
  pagePermissions: { ...permissions.pagePermissions },
  actionPermissions: { ...permissions.actionPermissions },
  fieldPermissions: { ...permissions.fieldPermissions },
});

const cloneDataScopes = (items: RoleDataScopeEntry[]) => items.map((item) => ({ ...item }));

function permitted(user: AuthUser | undefined, permission: string, legacy?: string) {
  return hasPermission(user?.permissions, permission)
    || Boolean(legacy && hasPermission(user?.permissions, legacy));
}

function RoleManagementPage({ page }: RoleManagementPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [roles, setRoles] = useState<RoleManagementRow[]>([]);
  const [currentUser, setCurrentUser] = useState<AuthUser>();
  const [activeRoleId, setActiveRoleId] = useState("");
  const [activeTab, setActiveTab] = useState<PermissionTabKey>("pages");
  const [roleKeyword, setRoleKeyword] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [loadError, setLoadError] = useState<string>();
  const [permissionsByRole, setPermissionsByRole] = useState<Record<string, RolePermissionState>>({});
  const [permissionCatalog, setPermissionCatalog] = useState<RolePermissionCatalog>(
    emptyRolePermissionCatalog,
  );
  const [dataScopesByRole, setDataScopesByRole] = useState<Record<string, RoleDataScopeEntry[]>>({});
  const [savedDataScopesByRole, setSavedDataScopesByRole] = useState<Record<string, RoleDataScopeEntry[]>>({});
  const [dataScopeLoading, setDataScopeLoading] = useState(false);
  const [auditEvents, setAuditEvents] = useState<RoleAuditEvent[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);

  const canCreateRole = permitted(
    currentUser,
    "action:settings:role-management:create",
    "settings:roles:write",
  );
  const canConfigurePermissions = permitted(
    currentUser,
    "action:settings:role-management:configure-permissions",
    "settings:roles:write",
  );
  const canConfigureDataScope = permitted(
    currentUser,
    "action:settings:role-management:configure-data-scope",
  );
  const canViewAudit = permitted(
    currentUser,
    "action:settings:role-management:view-audit",
  );

  const refreshRoles = useCallback(async () => {
    try {
      const [data, authenticatedUser] = await Promise.all([
        loadRoleManagementData(),
        fetchCurrentUser(),
      ]);
      if (!authenticatedUser) throw new Error("missing current user");
      setLoadError(undefined);
      setCurrentUser(authenticatedUser);
      setRoles(data.roles);
      setPermissionCatalog(data.permissionCatalog);
      setActiveRoleId((current) => (
        data.roles.some((role) => role.id === current)
          ? current
          : data.roles[0]?.id || ""
      ));
      setPermissionsByRole(Object.fromEntries(
        data.roles.map((role) => [
          role.id,
          permissionKeysToState(role.permissionKeys, data.permissionCatalog),
        ]),
      ));
    } catch {
      setRoles([]);
      setCurrentUser(undefined);
      setActiveRoleId("");
      setPermissionsByRole({});
      setPermissionCatalog(emptyRolePermissionCatalog);
      setLoadError("角色与权限目录加载失败；页面不会展示本地假数据。");
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshRoles();
    }, 0);

    return () => window.clearTimeout(timer);
  }, [refreshRoles]);

  const activeRole = useMemo(
    () => roles.find((role) => role.id === activeRoleId) ?? roles[0],
    [activeRoleId, roles],
  );
  const activePermissions = activeRole
    ? permissionsByRole[activeRole.id] ??
      permissionKeysToState(activeRole.permissionKeys, permissionCatalog)
    : permissionKeysToState([], permissionCatalog);
  const activeDataScopes = activeRole
    ? dataScopesByRole[activeRole.id] ?? []
    : [];
  const selectedRoleAuditEvents = useMemo(() => (
    activeRole
      ? auditEvents.filter((event) => (
          event.targetType === "role" && event.targetKey === activeRole.roleKey
        ))
      : []
  ), [activeRole, auditEvents]);
  const protectedSystemRole = activeRole?.roleKey === "admin" && !currentUser?.isSuperAdmin;
  const mayConfigurePermissions = canConfigurePermissions && !protectedSystemRole;
  const mayConfigureDataScope = canConfigureDataScope && !protectedSystemRole;

  const refreshDataScopes = useCallback(async (role: RoleManagementRow) => {
    setDataScopeLoading(true);
    try {
      const items = await loadRoleDataScopes(role.roleKey);
      setDataScopesByRole((current) => ({
        ...current,
        [role.id]: cloneDataScopes(items),
      }));
      setSavedDataScopesByRole((current) => ({
        ...current,
        [role.id]: cloneDataScopes(items),
      }));
    } catch {
      void messageApi.error("数据权限加载失败");
    } finally {
      setDataScopeLoading(false);
    }
  }, [messageApi]);

  const refreshAuditEvents = useCallback(async () => {
    if (!canViewAudit) return;
    setAuditLoading(true);
    try {
      setAuditEvents(await loadRoleAuditEvents());
    } catch {
      void messageApi.error("权限变更记录加载失败");
    } finally {
      setAuditLoading(false);
    }
  }, [canViewAudit, messageApi]);

  useEffect(() => {
    if (!activeRole) return;

    const shouldLoadDataScopes =
      activeTab === "dataScopes"
      && dataScopesByRole[activeRole.id] === undefined;
    const shouldLoadAudit =
      activeTab === "audit"
      && canViewAudit
      && auditEvents.length === 0;

    if (!shouldLoadDataScopes && !shouldLoadAudit) return;

    const role = activeRole;
    const timer = window.setTimeout(() => {
      if (shouldLoadDataScopes) {
        void refreshDataScopes(role);
      }
      if (shouldLoadAudit) {
        void refreshAuditEvents();
      }
    }, 0);

    return () => window.clearTimeout(timer);
  }, [
    activeRole,
    activeTab,
    auditEvents.length,
    canViewAudit,
    dataScopesByRole,
    refreshAuditEvents,
    refreshDataScopes,
  ]);

  const updateActivePermissions = (permissions: RolePermissionState) => {
    if (!activeRole || !mayConfigurePermissions) return;
    setPermissionsByRole((current) => ({
      ...current,
      [activeRole.id]: clonePermissions(permissions),
    }));
  };

  const updateActiveDataScopes = (items: RoleDataScopeEntry[]) => {
    if (!activeRole || !mayConfigureDataScope) return;
    setDataScopesByRole((current) => ({
      ...current,
      [activeRole.id]: cloneDataScopes(items),
    }));
  };

  const createNewRole = async (values: RoleFormValues) => {
    if (!canCreateRole) return;
    try {
      const role = await createRole(values);
      await refreshRoles();
      setActiveRoleId(role.id);
      setCreateOpen(false);
      void messageApi.success("角色已新增");
    } catch {
      void messageApi.error("角色新增失败，可能是名称重复或权限不足");
    }
  };

  const saveCurrentTab = async () => {
    if (!activeRole) return;

    try {
      if (activeTab === "dataScopes") {
        if (!mayConfigureDataScope) return;
        const items = await saveRoleDataScopes(activeRole.roleKey, activeDataScopes);
        setDataScopesByRole((current) => ({
          ...current,
          [activeRole.id]: cloneDataScopes(items),
        }));
        setSavedDataScopesByRole((current) => ({
          ...current,
          [activeRole.id]: cloneDataScopes(items),
        }));
        setAuditEvents([]);
        void messageApi.success("数据权限已保存");
        return;
      }

      if (activeTab === "audit" || !mayConfigurePermissions) return;
      const updatedRole = await saveRolePermissions(
        activeRole,
        activePermissions,
        permissionCatalog,
      );
      setRoles((current) => current.map((role) => (
        role.id === updatedRole.id ? updatedRole : role
      )));
      setPermissionsByRole((current) => ({
        ...current,
        [updatedRole.id]: permissionKeysToState(
          updatedRole.permissionKeys,
          permissionCatalog,
        ),
      }));
      setAuditEvents([]);
      void messageApi.success("权限已保存");
    } catch (error) {
      if (error instanceof BackendRequestError && error.status === 409) {
        void messageApi.error("角色已被其他管理员修改，请刷新后重试");
        await refreshRoles();
        return;
      }
      void messageApi.error("权限保存失败，请刷新后重试");
    }
  };

  const restoreCurrentTab = () => {
    if (!activeRole) return;
    if (activeTab === "dataScopes") {
      const savedItems = savedDataScopesByRole[activeRole.id] ?? [];
      setDataScopesByRole((current) => ({
        ...current,
        [activeRole.id]: cloneDataScopes(savedItems),
      }));
      void messageApi.info("已恢复本次数据范围修改");
      return;
    }
    if (activeTab === "audit") return;
    setPermissionsByRole((current) => ({
      ...current,
      [activeRole.id]: permissionKeysToState(
        activeRole.permissionKeys,
        permissionCatalog,
      ),
    }));
    void messageApi.info("已恢复本次权限修改");
  };

  const currentTabEditable = activeTab === "dataScopes"
    ? mayConfigureDataScope
    : activeTab !== "audit" && mayConfigurePermissions;

  return (
    <PageShell page={page}>
      {messageContextHolder}
      <div className="settings-management role-management">
        <section className="settings-management__page-card">
          <div className="settings-management__page-head">
            <div>
              <Typography.Title level={4}>角色管理</Typography.Title>
              <Typography.Text type="secondary">
                页面、功能、字段和数据权限均由后端 RBAC 目录动态驱动。
              </Typography.Text>
            </div>
            {canCreateRole && (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setCreateOpen(true)}
              >
                增加角色
              </Button>
            )}
          </div>
          {loadError ? (
            <Alert type="error" showIcon message={loadError} />
          ) : (
            <div className="role-management__layout">
              <RoleListPanel
                roles={roles}
                activeRoleId={activeRole?.id ?? ""}
                keyword={roleKeyword}
                canAdd={canCreateRole}
                onKeywordChange={setRoleKeyword}
                onSelect={setActiveRoleId}
                onAdd={() => setCreateOpen(true)}
              />
              <section className="role-management__permission-shell">
                {activeRole ? (
                  <RolePermissionEditor
                    role={activeRole}
                    activeTab={activeTab}
                    permissions={activePermissions}
                    permissionCatalog={permissionCatalog}
                    dataScopes={activeDataScopes}
                    auditEvents={selectedRoleAuditEvents}
                    dataScopeLoading={dataScopeLoading}
                    auditLoading={auditLoading}
                    canConfigurePermissions={mayConfigurePermissions}
                    canConfigureDataScope={mayConfigureDataScope}
                    canViewAudit={canViewAudit}
                    onTabChange={setActiveTab}
                    onChange={updateActivePermissions}
                    onDataScopeChange={updateActiveDataScopes}
                  />
                ) : (
                  <Typography.Text type="secondary">暂无真实角色数据</Typography.Text>
                )}
                {activeTab !== "audit" && (
                  <div className="role-management__footer-actions">
                    <Button disabled={!currentTabEditable} onClick={restoreCurrentTab}>
                      恢复本次修改
                    </Button>
                    <Button
                      type="primary"
                      disabled={!currentTabEditable}
                      onClick={() => void saveCurrentTab()}
                    >
                      {activeTab === "dataScopes" ? "保存数据权限" : "保存权限"}
                    </Button>
                  </div>
                )}
              </section>
            </div>
          )}
        </section>
      </div>
      <RoleCreateModal
        open={createOpen && canCreateRole}
        onCancel={() => setCreateOpen(false)}
        onSubmit={(values) => void createNewRole(values)}
      />
    </PageShell>
  );
}

export default RoleManagementPage;
