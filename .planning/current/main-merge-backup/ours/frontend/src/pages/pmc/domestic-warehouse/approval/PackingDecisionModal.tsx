import PackingCustomsSelect from "./PackingCustomsSelect";
/** Edit the final Listing identity while preserving the source SKU and evidence. */
import { Alert, Button, Descriptions, Form, Input, InputNumber, Modal, Select, Typography } from "antd";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { DOMESTIC_APPROVER_NAMES } from "./PackingApproveConfirmModal";
import { getPackingEditOptions, approvalErrorText, type ApprovalCandidate, type DecisionKind, type ListingChoice } from "./packingApprovalApi";
export interface DecisionValues { qty?: number; customs: "default" | "declare" | "skip"; rwh?: string; note?: string; target?: string; edit_reason?: string; operatorName?: string; passcode?: string }
const choiceKey = (r: ListingChoice) => JSON.stringify([r.store_id, r.item_id, r.listing_version]);
interface Props { row: ApprovalCandidate | null; kind: DecisionKind; busy: boolean; scope: string; onCancel: () => void; onSubmit: (values: DecisionValues) => Promise<void> }
export default function PackingDecisionModal({ row, kind, busy, scope, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm<DecisionValues>();
  const options = useQuery({ queryKey: ["packing-edit-options", scope, row?.source_account_ref, row?.id], queryFn: ({ signal }) => getPackingEditOptions(row!, signal), enabled: !!row && kind === "approve", staleTime: 0 });
  const choices = options.data?.data.listings ?? [];
  const target = Form.useWatch("target", form);
  const chosen = choices.find((r) => choiceKey(r) === target);
  const edited = !!chosen && (chosen.store_id !== row?.store_id || chosen.item_id !== row?.item_id);
  useEffect(() => { if (row) { form.resetFields(); form.setFieldsValue({ qty: row.default_quantity ?? undefined, customs: row.manual_customs ?? "default" }); } }, [row, form]);
  useEffect(() => {
    const original = options.data?.data.listings.find((r) => r.store_id === row?.store_id && r.item_id === row?.item_id);
    if (original && !form.getFieldValue("target")) form.setFieldValue("target", choiceKey(original));
  }, [options.data, row, form]);
  const packingNumber = row?.pk?.trim();
  const approveTitle = packingNumber ? `修改打包单 ${packingNumber}` : "修改打包单";
  const rejectTitle = packingNumber ? `驳回 · ${packingNumber} · ${row?.sku}` : `驳回 · ${row?.sku ?? ""}`;
  return <Modal title={kind === "approve" ? approveTitle : rejectTitle} open={!!row} confirmLoading={busy}
    okText={kind === "reject" ? "提交" : undefined} cancelText={kind === "reject" ? "取消" : undefined}
    okButtonProps={{ disabled: kind === "approve" && (options.isFetching || !!options.error) }}
    cancelButtonProps={{ disabled: busy }} closable={!busy} maskClosable={!busy} onCancel={onCancel}
    onOk={() => { void form.validateFields().then(onSubmit).catch(() => undefined); }} destroyOnHidden>
    {kind === "approve" && <Alert type="info" showIcon message="写入本系统打包单，不创建领星海外仓备货单，不回写箱规" />}
    {kind === "approve" && <Typography.Paragraph>{row?.inbound_order_sn} / SKU：{row?.sku}（固定不可修改）</Typography.Paragraph>}
    {kind === "approve" && options.error && <Alert type="error" message={approvalErrorText(options.error)} action={<Button onClick={() => void options.refetch()}>重试</Button>} />}
    <Form form={form} layout="vertical">
      {kind === "approve" ? <>
        <Form.Item label="目标店铺 / ItemID" name="target" rules={[{ required: true, message: "请选择同SKU的有效商品" }]}>
          <Select loading={options.isFetching} showSearch optionFilterProp="label" options={choices.map((r) => ({ value: choiceKey(r), label: `${r.store_name ?? r.store_id} / ${r.item_id}${r.cross_store ? "（跨店铺）" : ""}`, disabled: r.cross_store && !options.data?.data.cross_store_proof_available }))} />
        </Form.Item>
        <Descriptions size="small" column={1} items={[{ key: "gtin", label: "GTIN（跟随Listing）", children: chosen?.gtin ?? "—" }, { key: "msku", label: "MSKU（跟随Listing）", children: chosen?.msku ?? "—" }]} />
        {chosen?.cross_store && <Alert type="info" message="以原入库单为分配依据，SKU与库存来源不变；仅调整目标店铺，不改写领星库存归属。" />}
        {chosen && chosen.gtin !== row?.gtin && <Alert type="warning" message="GTIN发生变化，仓库需要重新核对商品标签" />}
        <Form.Item label="商品身份修改原因" name="edit_reason" rules={[{ required: edited, whitespace: true, min: 2, max: 500, message: "修改商品身份须填写至少2字原因" }]}><Input.TextArea maxLength={500} /></Form.Item>
        <Form.Item label={`备货数量（可用 ${row?.available_quantity ?? "未知"}）`} name="qty" rules={[{ required: true, message: "请填写备货数量" }, { type: "integer", min: 1, max: Math.min(row?.available_quantity ?? 0, 1000000), message: "数量必须为可用范围内的正整数" }]}><InputNumber min={1} precision={0} max={row?.available_quantity ?? 0} /></Form.Item>
        <Form.Item label="是否报关" name="customs"><PackingCustomsSelect row={row} /></Form.Item>
      </> : <>
        <Form.Item label="姓名" name="operatorName" initialValue={DOMESTIC_APPROVER_NAMES[0]} rules={[{ required: true, message: "请选择姓名" }]}><Select options={DOMESTIC_APPROVER_NAMES.map((name) => ({ value: name, label: name }))} /></Form.Item>
        <Form.Item label="驳回原因" name="note" rules={[{ required: true, whitespace: true, message: "请填写驳回原因" }, { max: 500, message: "驳回原因不能超过 500 个字" }]}><Input.TextArea maxLength={500} rows={3} /></Form.Item>
        <Form.Item label="口令" name="passcode" rules={[{ required: true, whitespace: true, message: "请输入口令" }]}><Input.Password autoComplete="off" /></Form.Item>
      </>}
    </Form>
  </Modal>;
}
