/** Collect a local draft snapshot. No approval or external execution is offered. */
import { Alert, Checkbox, Form, Input, Modal, Typography } from "antd";
import type { PendingRow, ReturnAddress } from "./pendingPackingTypes";
export default function PendingDraftDialog({ rows, selected, busy, error, onCancel, onSubmit }: {
  rows: PendingRow[]; selected: string[]; busy: boolean; error?: string;
  onCancel: () => void; onSubmit: (address: ReturnAddress, its: boolean) => Promise<void>;
}) {
  const [form] = Form.useForm<ReturnAddress & { its: boolean }>();
  const lines = rows.flatMap((r) => r.order.box_set?.lines.filter((l) => selected.includes(l.id)) ?? []);
  const groups = [...new Set(lines.map((l) => l.units_per_box))];
  return <Modal title="生成货件草稿" open confirmLoading={busy} closable={!busy} maskClosable={!busy}
    cancelButtonProps={{ disabled: busy }} onCancel={onCancel} okText="保存为待审批草稿" cancelText="取消"
    onOk={() => { void form.validateFields().then(({ its, ...address }) => onSubmit(address, its)).catch(() => undefined); }}>
    <Alert type="info" showIcon message={`将保存 ${groups.length} 张待审批草稿，共 ${lines.reduce((n, l) => n + l.boxes, 0)} 箱、${lines.reduce((n, l) => n + l.boxes * l.units_per_box, 0)} 件`} description="按每箱件数分组。不会批准草稿、写入 Walmart 或生成箱唛。" />
    {error && <Alert type="error" message={error} style={{ marginTop: 12 }} />}
    <Typography.Paragraph>退货地址随本次草稿保存，尚未经过 Walmart 验证。</Typography.Paragraph>
    <Form form={form} layout="vertical" initialValues={{ country_code: "US", its: false }}>
      <Form.Item name="address_line1" label="退货街道地址" rules={[{ required: true, whitespace: true, max: 200 }]}><Input maxLength={200} /></Form.Item>
      <Form.Item name="city" label="城市" rules={[{ required: true, whitespace: true, max: 100 }]}><Input maxLength={100} /></Form.Item>
      <Form.Item name="state_code" label="州代码" normalize={(v: string) => v.toUpperCase()} rules={[{ required: true, pattern: /^[A-Z]{2}$/ }]}><Input maxLength={2} placeholder="TX" /></Form.Item>
      <Form.Item name="postal_code" label="邮编" rules={[{ required: true, pattern: /^\d{5}(-\d{4})?$/ }]}><Input maxLength={10} /></Form.Item>
      <Form.Item name="country_code" label="国家"><Input disabled /></Form.Item>
      <Form.Item name="its" valuePropName="checked"><Checkbox>选择 ITS（仅保存选择，执行资格下阶段验证）</Checkbox></Form.Item>
    </Form>
  </Modal>;
}
