/** Form layout only; submit stays disabled until an approved approval API exists. */
import { Form, Input, InputNumber, Modal, Select, Tooltip, Typography } from "antd";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function PackingApprovalManualModal({ open, onClose }: Props) {
  const [form] = Form.useForm();
  return <Modal title="手工添加打包单" open={open} destroyOnHidden width={560}
    okText="提交审批" cancelText="取消"
    okButtonProps={{ disabled: true }}
    onCancel={() => { form.resetFields(); onClose(); }}
    footer={(_, { CancelBtn, OkBtn }) => <>
      <CancelBtn />
      <Tooltip title="打包单审批提交接口尚未接入">
        <span><OkBtn /></span>
      </Tooltip>
    </>}>
    <Form form={form} layout="vertical" disabled>
      <Form.Item label="入库单 / SKU" name="inboundSku" rules={[{ required: true }]}>
        <Select placeholder="选择入库单 × SKU" options={[]} />
      </Form.Item>
      <Form.Item label="备货数量" name="quantity" rules={[{ required: true }]}>
        <InputNumber className="domestic-approval__full-width" min={1} precision={0} placeholder="数量" />
      </Form.Item>
      <Form.Item label="店铺" name="storeId" rules={[{ required: true }]}>
        <Select placeholder="选择店铺" options={[]} />
      </Form.Item>
      <Form.Item label="ItemID（为该 SKU 选择在线商品；GTIN/MSKU 随所选商品）" name="itemId" rules={[{ required: true }]}>
        <Select placeholder="选择在线商品" options={[]} />
      </Form.Item>
      <Typography.Paragraph type="secondary" className="domestic-approval__hint">
        若 ItemID 不在在线商品列表，GTIN/MSKU 将沿用原行资料；真实选项待商品与入库关联服务接入。
      </Typography.Paragraph>
      <Form.Item label="收货仓" name="receivingWarehouse" initialValue="placeholder">
        <Select options={[{ value: "placeholder", label: "待接入海外仓选项" }]} />
      </Form.Item>
      <Form.Item label="修改原因（必填）" name="reason" rules={[{ required: true }]}>
        <Input.TextArea rows={3} placeholder="例如：客户要求分批发货 / 更换店铺发货" />
      </Form.Item>
    </Form>
  </Modal>;
}
