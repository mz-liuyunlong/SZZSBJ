/** Reuse the warehouse contract; the shared warehouse action dialog excludes customs. */
import { useQuery } from "@tanstack/react-query";
import { Alert, Form, Input, Modal, Select, Skeleton } from "antd";
import { getWarehouseOrder, warehouseError } from "../domestic-warehouse/packing/packingWarehouseApi";
import type { PackingWarehouseRow, WarehouseFields } from "../domestic-warehouse/packing/packingWarehouseTypes";

export default function PendingCustomsDialog({ id, scope, busy, onCancel, onSubmit }: {
  id: string; scope: string; busy: boolean; onCancel: () => void;
  onSubmit: (row: PackingWarehouseRow, fields: WarehouseFields) => Promise<void>;
}) {
  const [form] = Form.useForm<WarehouseFields>();
  const detail = useQuery({ queryKey: ["domestic-packing-warehouse", scope, "detail", id], queryFn: ({ signal }) => getWarehouseOrder(id, signal), staleTime: 0 });
  return <Modal open title="修改报关信息" onCancel={onCancel} confirmLoading={busy} okButtonProps={{ disabled: !detail.data || !!detail.error }}
    onOk={() => { void form.validateFields().then((values) => onSubmit(detail.data!.data, values)).catch(() => undefined); }}>
    {detail.error ? <Alert type="error" message={warehouseError(detail.error)} /> : !detail.data ? <Skeleton active /> : <Form form={form} layout="vertical" initialValues={{ value: detail.data.data.customs_value }}>
      <Form.Item name="value" label="是否报关" rules={[{ required: true }]}><Select options={[{ value: true, label: "报关" }, { value: false, label: "不报关" }]} /></Form.Item>
      <Form.Item name="reason" label="修改原因" rules={[{ required: true, whitespace: true, min: 2, max: 500 }]}><Input.TextArea /></Form.Item>
    </Form>}
  </Modal>;
}
