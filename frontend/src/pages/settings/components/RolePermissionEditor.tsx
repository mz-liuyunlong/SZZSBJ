/** Edits page-specific page, action, and field permissions from the backend catalog. */
import { Checkbox, Empty, Tabs, Tag, Typography } from "antd";
import type { RolePermissionCatalog } from "@/pages/settings/roleManagementApi";
import {
  permissionTabs,
  type PermissionGroup,
  type PermissionTabKey,
  type RoleManagementRow,
  type RolePermissionState,
} from "@/pages/settings/roleManagementTypes";

interface RolePermissionEditorProps {
  role: RoleManagementRow;
  activeTab: PermissionTabKey;
  permissions: RolePermissionState;
  permissionCatalog: RolePermissionCatalog;
  onTabChange: (tab: PermissionTabKey) => void;
  onChange: (permissions: RolePermissionState) => void;
}

function PermissionGroupSection({
  group,
  values,
  permissionCatalog,
  onGroupChange,
  onItemChange,
}: {
  group: PermissionGroup;
  values: Record<string, boolean>;
  permissionCatalog: RolePermissionCatalog;
  onGroupChange: (checked: boolean) => void;
  onItemChange: (item: string, checked: boolean) => void;
}) {
  const checkedCount = group.items.filter((item) => values[item] === true).length;
  const allChecked = group.items.length > 0 && checkedCount === group.items.length;
  const partialChecked = checkedCount > 0 && checkedCount < group.items.length;

  return (
    <section className="role-management__permission-section">
      <div className="role-management__permission-section-head">
        <Typography.Text strong>{group.title}</Typography.Text>
        <Checkbox
          checked={allChecked}
          indeterminate={partialChecked}
          onChange={(event) => onGroupChange(event.target.checked)}
        >
          全选
        </Checkbox>
      </div>
      <div className="role-management__permission-grid">
        {group.items.map((item) => (
          <label
            key={item}
            className="role-management__permission-check"
            title={permissionCatalog.permissionDescriptions[item] ?? item}
          >
            <Checkbox
              checked={values[item] === true}
              onChange={(event) => onItemChange(item, event.target.checked)}
            />
            <span>{permissionCatalog.permissionLabels[item] ?? item}</span>
            {permissionCatalog.highRiskPermissions.has(item) && (
              <Tag color="red">高危</Tag>
            )}
          </label>
        ))}
      </div>
    </section>
  );
}

function RolePermissionEditor({
  role,
  activeTab,
  permissions,
  permissionCatalog,
  onTabChange,
  onChange,
}: RolePermissionEditorProps) {
  const renderBooleanGroups = (
    groups: PermissionGroup[],
    keyName: keyof RolePermissionState,
  ) => (
    <div className="role-management__permission-scroll">
      {groups.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可配置权限" />
      ) : (
        groups.map((group) => (
          <PermissionGroupSection
            key={group.title}
            group={group}
            values={permissions[keyName]}
            permissionCatalog={permissionCatalog}
            onGroupChange={(checked) => {
              const nextValues = { ...permissions[keyName] };
              group.items.forEach((item) => {
                nextValues[item] = checked;
              });
              onChange({ ...permissions, [keyName]: nextValues });
            }}
            onItemChange={(item, checked) => onChange({
              ...permissions,
              [keyName]: { ...permissions[keyName], [item]: checked },
            })}
          />
        ))
      )}
    </div>
  );

  return (
    <section className="role-management__permission-card" aria-label="权限配置">
      <div className="role-management__permission-head">
        <div>
          <Typography.Title level={5}>{role.name}</Typography.Title>
          <Typography.Text type="secondary">{role.description}</Typography.Text>
        </div>
        <Typography.Text type="secondary">版本 {role.version}</Typography.Text>
      </div>
      <Tabs
        className="role-management__permission-tabs"
        activeKey={activeTab}
        items={permissionTabs.map((item) => ({ key: item.key, label: item.label }))}
        onChange={(key) => onTabChange(key as PermissionTabKey)}
      />
      {activeTab === "pages" &&
        renderBooleanGroups(permissionCatalog.pagePermissionGroups, "pagePermissions")}
      {activeTab === "actions" &&
        renderBooleanGroups(permissionCatalog.actionPermissionGroups, "actionPermissions")}
      {activeTab === "fields" &&
        renderBooleanGroups(permissionCatalog.fieldPermissionGroups, "fieldPermissions")}
    </section>
  );
}

export default RolePermissionEditor;
