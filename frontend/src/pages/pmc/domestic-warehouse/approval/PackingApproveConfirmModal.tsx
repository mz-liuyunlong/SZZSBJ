/** Confirm an existing candidate. The passphrase is sent once and checked on the server. */
import { Form, Input, Modal, Select, Typography } from "antd";
import type { ApprovalCandidate } from "./packingApprovalApi";

import { DOMESTIC_APPROVER_NAMES, approveConfirmTitle, approveConfirmSummary } from "./packingApproveConfirm";

interface ConfirmIdentity { operatorName: string; passcode: string }
interface Props {
  row: ApprovalCandidate | null;
  /** Batch approval: one identity confirmation for several candidates. */
  rows?: ApprovalCandidate[];
  progress?: string;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (values: ConfirmIdentity) => Promise<void>;
}

export default function PackingApproveConfirmModal({ row, rows, progress, busy, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm<ConfirmIdentity>();
  const batch = !row && !!rows?.length;
  const title = row ? approveConfirmTitle(row) : batch ? `批量审批 · ${rows!.length} 张` : "审批通过";
  return <Modal title={title} open={!!row || batch} okText={progress ?? "提交"} cancelText="取消" confirmLoading={busy}
    cancelButtonProps={{ disabled: busy }} closable={!busy} maskClosable={!busy} destroyOnHidden
    onCancel={onCancel} onOk={() => { void form.validateFields().then((values) => onSubmit(values)).catch(() => undefined); }}>
    {row && <Typography.Paragraph className="domestic-approval__confirm-copy" type="secondary">{approveConfirmSummary(row)}</Typography.Paragraph>}
    {batch && <Typography.Paragraph className="domestic-approval__confirm-copy" type="secondary">将按每张已保存的修改逐张审批（数量、报关、拆单都按保存的内容）；待补资料或未填数量的会跳过。拆单的每行各生成一张打包单。</Typography.Paragraph>}
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
