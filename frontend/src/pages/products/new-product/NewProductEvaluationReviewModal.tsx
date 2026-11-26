/** New-product assessment review request. Uses existing Ant Design controls; no new CSS. */
import { useState } from "react";
import { Alert, Form, Input, Modal, Select, Typography } from "antd";

export type ReviewReasonType = "calculation_error" | "scoring_basis_error" | "special_exception" | "manual_decision_change";

export default function NewProductEvaluationReviewModal({
  productName, itemId, visible, submitting, onClose, onSubmit, manualPassAllowed=false, legacyExceptionAllowed=false,
}: {
  productName: string;
  itemId: string;
  visible: boolean;
  submitting: boolean;
  manualPassAllowed?: boolean;
  legacyExceptionAllowed?: boolean;
  onClose: () => void;
  onSubmit: (reasonType: ReviewReasonType, reason: string, evidence: string) => Promise<void>;
}) {
  const [reasonType, setReasonType] = useState<ReviewReasonType>(manualPassAllowed ? "manual_decision_change" : "calculation_error");
  const [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState("");
  const isConclusion = reasonType === "manual_decision_change";
  const minLength = isConclusion ? 20 : 5;
  const valid = (isConclusion ? Array.from(reason.replace(/\s/g,"" )).length >= minLength : reason.trim().length >= minLength)
    && (!isConclusion || manualPassAllowed) && (reasonType!=="special_exception" || legacyExceptionAllowed)
    && reason.length <= 4000 && evidence.length <= 4000;
  return <Modal open={visible} title="新品测评复核申请" okText="提交复核申请"
    okButtonProps={{disabled:!valid,loading:submitting}} cancelButtonProps={{disabled:submitting}}
    onOk={() => void onSubmit(reasonType, reason.trim(), evidence.trim())}
    onCancel={onClose} destroyOnHidden>
    <Typography.Paragraph>{productName} · Item ID {itemId}</Typography.Paragraph>
    <Alert type="info" showIcon message={isConclusion ? "申请将测评结论改为通过" : "评分复核不会直接改动现有评级"}
      description={isConclusion ? "领导审批通过后变更人工测评结论；保留原评分、风险和历史，不自动采购。" : "先核实真实数据，再按批准的复核授权重新核算。D/Pass及风险限制不能通过人工复核绕过。"} />
    <Form layout="vertical" style={{marginTop:16}}>
      <Form.Item label="申请原因" required>
        <Select value={reasonType} onChange={setReasonType} options={[
          ...(manualPassAllowed ? [{label:"测评结论复核（改为通过）",value:"manual_decision_change" as const}] : []),
          {label:"数据计算错误",value:"calculation_error"},
          {label:"评分依据有误",value:"scoring_basis_error"},
          ...(legacyExceptionAllowed ? [{label:"特殊情况申请（不改变采购限制）",value:"special_exception" as const}] : []),
        ]} />
      </Form.Item>
      <Form.Item label="申请说明" required help={`至少${minLength}个字，明确需要复核的依据`}>
        <Input.TextArea value={reason} onChange={e=>setReason(e.target.value)}
          maxLength={4000} rows={4} placeholder={isConclusion?"请说明为什么原测评结论需要改为通过":"请描述数据、评分依据存在的问题"} />
      </Form.Item>
      <Form.Item label="证据说明 / 材料链接（选填）">
        <Input.TextArea value={evidence} onChange={e=>setEvidence(e.target.value)}
          maxLength={4000} rows={2} placeholder="如有截图、资料或来源链接，可填写相关说明" />
      </Form.Item>
    </Form>
  </Modal>;
}
