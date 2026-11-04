/** 创建默认值（按店铺）：右上角按钮打开的侧边抽屉。创建货件弹窗自动带出这里的值。 */
import { Alert, Button, Checkbox, Drawer, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography, message } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import EmptyState from "@/shared/states/EmptyState";
import { listStoreDefaults, saveStoreDefaults, type DefaultValues, type StoreDefaultsRow } from "./creationApi";
import { pendingError } from "./pendingPackingApi";

const transports = [
  { value: "LTL", label: "LTL 零担" },
  { value: "SMALL_PARCEL", label: "小包裹" },
  { value: "FTL", label: "FTL 整车" },
];
const carriers = [
  { value: "own", label: "自有承运人" },
  { value: "wm", label: "Walmart 合作承运人" },
];
const levels: Record<StoreDefaultsRow["level"], { text: string; color?: string }> = {
  store: { text: "本店铺", color: "blue" },
  account: { text: "沿用账号设置" },
  default: { text: "系统默认" },
};
const label = (options: { value: string; label: string }[], value: string) => options.find((o) => o.value === value)?.label ?? value;
const time = (v?: string | null) => v ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", dateStyle: "short", timeStyle: "short" }).format(new Date(v)) : "—";

interface FormValues extends Omit<DefaultValues, "return_address"> {
  address_line1?: string; city?: string; state_code?: string; postal_code?: string; reason?: string;
}

export default function StoreDefaultsDrawer({ open, scope, canManage, onClose }: {
  open: boolean; scope: string; canManage: boolean; onClose: () => void;
}) {
  const client = useQueryClient();
  const [messages, holder] = message.useMessage();
  const [editing, setEditing] = useState<StoreDefaultsRow>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [form] = Form.useForm<FormValues>();
  const query = useQuery({ queryKey: ["wfs-store-creation-defaults", scope], queryFn: ({ signal }) => listStoreDefaults(signal), enabled: open, retry: false });
  const edit = (row: StoreDefaultsRow) => {
    setError(undefined);
    setEditing(row);
    form.setFieldsValue({ ...row, ...(row.return_address ?? {}), reason: "" });
  };
  const save = async () => {
    const { address_line1, city, state_code, postal_code, reason, ...values } = await form.validateFields();
    const address = [address_line1, city, state_code, postal_code].some(Boolean)
      ? { address_line1: address_line1 ?? "", city: city ?? "", state_code: state_code ?? "", postal_code: postal_code ?? "", country_code: "US" as const }
      : null;
    setBusy(true); setError(undefined);
    try {
      await saveStoreDefaults(editing!.store_id, { ...values, return_address: address, reason });
      await Promise.all([
        client.invalidateQueries({ queryKey: ["wfs-store-creation-defaults"] }),
        client.invalidateQueries({ queryKey: ["wfs-creation-defaults"] }),
      ]);
      setEditing(undefined);
      void messages.success("已保存，之后创建货件会自动带出");
    } catch (e) {
      setError(pendingError(e));
    } finally {
      setBusy(false);
    }
  };
  const rows = query.data?.data.items ?? [];
  return <Drawer open={open} width={1080} title="创建默认值（按店铺）" onClose={onClose} destroyOnClose>
    {holder}
    <Typography.Paragraph type="secondary">
      每个店铺一套默认值；创建货件时自动带出，弹窗里改了只影响那一次。店铺没设置时沿用账号设置，再没有就用系统默认（运输方式 LTL、发货日偏移 15 天）。
    </Typography.Paragraph>
    {query.error && <Alert type="error" showIcon message={pendingError(query.error)} action={<Button size="small" onClick={() => void query.refetch()}>重试</Button>} />}
    <Table<StoreDefaultsRow> size="small" bordered rowKey={(r) => `${r.source_account_ref}:${r.store_id}`} loading={query.isFetching} dataSource={rows} pagination={false} scroll={{ x: 1000 }}
      locale={{ emptyText: <EmptyState title="暂无店铺" description={query.error ? "加载失败，请重试" : "当前账号下没有可设置的店铺"} compact /> }}
      columns={[
        { title: "店铺", width: 180, fixed: "left", render: (_, r) => <span>{r.store_name ?? r.store_id}<span className="wfs-create__sub">{r.store_id}</span></span> },
        { title: "来源", width: 110, render: (_, r) => <Tag color={levels[r.level].color} bordered={false}>{levels[r.level].text}</Tag> },
        { title: "运输方式", width: 100, render: (_, r) => label(transports, r.transport) },
        { title: "发货日偏移", width: 96, align: "right", render: (_, r) => `${r.ship_date_offset} 天` },
        { title: "托盘箱数 / 混装箱数", width: 130, align: "right", render: (_, r) => `${r.pallet_boxes} / ${r.mixed_boxes}` },
        { title: "承运人", width: 140, render: (_, r) => label(carriers, r.carrier_opt) },
        { title: "ITS", width: 64, render: (_, r) => r.its ? "是" : "否" },
        { title: "退货地址", width: 240, render: (_, r) => r.return_address ? `${r.return_address.address_line1}, ${r.return_address.city}, ${r.return_address.state_code} ${r.return_address.postal_code}` : <Typography.Text type="secondary">未设置，创建时手填</Typography.Text> },
        { title: "最后修改", width: 150, render: (_, r) => r.updated_by ? <span>{r.updated_by}<span className="wfs-create__sub">{time(r.updated_at)}</span></span> : "—" },
        { title: "操作", width: 80, fixed: "right", render: (_, r) => canManage ? <Button type="link" size="small" onClick={() => edit(r)}>编辑</Button> : <Typography.Text type="secondary">只读</Typography.Text> },
      ]} />
    <Modal open={!!editing} width={640} title={`编辑创建默认值 · ${editing?.store_name ?? editing?.store_id ?? ""}`} okText="保存" confirmLoading={busy} onOk={() => void save().catch(() => undefined)} onCancel={() => setEditing(undefined)} destroyOnClose>
      {error && <Alert type="error" showIcon message={error} />}
      <Form form={form} layout="vertical" disabled={busy}>
        <Space wrap align="start">
          <Form.Item name="transport" label="运输方式" rules={[{ required: true }]}><Select className="wfs-create__select" options={transports} /></Form.Item>
          <Form.Item name="carrier_opt" label="承运人" rules={[{ required: true }]}><Select className="wfs-create__select" options={carriers} /></Form.Item>
          <Form.Item name="ship_date_offset" label="发货日偏移（天）" rules={[{ required: true }]}><InputNumber min={0} max={120} precision={0} /></Form.Item>
          <Form.Item name="pallet_boxes" label="托盘箱数" rules={[{ required: true }]}><InputNumber min={1} max={100} precision={0} /></Form.Item>
          <Form.Item name="mixed_boxes" label="混装箱数" rules={[{ required: true }]}><InputNumber min={0} max={1000} precision={0} /></Form.Item>
        </Space>
        <Form.Item name="its" valuePropName="checked"><Checkbox>默认选择 ITS</Checkbox></Form.Item>
        <Typography.Text strong>退货地址（可不填；填就要填全）</Typography.Text>
        <Form.Item name="address_line1" label="街道地址" dependencies={["city", "state_code", "postal_code"]} rules={[({ getFieldValue }) => ({ validator: (_, v) => !v && ["city", "state_code", "postal_code"].some((k) => getFieldValue(k)) ? Promise.reject(new Error("请填写街道地址")) : Promise.resolve() })]}><Input maxLength={200} /></Form.Item>
        <Space wrap align="start">
          <Form.Item name="city" label="城市" dependencies={["address_line1"]} rules={[({ getFieldValue }) => ({ validator: (_, v) => !v && getFieldValue("address_line1") ? Promise.reject(new Error("请填写城市")) : Promise.resolve() })]}><Input maxLength={100} /></Form.Item>
          <Form.Item name="state_code" label="州代码" normalize={(v: string) => v?.toUpperCase()} dependencies={["address_line1"]} rules={[({ getFieldValue }) => ({ validator: (_, v) => (!v && !getFieldValue("address_line1")) || /^[A-Z]{2}$/.test(v ?? "") ? Promise.resolve() : Promise.reject(new Error("两位州代码")) })]}><Input maxLength={2} /></Form.Item>
          <Form.Item name="postal_code" label="邮编" dependencies={["address_line1"]} rules={[({ getFieldValue }) => ({ validator: (_, v) => (!v && !getFieldValue("address_line1")) || /^\d{5}(-\d{4})?$/.test(v ?? "") ? Promise.resolve() : Promise.reject(new Error("5 位邮编")) })]}><Input /></Form.Item>
        </Space>
        <Form.Item name="reason" label="修改原因（选填）"><Input maxLength={500} /></Form.Item>
      </Form>
    </Modal>
  </Drawer>;
}
