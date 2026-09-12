/** Role-management No-API page shell using local acceptance data only. */
import { PlusOutlined } from "@ant-design/icons";
import { Button, Typography, message } from "antd";
import { useMemo, useState } from "react";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import RoleCreateModal from "@/pages/settings/components/RoleCreateModal";
import RoleListPanel from "@/pages/settings/components/RoleListPanel";
import RolePermissionEditor from "@/pages/settings/components/RolePermissionEditor";
import {
  createDefaultRolePermissions,
  roleManagementMockData,
  rolePermissionMockData,
} from "@/pages/settings/roleManagementMockData";
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
  const [roles, setRoles] = useState<RoleManagementRow[]>(roleManagementMockData);
  const [activeRoleId, setActiveRoleId] = useState(roleManagementMockData[0].id);
  const [activeTab, setActiveTab] = useState<PermissionTabKey>("pages");
  const [roleKeyword, setRoleKeyword] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [permissionsByRole, setPermissionsByRole] = useState<Record<string, RolePermissionState>>(
    Object.fromEntries(Object.entries(rolePermissionMockData).map(([roleId, permissions]) => [
      roleId,
      clonePermissions(permissions),
    ])),
  );

  const activeRole = useMemo(
    () => roles.find((role) => role.id === activeRoleId) ?? roles[0],
    [activeRoleId, roles],
  );
  const activePermissions = permissionsByRole[activeRole.id] ?? createDefaultRolePermissions();

  const updateActivePermissions = (permissions: RolePermissionState) => {
    setPermissionsByRole((current) => ({
      ...current,
      [activeRole.id]: permissions,
    }));
  };

  const createRole = (values: RoleFormValues) => {
    const role: RoleManagementRow = {
      id: `role-${Date.now()}`,
      name: values.name.trim(),
      description: values.description?.trim() || "自定义角色",
      preset: false,
      userCount: 0,
    };
    setRoles((current) => [...current, role]);
    setPermissionsByRole((current) => ({
      ...current,
      [role.id]: createDefaultRolePermissions(),
    }));
    setActiveRoleId(role.id);
    setCreateOpen(false);
    void messageApi.success("角色已新增");
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
                必要权限配置：增加角色、页面权限、功能权限、字段权限。
              </Typography.Text>
            </div>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>增加角色</Button>
          </div>
          <div className="role-management__layout">
            <RoleListPanel
              roles={roles}
              activeRoleId={activeRole.id}
              keyword={roleKeyword}
              onKeywordChange={setRoleKeyword}
              onSelect={setActiveRoleId}
              onAdd={() => setCreateOpen(true)}
            />
            <section className="role-management__permission-shell">
              <RolePermissionEditor
                role={activeRole}
                activeTab={activeTab}
                permissions={activePermissions}
                onTabChange={setActiveTab}
                onChange={updateActivePermissions}
              />
              <div className="role-management__footer-actions">
                <Button
                  onClick={() => {
                    updateActivePermissions(createDefaultRolePermissions());
                    void messageApi.info("已恢复本次修改");
                  }}
                >
                  恢复本次修改
                </Button>
                <Button type="primary" onClick={() => void messageApi.success("权限已保存")}>保存权限</Button>
              </div>
            </section>
          </div>
        </section>
      </div>
      <RoleCreateModal open={createOpen} onCancel={() => setCreateOpen(false)} onSubmit={createRole} />
    </PageShell>
  );
}

export default RoleManagementPage;
