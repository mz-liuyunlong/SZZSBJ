import { Alert, Button, Form, Input, Modal, Select, Space, Typography } from "antd";
import { useEffect, useState } from "react";
import { searchFeishuUsers } from "@/pages/settings/userManagementApi";
import {
  userStatusOptions,
  type FeishuDirectoryUser,
  type UserFormValues,
  type UserManagementRow,
  type UserRoleOption,
} from "@/pages/settings/userManagementTypes";

interface UserFormModalProps {
  open: boolean;
  editingUser?: UserManagementRow;
  roleOptions: UserRoleOption[];
  onCancel: () => void;
  onSubmit: (values: UserFormValues) => void;
}

const initialValues: UserFormValues = {
  username: "",
  realName: "",
  phone: "",
  email: "",
  password: "",
  status: "启用",
  roles: [],
  feishuName: "",
  feishuOpenId: "",
  feishuUserId: "",
  feishuUnionId: "",
  feishuEmployeeId: "",
  feishuDepartmentIds: [],
};

function UserFormModal({
  open,
  editingUser,
  roleOptions,
  onCancel,
  onSubmit,
}: UserFormModalProps) {
  const [form] = Form.useForm<UserFormValues>();
  const [feishuSearchLoading, setFeishuSearchLoading] = useState(false);
  const [feishuSearchNotice, setFeishuSearchNotice] = useState<string>();
  const [feishuSearchNoticeType, setFeishuSearchNoticeType] = useState<"success" | "info" | "warning">("info");

  const boundFeishuOpenId = Form.useWatch("feishuOpenId", form);
  const boundFeishuName = Form.useWatch("feishuName", form);
  const boundFeishuUserId = Form.useWatch("feishuUserId", form);

  useEffect(() => {
    if (!open) return;

    form.setFieldsValue(editingUser ? {
      username: editingUser.username,
      realName: editingUser.realName,
      phone: editingUser.phone === "-" ? "" : editingUser.phone,
      email: editingUser.email === "-" ? "" : editingUser.email,
      password: "",
      status: editingUser.status,
      roles: editingUser.roles,
      feishuName: editingUser.feishuName ?? "",
      feishuOpenId: editingUser.feishuOpenId ?? "",
      feishuUserId: editingUser.feishuUserId ?? "",
      feishuUnionId: editingUser.feishuUnionId ?? "",
      feishuEmployeeId: editingUser.feishuEmployeeId ?? "",
      feishuDepartmentIds: editingUser.feishuDepartmentIds ?? [],
    } : initialValues);
  }, [editingUser, form, open]);

  const applyFeishuUser = (user: FeishuDirectoryUser) => {
    form.setFieldsValue({
      realName: user.name,
      feishuName: user.name,
      feishuOpenId: user.openId,
      feishuUserId: user.userId ?? "",
      feishuUnionId: user.unionId ?? "",
      feishuEmployeeId: user.employeeId ?? "",
      feishuDepartmentIds: user.departmentIds,
    });
  };

  const handleSearchFeishuUser = async () => {
    const realName = String(form.getFieldValue("realName") ?? "").trim();

    if (!realName) {
      setFeishuSearchNoticeType("warning");
      setFeishuSearchNotice("请先输入真实姓名，再搜索飞书员工。");
      return;
    }

    setFeishuSearchLoading(true);
    setFeishuSearchNotice(undefined);

    try {
      const result = await searchFeishuUsers(realName);

      if (result.matchedCount === 0) {
        setFeishuSearchNoticeType("warning");
        setFeishuSearchNotice(`飞书通讯录未找到「${realName}」。请确认姓名是否和飞书一致。`);
        return;
      }

      if (!result.isUnique || result.users.length !== 1) {
        setFeishuSearchNoticeType("warning");
        setFeishuSearchNotice(`飞书通讯录找到 ${result.matchedCount} 个同名员工。为避免绑定错误，请联系管理员确认。`);
        return;
      }

      const [user] = result.users;
      applyFeishuUser(user);
      setFeishuSearchNoticeType("success");
      setFeishuSearchNotice(`已绑定飞书员工：${user.name} / ${user.userId ?? user.openId}`);
    } catch {
      setFeishuSearchNoticeType("warning");
      setFeishuSearchNotice("飞书通讯录查询失败，请确认后端飞书配置和管理员权限。");
    } finally {
      setFeishuSearchLoading(false);
    }
  };

  return (
    <Modal
      title={editingUser ? "编辑用户" : "新增用户"}
      open={open}
      width={680}
      destroyOnHidden
      okText="保存"
      cancelText="取消"
      className="user-management-modal"
      afterOpenChange={(visible) => {
        if (!visible) {
          setFeishuSearchNotice(undefined);
          setFeishuSearchNoticeType("info");
        }
      }}
      onCancel={onCancel}
      onOk={() => void form.validateFields().then(onSubmit)}
    >
      <Form form={form} layout="vertical" requiredMark>
        <Form.Item
          name="username"
          label="用户名"
          rules={[{ required: true, message: "请输入用户名" }]}
        >
          <Input disabled={Boolean(editingUser)} placeholder="请输入用户名" />
        </Form.Item>

        <Form.Item
          name="realName"
          label="真实姓名"
          rules={[{ required: true, message: "请输入真实姓名" }]}
        >
          <Input placeholder="请输入真实姓名，需要和飞书姓名一致" />
        </Form.Item>

        <Form.Item label="飞书员工绑定">
          <Space.Compact block>
            <Input
              readOnly
              value={boundFeishuOpenId
                ? `${boundFeishuName || "已绑定"} / ${boundFeishuUserId || boundFeishuOpenId}`
                : ""}
              placeholder="输入真实姓名后，点击右侧按钮搜索飞书员工"
            />
            <Button loading={feishuSearchLoading} onClick={() => void handleSearchFeishuUser()}>
              搜索飞书
            </Button>
          </Space.Compact>
          <Typography.Paragraph type="secondary" style={{ margin: "8px 0 0" }}>
            绑定后可用于忘记密码、入职设置密码、离职通知和飞书消息触达。
          </Typography.Paragraph>
          {feishuSearchNotice && (
            <Alert
              showIcon
              type={feishuSearchNoticeType}
              message={feishuSearchNotice}
              style={{ marginTop: 8 }}
            />
          )}
        </Form.Item>

        <Form.Item name="feishuName" hidden>
          <Input />
        </Form.Item>
        <Form.Item name="feishuOpenId" hidden>
          <Input />
        </Form.Item>
        <Form.Item name="feishuUserId" hidden>
          <Input />
        </Form.Item>
        <Form.Item name="feishuUnionId" hidden>
          <Input />
        </Form.Item>
        <Form.Item name="feishuEmployeeId" hidden>
          <Input />
        </Form.Item>

        {!editingUser && (
          <Form.Item
            name="password"
            label="初始密码（可选）"
            extra="绑定飞书员工后可不填，系统会通过飞书发送入职设置密码卡片。"
            rules={[{ min: 8, message: "密码至少 8 位" }]}
          >
            <Input.Password placeholder="可不填，绑定飞书后由员工自行设置" />
          </Form.Item>
        )}

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
            options={roleOptions.map((role) => ({ value: role.name, label: role.name }))}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default UserFormModal;
