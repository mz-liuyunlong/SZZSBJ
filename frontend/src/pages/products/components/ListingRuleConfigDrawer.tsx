/** Owner-approved V1: Listing grade configuration only; other sections are read-only. */
import { useEffect, useState } from "react";
import { Alert, Button, Checkbox, Drawer, Empty, Form, Input, InputNumber, Modal, Skeleton, Space, Tabs, Tag, Typography, message } from "antd";
import type { GradeStage, ListingGradeRuleConfig, ListingGradeRuleHistory, ListingGradeRuleRead } from "@/pages/products/listingRuleConfigApi";
import { fetchListingGradeRule, fetchListingGradeRuleHistory, saveListingGradeRule } from "@/pages/products/listingRuleConfigApi";
import { BackendRequestError } from "@/api/backendApi";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface FormValues extends Omit<ListingGradeRuleConfig, "c_min_percent" | "b_min_percent" | "a_above_percent"> {
  c_min_percent: number;
  b_min_percent: number;
  a_above_percent: number;
  change_reason: string;
}

const stages: GradeStage[] = ["测品期", "打品期", "启动期", "上升期", "稳定期", "下滑期", "断货期", "修复期"];
const toForm = (config: ListingGradeRuleConfig): Partial<FormValues> => ({
  ...config,
  c_min_percent: Number(config.c_min_percent),
  b_min_percent: Number(config.b_min_percent),
  a_above_percent: Number(config.a_above_percent),
  change_reason: "",
});
const toConfig = (values: FormValues): ListingGradeRuleConfig => ({
  short_days: values.short_days,
  medium_days: values.medium_days,
  short_weight_percent: values.short_weight_percent,
  medium_weight_percent: values.medium_weight_percent,
  short_min_valid_days: values.short_min_valid_days,
  medium_min_valid_days: values.medium_min_valid_days,
  c_min_percent: String(values.c_min_percent),
  b_min_percent: String(values.b_min_percent),
  a_above_percent: String(values.a_above_percent),
  included_stages: values.included_stages,
});

export default function ListingRuleConfigDrawer({ open, onClose }: Props) {
  const [form] = Form.useForm<FormValues>();
  const [messageApi, contextHolder] = message.useMessage();
  const [record, setRecord] = useState<ListingGradeRuleRead | null>(null);
  const [history, setHistory] = useState<ListingGradeRuleHistory | null>(null);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [tab, setTab] = useState("grade");

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(false);
    setHistory(null);
    setDirty(false);
    void fetchListingGradeRule().then((result) => {
      if (cancelled) return;
      setRecord(result);
      form.setFieldsValue(toForm(result.config));
    }).catch(() => {
      if (!cancelled) setError(true);
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, form]);

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      setHistory(await fetchListingGradeRuleHistory());
    } catch {
      messageApi.error("规则历史读取失败");
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleClose = () => {
    if (!dirty) { onClose(); return; }
    Modal.confirm({
      title: "放弃未保存的规则修改？",
      content: "关闭后本次编辑内容将丢失。",
      okText: "放弃修改",
      cancelText: "继续编辑",
      onOk: onClose,
    });
  };

  const save = async (values: FormValues) => {
    if (!record || !record.can_edit) return;
    if (values.short_days >= values.medium_days) {
      messageApi.error("短期统计窗口必须小于中期统计窗口"); return;
    }
    if (values.short_weight_percent + values.medium_weight_percent !== 100) {
      messageApi.error("两个窗口的权重之和必须为100%"); return;
    }
    if (values.short_min_valid_days > values.short_days || values.medium_min_valid_days > values.medium_days) {
      messageApi.error("最低有效天数不得超过对应统计窗口"); return;
    }
    if (!(values.c_min_percent < values.b_min_percent && values.b_min_percent < values.a_above_percent)) {
      messageApi.error("评级阈值必须严格递增"); return;
    }
    if (!values.included_stages?.length || !values.change_reason?.trim()) {
      messageApi.error("请填写参与评级的生命周期及修改原因"); return;
    }
    const config = toConfig(values);
    setSaving(true);
    try {
      const next = await saveListingGradeRule(config, record.version, values.change_reason);
      setRecord(next);
      setDirty(false);
      form.setFieldsValue(toForm(next.config));
      setHistory(null);
      messageApi.success("规则已保存，将于下一次北京时间22:30生效；不会自动重算历史数据");
    } catch (e) {
      if (e instanceof BackendRequestError && e.status === 409) {
        messageApi.error("配置版本已发生变化或无修改，请刷新规则后重新提交");
      } else {
        messageApi.error("保存失败，请检查权限和表结构是否已在本地准备好");
      }
    } finally { setSaving(false); }
  };

  const numberField = (key: keyof FormValues, label: string, max = 180, step = 1) => (
    <Form.Item name={key} label={label} rules={[{ required: true, message: `请填写${label}` }]}>
      <InputNumber min={1} max={max} step={step} precision={step === 1 ? 0 : 2} style={{ width: "100%" }} disabled={!record?.can_edit}/>
    </Form.Item>
  );

  const gradeContent = (
    <Form form={form} layout="vertical" onFinish={(values) => void save(values)} onValuesChange={() => setDirty(true)} disabled={!record?.can_edit}>
      <Typography.Title level={5}>统计窗口与权重</Typography.Title>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 16px" }}>
        {numberField("short_days", "短期统计天数", 90)}
        {numberField("medium_days", "中期统计天数")}
        {numberField("short_weight_percent", "短期权重（%）", 99)}
        {numberField("medium_weight_percent", "中期权重（%）", 99)}
        {numberField("short_min_valid_days", "短期最低有效日期", 90)}
        {numberField("medium_min_valid_days", "中期最低有效日期")}
      </div>
      <Typography.Title level={5}>毛利率等级边界</Typography.Title>
      <Typography.Paragraph type="secondary">D级低于C下限，C级低于B下限，B级不超过A级边界。判级使用精确值。</Typography.Paragraph>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        {numberField("c_min_percent", "C级下限（%）", 1000, 0.01)}
        {numberField("b_min_percent", "B级下限（%）", 1000, 0.01)}
        {numberField("a_above_percent", "A级严格高于（%）", 1000, 0.01)}
      </div>
      <Typography.Title level={5}>参与评级的生命周期</Typography.Title>
      <Form.Item name="included_stages" rules={[{ required: true, type: "array", min: 1, message: "至少选择一个生命周期" }]}>
        <Checkbox.Group options={stages.map((s) => ({ label: s, value: s }))} />
      </Form.Item>
      <Typography.Paragraph type="secondary">清货期与已归档永久不参与，无法配置开启。</Typography.Paragraph>
      <Typography.Title level={5}>生效规则（受保护）</Typography.Title>
      <Alert type="info" showIcon message="每天北京时间22:30评级；洛杉矶业务日期T-2截止。销售、广告、成本必须完整，缺失不得当作0。" style={{ marginBottom: 16 }} />
      {record?.can_edit && (
        <>
          <Form.Item name="change_reason" label="本次变更原因" rules={[{ required: true, min: 3, message: "至少填写3个字符的修改原因" }]}>
            <Input.TextArea placeholder="说明调整原因，记录在变更历史中" rows={2} maxLength={500}/>
          </Form.Item>
          <Space style={{ display: "flex", justifyContent: "flex-end" }}>
            <Button onClick={() => { form.setFieldsValue(toForm(record.config)); setDirty(false); }}>恢复本次修改</Button>
            <Button type="primary" htmlType="submit" loading={saving} disabled={!dirty}>保存新版本</Button>
          </Space>
        </>
      )}
      {!record?.can_edit && <Alert type="warning" message="当前账号只有查看权限。请通过角色管理授予「配置Listing评级规则」动作权限。" showIcon/>}
    </Form>
  );

  const readOnly = (title: string, description: string) => (
    <div style={{ padding: 16 }}>
      <Typography.Title level={5}>{title}</Typography.Title>
      <Alert type="info" showIcon message="本分组的在线编辑将在后续独立版本实现" description={description}/>
    </div>
  );

  return (
    <>
      {contextHolder}
      <Drawer title="Listing 规则配置" open={open} onClose={handleClose} destroyOnHidden width={760}
        extra={record && <Space><Tag color={record.is_pending ? "gold" : "blue"}>v{record.version}{record.is_pending ? " 待生效" : ""}</Tag><Button onClick={() => { form.setFieldsValue(toForm(record.config)); setDirty(false); }}>重置草稿</Button></Space>}>
        {loading ? <Skeleton active paragraph={{ rows: 10 }}/> : error || !record ? (
          <Alert type="error" message="规则加载失败" action={<Button onClick={() => { onClose(); }}>关闭后重试</Button>}/>
        ) : (
          <Tabs activeKey={tab} onChange={(key) => {
            if (dirty && key !== tab) { messageApi.warning("请先保存或恢复当前修改，再切换分组"); return; }
            setTab(key);
            if (key === "history") void loadHistory();
          }} items={[
            { key: "grade", label: "等级评级", children: gradeContent },
            { key: "lifecycle", label: "生命周期", children: readOnly("生命周期", "上升、稳定、下滑的销量阶梯及样本门槛。") },
            { key: "stock", label: "库存与修复", children: readOnly("库存与修复", "WFS低库存、连续断货和修复验收规则。") },
            { key: "follow", label: "运营跟进", children: readOnly("运营跟进", "C/D逐条检查，复用运营日志。跟进时间尚待业务确认。") },
            { key: "history", label: "变更记录", children: historyLoading ? <Skeleton active/> : history?.items.length ? (
              <Space direction="vertical" style={{ width: "100%" }}>
                {history.items.map((item) => (
                  <div key={item.version} style={{ borderBottom: "1px solid #e5e7eb", padding: "12px 0" }}>
                    <strong>v{item.version}</strong> · {item.change_reason}
                    <Typography.Paragraph type="secondary">修改人：{item.created_by} · 下次评级生效时间：{new Date(item.effective_from).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</Typography.Paragraph>
                  </div>
                ))}
              </Space>
            ) : <Empty description="暂无历史修改记录"/>,
            },
          ]}/>
        )}
      </Drawer>
    </>
  );
}
