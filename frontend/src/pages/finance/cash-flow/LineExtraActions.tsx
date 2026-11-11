/**
 * 日记账 Rocky 11-10 新加的两个动作：
 * - 关闭异常：确认不用处理的异常写原因关掉（只在接口版；现在只有管理员能用），关掉的可以在「已关闭」里重新打开；
 * - 改折人民币：外币付款按约定汇率、每笔不同，财务直接填人民币金额，必须写原因；改了退回待初审。
 */
import { Button, Input, InputNumber, List, Modal, Space, Tag, Typography, message } from "antd";
import { useState } from "react";
import { cashErrorText, postLineEvent, useAlertClosureActions, useRefreshJournal, type AlertClosure, type LiveCashLine } from "@/pages/finance/cash-flow/journalApi";
import { alertShort, type CashAlert } from "@/pages/finance/cash-flow/data";

export function AlertCloseButton({ alert }: { alert: CashAlert }) {
  const { close } = useAlertClosureActions();
  const [messageApi, holder] = message.useMessage();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const submit = async () => {
    try {
      await close.mutateAsync({ alert_key: alert.id, alert_type: alert.type, reason: reason.trim() });
      void messageApi.success("已关闭这条异常");
      setOpen(false);
      setReason("");
    } catch (error) {
      void messageApi.error(cashErrorText(error));
    }
  };
  return (
    <>
      {holder}
      <Button size="small" onClick={() => setOpen(true)}>关闭异常</Button>
      <Modal open={open} title={`关闭异常 · ${alertShort(alert.type)}`} okText="关闭" cancelText="取消" confirmLoading={close.isPending} okButtonProps={{ disabled: !reason.trim() }}
        onOk={() => void submit()} onCancel={() => { setOpen(false); setReason(""); }} destroyOnHidden>
        <Typography.Paragraph type="secondary">{alert.msg}</Typography.Paragraph>
        <Input.TextArea autoFocus rows={3} maxLength={500} showCount placeholder="必填：为什么不用处理（例如：9 月流水没导入，这笔剔除在 9 月已处理）" value={reason} onChange={(event) => setReason(event.target.value)} />
      </Modal>
    </>
  );
}

export function ClosedAlertsButton({ closures }: { closures: AlertClosure[] }) {
  const { reopen } = useAlertClosureActions();
  const [messageApi, holder] = message.useMessage();
  const [open, setOpen] = useState(false);
  const [reopening, setReopening] = useState<AlertClosure>();
  const [reason, setReason] = useState("");
  if (!closures.length) return null;
  const submit = async () => {
    if (!reopening) return;
    try {
      await reopen.mutateAsync({ alert_key: reopening.alert_key, reason: reason.trim() });
      void messageApi.success("已重新打开");
      setReopening(undefined);
      setReason("");
    } catch (error) {
      void messageApi.error(cashErrorText(error));
    }
  };
  return (
    <>
      {holder}
      <Button size="small" type="link" onClick={() => setOpen(true)}>已关闭的异常（{closures.length}）</Button>
      <Modal open={open} width={720} title="已关闭的异常" footer={null} onCancel={() => setOpen(false)} destroyOnHidden>
        <List size="small" dataSource={closures} renderItem={(item) => (
          <List.Item actions={[<Button key="reopen" size="small" onClick={() => setReopening(item)}>重新打开</Button>]}>
            <Space direction="vertical" size={0}>
              <Space size={6}><Tag bordered={false}>{alertShort(item.alert_type)}</Tag><Typography.Text type="secondary">{item.alert_key}</Typography.Text></Space>
              <Typography.Text>原因：{item.reason}</Typography.Text>
              <Typography.Text type="secondary">{item.closed_by} · {new Date(item.closed_at).toLocaleString("zh-CN", { hour12: false })}</Typography.Text>
            </Space>
          </List.Item>
        )} />
      </Modal>
      <Modal open={Boolean(reopening)} title="重新打开这条异常" okText="重新打开" cancelText="取消" confirmLoading={reopen.isPending} okButtonProps={{ disabled: !reason.trim() }}
        onOk={() => void submit()} onCancel={() => { setReopening(undefined); setReason(""); }} destroyOnHidden>
        <Input.TextArea autoFocus rows={3} maxLength={500} showCount placeholder="必填：为什么重新打开" value={reason} onChange={(event) => setReason(event.target.value)} />
      </Modal>
    </>
  );
}

export function CnyEditButton({ line }: { line: LiveCashLine }) {
  const refresh = useRefreshJournal();
  const [messageApi, holder] = message.useMessage();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [amount, setAmount] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  if (line.cur === "CNY" || line.cur === "CNH") return null;
  const manual = line.fxSource === "manual";
  const send = async (payload: Record<string, unknown>, why: string | undefined, done: string) => {
    setBusy(true);
    try {
      const result = await postLineEvent(line, "set_cny", { payload, reason: why });
      void messageApi.success(done);
      if (result.auto_reset) void messageApi.info("这笔已审过，改动后自动退回待初审");
      setOpen(false);
      setAmount(null);
      setReason("");
    } catch (error) {
      void messageApi.error(cashErrorText(error));
    }
    setBusy(false);
    void refresh();
  };
  const rate = amount && line.amt ? (amount / Math.abs(line.amt)).toFixed(4) : null;
  return (
    <>
      {holder}
      <Space size={4}>
        <Button size="small" type="link" onClick={() => { setAmount(line.cny == null ? null : Math.abs(line.cny)); setOpen(true); }}>改折人民币</Button>
        {manual && <Button size="small" type="link" danger loading={busy} onClick={() => void send({ amount_cny: null }, undefined, "已恢复系统折算")}>恢复系统折算</Button>}
      </Space>
      <Modal open={open} title="改折人民币" okText="保存" cancelText="取消" confirmLoading={busy} okButtonProps={{ disabled: !amount || amount <= 0 || !reason.trim() }}
        onOk={() => void send({ amount_cny: amount?.toFixed(2) }, reason.trim(), "已改折人民币")} onCancel={() => setOpen(false)} destroyOnHidden>
        <Typography.Paragraph type="secondary">这笔 {line.cur} {Math.abs(line.amt ?? 0).toFixed(2)}。填实际的人民币金额（正数），按约定汇率算好的；改了这笔会退回待初审。</Typography.Paragraph>
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          <InputNumber aria-label="折人民币金额" prefix="¥" min={0.01} precision={2} style={{ width: 220 }} value={amount} onChange={(next) => setAmount(next == null ? null : Number(next))} />
          {rate && <Typography.Text type="secondary">相当于汇率 {rate}</Typography.Text>}
          <Input.TextArea rows={3} maxLength={500} showCount placeholder="必填：原因（例如：和供应商约定汇率 6.9）" value={reason} onChange={(event) => setReason(event.target.value)} />
        </Space>
      </Modal>
    </>
  );
}
