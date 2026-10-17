/** Safely edits user-level overrides while showing inherited and effective scope sources. */
import { Alert, Modal, Space, Tag, Typography } from "antd";
import RoleDataScopeEditor from "@/pages/settings/components/RoleDataScopeEditor";
import type { RoleDataScopeEntry } from "@/pages/settings/roleManagementTypes";
import type { UserManagementRow } from "@/pages/settings/userManagementTypes";

export interface EffectiveUserDataScopeEntry extends RoleDataScopeEntry {
  source: "user" | "role";
}

interface UserDataScopeModalProps {
  user?: UserManagementRow;
  items: RoleDataScopeEntry[];
  effectiveItems: EffectiveUserDataScopeEntry[];
  loading: boolean;
  saving: boolean;
  onChange: (items: RoleDataScopeEntry[]) => void;
  onCancel: () => void;
  onSubmit: () => void;
}

function UserDataScopeModal({
  user,
  items,
  effectiveItems,
  loading,
  saving,
  onChange,
  onCancel,
  onSubmit,
}: UserDataScopeModalProps) {
  return (
    <Modal
      title={user ? `用户数据范围：${user.username}` : "用户数据范围"}
      open={Boolean(user)}
      width={760}
      okText="保存用户范围"
      cancelText="取消"
      confirmLoading={saving}
      onCancel={onCancel}
      onOk={onSubmit}
      destroyOnHidden
    >
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <Alert
          type="warning"
          showIcon
          message="用户级同类型范围会覆盖角色范围"
          description="删除该类型的全部用户级条目后，系统才会回退使用角色范围。通配符属于高风险授权，后端仅允许超级管理员配置。"
        />
        <RoleDataScopeEditor
          items={items}
          loading={loading}
          disabled={saving}
          subjectLabel="用户"
          onChange={onChange}
        />
        <div>
          <Typography.Text strong>当前有效范围来源</Typography.Text>
          <div>
            {effectiveItems.length === 0 ? (
              <Typography.Text type="danger">无有效范围（业务数据接口将拒绝）</Typography.Text>
            ) : effectiveItems.map((item) => (
              <Tag
                key={`${item.source}-${item.scopeType}-${item.scopeValue}`}
                color={item.source === "user" ? "blue" : "default"}
              >
                {item.source === "user" ? "用户" : "角色"}：{item.scopeType}={item.scopeValue}
              </Tag>
            ))}
          </div>
        </div>
      </Space>
    </Modal>
  );
}

export default UserDataScopeModal;
