/** New-product assessment review request. Uses existing Ant Design controls; no new CSS. */
import { useState } from "react";
import { Alert, Form, Input, Modal, Select, Typography } from "antd";

export type ReviewReasonType = "calculation_error" | "scoring_basis_error" | "special_exception";

export default function NewProductEvaluationReviewModal({
  productName, itemId, visible, submitting, onClose, onSubmit,
}: {
  productName: string;
  itemId: string;
  visible: boolean;
  submitting: boolean;
  onClose: () => void;
  onSubmit: (reasonType: ReviewReasonType, reason: string, evidence: string) => Promise<void>;
}) {
  const [reasonType, setReasonType] = useState<ReviewReasonType>("calculation_error");
  const [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState("");
  const valid = reason.trim().length >= 5 && reason.length <= 4000 && evidence.length <= 4000;
  return <Modal open={visible} title="新品测评复核申请" okText="提交复核申请"
    okButtonProps={{disabled:!valid,loading:submitting}} cancelButtonProps={{disabled:submitting}}
    onOk={() => void onSubmit(reasonType, reason.trim(), evidence.trim())}
    onCancel={onClose} destroyOnHidden>
    <Typography.Paragraph>{productName} · Item ID {itemId}</Typography.Paragraph>
    <Alert type="info" showIcon message="人工复核不直接修改系统评级"
      description="如属计算错误，核实真实数据后再重新评分；特殊情况特批保留原 D/Pass 评级及审批凭证。" />
    <Form layout="vertical" style={{marginTop:16}}>
      <Form.Item label="申请原因" required>
        <Select value={reasonType} onChange={setReasonType} options={[
          {label:"数据计算错误",value:"calculation_error"},
          {label:"评分依据有误",value:"scoring_basis_error"},
          {label:"特殊情况申请",value:"special_exception"},
        ]} />
      </Form.Item>
      <Form.Item label="申请说明" required help="至少5个字，明确需要复核的依据">
        <Input.TextArea value={reason} onChange={e=>setReason(e.target.value)}
          maxLength={4000} rows={4} placeholder="请描述评分存在的问题或特批理由" />
      </Form.Item>
      <Form.Item label="证据说明 / 材料链接（选填）">
        <Input.TextArea value={evidence} onChange={e=>setEvidence(e.target.value)}
          maxLength={4000} rows={2} placeholder="如有截图、资料或来源链接，可填写相关说明" />
      </Form.Item>
    </Form>
  </Modal>;
}
