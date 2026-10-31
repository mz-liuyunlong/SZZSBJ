import PackingCustomsSelect from "./PackingCustomsSelect";
/** Edit a pending packing slip: ItemID search targets, optional split into several lines. */
import { Alert, Button, Descriptions, Form, Input, InputNumber, Modal, Select, Space, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { DOMESTIC_APPROVER_NAMES } from "./packingApproveConfirm";
import { approvalBlockedText, approvalErrorText, searchPackingListings, type ApprovalCandidate, type DecisionKind, type ListingHit } from "./packingApprovalApi";

export interface DraftLineValue { hit: ListingHit; qty: number }
export interface DecisionValues { qty?: number; customs: "default" | "declare" | "skip"; rwh?: string; note?: string; edit_reason?: string; operatorName?: string; passcode?: string; lines?: DraftLineValue[] }

export const MAX_SPLIT_LINES = 10;
const ITEM_ID_PATTERN = /^\d{4,20}$/;

interface LineState { key: number; hit?: ListingHit; qty?: number; options: ListingHit[]; searching: boolean; error?: string }

const hitKey = (hit: ListingHit) => JSON.stringify([hit.store_id, hit.item_id]);
const hitLabel = (hit: ListingHit) => `${hit.store_name ?? hit.store_id} / ${hit.item_id} / ${hit.msku ?? "无MSKU"} / ${hit.local_sku ?? "无本地SKU"}`;

/** Lines restored from a saved draft or the row's current identity. */
function initialLines(row: ApprovalCandidate | null): LineState[] {
  if (!row) return [];
  if (row.split_lines?.length) {
    return row.split_lines.map((line, index) => {
      const hit: ListingHit = { store_id: line.store_id, store_name: line.store_name, item_id: line.item_id, gtin: line.gtin, msku: line.msku, local_sku: row.sku,
        listing_version: line.listing_version, cross_store: line.store_id !== row.store_id, wfs_converted: true, usable: true, blocked_reasons: [] };
      return { key: index + 1, hit, qty: line.qty, options: [hit], searching: false };
    });
  }
  return [{ key: 1, qty: row.default_quantity ?? undefined, options: [], searching: false }];
}

interface Props {
  row: ApprovalCandidate | null;
  kind: DecisionKind;
  busy: boolean;
  scope: string;
  onCancel: () => void;
  onSubmit: (values: DecisionValues) => Promise<void>;
}
export default function PackingDecisionModal({ row, kind, busy, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm<DecisionValues>();
  const [lines, setLines] = useState<LineState[]>([]);
  const nextKey = useRef(2);
  const timers = useRef<Record<number, ReturnType<typeof setTimeout>>>({});
  const aborts = useRef<Record<number, AbortController>>({});
  const reason = Form.useWatch("edit_reason", form);
  useEffect(() => {
    if (!row) return undefined;
    form.resetFields();
    form.setFieldsValue({ customs: row.manual_customs ?? "default" });
    const restored = initialLines(row);
    nextKey.current = restored.length + 1;
    setLines(restored);
    if (kind !== "approve" || row.split_lines?.length || !row.item_id) return undefined;
    // Pre-select the row's current identity by looking it up like a typed search.
    const controller = new AbortController();
    const currentItem = row.item_id;
    setLines((current) => current.map((line) => (line.key === 1 ? { ...line, searching: true } : line)));
    searchPackingListings(row, currentItem, controller.signal)
      .then((result) => {
        const items = result.data.items;
        const current = items.find((hit) => hit.item_id === currentItem && hit.store_id === row.store_id) ?? items.find((hit) => hit.item_id === currentItem);
        setLines((existing) => existing.map((line) => (line.key === 1 && !line.hit ? { ...line, options: items, hit: current, searching: false } : line)));
      })
      .catch(() => { if (!controller.signal.aborted) setLines((existing) => existing.map((line) => (line.key === 1 ? { ...line, searching: false } : line))); });
    return () => controller.abort();
  }, [row, kind, form]);
  useEffect(() => {
    const pendingTimers = timers.current;
    const pendingRequests = aborts.current;
    return () => {
      Object.values(pendingTimers).forEach(clearTimeout);
      Object.values(pendingRequests).forEach((controller) => controller.abort());
    };
  }, []);

  const patch = (key: number, update: Partial<LineState>) => setLines((current) => current.map((line) => (line.key === key ? { ...line, ...update } : line)));
  const search = (key: number, text: string) => {
    const value = text.trim();
    clearTimeout(timers.current[key]);
    aborts.current[key]?.abort();
    if (!row || !ITEM_ID_PATTERN.test(value)) { patch(key, { searching: false, error: undefined }); return; }
    timers.current[key] = setTimeout(() => {
      const controller = new AbortController();
      aborts.current[key] = controller;
      patch(key, { searching: true, error: undefined });
      searchPackingListings(row, value, controller.signal)
        .then((result) => patch(key, { options: result.data.items, searching: false }))
        .catch((error: unknown) => { if (!controller.signal.aborted) patch(key, { searching: false, error: approvalErrorText(error) }); });
    }, 300);
  };
  const choose = (key: number, value: string) => {
    const line = lines.find((item) => item.key === key);
    patch(key, { hit: line?.options.find((hit) => hitKey(hit) === value) });
  };
  const addLine = () => setLines((current) => (current.length >= MAX_SPLIT_LINES ? current : [...current, { key: nextKey.current++, options: [], searching: false }]));
  const removeLine = (key: number) => setLines((current) => (current.length <= 1 ? current : current.filter((line) => line.key !== key)));

  const available = row?.available_quantity ?? 0;
  const total = lines.reduce((sum, line) => sum + (line.qty ?? 0), 0);
  const chosenKeys = lines.filter((line) => line.hit).map((line) => hitKey(line.hit!));
  const duplicated = new Set(chosenKeys).size !== chosenKeys.length;
  const incomplete = lines.some((line) => !line.hit || !line.qty || line.qty < 1);
  const unusable = lines.some((line) => line.hit && !line.hit.usable);
  const reasonMissing = (reason ?? "").trim().length < 2;
  const saveDisabled = kind === "approve" && (incomplete || unusable || duplicated || total > available || total < 1 || reasonMissing);

  const packingNumber = row?.pk?.trim();
  const approveTitle = packingNumber ? `修改打包单 ${packingNumber}` : "修改打包单";
  const rejectTitle = packingNumber ? `驳回 · ${packingNumber} · ${row?.sku}` : `驳回 · ${row?.sku ?? ""}`;
  const submit = () => {
    void form.validateFields().then((values) => {
      if (kind !== "approve") return onSubmit(values);
      if (saveDisabled) return undefined;
      return onSubmit({ ...values, qty: total, lines: lines.map((line) => ({ hit: line.hit!, qty: line.qty! })) });
    }).catch(() => undefined);
  };
  return <Modal title={kind === "approve" ? approveTitle : rejectTitle} open={!!row} width={kind === "approve" ? 760 : undefined} confirmLoading={busy}
    okText={kind === "approve" ? "保存" : "提交"} cancelText="取消"
    okButtonProps={{ disabled: saveDisabled }}
    cancelButtonProps={{ disabled: busy }} closable={!busy} maskClosable={!busy} onCancel={onCancel}
    onOk={submit} destroyOnHidden>
    {kind === "approve" && <Typography.Paragraph>{row?.inbound_order_sn} / SKU：{row?.sku}</Typography.Paragraph>}
    {kind === "approve" && <Typography.Paragraph type="secondary">输入 ItemID 搜索 Listing 管理里的在线商品；未完成 WFS 转换或属于其他 SKU 的不能保存。一票货可拆成多行（多个店铺 / ItemID），审批后每行生成一张独立打包单。</Typography.Paragraph>}
    <Form form={form} layout="vertical">
      {kind === "approve" ? <>
        {lines.map((line, index) => <div key={line.key} className="domestic-approval__split-line" data-testid="split-line">
          <Space align="start" wrap>
            <Form.Item label={lines.length > 1 ? `第 ${index + 1} 行 · 目标店铺 / ItemID` : "目标店铺 / ItemID"} required style={{ minWidth: 420 }}>
              <Select aria-label={`第 ${index + 1} 行 ItemID`} showSearch filterOption={false} allowClear loading={line.searching} placeholder="输入 ItemID 搜索（至少 4 位数字）"
                value={line.hit ? hitKey(line.hit) : undefined} onSearch={(text) => search(line.key, text)} onChange={(value: string | undefined) => (value ? choose(line.key, value) : patch(line.key, { hit: undefined }))}
                notFoundContent={line.searching ? "搜索中…" : "输入 ItemID 搜索"}
                options={line.options.map((hit) => ({ value: hitKey(hit), label: hitLabel(hit) }))} style={{ width: 420 }} />
            </Form.Item>
            <Form.Item label="数量" required>
              <InputNumber aria-label={`第 ${index + 1} 行数量`} min={1} precision={0} max={1000000} value={line.qty} onChange={(value) => patch(line.key, { qty: value ?? undefined })} style={{ width: 120 }} />
            </Form.Item>
            {lines.length > 1 && <Form.Item label=" "><Button aria-label={`删除第 ${index + 1} 行`} onClick={() => removeLine(line.key)}>删除</Button></Form.Item>}
          </Space>
          {line.error && <Alert type="error" message={line.error} />}
          {line.hit && <Descriptions size="small" column={3} items={[
            { key: "store", label: "店铺", children: line.hit.store_name ?? line.hit.store_id },
            { key: "msku", label: "MSKU（跟随Listing）", children: line.hit.msku ?? "—" },
            { key: "gtin", label: "GTIN（跟随Listing）", children: line.hit.gtin ?? "—" },
          ]} />}
          {line.hit && !line.hit.usable && <Alert type="error" showIcon message={approvalBlockedText(line.hit.blocked_reasons)} />}
          {line.hit?.usable && line.hit.gtin !== row?.gtin && <Alert type="warning" message="GTIN发生变化，仓库需要重新核对商品标签" />}
        </div>)}
        <Space style={{ marginBottom: 12 }}>
          <Button onClick={addLine} disabled={lines.length >= MAX_SPLIT_LINES}>添加一行（拆单）</Button>
          <Typography.Text type={total > available ? "danger" : undefined}>合计 {total} / 可用 {row?.available_quantity ?? "未知"}</Typography.Text>
        </Space>
        {duplicated && <Alert type="error" message="拆单的店铺 / ItemID 不能重复" />}
        {total > available && <Alert type="error" message="拆单数量合计超过可用库存" />}
        <Form.Item label="修改原因" name="edit_reason" rules={[{ required: true, whitespace: true, min: 2, max: 500, message: "修改原因必填（至少2个字）" }]}>
          <Input.TextArea maxLength={500} rows={3} placeholder="例：客户要求分两批 / 换店铺发" />
        </Form.Item>
        <Form.Item label="是否报关" name="customs"><PackingCustomsSelect row={row} /></Form.Item>
      </> : <>
        <Form.Item label="姓名" name="operatorName" initialValue={DOMESTIC_APPROVER_NAMES[0]} rules={[{ required: true, message: "请选择姓名" }]}><Select options={DOMESTIC_APPROVER_NAMES.map((name) => ({ value: name, label: name }))} /></Form.Item>
        <Form.Item label="驳回原因" name="note" rules={[{ required: true, whitespace: true, message: "请填写驳回原因" }, { max: 500, message: "驳回原因不能超过 500 个字" }]}><Input.TextArea maxLength={500} rows={3} /></Form.Item>
        <Form.Item label="口令" name="passcode" rules={[{ required: true, whitespace: true, message: "请输入口令" }]}><Input.Password autoComplete="off" /></Form.Item>
      </>}
    </Form>
  </Modal>;
}
