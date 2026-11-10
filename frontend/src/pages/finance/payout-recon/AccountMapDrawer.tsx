/**
 * 收款账户匹配（弹出抽屉，放在「手动同步」旁边；以后挪到财务设置）。Rocky 2026-11-09 / 11-10：
 * - 一个店铺一个收款账户：收款机构（PingPong / 派安盈，跟着入账账户走）+ 收款账户（派安盈是付款邮箱，PingPong 是公司名称）+ 入账账户（日记账）。
 * - 换账户：新账户从生效日期起用，旧的自动截止到前一天，进「历史账户」；换账户要写原因。
 * - 真实账户信息不进 GitHub：上线后由部署 AI 录入生产库；之后财务在这里维护（要终审权限）。
 */
import { Button, DatePicker, Drawer, Form, Input, Modal, Select, Space, Tag, Typography, message } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import dayjs from "dayjs";
import { useState } from "react";
import BoardTable from "./BoardTable";
import { createAccount, deactivateAccount, reconErrorText, updateAccount, useAccountMap, type ApiAccountRow } from "./reconApi";
import { timeText } from "./reconModel";

interface FormValues {
  sid: string;
  accountKey: string;
  ident?: string;
  effectiveFrom?: dayjs.Dayjs;
  reason?: string;
}

type Mode = { kind: "new" } | { kind: "replace"; row: ApiAccountRow } | { kind: "edit"; row: ApiAccountRow };

function AccountMapDrawer({ open, onClose, onChanged }: { open: boolean; onClose: () => void; onChanged: () => void }) {
  const [messageApi, holder] = message.useMessage();
  const map = useAccountMap(open);
  const [mode, setMode] = useState<Mode>();
  const [historyOf, setHistoryOf] = useState<string>();
  const [stopping, setStopping] = useState<ApiAccountRow>();
  const [stopReason, setStopReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [form] = Form.useForm<FormValues>();
  const rows = (map.data?.items ?? []).filter((row) => row.is_active);
  const current = rows.filter((row) => !row.effective_to).sort((a, b) => a.store_code.localeCompare(b.store_code));
  const takenSids = new Set(current.map((row) => row.store_id));
  const stores = (map.data?.stores ?? []).map((store) => ({ value: store.store_id, label: store.store_code }));
  const accounts = (map.data?.accounts ?? []).map((account) => ({ value: account.account_key, label: `${account.org} · ${account.account_name}（${account.currency_code}）` }));
  const history = (sid: string) => (map.data?.items ?? []).filter((row) => row.store_id === sid && (row.effective_to || !row.is_active));

  const openForm = (next: Mode) => {
    setMode(next);
    const row = next.kind === "new" ? undefined : next.row;
    form.setFieldsValue({
      sid: row?.store_id ?? stores.find((store) => !takenSids.has(store.value))?.value,
      accountKey: row?.account_key,
      ident: row?.payee ?? "",
      effectiveFrom: next.kind === "replace" ? dayjs() : dayjs("2026-10-01"),
      reason: "",
    });
  };
  const save = async () => {
    if (!mode) return;
    const values = await form.validateFields();
    setBusy(true);
    try {
      if (mode.kind === "edit") {
        await updateAccount(mode.row.id, { account_key: values.accountKey, payee: (values.ident ?? "").trim(), reason: values.reason?.trim() || undefined });
      } else {
        await createAccount({
          store_id: values.sid,
          account_key: values.accountKey,
          payee: (values.ident ?? "").trim(),
          effective_from: (values.effectiveFrom ?? dayjs()).format("YYYY-MM-DD"),
          reason: values.reason?.trim() || undefined,
        });
      }
      void messageApi.success("已保存；回款对账会按新账户重新判断");
      setMode(undefined);
      onChanged();
    } catch (error) {
      void messageApi.error(reconErrorText(error));
    } finally {
      setBusy(false);
    }
  };
  const stop = async () => {
    if (!stopping) return;
    try {
      await deactivateAccount(stopping.id, stopReason.trim());
      void messageApi.success("已停用");
      setStopping(undefined);
      setStopReason("");
      onChanged();
    } catch (error) {
      void messageApi.error(reconErrorText(error));
    }
  };

  const columns: ProColumns<ApiAccountRow>[] = [
    { key: "code", title: "店铺", dataIndex: "store_code", width: 90, fixed: "left", render: (_, row) => <Tag bordered={false}>{row.store_code}</Tag> },
    { key: "org", title: "收款机构", dataIndex: "org", width: 100 },
    { key: "ident", title: "收款账户", dataIndex: "payee", width: 260, tooltip: "派安盈是付款邮箱，PingPong 是公司名称；填了就用来认出到账属于哪个店", render: (_, row) => <Typography.Text className="finance-board__fulltext">{row.payee || "—"}</Typography.Text> },
    { key: "account", title: "入账账户（日记账）", dataIndex: "account_name", width: 200, tooltip: "钱进的是日记账里的哪个账户" },
    { key: "from", title: "生效日期", dataIndex: "effective_from", width: 110 },
    { key: "updated", title: "最后修改", width: 140, render: (_, row) => timeText(row.updated_at) },
    {
      key: "op", title: "操作", width: 250, fixed: "right",
      render: (_, row) => (
        <Space size={0}>
          <Button type="link" size="small" onClick={() => openForm({ kind: "edit", row })}>修改</Button>
          <Button type="link" size="small" onClick={() => openForm({ kind: "replace", row })}>换账户</Button>
          <Button type="link" size="small" disabled={!history(row.store_id).length} onClick={() => setHistoryOf(row.store_id)}>历史账户（{history(row.store_id).length}）</Button>
          <Button type="link" size="small" danger onClick={() => setStopping(row)}>停用</Button>
        </Space>
      ),
    },
  ];
  const historyColumns: ProColumns<ApiAccountRow>[] = [
    { key: "org", title: "收款机构", dataIndex: "org", width: 100 },
    { key: "ident", title: "收款账户", dataIndex: "payee", width: 240, render: (_, row) => row.payee || "—" },
    { key: "account", title: "入账账户", dataIndex: "account_name", width: 180 },
    { key: "period", title: "使用期间", width: 220, render: (_, row) => `${row.effective_from} ~ ${row.effective_to ?? (row.is_active ? "—" : "已停用")}` },
    { key: "reason", title: "原因", dataIndex: "change_reason", width: 200, render: (_, row) => row.change_reason || "—" },
  ];
  const title = mode?.kind === "edit" ? `修改 · ${mode.row.store_code}` : mode?.kind === "replace" ? `换账户 · ${mode.row.store_code}` : "新增匹配";

  return (
    <Drawer open={open} width={1180} rootClassName="fin-payout-recon__drawer" title="收款账户匹配" onClose={onClose}
      extra={<Button type="primary" disabled={!stores.some((store) => !takenSids.has(store.value))} onClick={() => openForm({ kind: "new" })}>新增匹配</Button>}>
      {holder}
      <Typography.Paragraph type="secondary">一个店铺对应一个收款账户；换账户后旧账户进「历史账户」。改这里要终审权限。自动配对按账单日当天生效的账户判断。</Typography.Paragraph>
      <BoardTable<ApiAccountRow> label="收款账户匹配" resizeKey="finance-payout-recon:accounts" rowKey="id" rows={current} columns={columns} pageSize={20} autoHeight
        emptyTitle={map.error ? "读取失败" : "还没有匹配"} emptyText={map.error ? reconErrorText(map.error) : "点「新增匹配」"} />

      <Drawer open={Boolean(mode)} width={480} title={title} onClose={() => setMode(undefined)} destroyOnHidden
        extra={<Space><Button onClick={() => setMode(undefined)}>取消</Button><Button type="primary" loading={busy} onClick={() => void save()}>保存</Button></Space>}>
        {mode && mode.kind !== "new" && <Typography.Paragraph type="secondary">现在：{mode.row.payee || "—"} · 入账 {mode.row.account_name}（{mode.row.effective_from} 起）。{mode.kind === "replace" ? "保存后它截止到新生效日期前一天，进「历史账户」。" : "修改不换生效日期。"}</Typography.Paragraph>}
        <Form form={form} layout="vertical" requiredMark>
          <Form.Item name="sid" label="店铺" rules={[{ required: true, message: "选店铺" }]}>
            <Select disabled={mode?.kind !== "new"} options={stores.filter((store) => mode?.kind !== "new" || !takenSids.has(store.value))} />
          </Form.Item>
          <Form.Item name="ident" label="收款账户" extra="派安盈填付款邮箱，PingPong 填公司名称；用来认出到账是哪个店的（不填就只按入账账户认）">
            <Input maxLength={200} />
          </Form.Item>
          <Form.Item name="accountKey" label="入账账户（日记账）" rules={[{ required: true, message: "选入账账户" }]} extra={mode?.kind === "edit" ? "修改只能改收款账户；换入账账户请用「换账户」（写生效日和原因）" : "钱进日记账里的哪个账户；账户在「资金流水 → 账户管理」里维护"}>
            <Select showSearch optionFilterProp="label" options={accounts} disabled={mode?.kind === "edit"} />
          </Form.Item>
          {mode?.kind !== "edit" && (
            <Form.Item name="effectiveFrom" label="生效日期" rules={[{ required: true, message: "选生效日期" }]} extra="从这一天起的账单按这个账户对账">
              <DatePicker />
            </Form.Item>
          )}
          {mode?.kind !== "new" && (
            <Form.Item name="reason" label={mode?.kind === "replace" ? "换账户原因" : "修改原因"} rules={mode?.kind === "replace" ? [{ required: true, whitespace: true, message: "换账户要写原因" }] : []}>
              <Input.TextArea rows={2} maxLength={200} />
            </Form.Item>
          )}
        </Form>
      </Drawer>

      <Drawer open={Boolean(historyOf)} width={900} title={`历史账户 · ${historyOf ? rows.find((row) => row.store_id === historyOf)?.store_code ?? "" : ""}`} onClose={() => setHistoryOf(undefined)}>
        <BoardTable<ApiAccountRow> label="历史账户" rowKey="id" rows={historyOf ? history(historyOf) : []} columns={historyColumns} pageSize={20} autoHeight emptyTitle="没有历史账户" emptyText="这个店铺没有换过账户" />
      </Drawer>

      <Modal open={Boolean(stopping)} title={`停用 · ${stopping?.store_code ?? ""}`} okText="确定停用" okButtonProps={{ danger: true, disabled: !stopReason.trim() }} cancelText="取消"
        onOk={() => void stop()} onCancel={() => { setStopping(undefined); setStopReason(""); }} destroyOnHidden>
        <Typography.Paragraph type="secondary">停用后这个店铺的账单不再自动配对。这条账户期间内还有生效中的配对时不能停用，要先撤销配对。</Typography.Paragraph>
        <Input.TextArea autoFocus rows={3} maxLength={300} showCount value={stopReason} onChange={(event) => setStopReason(event.target.value)} placeholder="必填：停用原因" />
      </Modal>
    </Drawer>
  );
}

export default AccountMapDrawer;
