/**
 * 录成本 / 确认（PRP §8.4）：范围 = MSKU × 发货单 / 出库单 / 平台订单号（自发货订单、流水没覆盖的差额），一次录入覆盖范围内所有订单行（含跨期）。
 * - 确认（confirm）：接受系统预填的四项（领星发货单值）；
 * - 修正（override）：改值，原因必填，系统提示同时去领星改；不回写领星。
 * 撤销一条录入 → 受影响的行退回待审并重算。
 */
import { Alert, Button, Drawer, Form, Input, InputNumber, Radio, Select, Space, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";
import { SOURCE_KIND_TEXT, errorText, getCostEntry, postCostEntry, revokeCostEntry, type ApiCostSource, type ApiLine } from "./orderReviewApi";

interface Scope { msku: string; shipping_list_code?: string | null; outbound_order_no?: string | null; platform_order_no?: string | null; label: string; source: ApiCostSource }

const SCOPE_LABEL: Record<string, string> = { shipping: "发货单", outbound: "出库单", order: "平台订单" };

function scopesOf(line: ApiLine): Scope[] {
  const out: Scope[] = [];
  const seen = new Set<string>();
  for (const source of line.cost_sources) {
    const msku = source.msku ?? line.msku;
    const scope = source.scope_ref ?? "";
    if (!msku || !scope) continue;
    const [prefix, ref] = scope.split(":", 2);
    if (!ref || !SCOPE_LABEL[prefix]) continue;
    // 自发货订单各段共用一个范围（MSKU × 平台订单号），只列一次
    if (seen.has(`${msku}|${scope}`)) continue;
    seen.add(`${msku}|${scope}`);
    const base = { msku, label: `${msku} × ${SCOPE_LABEL[prefix]} ${ref}（${SOURCE_KIND_TEXT[source.kind] ?? source.kind}）`, source };
    if (prefix === "shipping") out.push({ ...base, shipping_list_code: ref });
    else if (prefix === "outbound") out.push({ ...base, outbound_order_no: ref });
    else out.push({ ...base, platform_order_no: ref });
  }
  return out;
}

const num = (value?: string | null) => (value == null || value === "" ? undefined : Number(value));

function CostEntryDrawer({ line, onClose, onDone }: { line?: ApiLine; onClose: () => void; onDone: () => void }) {
  const [form] = Form.useForm();
  const [messageApi, holder] = message.useMessage();
  const [busy, setBusy] = useState(false);
  const [scopeIndex, setScopeIndex] = useState(0);
  const scopes = useMemo(() => (line ? scopesOf(line) : []), [line]);
  const scope = scopes[scopeIndex];
  const seller = line?.fulfillment_type === "seller";

  // 父组件按 review_id 给 key，换一行就重新挂载，scopeIndex 自然回到 0
  useEffect(() => {
    if (!scope) return;
    const prefill = scope.source.prefill ?? {};
    const head = scope.source.head_cny ?? (prefill.head_cny ?? null);
    form.setFieldsValue({
      entry_kind: scope.source.entry_id ? "override" : "confirm",
      purchase_cny: num(scope.source.purchase_cny ?? prefill.purchase_price ?? prefill.purchase_cny),
      head_cny: num(head),
      last_leg_cny: num(scope.source.last_leg_cny ?? scope.source.last_leg_prefill_cny),
      reason: "",
    });
  }, [form, scope]);

  if (!line) return null;
  const existingEntry = scope?.source.entry_id ?? null;

  const submit = async () => {
    if (!scope) return;
    const values = await form.validateFields();
    setBusy(true);
    try {
      const result = await postCostEntry(
        {
          store_id: line.store_id,
          scope: { msku: scope.msku, shipping_list_code: scope.shipping_list_code ?? null, outbound_order_no: scope.outbound_order_no ?? null, platform_order_no: scope.platform_order_no ?? null },
          entry_kind: values.entry_kind,
          purchase_cny: values.purchase_cny == null ? null : String(values.purchase_cny),
          head_cny: values.head_cny == null ? null : String(values.head_cny),
          last_leg_cny: seller && values.last_leg_cny != null ? String(values.last_leg_cny) : null,
          reason: values.reason?.trim() || null,
        },
        crypto.randomUUID(),
      );
      void messageApi.success(`已${values.entry_kind === "confirm" ? "确认" : "修正"}，影响 ${result.affected_lines} 行、重算 ${result.recalculated_periods} 期${values.entry_kind === "override" ? "；请同时去领星把发货单的值改掉" : ""}`);
      onDone();
      onClose();
    } catch (e) {
      void messageApi.error(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const revoke = async () => {
    if (!existingEntry) return;
    const reason = window.prompt("撤销原因（必填）");
    if (!reason?.trim()) return;
    setBusy(true);
    try {
      const entry = await getCostEntry(existingEntry);
      const result = await revokeCostEntry(existingEntry, reason.trim(), entry.version);
      void messageApi.success(`已撤销，影响 ${result.affected_lines} 行，退回待审`);
      onDone();
      onClose();
    } catch (e) {
      void messageApi.error(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer open title={`录成本 · ${line.platform_order_no} / ${line.order_line_no}`} width={520} onClose={onClose} destroyOnHidden
      footer={<Space>
        <Button onClick={onClose}>取消</Button>
        {existingEntry && <Button danger loading={busy} onClick={() => void revoke()}>撤销已有录入</Button>}
        <Button type="primary" loading={busy} disabled={!scope || !!existingEntry} onClick={() => void submit()}>保存</Button>
      </Space>}>
      {holder}
      {!scopes.length && <Alert type="warning" showIcon message="这一行没有可录入的范围（退款冲回行或取消退款行不用录成本）" />}
      {scopes.length > 0 && (
        <Form form={form} layout="vertical">
          <Form.Item label="范围（MSKU × 单据，一次录入覆盖范围内所有订单行，含跨期）">
            <Select value={scopeIndex} onChange={setScopeIndex} options={scopes.map((s, index) => ({ value: index, label: s.label }))} />
          </Form.Item>
          {scope?.source.outbound_order_nos && <Typography.Paragraph type="secondary">出库单：{scope.source.outbound_order_nos.length ? scope.source.outbound_order_nos.join("、") : "没找到本 MSKU 的出库单"}{scope.source.last_leg_msku_total_cny ? ` · 本 MSKU 运费合计 ¥${scope.source.last_leg_msku_total_cny}` : ""}{scope.source.last_leg_note ? "（尾程没法预填，请手填）" : ""}</Typography.Paragraph>}
          {scope?.source.logistics_provider_name && <Typography.Paragraph type="secondary">物流商：{scope.source.logistics_provider_name}{scope.source.logistics_way ? ` · ${scope.source.logistics_way}` : ""}</Typography.Paragraph>}
          {scope?.source.prefill && (
            <Typography.Paragraph type="secondary">
              领星发货单：采购价 {scope.source.prefill.purchase_price ?? "—"} · 出库头程 {scope.source.prefill.head_stock_price ?? "—"} · 头程费用 {scope.source.prefill.per_firstlet_cost ?? "—"} · 税 {scope.source.prefill.per_tax ?? "—"} · 单位成本 {scope.source.prefill.wfs_stock_price ?? "—"}（{scope.source.prefill.currency_code ?? "?"}）
            </Typography.Paragraph>
          )}
          {existingEntry && <Alert type="info" showIcon style={{ marginBottom: 12 }} message="这个范围已有一条录入；要改值先撤销它" />}
          <Form.Item name="entry_kind" label="方式" rules={[{ required: true }]}>
            <Radio.Group options={[{ value: "confirm", label: "确认（接受领星值）" }, { value: "override", label: "修正（改值，原因必填）" }]} />
          </Form.Item>
          <Form.Item name="purchase_cny" label="采购价（¥ / 件）" rules={[{ required: true, message: "必填" }]}>
            <InputNumber min={0} precision={4} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="head_cny" label="头程（¥ / 件，= 出库头程 + 头程费用 + 税）" rules={[{ required: true, message: "必填" }]}>
            <InputNumber min={0} precision={4} style={{ width: "100%" }} />
          </Form.Item>
          {seller && (
            <Form.Item name="last_leg_cny" label="尾程（¥ / 件；自发货订单，预填销售出库单物流费用）" rules={[{ required: true, message: "必填" }]}>
              <InputNumber min={0} precision={4} style={{ width: "100%" }} />
            </Form.Item>
          )}
          <Form.Item noStyle shouldUpdate={(prev, next) => prev.entry_kind !== next.entry_kind}>
            {({ getFieldValue }) => getFieldValue("entry_kind") === "override" && (
              <Form.Item name="reason" label="修正原因（必填；系统不回写领星，请同时去领星改）" rules={[{ required: true, message: "必填" }]}>
                <Input.TextArea rows={3} maxLength={2000} />
              </Form.Item>
            )}
          </Form.Item>
        </Form>
      )}
    </Drawer>
  );
}

export default CostEntryDrawer;
