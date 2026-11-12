/** 无 GTIN 费用的调整：改分摊（分到哪些商品、各多少，合计 = 原金额）或记公司；必填原因，留痕。 */
import { Alert, Button, Input, InputNumber, Modal, Radio, Space, Table, Typography, message } from "antd";
import { useState } from "react";
import { FinMoney } from "@/pages/finance/FinanceBoardFrame";
import type { Row } from "./FinanceWfsFeesPage";
import { adjustLine, wfsErrorText } from "./wfsFeesApi";

interface Share { key: string; gtin: string; item_id: string; msku: string; amount: number | null }

const round2 = (value: number) => Math.round(value * 100) / 100;

/** 每次打开都是新实例（外层按行 id 给 key），初值直接取自这一行，不用 effect 同步。 */
function AdjustModal({ row, onClose, onDone }: { row: Row; onClose: () => void; onDone: () => void }) {
  const [kind, setKind] = useState<"realloc" | "company">(row.attribution === "company" ? "company" : "realloc");
  const [shares, setShares] = useState<Share[]>(() => (row.children ?? []).map((c, i) => ({ key: `${i}`, gtin: c.gtin, item_id: c.item_id, msku: c.msku, amount: c.amount })));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [messageApi, messageHolder] = message.useMessage();
  const total = round2(shares.reduce((sum, s) => sum + (s.amount ?? 0), 0));
  const target = round2(row.amount ?? 0);
  const balanced = kind === "company" || (shares.length > 0 && Math.abs(total - target) < 0.005);
  const submit = async () => {
    setBusy(true);
    try {
      await adjustLine(row.id, {
        kind, reason,
        payload: kind === "realloc" ? { shares: shares.map((s) => ({ gtin: s.gtin.trim(), item_id: s.item_id.trim(), msku: s.msku.trim(), amount: (s.amount ?? 0).toFixed(2) })) } : {},
      });
      onDone();
    } catch (error) {
      void messageApi.error(wfsErrorText(error));
    } finally {
      setBusy(false);
    }
  };
  const edit = (key: string, patch: Partial<Share>) => setShares((current) => current.map((s) => (s.key === key ? { ...s, ...patch } : s)));
  return (
    <Modal open width={760} title={`调整归属 · ${row.storeCode} · ${row.typeName} · ${row.date_charged}`} okText="确定" cancelText="取消"
      okButtonProps={{ disabled: !reason.trim() || !balanced, loading: busy }} onOk={() => void submit()} onCancel={onClose} destroyOnHidden>
      {messageHolder}
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Typography.Text>原金额 <FinMoney value={row.amount} cur="USD" />；现在：{row.allocation_basis || row.attribution}</Typography.Text>
        <Radio.Group value={kind} onChange={(e) => setKind(e.target.value)}>
          <Radio value="realloc">分摊到商品</Radio>
          <Radio value="company">记公司（不分到商品）</Radio>
        </Radio.Group>
        {kind === "realloc" && (
          <>
            <Table<Share> size="small" bordered pagination={false} rowKey="key" dataSource={shares} columns={[
              { title: "GTIN", width: 160, render: (_, s) => <Input size="small" value={s.gtin} placeholder="有就填，自动带出商品" onChange={(e) => edit(s.key, { gtin: e.target.value })} /> },
              { title: "ITEM ID", width: 140, render: (_, s) => <Input size="small" value={s.item_id} onChange={(e) => edit(s.key, { item_id: e.target.value })} /> },
              { title: "MSKU", width: 160, render: (_, s) => <Input size="small" value={s.msku} onChange={(e) => edit(s.key, { msku: e.target.value })} /> },
              { title: "金额（USD）", width: 140, render: (_, s) => <InputNumber size="small" style={{ width: "100%" }} value={s.amount} precision={2} onChange={(value) => edit(s.key, { amount: value })} /> },
              { title: "", width: 60, render: (_, s) => <Button type="link" size="small" danger onClick={() => setShares((c) => c.filter((x) => x.key !== s.key))}>删</Button> },
            ]} />
            <Space>
              <Button size="small" onClick={() => setShares((c) => [...c, { key: crypto.randomUUID(), gtin: "", item_id: "", msku: "", amount: null }])}>加一行</Button>
              <Button size="small" disabled={!shares.length} onClick={() => setShares((c) => {
                const each = round2(target / c.length);
                return c.map((s, i) => ({ ...s, amount: i === c.length - 1 ? round2(target - each * (c.length - 1)) : each }));
              })}>平均分</Button>
              <Typography.Text type={balanced ? "secondary" : "danger"}>合计 {total.toFixed(2)} / 原金额 {target.toFixed(2)}{balanced ? "" : "，要相等"}</Typography.Text>
            </Space>
          </>
        )}
        <Input.TextArea autoFocus rows={3} maxLength={500} showCount placeholder="必填：原因（为什么这样分 / 为什么记公司）" value={reason} onChange={(e) => setReason(e.target.value)} />
        <Alert type="info" showIcon message="调整过的行以后重新导入不会被覆盖；要恢复自动规则，告诉管理员。" />
      </Space>
    </Modal>
  );
}

export default AdjustModal;