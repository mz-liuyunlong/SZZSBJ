/** 编辑跟进信息：格式照 WFS 费用异常总表（Case 编号、下次跟进时间、最新跟进记录必填）；每次保存追加一条记录。 */
import { Button, DatePicker, Form, Input, Modal, Space, Typography } from "antd";
import dayjs from "dayjs";
import { useEffect, useState } from "react";
import type { ReconRow } from "./reconApi";
import { n2 } from "./reconModel";

interface FollowFormValues {
  caseNo?: string;
  nextAt?: dayjs.Dayjs;
  text?: string;
}

function FollowModal({ row, onClose, onSubmit }: {
  row?: ReconRow;
  onClose: () => void;
  onSubmit: (values: { content: string; caseNo?: string; nextAt?: string }) => Promise<void>;
}) {
  const [form] = Form.useForm<FollowFormValues>();
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!row) return;
    form.setFieldsValue({
      caseNo: row.latestFollow?.case_no ?? "",
      nextAt: row.latestFollow?.next_follow_date ? dayjs(row.latestFollow.next_follow_date) : undefined,
      text: "",
    });
  }, [form, row]);
  if (!row) return null;
  return (
    <Modal width={640} open title={`编辑跟进信息 · ${row.code} · 账单日 ${row.payDate}`} onCancel={onClose} destroyOnHidden footer={null}>
      <div className="fin-payout-recon__follow-summary">
        <div><Typography.Text type="secondary">应付</Typography.Text><strong>${n2(row.payable)}</strong></div>
        <div><Typography.Text type="secondary">到账</Typography.Text><strong>{row.arrived == null ? "未到账" : `$${n2(row.arrived)}`}</strong></div>
        <div><Typography.Text type="secondary">差额</Typography.Text><strong>{row.diff == null ? "—" : `$${n2(row.diff)}`}</strong></div>
      </div>
      <Form<FollowFormValues>
        form={form}
        layout="vertical"
        onFinish={async (values) => {
          setBusy(true);
          try {
            await onSubmit({ content: values.text?.trim() ?? "", caseNo: values.caseNo?.trim(), nextAt: values.nextAt?.format("YYYY-MM-DD") });
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="fin-payout-recon__follow-grid">
          <Form.Item label="Case 编号" name="caseNo"><Input placeholder="沃尔玛 Case 编号（有就填）" maxLength={64} /></Form.Item>
          <Form.Item label="下次跟进时间" name="nextAt"><DatePicker className="fin-payout-recon__full" /></Form.Item>
        </div>
        <Form.Item label="最新跟进记录" name="text" rules={[{ required: true, whitespace: true, message: "请填写最新跟进记录" }]}>
          <Input.TextArea rows={4} maxLength={500} showCount placeholder="例如：沃尔玛后台显示本期已打款，收款账户还没入账；已开 Case，预计 3 天内到账。" />
        </Form.Item>
        <div className="fin-payout-recon__follow-footer">
          <Space><Button onClick={onClose}>取消</Button><Button type="primary" htmlType="submit" loading={busy}>保存跟进</Button></Space>
        </div>
      </Form>
    </Modal>
  );
}

export default FollowModal;
