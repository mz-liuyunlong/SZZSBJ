/** Count selection stays independent from editing warehouse packing facts. */
import { Alert, Button, Checkbox, Form, InputNumber, Modal, Space, Table, Typography } from "antd";
import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { allocationPreview, createShipments, getCreationCapabilities, optionalPreview, type AllocationInput, type AllocationPreview, type CreationInput, type CreationOperation } from "./creationApi";
import { pendingError } from "./pendingPackingApi";
import type { PendingRow } from "./pendingPackingTypes";

// Owner decisions 2026-10-31: return address = store default (not asked), expected delivery =
// Beijing today + 30 days (server side), ITS on by default (store must be marked ITS-capable).
interface Values { its: boolean }
export default function CreationDialog({ rows, scope, canProbe, onCancel, onCreated }: {
  rows: PendingRow[]; scope: string; canProbe: boolean; onCancel: () => void;
  onCreated: (result: CreationOperation) => void;
}) {
  const row = rows[0];
  const availableBoxes = rows.reduce((sum, r) => sum + r.available_boxes, 0);
  const [form] = Form.useForm<Values>();
  const [boxes, setBoxes] = useState(Math.min(availableBoxes, 9999));
  const [counts, setCounts] = useState([Math.min(availableBoxes, 9999)]);
  const [preview, setPreview] = useState<AllocationPreview>();
  const [probe, setProbe] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const key = useRef<{ signature: string; key: string } | undefined>(undefined);
  const capabilities = useQuery({ queryKey: ["wfs-creation-capabilities", scope], queryFn: ({ signal }) => getCreationCapabilities(signal) });
  const valid = Number.isInteger(boxes) && boxes > 0 && boxes <= Math.min(availableBoxes, 9999) && counts.every((n) => Number.isInteger(n) && n > 0) && counts.reduce((a, b) => a + b, 0) === boxes;
  const invalidate = () => { setPreview(undefined); setProbe(undefined); };
  const input = (): AllocationInput => ({ order_id: row.order.id, expected_version: row.order.version, expected_box_version: row.order.box_set!.version, additional_selections: rows.slice(1).map((r) => ({ order_id: r.order.id, expected_version: r.order.version, expected_box_version: r.order.box_set!.version })), shipping_boxes: boxes, shipment_count: counts.length, shipment_boxes: counts });
  const perform = async (action: () => Promise<void>) => {
    setBusy(true); setError(undefined);
    try { await action(); } catch (e) { if (!(e && typeof e === "object" && "errorFields" in e)) setError(pendingError(e)); }
    finally { setBusy(false); }
  };
  const body = async (): Promise<CreationInput> => {
    const { its } = await form.validateFields();
    const data = { ...input(), source_account_ref: row.order.source_account_ref, preview_hash: preview!.preview_hash, its };
    const signature = JSON.stringify(data);
    if (key.current?.signature !== signature) key.current = { signature, key: crypto.randomUUID() };
    return { ...data, idempotency_key: key.current.key };
  };
  return <Modal open width={920} title={`创建 WFS 货件 · ${rows.map((r) => r.order.pk).join("、")}`} onCancel={onCancel} closable={!busy} maskClosable={!busy} footer={<Space>
    <Button disabled={busy} onClick={onCancel}>取消</Button>
    {canProbe && <Button disabled={!preview || !capabilities.data?.data.preview_enabled} loading={busy} onClick={() => void perform(async () => { const result = await optionalPreview(await body()); setProbe(`探测时间 ${new Date().toLocaleString("zh-CN", { timeZone: "Asia/Taipei" })}：${JSON.stringify(result.data.result)}`); })}>按需探测</Button>}
    <Button aria-label="确认创建" type="primary" disabled={busy || !valid || !preview || !capabilities.data?.data.creation_enabled} loading={busy} onClick={() => void perform(async () => { const result = await createShipments(await body()); onCreated(result.data); })}>确认创建</Button>
  </Space>}>
    <Typography.Paragraph>选择本次发货箱数和分票方式，核对每票实际箱子后确认创建。无需 OWS，程序校验通过后自动审批并执行，探测可选。</Typography.Paragraph>
    {capabilities.data?.data.reason && <Alert type="info" showIcon message={capabilities.data.data.reason} />}
    {(error || capabilities.error) && <Alert type="error" showIcon message={error ?? pendingError(capabilities.error)} />}
    <Space wrap style={{ marginBlock: 16 }}>
      <label>本次发货箱数 <InputNumber aria-label="本次发货箱数" min={1} max={Math.min(availableBoxes, 9999)} precision={0} value={boxes} disabled={busy} onChange={(v) => { setBoxes(v ?? 0); invalidate(); }} /></label>
      <label>计划货件数量 <InputNumber aria-label="计划货件数量" min={1} max={Math.min(boxes, 9999)} precision={0} value={counts.length} disabled={busy} onChange={(v) => { if (v && Number.isInteger(v) && v <= boxes) { setCounts(Array.from({ length: v }, (_, i) => Math.floor(boxes / v) + (i < boxes % v ? 1 : 0))); invalidate(); } }} /></label>
      <Button disabled={!valid || busy} onClick={() => void perform(async () => { setPreview((await allocationPreview(input())).data); })}>核对分箱</Button>
    </Space>
    <Table size="small" pagination={false} rowKey="number" dataSource={counts.map((n, i) => ({ number: i + 1, boxes: n }))} columns={[
      { title: "计划货件", dataIndex: "number" },
      { title: "箱数", render: (_, r) => <InputNumber aria-label={`货件${r.number}箱数`} min={1} precision={0} value={r.boxes} disabled={busy} onChange={(v) => { setCounts((old) => old.map((n, i) => i === r.number - 1 ? v ?? 0 : n)); invalidate(); }} /> },
      { title: "商品件数", render: (_, r) => preview?.tickets[r.number - 1]?.units ?? "待核对" },
      { title: "实际箱范围及箱规", render: (_, r) => preview?.tickets[r.number - 1]?.ranges.map((range) => <div key={`${range.line_id}-${range.start}`}>{range.pk} · {range.sku} · 第{range.line_no}行，第{range.start}–{range.end}箱：{range.boxes}箱×{range.units_per_box}件；{range.length_cm}×{range.width_cm}×{range.height_cm} cm / {range.gross_weight_kg} kg</div>) ?? "待核对" },
    ]} />
    <Typography.Paragraph type={valid ? undefined : "danger"}>已分配 {counts.reduce((a, b) => a + b, 0)} / 本次 {boxes} 箱；当前可发 {availableBoxes} 箱{preview ? `，本次安排后剩余 ${preview.remaining_boxes} 箱` : ""}</Typography.Paragraph>
    <Form form={form} layout="vertical" initialValues={{ its: true }} disabled={busy} onValuesChange={() => setProbe(undefined)}>
      <Form.Item name="its" valuePropName="checked" extra="默认走 ITS（转运中心，一票一张货件）；店铺需已在 WFS 设置中确认 ITS 可用。取消勾选则由 Walmart 按仓拆成多张货件。"><Checkbox>使用 ITS</Checkbox></Form.Item>
    </Form>
    <Typography.Paragraph type="secondary">退货地址使用店铺在 Walmart 的默认地址；预计到仓日期按北京时间今天 +30 天自动填写。</Typography.Paragraph>
    {probe && <Alert type="info" message="分仓预览，不保证最终仓库" description={probe} />}
    <Alert type="info" message="计划拆票数量与 Walmart 最终返回的实际货件数量可能不同。提交后结果未知时请在创建记录中核实，勿重复创建。" />
  </Modal>;
}
