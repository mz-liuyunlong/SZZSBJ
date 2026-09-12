/** Modal for assigning one or more roles to a selected user. */
import { Checkbox, Modal, Typography } from "antd";
import { useEffect, useState } from "react";
import {
  userRoleOptions,
  type UserManagementRow,
  type UserRoleName,
} from "@/pages/settings/userManagementTypes";

interface UserRoleModalProps {
  user?: UserManagementRow;
  onCancel: () => void;
  onSubmit: (userId: string, roles: UserRoleName[]) => void;
}

function UserRoleModal({ user, onCancel, onSubmit }: UserRoleModalProps) {
  const [roles, setRoles] = useState<UserRoleName[]>([]);

  useEffect(() => {
    setRoles(user?.roles ?? []);
  }, [user]);

  return (
    <Modal
      title="设置角色"
      open={Boolean(user)}
      width={440}
      destroyOnHidden
      okText="保存角色"
      cancelText="取消"
      onCancel={onCancel}
      onOk={() => {
        if (!user || roles.length === 0) return;
        onSubmit(user.id, roles);
      }}
      okButtonProps={{ disabled: roles.length === 0 }}
    >
      <div className="user-role-modal__target">
        <Typography.Text strong>{user ? `${user.username} / ${user.realName}` : "-"}</Typography.Text>
        <Typography.Text type="secondary">为该用户勾选一个或多个角色。</Typography.Text>
      </div>
      <Checkbox.Group
        className="user-role-modal__checks"
        value={roles}
        options={userRoleOptions.map((value) => ({ value, label: value }))}
        onChange={(values) => setRoles(values as UserRoleName[])}
      />
    </Modal>
  );
}

export default UserRoleModal;
