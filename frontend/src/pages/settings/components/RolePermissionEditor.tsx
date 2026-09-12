/** Edits page, action and field permissions for one selected role using local acceptance state. */
import { Checkbox, Radio, Table, Tabs, Typography, type TableColumnsType } from "antd";
import {
  actionPermissionGroups,
  fieldPermissionNames,
  pagePermissionGroups,
} from "@/pages/settings/roleManagementMockData";
import {
  fieldPermissionOptions,
  permissionTabs,
  type FieldPermissionValue,
  type PermissionGroup,
  type PermissionTabKey,
  type RoleManagementRow,
  type RolePermissionState,
} from "@/pages/settings/roleManagementTypes";

interface RolePermissionEditorProps {
  role: RoleManagementRow;
  activeTab: PermissionTabKey;
  permissions: RolePermissionState;
  onTabChange: (tab: PermissionTabKey) => void;
  onChange: (permissions: RolePermissionState) => void;
}

interface PermissionItemRow {
  key: string;
  field: string;
}

const fieldColumns = (
  permissions: RolePermissionState,
  onChange: (next: RolePermissionState) => void,
): TableColumnsType<PermissionItemRow> => [
  {
    title: "字段",
    dataIndex: "field",
    key: "field",
    width: 220,
    render: (field: string) => <Typography.Text strong>{field}</Typography.Text>,
  },
  {
    title: "权限",
    key: "permission",
    render: (_, row) => (
      <Radio.Group
        options={fieldPermissionOptions}
        value={permissions.fieldPermissions[row.field] ?? "visible"}
        onChange={(event) => onChange({
          ...permissions,
          fieldPermissions: {
            ...permissions.fieldPermissions,
            [row.field]: event.target.value as FieldPermissionValue,
          },
        })}
      />
    ),
  },
];

function PermissionGroupSection({
  group,
  values,
  onGroupChange,
  onItemChange,
}: {
  group: PermissionGroup;
  values: Record<string, boolean>;
  onGroupChange: (checked: boolean) => void;
  onItemChange: (item: string, checked: boolean) => void;
}) {
  const checkedCount = group.items.filter((item) => values[item] !== false).length;
  const allChecked = checkedCount === group.items.length;
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
          <label key={item} className="role-management__permission-check">
            <Checkbox
              checked={values[item] !== false}
              onChange={(event) => onItemChange(item, event.target.checked)}
            />
            <span>{item}</span>
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
  onTabChange,
  onChange,
}: RolePermissionEditorProps) {
  const renderBooleanGroups = (
    groups: PermissionGroup[],
    keyName: "pagePermissions" | "actionPermissions",
  ) => (
    <div className="role-management__permission-scroll">
      {groups.map((group) => (
        <PermissionGroupSection
          key={group.title}
          group={group}
          values={permissions[keyName]}
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
      ))}
    </div>
  );

  return (
    <section className="role-management__permission-card" aria-label="权限配置">
      <div className="role-management__permission-head">
        <div>
          <Typography.Title level={5}>{role.name}</Typography.Title>
          <Typography.Text type="secondary">{role.description}</Typography.Text>
        </div>
        <Typography.Text type="secondary">权限区域内部滚动</Typography.Text>
      </div>
      <Tabs
        className="role-management__permission-tabs"
        activeKey={activeTab}
        items={permissionTabs.map((item) => ({ key: item.key, label: item.label }))}
        onChange={(key) => onTabChange(key as PermissionTabKey)}
      />
      {activeTab === "pages" && renderBooleanGroups(pagePermissionGroups, "pagePermissions")}
      {activeTab === "actions" && renderBooleanGroups(actionPermissionGroups, "actionPermissions")}
      {activeTab === "fields" && (
        <div className="role-management__permission-scroll">
          <Table<PermissionItemRow>
            className="role-management__field-table"
            rowKey="key"
            pagination={false}
            size="small"
            columns={fieldColumns(permissions, onChange)}
            dataSource={fieldPermissionNames.map((field) => ({ key: field, field }))}
          />
        </div>
      )}
    </section>
  );
}

export default RolePermissionEditor;
