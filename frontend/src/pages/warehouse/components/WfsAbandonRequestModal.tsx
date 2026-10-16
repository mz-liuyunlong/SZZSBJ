import { Form, Input, Modal, Select, Typography, message } from "antd";
import { useState } from "react";
import type { WfsFeeAlertRow } from "@/pages/warehouse/wfsFeeAlertTypes";
import { submitWfsArchiveRequest } from "@/pages/data-center/approval-workspace/approvalApi";

interface Props { row?: WfsFeeAlertRow; onClose(): void; onSuccess(): void }
interface RequestValues { reasonType: string; reason: string; evidence?: string }
export default function WfsAbandonRequestModal({ row, onClose, onSuccess }: Props) {
 const [form] = Form.useForm<RequestValues>();
 const [saving, setSaving] = useState(false);
 const [messageApi, holder] = message.useMessage();
 const save = async () => {
  if (!row || saving) return;
  const v = await form.validateFields();
  setSaving(true);
  try {
   await submitWfsArchiveRequest(row.id, v.reasonType, v.reason.trim(), (v.evidence || "").trim());
   form.resetFields(); onSuccess(); onClose();
   void messageApi.success("已提交管理审批");
  } catch {
   void messageApi.error("提交失败，请检查权限、原因或状态是否发生变化");
  } finally { setSaving(false); }
 };
 return <>
  {holder}
  <Modal title="申请放弃跟进（需管理审批）" open={!!row} destroyOnHidden
   onCancel={onClose} onOk={() => void save()} okText="提交审批" okButtonProps={{loading:saving}}>
   <Typography.Paragraph type="secondary">
    提交后进入待审批，未获批准不得关闭此 Case。请完整说明不继续追回的理由。
   </Typography.Paragraph>
   <Form form={form} layout="vertical" preserve={false}>
    <Form.Item label="放弃类型" name="reasonType" rules={[{required:true,message:"请选择原因类型"}]}>
     <Select options={[
      {label:"平台明确拒绝赔付",value:"platform_rejected"},
      {label:"证据不足难以追偿",value:"insufficient_evidence"},
      {label:"处理成本不合理",value:"cost_exceeds_benefit"},
      {label:"尚未开 Case，确认无需跟进",value:"not_actionable"},
      {label:"其他原因",value:"other"},
     ]}/>
    </Form.Item>
    <Form.Item label="详细原因" name="reason" rules={[
     {required:true,message:"请填写原因"},
     {min:5,message:"至少填写5个字"},
    ]}><Input.TextArea maxLength={4000} showCount rows={4} /></Form.Item>
    <Form.Item label="平台答复/附件证据说明" name="evidence">
     <Input.TextArea maxLength={4000} showCount rows={3}/>
    </Form.Item>
   </Form>
  </Modal>
 </>;
}
