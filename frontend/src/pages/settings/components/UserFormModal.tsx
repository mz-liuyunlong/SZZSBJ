/** Modal for creating and editing local no-API users. */
import { Form, Input, Modal, Select } from "antd";
import { useEffect } from "react";
import {
  userRoleOptions,
  userStatusOptions,
  type UserFormValues,
  type UserManagementRow,
} from "@/pages/settings/userManagementTypes";

interface UserFormModalProps {
  open: boolean;
  editingUser?: UserManagementRow;
  onCancel: () => void;
  onSubmit: (values: UserFormValues) => void;
}

const initialValues: UserFormValues = {
  username: "",
  realName: "",
  phone: "",
  email: "",
  status: "启用",
  roles: [],
};

function UserFormModal({ open, editingUser, onCancel, onSubmit }: UserFormModalProps) {
  const [form] = Form.useForm<UserFormValues>();

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue(editingUser ? {
      username: editingUser.username,
      realName: editingUser.realName,
      phone: editingUser.phone === "-" ? "" : editingUser.phone,
      email: editingUser.email === "-" ? "" : editingUser.email,
      status: editingUser.status,
      roles: editingUser.roles,
    } : initialValues);
  }, [editingUser, form, open]);

  return (
    <Modal
      title={editingUser ? "编辑用户" : "新增用户"}
      open={open}
      width={620}
      destroyOnHidden
      okText="保存"
      cancelText="取消"
      className="user-management-modal"
      onCancel={onCancel}
      onOk={() => void form.validateFields().then(onSubmit)}
    >
      <Form form={form} layout="vertical" requiredMark>
        <Form.Item
          name="username"
          label="用户名"
          rules={[{ required: true, message: "请输入用户名" }]}
        >
          <Input placeholder="请输入用户名" />
        </Form.Item>
        <Form.Item
          name="realName"
          label="真实姓名"
          rules={[{ required: true, message: "请输入真实姓名" }]}
        >
          <Input placeholder="请输入真实姓名" />
        </Form.Item>
        <div className="user-management-modal__grid">
          <Form.Item name="phone" label="手机号">
            <Input placeholder="请输入手机号" />
          </Form.Item>
          <Form.Item name="email" label="邮箱">
            <Input placeholder="请输入邮箱" />
          </Form.Item>
        </div>
        <Form.Item
          name="status"
          label="状态"
          rules={[{ required: true, message: "请选择状态" }]}
        >
          <Select options={userStatusOptions.map((value) => ({ value, label: value }))} />
        </Form.Item>
        <Form.Item
          name="roles"
          label="角色"
          rules={[{ required: true, message: "至少选择一个角色" }]}
        >
          <Select
            mode="multiple"
            placeholder="请选择角色"
            options={userRoleOptions.map((value) => ({ value, label: value }))}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default UserFormModal;
