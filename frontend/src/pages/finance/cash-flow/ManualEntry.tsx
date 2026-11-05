/**
 * 日记账 ·「手工录入」：现金账户的收支，或者银行 / 平台流水里没有的那笔（比如另外扣的手续费）。
 * 录进去的流水和导入的一样走分类、初审终审；录错了用剔除。手工账户的余额从第一笔往下累计，期初就录一笔「期初余额」。
 */
import { Button, DatePicker, Form, Input, InputNumber, Modal, Radio, Select, Typography, message } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useEffect, useMemo, useState } from "react";
import { manualErrorText, PROVIDER_SHORT, useAdminAccounts, useCreateManualLine } from "@/pages/finance/cash-flow/accountsApi";
import { defaultAccountKey, manualAccounts } from "@/pages/finance/cash-flow/manualEntryOptions";
import { currencyName } from "@/pages/finance/currencyName";
import type { CashSnapshot } from "@/pages/finance/localFinData";

const FEE_CATEGORY = "F01";

type EntryType = "normal" | "fee";
interface FormValues {
  type: EntryType; account_key?: string; business_date: Dayjs; direction: "in" | "out"; amount: number | string;
  description: string; counterparty_name?: string; memo?: string; category_code?: string;
}

export function ManualEntryButton({ data, live }: { data: CashSnapshot; live: boolean }) {
  const [open, setOpen] = useState(false);
  if (!live) return null;
  return (
    <>
      <Button onClick={() => setOpen(true)}>手工录入</Button>
      {open && <ManualEntryModal data={data} onClose={() => setOpen(false)} />}
    </>
  );
}

function ManualEntryModal({ data, onClose }: { data: CashSnapshot; onClose: () => void }) {
  const [form] = Form.useForm<FormValues>();
  const [messageApi, holder] = message.useMessage();
  const [requestKey, setRequestKey] = useState(() => crypto.randomUUID());
  const accounts = useAdminAccounts();
  const create = useCreateManualLine();
  const type = Form.useWatch("type", form) ?? "normal";
  const accountKey = Form.useWatch("account_key", form);
  const active = useMemo(() => manualAccounts((accounts.data ?? []).filter((row) => row.is_active)), [accounts.data]);
  /* 账户读到后默认选现金；财务已经选过就不动。 */
  useEffect(() => {
    if (!form.getFieldValue("account_key")) form.setFieldsValue({ account_key: defaultAccountKey(active) });
  }, [active, form]);
  const currency = active.find((row) => row.account_key === accountKey)?.currency_code;
  const catOptions = data.cats.map((cat) => ({ value: cat.code, label: `${cat.code} ${cat.big}·${cat.name}` }));

  const pickType = (next: EntryType) => {
    if (next === "fee") form.setFieldsValue({ direction: "out", category_code: FEE_CATEGORY, description: form.getFieldValue("description") || "手续费" });
  };

  const submit = async (keepOpen: boolean) => {
    const values = await form.validateFields();
    try {
      await create.mutateAsync({
        account_key: values.account_key as string,
        business_date: values.business_date.format("YYYY-MM-DD"),
        direction: values.direction,
        amount: String(values.amount),
        description: values.description.trim(),
        counterparty_name: values.counterparty_name?.trim() ?? "",
        memo: values.memo?.trim() ?? "",
        category_code: values.category_code || null,
        idempotency_key: requestKey,
      });
      setRequestKey(crypto.randomUUID());
      if (keepOpen) {
        void messageApi.success("已录入，可以接着录下一笔");
        form.setFieldsValue({ amount: undefined, description: type === "fee" ? "手续费" : "", counterparty_name: "", memo: "" });
      } else {
        void messageApi.success("已录入，在日记账里等初审");
        onClose();
      }
    } catch (error) {
      void messageApi.error(manualErrorText(error));
    }
  };

  return (
    <Modal open title="手工录入流水" width={560} onCancel={onClose} destroyOnHidden
      footer={[
        <Button key="cancel" onClick={onClose}>取消</Button>,
        <Button key="more" loading={create.isPending} onClick={() => void submit(true)}>保存并录下一笔</Button>,
        <Button key="ok" type="primary" loading={create.isPending} onClick={() => void submit(false)}>保存</Button>,
      ]}>
      {holder}
      <Typography.Paragraph type="secondary">
        用于现金账户（只记人民币），或者银行 / 平台流水里没有的那笔；币种跟所选账户走，要记美元就选美元账户（比如另外扣的手续费）。录完和导入的流水一样走初审、终审；录错了用「剔除」。
      </Typography.Paragraph>
      <Form<FormValues> form={form} layout="vertical" requiredMark="optional"
        initialValues={{ type: "normal", direction: "out", business_date: dayjs() }}>
        <Form.Item name="type" label="类型">
          <Radio.Group optionType="button" onChange={(event) => pickType(event.target.value as EntryType)}
            options={[{ value: "normal", label: "普通收支" }, { value: "fee", label: "手续费（流水里没有）" }]} />
        </Form.Item>
        <Form.Item name="account_key" label="账户" rules={[{ required: true, message: "选一个账户" }]}>
          <Select showSearch optionFilterProp="label" placeholder={accounts.isPending ? "读取中" : "选账户"} loading={accounts.isPending}
            options={active.map((row) => ({ value: row.account_key, label: `${row.display_name} · ${currencyName(row.currency_code)}${row.account_no_last4 ? ` · 尾号 ${row.account_no_last4}` : ""} · ${PROVIDER_SHORT[row.provider] ?? row.provider}` }))} />
        </Form.Item>
        <Form.Item name="business_date" label="日期" rules={[{ required: true, message: "选日期" }]}>
          <DatePicker style={{ width: "100%" }} disabledDate={(day) => day.isAfter(dayjs(), "day")} />
        </Form.Item>
        <Form.Item name="direction" label="收入 / 支出">
          <Radio.Group options={[{ value: "in", label: "收入" }, { value: "out", label: "支出" }]} />
        </Form.Item>
        <Form.Item name="amount" label={`金额${currency ? `（${currencyName(currency)}）` : ""}`} rules={[{ required: true, message: "填金额" }]}>
          <InputNumber<string> stringMode min="0.01" precision={2} style={{ width: "100%" }} placeholder="正数，方向看上面" />
        </Form.Item>
        <Form.Item name="description" label="摘要" rules={[{ required: true, whitespace: true, message: "写摘要" }]}>
          <Input maxLength={500} placeholder="例如：期初余额、买办公用品、中行年费" />
        </Form.Item>
        <Form.Item name="counterparty_name" label="对方">
          <Input maxLength={200} placeholder="收款人 / 付款人，可不填" />
        </Form.Item>
        <Form.Item name="category_code" label="类别">
          <Select allowClear showSearch optionFilterProp="label" placeholder="不选就按规则自动分类" options={catOptions} />
        </Form.Item>
        <Form.Item name="memo" label="备注">
          <Input.TextArea rows={2} maxLength={500} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
