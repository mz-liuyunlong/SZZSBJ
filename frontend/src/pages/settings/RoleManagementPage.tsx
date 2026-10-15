import { PlusOutlined } from "@ant-design/icons";
import { Button, Typography, message } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import RoleCreateModal from "@/pages/settings/components/RoleCreateModal";
import RoleListPanel from "@/pages/settings/components/RoleListPanel";
import RolePermissionEditor from "@/pages/settings/components/RolePermissionEditor";
import {
  createRole,
  emptyRolePermissionCatalog,
  loadRoleManagementData,
  permissionKeysToState,
  saveRolePermissions,
  type RolePermissionCatalog,
} from "@/pages/settings/roleManagementApi";
import {
  type PermissionTabKey,
  type RoleFormValues,
  type RoleManagementRow,
  type RolePermissionState,
} from "@/pages/settings/roleManagementTypes";
import "@/pages/settings/RoleManagementPage.css";

interface RoleManagementPageProps {
  page: NavigationPage;
}

const clonePermissions = (permissions: RolePermissionState) => ({
  pagePermissions: { ...permissions.pagePermissions },
  actionPermissions: { ...permissions.actionPermissions },
  fieldPermissions: { ...permissions.fieldPermissions },
});

function RoleManagementPage({ page }: RoleManagementPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [roles, setRoles] = useState<RoleManagementRow[]>([]);
  const [activeRoleId, setActiveRoleId] = useState("");
  const [activeTab, setActiveTab] = useState<PermissionTabKey>("pages");
  const [roleKeyword, setRoleKeyword] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [permissionsByRole, setPermissionsByRole] = useState<Record<string, RolePermissionState>>({});
  const [permissionCatalog, setPermissionCatalog] = useState<RolePermissionCatalog>(
    emptyRolePermissionCatalog,
  );

  const refreshRoles = useCallback(async () => {
    try {
      const data = await loadRoleManagementData();
      setRoles(data.roles);
      setPermissionCatalog(data.permissionCatalog);
      setActiveRoleId((current) => current || data.roles[0]?.id || "");
      setPermissionsByRole(Object.fromEntries(
        data.roles.map((role) => [
          role.id,
          permissionKeysToState(role.permissionKeys, data.permissionCatalog),
        ]),
      ));
    } catch {
      void messageApi.error("角色数据加载失败，请确认已登录管理员账号");
    }
  }, [messageApi]);

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

  const updateActivePermissions = (permissions: RolePermissionState) => {
    if (!activeRole) return;
    setPermissionsByRole((current) => ({
      ...current,
      [activeRole.id]: clonePermissions(permissions),
    }));
  };

  const createNewRole = async (values: RoleFormValues) => {
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

  const savePermissions = async () => {
    if (!activeRole) return;

    try {
      const updatedRole = await saveRolePermissions(activeRole, activePermissions, permissionCatalog);
      setRoles((current) => current.map((role) => (
        role.id === updatedRole.id ? updatedRole : role
      )));
      setPermissionsByRole((current) => ({
        ...current,
        [updatedRole.id]: permissionKeysToState(updatedRole.permissionKeys, permissionCatalog),
      }));
      void messageApi.success("权限已保存");
    } catch {
      void messageApi.error("权限保存失败");
    }
  };

  return (
    <PageShell page={page}>
      {messageContextHolder}
      <div className="settings-management role-management">
        <section className="settings-management__page-card">
          <div className="settings-management__page-head">
            <div>
              <Typography.Title level={4}>角色管理</Typography.Title>
              <Typography.Text type="secondary">
                真实角色权限配置：增加角色、页面权限、功能权限、字段权限。
              </Typography.Text>
            </div>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              增加角色
            </Button>
          </div>
          <div className="role-management__layout">
            <RoleListPanel
              roles={roles}
              activeRoleId={activeRole?.id ?? ""}
              keyword={roleKeyword}
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
                  onTabChange={setActiveTab}
                  onChange={updateActivePermissions}
                />
              ) : (
                <Typography.Text type="secondary">暂无角色数据</Typography.Text>
              )}
              <div className="role-management__footer-actions">
                <Button
                  onClick={() => {
                    if (!activeRole) return;
                    updateActivePermissions(permissionKeysToState(activeRole.permissionKeys, permissionCatalog));
                    void messageApi.info("已恢复本次修改");
                  }}
                >
                  恢复本次修改
                </Button>
                <Button type="primary" onClick={() => void savePermissions()}>
                  保存权限
                </Button>
              </div>
            </section>
          </div>
        </section>
      </div>
      <RoleCreateModal
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onSubmit={(values) => void createNewRole(values)}
      />
    </PageShell>
  );
}

export default RoleManagementPage;
