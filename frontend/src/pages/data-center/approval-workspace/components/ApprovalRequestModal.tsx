import { Alert, Form, Input, Modal, Select, message } from "antd";
import { useState } from "react";
import { submitGenericApproval, type GenericApprovalType } from "../approvalWorkflowApi";

interface FormValues {
 type: GenericApprovalType;
 account: string;
 source: string;
 reason: string;
 evidence: string;
}
interface Props { open: boolean; onClose(): void; onUpdated(): void }
export default function ApprovalRequestModal({ open, onClose, onUpdated }: Props) {
 const [form] = Form.useForm<FormValues>();
 const [saving, setSaving] = useState(false);
 const [api, holder] = message.useMessage();
 const [type, setType] = useState<GenericApprovalType>("purchase_exception");
 const create = async () => {
  const value = await form.validateFields();
  setSaving(true);
  try {
   await submitGenericApproval(value.type, value.source, value.account, value.reason, value.evidence || "");
   form.resetFields(); onClose(); onUpdated();
   void api.success("申请已提交；审批通过后仍需由授权执行者单独执行业务操作");
  } catch {
   void api.error("提交失败：数据来源不存在、账号范围不匹配或权限不足");
  } finally { setSaving(false); }
 };
 return <>
  {holder}
  <Modal title="发起审批" open={open} destroyOnHidden onCancel={onClose}
   onOk={() => void create()} okButtonProps={{ loading:saving }} okText="提交申请">
   <Alert type="info" showIcon style={{ marginBottom:16 }}
    message="审批与执行分离"
    description="采购、财务、权限的批准仅形成管理决策与审计记录，不会自动修改采购订单、利润或账号权限。" />
   <Form layout="vertical" form={form} preserve={false} initialValues={{ type:"purchase_exception" }}>
    <Form.Item label="业务类型" name="type" rules={[{ required:true }]}>
     <Select onChange={(v:GenericApprovalType) => setType(v)} options={[
      { label:"采购异常处理",value:"purchase_exception" },
      { label:"财务例外处理",value:"finance_exception" },
      { label:"用户权限变更",value:"access_change" },
     ]} />
    </Form.Item>
    <Form.Item label="数据源账号标识" name="account" rules={[{ required:true }]}>
     <Input maxLength={128} placeholder="输入本人已授权的数据源账号标识" />
    </Form.Item>
    <Form.Item label={type === "purchase_exception" ? "采购订单号" :
     type === "finance_exception" ? "业务日期|SKU" : "目标用户 ID"} name="source"
     rules={[{ required:true }]}>
     <Input maxLength={128} placeholder={type === "finance_exception" ? "YYYY-MM-DD|SKU" : "输入真实业务对象标识"} />
    </Form.Item>
    <Form.Item name="reason" label="申请原因" rules={[{ required:true }, { min:5 }]}>
     <Input.TextArea rows={4} maxLength={4000} showCount />
    </Form.Item>
    <Form.Item name="evidence" label="证明材料/依据">
     <Input.TextArea rows={3} maxLength={4000} showCount />
    </Form.Item>
   </Form>
  </Modal>
 </>;
}
