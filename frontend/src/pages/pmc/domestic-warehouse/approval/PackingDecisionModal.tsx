/** Confirmation owns validation; the server remains the stock and permission authority. */
import { Alert, Form, Input, InputNumber, Modal, Select, Typography } from "antd";
import { useEffect } from "react";
import type { ApprovalCandidate, DecisionKind } from "./packingApprovalApi";
export interface DecisionValues { qty?: number; customs: "default" | "declare" | "skip"; rwh?: string; note?: string }
interface Props { row: ApprovalCandidate | null; kind: DecisionKind; busy: boolean; onCancel: () => void; onSubmit: (values: DecisionValues) => Promise<void> }
export default function PackingDecisionModal({ row, kind, busy, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm<DecisionValues>();
  useEffect(() => { if (row) { form.resetFields(); form.setFieldsValue({ qty: row.default_quantity ?? undefined, customs: "default" }); } }, [row, form]);
  return <Modal title={kind === "approve" ? "审批通过并生成打包单" : "驳回打包单"} open={!!row} confirmLoading={busy} cancelButtonProps={{ disabled: busy }} closable={!busy} maskClosable={!busy} onCancel={onCancel}
    onOk={() => { void form.validateFields().then(onSubmit).catch(() => undefined); }} destroyOnHidden>
    <Alert type="info" showIcon message="仅写本地验证单，不创建领星 OWS" />
    <Typography.Paragraph>{row?.inbound_order_sn} / {row?.sku} / {row?.item_id ?? "商品待补"}</Typography.Paragraph>
    <Form form={form} layout="vertical">
      {kind === "approve" ? <><Form.Item label={`备货数量（可用 ${row?.available_quantity ?? "未知"}）`} name="qty" rules={[{ required: true, message: "请填写备货数量" }, { type: "integer", min: 1, max: Math.min(row?.available_quantity ?? 0, 1000000), message: "数量必须为可用范围内的正整数" }]}><InputNumber min={1} precision={0} max={row?.available_quantity ?? 0} /></Form.Item>
      <Form.Item label="是否报关" name="customs"><Select options={[{ value: "default", label: "默认（来源未提供，保持未知）" }, { value: "declare", label: "报关" }, { value: "skip", label: "不报关" }]} /></Form.Item>
      <Form.Item label="收货仓备注（选填）" name="rwh" rules={[{ max: 128 }]}><Input maxLength={128} /></Form.Item></>
      : <Form.Item label="驳回原因" name="note" rules={[{ required: true, whitespace: true, message: "请填写驳回原因" }, { max: 500 }]}><Input.TextArea maxLength={500} rows={3} /></Form.Item>}
    </Form>
  </Modal>;
}
