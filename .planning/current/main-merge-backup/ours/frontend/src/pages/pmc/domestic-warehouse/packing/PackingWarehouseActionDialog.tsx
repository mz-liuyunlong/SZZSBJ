/** Load the latest order/version before editing; a failed request never closes the form. */
import { Alert, Button, Descriptions, Form, Input, Modal, Select, Skeleton } from "antd";
import { useQuery } from "@tanstack/react-query";
import PackingWarehouseBoxForm from "./PackingWarehouseBoxForm";
import PackingOverpackFields from "./PackingOverpackFields";
import PackingPackageFields from "./PackingPackageFields";
import { getWarehouseOrder, warehouseError, warehouseReason, warehouseSyncLabel } from "./packingWarehouseApi";
import { noteCategories, type BoxInput, type PackageData, type PackingWarehouseRow, type WarehouseAction, type WarehouseFields } from "./packingWarehouseTypes";
interface Values { inbound_order_sn?: string; confirm_extra?: boolean; action?: "resend" | "void"; reason_category?: "shortage" | "damage" | "box_capacity" | "other"; lines: BoxInput[]; reason?: string; measure_package?: boolean; package?: PackageData; category?: WarehouseFields["category"]; text?: string }
type DialogAction = Exclude<WarehouseAction, "customs">;
interface Props { id: string; kind: DialogAction; scope: string; busy: boolean; onCancel: () => void; onSubmit: (row: PackingWarehouseRow, action: WarehouseAction, fields: WarehouseFields) => Promise<void> }
const titles: Record<DialogAction, string> = { boxes: "填写装箱数据", done: "确认打包完成", notes: "填写延迟备注", unpacked: "处置未装数量", rebox: "改装箱（已完成单）", "supplemental-inbound": "已补入库单", "supplemental-sync": "同步校验补入库单" };
function ActionForm({ row, kind, busy, onCancel, onSubmit }: Omit<Props, "id" | "scope"> & { row: PackingWarehouseRow }) {
  const [form] = Form.useForm<Values>();
  const watchedLines = Form.useWatch("lines", form) as BoxInput[] | undefined;
  const packed = kind === "rebox" ? (watchedLines ?? row.box_set?.lines ?? []).reduce((sum, line) => sum + Number(line.boxes ?? 0) * Number(line.units_per_box ?? 0), 0) : row.box_set?.total_qty ?? 0;
  const measured = row.box_set?.package_snapshot?.source === "warehouse_draft";
  const needsPackage = kind === "done" && row.product_requirement.state !== "complete";
  const submit = async () => {
    const values = await form.validateFields();
    let fields: WarehouseFields;
    if (kind === "boxes" || kind === "rebox") fields = { ...(kind === "rebox" ? { confirm_extra: values.confirm_extra ?? false, expected_box_version: row.box_set!.version, reason_category: values.reason_category } : {}), lines: values.lines.map((line) => ({ box_type: line.box_type, boxes: line.boxes, units_per_box: line.units_per_box, gross_weight_kg: line.gross_weight_kg, ...(line.box_type === "custom" ? { length_cm: line.length_cm, width_cm: line.width_cm, height_cm: line.height_cm } : {}) })), reason: values.reason?.trim() || undefined, ...(values.measure_package ? { package: values.package } : {}) };
    else if (kind === "done") fields = { confirm_extra: values.confirm_extra ?? false, reason_category: values.reason_category, reason: values.reason?.trim() || undefined, expected_box_version: row.box_set!.version, requirement_version: row.product_requirement.version, ...(needsPackage ? { package: values.package } : {}) };
    else if (kind === "supplemental-inbound") fields = { inbound_order_sn: values.inbound_order_sn?.trim().toUpperCase() };
    else if (kind === "supplemental-sync") fields = {};
    else if (kind === "unpacked") fields = { action: values.action, reason: values.reason?.trim() };
    else fields = { category: values.category, text: values.text?.trim() ?? "" };
    await onSubmit(row, kind, fields);
  };
  const reasons = row.completion_blocked_reasons.filter((r) => r !== "PACKAGE_REQUIRED");
  return <Modal title={titles[kind]} open width={kind === "boxes" || kind === "rebox" ? 820 : 620} okText={kind === "done" ? "确认完成" : "保存"} cancelText="取消" confirmLoading={busy} closable={!busy} maskClosable={!busy} cancelButtonProps={{ disabled: busy }} onCancel={onCancel}
    okButtonProps={{ disabled: kind === "done" && reasons.length > 0 }} onOk={() => { void submit().catch(() => undefined); }}>
    <Descriptions size="small" column={2} items={[{ key: "pk", label: "打包单", children: row.pk }, { key: "sku", label: "SKU", children: row.sku }, { key: "qty", label: "审批数量", children: row.approved_quantity }, { key: "v", label: "版本", children: row.version }]} />
    {kind === "done" && reasons.length > 0 && <Alert type="warning" message={reasons.map(warehouseReason).join("；")} />}
    <Form form={form} layout="vertical" initialValues={{ inbound_order_sn: row.variance_case?.supplemental_ib ?? undefined, lines: (kind === "rebox" && row.variance_case?.proposed_lines ? row.variance_case.proposed_lines : row.box_set?.lines)?.map((line) => ({ ...line, gross_weight_kg: Number(line.gross_weight_kg), length_cm: Number(line.length_cm), width_cm: Number(line.width_cm), height_cm: Number(line.height_cm) })) ?? [{ box_type: "A", boxes: 1, units_per_box: Math.min(row.approved_quantity, 100000) }], reason: kind === "boxes" ? row.box_set?.variance_reason ?? undefined : undefined, measure_package: measured, package: row.box_set?.package_snapshot?.values ? Object.fromEntries(Object.entries(row.box_set.package_snapshot.values).map(([k, v]) => [k, v === null ? undefined : Number(v)])) : undefined }}>
      {(kind === "boxes" || kind === "rebox") && <PackingWarehouseBoxForm row={row} form={form} hideReason={kind === "rebox"} />}
      {kind === "rebox" && <><Alert type="warning" message="将重新校验装箱，保留原完成时间并记录修改前后明细；不会再次完成本 PK。" />
        <Form.Item name="reason" label="改装箱原因" rules={[{ required: true, whitespace: true, min: 2, max: 500 }]}><Input.TextArea rows={2} maxLength={500} /></Form.Item>
        <Form.Item name="reason_category" label="如改后少装，请选择少装原因"><Select allowClear options={[{ value: "shortage", label: "实物短少" }, { value: "damage", label: "破损" }, { value: "box_capacity", label: "装不下箱" }, { value: "other", label: "其他" }]} /></Form.Item></>}
      {(kind === "done" || kind === "rebox") && <PackingOverpackFields excess={Math.max(0, packed - row.approved_quantity)} available={row.extra_available} rebox={kind === "rebox"} />}
      {kind === "supplemental-inbound" && <><Alert type="info" message="请先在领星手工补建入库单，再登记 IB 号；此操作不代表校验通过。" /><Form.Item name="inbound_order_sn" label="补入库单号" rules={[{ required: true, whitespace: true, pattern: /^IB[A-Z0-9_-]{1,62}$/ }]}><Input maxLength={64} placeholder="IB..." /></Form.Item></>}
      {kind === "supplemental-sync" && <Alert type="info" message={`补入库单：${row.variance_case?.supplemental_ib ?? "未登记"}`} description={`${warehouseSyncLabel(row.variance_case?.last_sync_code)}。真实领星同步当前未配置；校验通过仅解除阻塞，仍需仓库再次确认。`} />}
      {kind === "done" && <>
        {row.box_set && row.box_set.total_qty < row.approved_quantity && <>
          <Alert type="warning" message={`未装 ${row.approved_quantity - row.box_set.total_qty} 件，完成后待中台处理；本 PK 不再二次完成。`} />
          <Form.Item name="reason_category" label="少装原因" rules={[{ required: true }]}><Select options={[{ value: "shortage", label: "实物短少" }, { value: "damage", label: "破损" }, { value: "box_capacity", label: "装不下箱" }, { value: "other", label: "其他" }]} /></Form.Item>
          <Form.Item noStyle shouldUpdate={(a, b) => a.reason_category !== b.reason_category}>{({ getFieldValue }) => <Form.Item name="reason" label="原因说明" rules={[{ required: getFieldValue("reason_category") === "other", whitespace: true, min: getFieldValue("reason_category") === "other" ? 2 : undefined, max: 500 }]}><Input.TextArea rows={2} maxLength={500} /></Form.Item>}</Form.Item>
        </>}
        <Alert type="info" message="完成后装箱冻结，进入已打包待发；本操作不代表发货，不写领星。" />{needsPackage ? <><Alert type="warning" message="产品包装资料缺失或未知，请补填单品尺寸和毛重" /><PackingPackageFields /></> : <p>产品包装资料完整，将随完成记录保存快照。</p>}</>}
      {kind === "unpacked" && <>
        <Alert type="warning" message={`未装 ${row.variance_case?.quantity ?? 0} 件`} description="下次再发：释放未装占用，后续须重新审批新 PK；作废未装：填写原因并终结未装任务，保留库存排除占用，不改领星库存。" />
        <Form.Item name="action" label="处置方式" rules={[{ required: true }]}><Select options={[{ value: "resend", label: "下次再发" }, { value: "void", label: "作废未装" }]} /></Form.Item>
        <Form.Item noStyle shouldUpdate={(a, b) => a.action !== b.action}>{({ getFieldValue }) => <Form.Item name="reason" label="处置原因" rules={[{ required: getFieldValue("action") === "void", whitespace: true, min: getFieldValue("action") === "void" ? 2 : undefined, max: 500 }]}><Input.TextArea rows={2} maxLength={500} /></Form.Item>}</Form.Item>
      </>}
      {kind === "notes" && <><Form.Item name="category" label="原因分类" rules={[{ required: true }]}><Select options={noteCategories.map((item) => ({ ...item, disabled: item.value === "resolved" && (!row.current_note || row.current_note.resolved) }))} /></Form.Item><Form.Item noStyle shouldUpdate={(before, after) => before.category !== after.category}>{({ getFieldValue }) => <Form.Item name="text" label="说明" rules={[{ required: getFieldValue("category") === "other", whitespace: true, min: getFieldValue("category") === "other" ? 2 : undefined, max: 500 }]}><Input.TextArea rows={3} maxLength={500} /></Form.Item>}</Form.Item></>}
    </Form>
  </Modal>;
}
export default function PackingWarehouseActionDialog(props: Props) {
  const detail = useQuery({ queryKey: ["domestic-packing-warehouse", props.scope, "detail", props.id], queryFn: ({ signal }) => getWarehouseOrder(props.id, signal), staleTime: 0, refetchOnWindowFocus: false });
  if (!detail.data || detail.error) return <Modal title={titles[props.kind]} open footer={null} onCancel={props.onCancel}>{detail.error ? <Alert type="error" message={warehouseError(detail.error)} action={<Button onClick={() => void detail.refetch()}>重试</Button>} /> : <Skeleton active />}</Modal>;
  return <ActionForm key={`${detail.data.data.id}:${detail.data.data.version}`} row={detail.data.data} kind={props.kind} busy={props.busy} onCancel={props.onCancel} onSubmit={props.onSubmit} />;
}
