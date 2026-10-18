import { Alert, Form, Input, Modal, Select, message } from "antd";
import { useState } from "react";
import { reattestLegacyWfs } from "../approvalWorkflowApi";

interface FormValues { reasonType: string; reason: string; evidence: string }
interface Props { caseId?: string; onClose(): void; onSuccess(): void }
export default function LegacyReattestModal({ caseId, onClose, onSuccess }: Props) {
 const [form] = Form.useForm<FormValues>();
 const [busy, setBusy] = useState(false);
 const [api, context] = message.useMessage();
 const confirm = async () => {
  if (!caseId || busy) return;
  const value = await form.validateFields();
  setBusy(true);
  try {
   await reattestLegacyWfs(caseId, value.reasonType, value.reason.trim(), value.evidence?.trim() || "");
   form.resetFields();
   onClose(); onSuccess();
   void api.success("已以当前账号重新提交申请，请由其他有权限的审核人处理");
  } catch {
   void api.error("提交失败：请检查资料、权限或该 Case 是否已有正式审批单");
  } finally { setBusy(false); }
 };
 return <>
  {context}
  <Modal open={!!caseId} title="历史 WFS 申请 · 重新核验并提交" destroyOnHidden
   okText="以当前账号提交正式审批" okButtonProps={{ loading:busy }}
   onCancel={onClose} onOk={() => void confirm()}>
   <Alert showIcon type="warning" style={{ marginBottom:16 }}
    message="这是一份新的申请，不是对旧申请时间或旧操作人的认证。"
    description="原始 Case、旧操作人和时间均保持不变，审核过程保留完整证据链。当前提交者不能审批自己的申请。" />
   <Form form={form} layout="vertical" preserve={false}>
    <Form.Item name="reasonType" label="放弃原因分类" rules={[{ required:true }]}>
     <Select options={[
      { label:"平台明确拒绝赔付", value:"platform_rejected" },
      { label:"现有证据不足", value:"insufficient_evidence" },
      { label:"处理成本超过潜在追回", value:"cost_exceeds_benefit" },
      { label:"其他", value:"other" },
     ]} />
    </Form.Item>
    <Form.Item name="reason" label="本次申请的完整原因" rules={[
     { required:true }, { min:5, message:"至少填写5个字" },
    ]}><Input.TextArea rows={4} maxLength={4000} showCount /></Form.Item>
    <Form.Item name="evidence" label="证明材料与 Walmart 回复摘要（必填）" rules={[{ required:true }, { min:5 }]}>
     <Input.TextArea rows={3} maxLength={4000} showCount />
    </Form.Item>
   </Form>
  </Modal>
 </>;
}
