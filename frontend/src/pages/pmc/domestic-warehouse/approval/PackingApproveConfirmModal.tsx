/** Confirm an existing candidate. The passphrase is sent once and checked on the server. */
import { Form, Input, Modal, Select, Typography } from "antd";
import type { ApprovalCandidate } from "./packingApprovalApi";

export const DOMESTIC_APPROVER_NAMES = ["吴贤玲"];

function dash(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

export function approveConfirmTitle(row: ApprovalCandidate) {
  const pk = row.pk?.trim();
  return pk ? `审批通过 · ${pk} · ${row.sku}` : `审批通过 · ${row.sku}`;
}

export function approveConfirmSummary(row: ApprovalCandidate) {
  return `入库单 ${row.inbound_order_sn} · ItemID ${dash(row.item_id)} · GTIN ${dash(row.gtin)} · MSKU ${dash(row.msku)}`;
}

interface ConfirmIdentity { operatorName: string; passcode: string }
interface Props {
  row: ApprovalCandidate | null;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (values: ConfirmIdentity) => Promise<void>;
}

export default function PackingApproveConfirmModal({ row, busy, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm<ConfirmIdentity>();
  return <Modal title={row ? approveConfirmTitle(row) : "审批通过"} open={!!row} okText="提交" cancelText="取消" confirmLoading={busy}
    cancelButtonProps={{ disabled: busy }} closable={!busy} maskClosable={!busy} destroyOnHidden
    onCancel={onCancel} onOk={() => { void form.validateFields().then((values) => onSubmit(values)).catch(() => undefined); }}>
    {row && <Typography.Paragraph className="domestic-approval__confirm-copy" type="secondary">{approveConfirmSummary(row)}</Typography.Paragraph>}
    <Form form={form} layout="vertical" initialValues={{ operatorName: DOMESTIC_APPROVER_NAMES[0] }} preserve={false}>
      <Form.Item name="operatorName" label="姓名" rules={[{ required: true, message: "请选择姓名" }]}>
        <Select options={DOMESTIC_APPROVER_NAMES.map((name) => ({ value: name, label: name }))} />
      </Form.Item>
      <Form.Item name="passcode" label="口令" rules={[{ required: true, whitespace: true, message: "请输入口令" }]}>
        <Input.Password autoComplete="off" />
      </Form.Item>
    </Form>
  </Modal>;
}
