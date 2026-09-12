/** Creates a local no-API role record. */
import { Form, Input, Modal } from "antd";
import { useEffect } from "react";
import type { RoleFormValues } from "@/pages/settings/roleManagementTypes";

interface RoleCreateModalProps {
  open: boolean;
  onCancel: () => void;
  onSubmit: (values: RoleFormValues) => void;
}

function RoleCreateModal({ open, onCancel, onSubmit }: RoleCreateModalProps) {
  const [form] = Form.useForm<RoleFormValues>();

  useEffect(() => {
    if (open) form.resetFields();
  }, [form, open]);

  return (
    <Modal
      title="增加角色"
      open={open}
      width={440}
      destroyOnHidden
      okText="确认新增"
      cancelText="取消"
      onCancel={onCancel}
      onOk={() => void form.validateFields().then(onSubmit)}
    >
      <Form form={form} layout="vertical" requiredMark>
        <Form.Item
          name="name"
          label="角色名称"
          rules={[{ required: true, message: "请输入角色名称" }]}
        >
          <Input placeholder="请输入角色名称" />
        </Form.Item>
        <Form.Item name="description" label="角色说明">
          <Input.TextArea rows={4} placeholder="这个角色可以做什么" />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default RoleCreateModal;
