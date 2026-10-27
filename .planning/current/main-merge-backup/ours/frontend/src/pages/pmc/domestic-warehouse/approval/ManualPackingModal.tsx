import PackingCustomsSelect from "./PackingCustomsSelect";
/** Manual submission starts with a published inbound source, never a free-text SKU. */
import { Alert, Button, Descriptions, Form, Input, InputNumber, Modal, Select, message } from "antd";
import { useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { approvalErrorText, getManualPackingOptions, listManualPackingSources, submitManualPacking, type ApprovalCandidate, type ManualPackingPayload } from "./packingApprovalApi";

interface Values { source: string; target: string; qty: number; customs: "default" | "declare" | "skip"; reason: string }
interface Props { open: boolean; scope: string; onCancel: () => void; onSubmitted: () => void }
export default function ManualPackingModal({ open, scope, onCancel, onSubmitted }: Props) {
  const [form] = Form.useForm<Values>();
  const [keyword, setKeyword] = useState("");
  const [source, setSource] = useState<ApprovalCandidate>();
  const [messages, context] = message.useMessage();
  const retry = useRef<{ signature: string; key: string } | undefined>(undefined);
  const sources = useQuery({ queryKey: ["packing-manual-sources", scope, keyword], queryFn: ({ signal }) => listManualPackingSources(keyword, signal), enabled: open });
  const options = useQuery({ queryKey: ["packing-manual-options", scope, source?.source_account_ref, source?.board_id], queryFn: ({ signal }) => getManualPackingOptions(source!, signal), enabled: open && !!source, staleTime: 0 });
  const basis = options.data?.data.candidate;
  const choices = options.data?.data.listings ?? [];
  const targetKey = Form.useWatch("target", form);
  const choiceKey = (r: typeof choices[number]) => JSON.stringify([r.store_id, r.item_id, r.listing_version]);
  const target = choices.find((r) => choiceKey(r) === targetKey);
  const mutation = useMutation({ mutationFn: submitManualPacking, onSuccess: () => { onSubmitted(); }, onError: (error) => { void messages.error(approvalErrorText(error)); void options.refetch(); } });
  const submit = async () => {
    const values = await form.validateFields();
    if (!basis || !target) return;
    const data = { source_account_ref: basis.source_account_ref, warehouse_id: "16168" as const, board_id: basis.board_id, source_version: basis.candidate_version,
      target_store_id: target.store_id, target_item_id: target.item_id, listing_version: target.listing_version, qty: values.qty, customs: values.customs, rwh: basis.warehouse_name?.trim() || undefined, reason: values.reason.trim() };
    const signature = JSON.stringify(data);
    if (retry.current?.signature !== signature) retry.current = { signature, key: crypto.randomUUID() };
    const body: ManualPackingPayload = { ...data, idempotency_key: retry.current.key };
    mutation.mutate(body);
  };
  const error = sources.error ?? options.error;
  return <Modal title="手工添加打包单" open={open} destroyOnHidden okText="提交审批" cancelText="取消" width={680} confirmLoading={mutation.isPending} getContainer={() => document.body}
    onCancel={() => { if (!mutation.isPending) onCancel(); }} closable={!mutation.isPending} cancelButtonProps={{ disabled: mutation.isPending }}
    okButtonProps={{ disabled: !basis || !target || options.isFetching || !!error }} onOk={() => { void submit().catch(() => undefined); }}>
    {context}
    <Alert type="info" showIcon message="先选择入库单×SKU。提交仅新增待审批申请，不发PK、不占用库存；通过审批时重新校验并分配原入库库存。" />
    {error && <Alert type="error" message={approvalErrorText(error)} action={<Button onClick={() => { void sources.refetch(); if (source) void options.refetch(); }}>重试</Button>} />}
    <Form form={form} layout="vertical" initialValues={{ customs: "default" }}>
      <Form.Item name="source" label="入库单 × SKU" rules={[{ required: true, message: "请先选择来源入库单与SKU" }]}>
        <Select showSearch filterOption={false} loading={sources.isFetching} placeholder="搜索入库单 / SKU" onSearch={setKeyword}
          options={(sources.data?.data.items ?? []).map((r) => ({ value: `${r.source_account_ref}|${r.board_id}`, label: `${r.inbound_order_sn} / ${r.sku} / ${r.store_name ?? r.store_id ?? "未归属"}（可用 ${r.available_quantity ?? "未知"}）`, disabled: !r.available_quantity }))}
          onChange={(value) => { setSource(sources.data?.data.items.find((r) => `${r.source_account_ref}|${r.board_id}` === value)); form.setFieldsValue({ target: undefined, qty: undefined }); }} />
      </Form.Item>
      {basis && <Descriptions size="small" column={2} items={[{ key: "sku", label: "SKU（固定）", children: basis.sku }, { key: "stock", label: "可用数量", children: basis.available_quantity ?? "未知" }]} />}
      <Form.Item name="target" label="目标店铺 / ItemID" rules={[{ required: true, message: "请选择同SKU的有效商品" }]}>
        <Select disabled={!basis} loading={options.isFetching} showSearch optionFilterProp="label" placeholder="先选入库单，再选商品"
          options={choices.map((r) => ({ value: choiceKey(r), label: `${r.store_name ?? r.store_id} / ${r.item_id}${r.cross_store ? "（跨店铺）" : ""}` }))} />
      </Form.Item>
      <Descriptions size="small" column={2} items={[{ key: "gtin", label: "GTIN", children: target?.gtin ?? "—" }, { key: "msku", label: "MSKU", children: target?.msku ?? "—" }]} />
      {target?.cross_store && <Alert type="warning" message="目标店铺与来源店铺不同。以所选入库单为分配依据，保留两者快照，不改写领星库存归属。" />}
      <Form.Item name="qty" label="备货数量" rules={[{ required: true, message: "请填写备货数量" }, { type: "integer", min: 1, max: Math.min(basis?.available_quantity ?? 0, 1000000), message: "填写可用范围内的正整数" }]}><InputNumber min={1} precision={0} max={basis?.available_quantity ?? 0} /></Form.Item>
      <Form.Item name="customs" label="是否报关"><PackingCustomsSelect row={basis} /></Form.Item>
      <Form.Item name="reason" label="添加原因（必填）" rules={[{ required: true, whitespace: true, message: "请填写添加原因" }, { min: 2, max: 500, message: "添加原因请填写 2 到 500 个字" }]}><Input.TextArea maxLength={500} rows={3} /></Form.Item>
    </Form>
  </Modal>;
}
