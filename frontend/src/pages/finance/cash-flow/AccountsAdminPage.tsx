/**
 * 资金流水 ·「账户管理」：新增 / 修改 / 停用账户（只有超级管理员能用，接口同日记账）。
 * - 识别值（完整账号、查询账号、用户号）只写不读：列表只显示尾号和「已填」，修改时留空 = 不改。
 * - 已有流水的账户不能改平台和币种，也不能删除，只能停用；停用后导入不再认它，已有流水照常显示。
 */
import { Alert, Button, Checkbox, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Tag, Typography, message } from "antd";
import { type ProColumns } from "@ant-design/pro-components";
import { useState } from "react";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import FinanceBoardFrame from "@/pages/finance/FinanceBoardFrame";
import { BoardTable } from "@/pages/finance/cash-flow/BoardTable";
import {
  accountErrorText, CURRENCY_OPTIONS, identityMissing, KIND_OPTIONS, PROVIDER_LABEL, PROVIDER_SHORT, useAdminAccounts, useSaveAccount,
  type AccountInput, type AccountPatch, type AdminAccount, type CashProvider, type Identity,
} from "@/pages/finance/cash-flow/accountsApi";
import { cashErrorText, isCashLive } from "@/pages/finance/cash-flow/journalApi";
import { currencyName, currencyText } from "@/pages/finance/currencyName";
import "@/pages/finance/cash-flow/cash-flow.css";
import EmptyState from "@/shared/states/EmptyState";

interface FormValues {
  display_name: string; entity: string; kind: string; currency_code: string; provider: CashProvider; account_no_last4?: string; sort_order?: number;
  inquiry_account?: string; account_no?: string; feature?: string; user_no?: string; main?: boolean; account_id?: string;
}

const IDENTITY_KEYS = ["inquiry_account", "account_no", "feature", "user_no", "main", "account_id"] as const;

function identityOf(values: FormValues): Identity {
  const out: Identity = {};
  IDENTITY_KEYS.forEach((key) => {
    const value = values[key];
    if (typeof value === "boolean") out[key] = value;
    else if (value && String(value).trim()) out[key] = String(value).trim();
  });
  return out;
}

function AccountForm({ editing, onClose }: { editing?: AdminAccount; onClose: () => void }) {
  const [form] = Form.useForm<FormValues>();
  const [messageApi, holder] = message.useMessage();
  const save = useSaveAccount();
  const provider = (Form.useWatch("provider", form) ?? editing?.provider ?? "manual") as CashProvider;
  const main = Form.useWatch("main", form);
  const locked = Boolean(editing?.line_count);
  const providerChanged = Boolean(editing && provider !== editing.provider);
  const identityHint = editing && !providerChanged ? "已填过；不改就留空" : undefined;

  const submit = async () => {
    const values = await form.validateFields();
    const identity = identityOf(values);
    const touched = Object.keys(identity).some((key) => key !== "main") || providerChanged || !editing;
    if (touched) {
      const missing = identityMissing(provider, identity);
      if (missing) { void messageApi.error(missing); return; }
    }
    const base = {
      display_name: values.display_name.trim(), entity: values.entity.trim(), kind: values.kind.trim(), currency_code: values.currency_code, provider,
      account_no_last4: values.account_no_last4?.trim() || undefined, sort_order: values.sort_order ?? undefined,
    };
    try {
      if (editing) {
        const body: AccountPatch = { ...base, ...(touched ? { identity } : {}) };
        await save.mutateAsync({ key: editing.account_key, body });
        void messageApi.success("已保存");
      } else {
        const body: AccountInput = { ...base, identity };
        await save.mutateAsync({ body });
        void messageApi.success("已新增，导入或手工录入时就能选到");
      }
      onClose();
    } catch (error) {
      void messageApi.error(accountErrorText(error));
    }
  };

  return (
    <Modal open title={editing ? `修改账户 · ${editing.display_name}` : "新增账户"} width={560} okText="保存" cancelText="取消" confirmLoading={save.isPending}
      onOk={() => void submit()} onCancel={onClose} destroyOnHidden>
      {holder}
      <Form<FormValues> form={form} layout="vertical" requiredMark="optional"
        initialValues={editing
          ? { display_name: editing.display_name, entity: editing.entity, kind: editing.kind, currency_code: editing.currency_code, provider: editing.provider as CashProvider, account_no_last4: editing.account_no_last4, sort_order: editing.sort_order, feature: editing.payoneer_feature ?? undefined, main: editing.pingpong_main ?? false }
          : { provider: "manual", currency_code: "CNY", kind: "现金", main: true }}>
        <Form.Item name="display_name" label="账户名称" rules={[{ required: true, whitespace: true, message: "写账户名称" }]}>
          <Input maxLength={128} placeholder="例如：主体 · 银行 · 尾号" />
        </Form.Item>
        <Form.Item name="entity" label="所属主体" rules={[{ required: true, whitespace: true, message: "写主体（哪家公司）" }]}>
          <Input maxLength={128} />
        </Form.Item>
        <Space size={12} style={{ width: "100%" }} align="start">
          <Form.Item name="kind" label="类型" rules={[{ required: true, message: "选类型" }]}>
            <Select style={{ width: 120 }} options={KIND_OPTIONS.map((value) => ({ value, label: value }))} />
          </Form.Item>
          <Form.Item name="currency_code" label="币种" rules={[{ required: true }]} tooltip={locked ? "已有流水，不能改" : provider === "manual" ? "手工账户只记人民币" : undefined}>
            <Select style={{ width: 110 }} disabled={locked || provider === "manual"} options={CURRENCY_OPTIONS.map((value) => ({ value, label: value === "CNH" ? "人民币（离岸）" : currencyName(value) }))} />
          </Form.Item>
          <Form.Item name="sort_order" label="排序">
            <InputNumber<number> min={0} precision={0} style={{ width: 100 }} placeholder="自动" />
          </Form.Item>
        </Space>
        <Form.Item name="provider" label="流水来源" rules={[{ required: true }]} tooltip={locked ? "已有流水，不能改" : "决定导入时按哪种格式读文件；手工录入的账户不导入文件"}>
          <Select disabled={locked} onChange={(value: CashProvider) => { if (value === "manual") form.setFieldsValue({ currency_code: "CNY" }); }} options={(Object.keys(PROVIDER_LABEL) as CashProvider[]).map((value) => ({ value, label: PROVIDER_LABEL[value] }))} />
        </Form.Item>
        {provider === "boc" && (
          <Form.Item name="inquiry_account" label="查询账号" extra={identityHint ?? "中行「交易明细」表头里的查询账号；人民币户和外币户共用一个查询账号时，各建一个账户、币种不同"}>
            <Input autoComplete="off" />
          </Form.Item>
        )}
        {(provider === "cmb" || provider === "shenzhen_rural_bank") && (
          <Form.Item name="account_no" label="完整银行账号" extra={identityHint ?? (provider === "cmb" ? "招行流水 PDF 里账号只露前 4 后 4 位，系统按这 8 位 + 币种认账户" : "导入时按账号认账户")}>
            <Input autoComplete="off" />
          </Form.Item>
        )}
        {provider === "payoneer" && (
          <Form.Item name="feature" label="派安盈户类型">
            <Select options={[{ value: "seller", label: "卖家收款户（Walmart 回款、卡扣款）" }, { value: "collector", label: "归集户（STRIPE、connected account 转入）" }]} />
          </Form.Item>
        )}
        {provider === "pingpong" && (<>
          <Form.Item name="user_no" label="PingPong 用户编号" extra={identityHint}>
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="main" valuePropName="checked">
            <Checkbox>这是主账户（不勾就是店铺子账户）</Checkbox>
          </Form.Item>
          {!main && (
            <Form.Item name="account_id" label="店铺子账户 ID" extra={identityHint}>
              <Input autoComplete="off" />
            </Form.Item>
          )}
        </>)}
        {provider === "worldfirst" && <Alert type="info" showIcon message="万里汇只能有一个启用中的账户，导入时不用填识别号" />}
        {provider === "manual" && <Alert type="info" showIcon message="手工账户不导入文件：在日记账点「手工录入」逐笔录。余额从第一笔往下累计，期初就录一笔「期初余额」。" />}
        <Form.Item name="account_no_last4" label="尾号" extra="不填就从账号自动取后 4 位；内部转账配对、页面显示用" style={{ marginTop: 16 }}>
          <Input maxLength={8} style={{ width: 140 }} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

function AccountsAdminBoard() {
  const accounts = useAdminAccounts();
  const save = useSaveAccount();
  const [messageApi, holder] = message.useMessage();
  const [editing, setEditing] = useState<AdminAccount | "new">();

  const toggle = async (row: AdminAccount) => {
    try {
      await save.mutateAsync({ key: row.account_key, body: { is_active: !row.is_active } });
      void messageApi.success(row.is_active ? "已停用，导入时不再认这个账户" : "已启用");
    } catch (error) {
      void messageApi.error(accountErrorText(error));
    }
  };

  const columns: ProColumns<AdminAccount>[] = [
    { title: "账户", dataIndex: "display_name", width: 260, fixed: "left", render: (_, row) => <Space direction="vertical" size={0}><Typography.Text strong>{currencyText(row.display_name)}</Typography.Text><Typography.Text type="secondary" style={{ fontSize: 12 }}>{row.account_key}</Typography.Text></Space> },
    { title: "主体", dataIndex: "entity", width: 140 },
    { title: "类型", dataIndex: "kind", width: 80 },
    { title: "币种", dataIndex: "currency_code", width: 70, render: (_, row) => currencyName(row.currency_code) },
    { title: "流水来源", dataIndex: "provider", width: 100, render: (_, row) => PROVIDER_SHORT[row.provider] ?? row.provider },
    { title: "尾号", dataIndex: "account_no_last4", width: 80, render: (_, row) => row.account_no_last4 || "—" },
    { title: "识别号", width: 90, render: (_, row) => (row.provider === "manual" || row.provider === "worldfirst" ? <Typography.Text type="secondary">不用</Typography.Text> : row.identity_fields.length ? <Tag color="green" bordered={false}>已填</Tag> : <Tag color="red" bordered={false}>未填</Tag>) },
    { title: "流水数", dataIndex: "line_count", width: 80, align: "right" },
    { title: "状态", dataIndex: "is_active", width: 80, render: (_, row) => (row.is_active ? <Tag color="blue" bordered={false}>启用</Tag> : <Tag bordered={false}>停用</Tag>) },
    { title: "操作", width: 130, fixed: "right", render: (_, row) => (
      <Space size={0}>
        <Button type="link" size="small" onClick={() => setEditing(row)}>修改</Button>
        <Popconfirm title={row.is_active ? "停用后导入时不再认这个账户，已有流水照常显示。确定停用？" : "确定启用？"} okText="确定" cancelText="取消" onConfirm={() => void toggle(row)}>
          <Button type="link" size="small" danger={row.is_active}>{row.is_active ? "停用" : "启用"}</Button>
        </Popconfirm>
      </Space>
    ) },
  ];

  return (
    <FinanceBoardFrame title="账户管理" preview={false} loading={accounts.isPending}
      subtitle="新增银行 / 平台账户，或者现金这种手工录入的账户；账户不能删除，不用了就停用"
      toolbar={<span className="finance-board__toolbar-actions"><Button type="primary" onClick={() => setEditing("new")}>新增账户</Button></span>}>
      {holder}
      {accounts.error ? <EmptyState title="账户读取失败" description={cashErrorText(accounts.error)} />
        : <BoardTable<AdminAccount> label="账户管理表格" rowKey="account_key" rows={accounts.data ?? []} columns={columns} emptyTitle="还没有账户" emptyText="点右上角「新增账户」" />}
      {editing && <AccountForm editing={editing === "new" ? undefined : editing} onClose={() => setEditing(undefined)} />}
    </FinanceBoardFrame>
  );
}

function AccountsAdminPage({ page }: { page: NavigationPage }) {
  return (
    <PageShell page={page}>
      {isCashLive ? <AccountsAdminBoard /> : (
        <FinanceBoardFrame title="账户管理" preview={false}>
          <EmptyState title="建设中" description="账户管理要接正式接口，本地 Demo 模式下不可用" />
        </FinanceBoardFrame>
      )}
    </PageShell>
  );
}

export default AccountsAdminPage;
