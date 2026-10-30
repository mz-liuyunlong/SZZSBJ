/** Reload scoped identity proof before an atomic PK replacement. */
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Form, Input, Modal, Select, Skeleton } from "antd";
import { getPending, identityOptions, pendingError } from "./pendingPackingApi";
import type { IdentityFields, PendingRow } from "./pendingPackingTypes";
export default function PendingIdentityDialog({ id, scope, busy, error, onCancel, onSubmit }: {
  id: string; scope: string; busy: boolean; error?: string; onCancel: () => void;
  onSubmit: (row: PendingRow, fields: IdentityFields) => Promise<void>;
}) {
  const [form] = Form.useForm<{ choice: string; reason: string }>();
  const detail = useQuery({ queryKey: ["wfs-pending-packing", scope, "identity", id], queryFn: async ({ signal }) => ({ row: (await getPending(id, signal)).data, choices: (await identityOptions(id, signal)).data.listings }), retry: false, staleTime: 0 });
  return <Modal title="换店铺 / 换链接" open confirmLoading={busy} closable={!busy} maskClosable={!busy}
    cancelButtonProps={{ disabled: busy }} onCancel={onCancel} okText="确认换单" cancelText="取消"
    okButtonProps={{ disabled: !detail.data?.row.can_edit }} onOk={() => { void form.validateFields().then(async (v) => {
      const choice = detail.data?.choices.find((c) => `${c.store_id}|${c.item_id}` === v.choice);
      if (!choice || !detail.data) return;
      await onSubmit(detail.data.row, { target_store_id: choice.store_id, target_item_id: choice.item_id, listing_version: choice.listing_version, reason: v.reason });
    }).catch(() => undefined); }}>
    {detail.error ? <Alert type="error" message={pendingError(detail.error)} action={<Button onClick={() => void detail.refetch()}>重试</Button>} /> : !detail.data ? <Skeleton active /> : <>
      <Alert type="warning" message="原 PK 作废，生成新 PK 并继承本系统装箱" description="保留来源库存与历史审计；不会在领星创建或作废单据。" />
      {error && <Alert type="error" message={error} />}
      <Form form={form} layout="vertical">
        <Form.Item name="choice" label="目标店铺 / Item ID" rules={[{ required: true }]}><Select showSearch optionFilterProp="label" options={detail.data.choices.map((c) => ({ value: `${c.store_id}|${c.item_id}`, label: `${c.store_name ?? c.store_id} · ${c.item_id} · ${c.gtin ?? "缺GTIN"}`, disabled: !c.gtin || !c.msku || (c.store_id === detail.data.row.order.store_id && c.item_id === detail.data.row.order.item_id) }))} /></Form.Item>
        <Form.Item name="reason" label="修改原因" rules={[{ required: true, whitespace: true, min: 2, max: 500 }]}><Input.TextArea maxLength={500} /></Form.Item>
      </Form>
    </>}
  </Modal>;
}
