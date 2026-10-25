/** Listing rule configuration: grade, lifecycle, inventory/repair and follow-up. */
import { useEffect, useState } from "react";
import { Alert, Button, Checkbox, Drawer, Empty, Form, Input, InputNumber, Modal, Skeleton, Space, Tabs, Tag, Typography, message } from "antd";
import type { GradeStage, ListingGradeRuleConfig, ListingGradeRuleHistory, ListingGradeRuleRead } from "@/pages/products/listingRuleConfigApi";
import { fetchListingGradeRule, fetchListingGradeRuleHistory, saveListingGradeRule } from "@/pages/products/listingRuleConfigApi";
import { BackendRequestError } from "@/api/backendApi";

export interface ListingRuleTransport {
  fetchRule: typeof fetchListingGradeRule;
  fetchHistory: typeof fetchListingGradeRuleHistory;
  saveRule: typeof saveListingGradeRule;
}

const DEFAULT_TRANSPORT: ListingRuleTransport = {
  fetchRule: fetchListingGradeRule,
  fetchHistory: fetchListingGradeRuleHistory,
  saveRule: saveListingGradeRule,
};

interface Props {
  open: boolean;
  onClose: () => void;
  transport?: ListingRuleTransport;
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
const toConfig = (values: FormValues, previous: ListingGradeRuleConfig): ListingGradeRuleConfig => ({
  ...previous,
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

export default function ListingRuleConfigDrawer({
  open,
  onClose,
  transport = DEFAULT_TRANSPORT,
}: Props) {
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
  const [reloadCount, setReloadCount] = useState(0);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(false);
    setHistory(null);
    setDirty(false);
    void transport.fetchRule().then((result) => {
      if (cancelled) return;
      setRecord(result);
      form.setFieldsValue(toForm(result.config));
    }).catch(() => {
      if (!cancelled) setError(true);
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, form, reloadCount, transport]);

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      setHistory(await transport.fetchHistory());
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
    if (!record || !record.can_edit || !record.storage_ready) return;
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
    const config = toConfig(values, record.config);
    setSaving(true);
    try {
      const next = await transport.saveRule(config, record.version, values.change_reason);
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

  const saveSection = async (section: "lifecycle" | "inventory_repair" | "follow_up", values: Record<string, unknown>) => {
    if (!record || !record.can_edit || !record.storage_ready) return;
    const { change_reason, ...rawSectionValues } = values;
    const sectionValues = section === "follow_up"
      ? { ...rawSectionValues,
          reminder_time: rawSectionValues.reminder_time || null,
          deadline_time: rawSectionValues.deadline_time || null }
      : rawSectionValues;
    if (typeof change_reason !== "string" || change_reason.trim().length < 3) {
      messageApi.error("请输入至少3个字符的变更原因");
      return;
    }
    setSaving(true);
    try {
      const updatedConfig = {
        ...record.config,
        [section]: sectionValues,
      } as ListingGradeRuleConfig;
      const next = await transport.saveRule(updatedConfig, record.version, change_reason);
      setRecord(next);
      form.setFieldsValue(toForm(next.config));
      setDirty(false);
      setHistory(null);
      messageApi.success("已保存规则新版本；配置引擎尚未接入生命周期和提醒自动执行");
    } catch (error) {
      if (error instanceof BackendRequestError && error.status === 409) {
        messageApi.error("规则版本冲突或没有变更，请重新打开页面获取新版本");
      } else if (error instanceof BackendRequestError && error.status === 422) {
        messageApi.error("参数不符合业务约束，请检查窗口、阶梯或时间设置");
      } else {
        messageApi.error("保存失败；请确认使用隔离开发库和写入权限");
      }
    } finally {
      setSaving(false);
    }
  };

  const numberInput = (name: string | string[], label: string, min = 1, max = 365) => (
    <Form.Item name={name} label={label} rules={[{ required: true, message: "请输入" + label }]}>
      <InputNumber min={min} max={max} precision={0} style={{ width: "100%" }} />
    </Form.Item>
  );

  const sectionEditor = (section: "lifecycle" | "inventory_repair" | "follow_up") => {
    const values = record?.config[section];
    if (!values) return null;
    const editable = record.can_edit && record.storage_ready;
    const tierFields = [
      { key: "lt2", label: "日均不足2件" },
      { key: "from2to5", label: "2–不足5件" },
      { key: "from5to10", label: "5–不足10件" },
      { key: "from10to20", label: "10–不足20件" },
      { key: "gte20", label: "20件及以上" },
    ];
    const lifecycle = section === "lifecycle" ? (
      <>
        <Alert type="info" showIcon message="按28天4个周窗口计算有效日均销量；每周7天、连续2次周趋势等算法结构不开放修改。" />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "0 16px", marginTop: 16 }}>
          {numberInput("min_week_valid_days", "每周最低有效有货日", 1, 7)}
          {numberInput("growth_min_valid_days_30", "上升期30天最低有效日", 1, 30)}
          {numberInput("stable_min_valid_days_30", "稳定期30天最低有效日", 1, 30)}
          {numberInput("decline_min_valid_days_30", "下滑期30天最低有效日", 1, 30)}
        </div>
        {([
          ["growth_threshold_pct", "上升期增长幅度"],
          ["decline_threshold_pct", "下滑期下降幅度"],
          ["stable_tolerance_pct", "稳定期允许波动"],
        ] as const).map(([field, label]) => (
          <div key={field}>
            <Typography.Title level={5}>{label}（%）</Typography.Title>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: "0 12px" }}>
              {tierFields.map((tier) => (
                <div key={tier.key}>{numberInput([field, tier.key], tier.label, 1, 200)}</div>
              ))}
            </div>
          </div>
        ))}
      </>
    ) : null;
    const inventory = section === "inventory_repair" ? (
      <>
        <Alert type="info" showIcon message="低库存阈值≤N、有效有货>N自动联动。首次有效入库、二次断货清零、清货审批及归档规则固定不变。" style={{ marginBottom: 16 }} />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "0 16px" }}>
          {numberInput("low_stock_max_units", "WFS低库存阈值（件）", 0, 10000)}
          {numberInput("stockout_consecutive_days", "连续低库存进入断货期（天）", 1, 90)}
          {numberInput("long_stockout_days", "长期断货门槛（超过N天）", 2, 365)}
          {numberInput("stockout_repair_valid_days", "长期断货修复有效有货日", 1, 180)}
          {numberInput("strike_price_abnormal_days", "划线价异常门槛（超过N天）", 1, 365)}
          {numberInput("buybox_abnormal_days", "购物车异常门槛（超过N天）", 1, 365)}
          {numberInput("abnormal_recovery_days", "异常恢复连续正常天数", 1, 90)}
        </div>
      </>
    ) : null;
    const follow = section === "follow_up" ? (
      <>
        <Alert type="info" showIcon message="C/D级每天逐条跟进、D级优先、日志复用的原则固定。此处仅保存待未来提醒服务消费的参数，不会自动发出提醒。" style={{ marginBottom: 16 }} />
        <Form.Item name="reminder_time" label="每日提醒时间（中国时间）" rules={[{ pattern: /^([01]\d|2[0-3]):[0-5]\d$/, message: "格式 HH:mm" }]}>
          <Input placeholder="例如 09:00，留空则不设置" />
        </Form.Item>
        <Form.Item name="deadline_time" label="每日完成截止时间（中国时间）" rules={[{ pattern: /^([01]\d|2[0-3]):[0-5]\d$/, message: "格式 HH:mm" }]}>
          <Input placeholder="例如 18:00，留空则不设置" />
        </Form.Item>
        <Form.Item name="overdue_notice" valuePropName="checked">
          <Checkbox>启用未来逾期通知（当前不会派发）</Checkbox>
        </Form.Item>
      </>
    ) : null;
    return (
      <Form key={section + record.version + reloadCount} layout="vertical" initialValues={values}
        disabled={!editable} onValuesChange={() => setDirty(true)}
        onFinish={(values) => void saveSection(section, values as Record<string, unknown>)}>
        {lifecycle}{inventory}{follow}
        {editable ? (
          <>
            <Form.Item name="change_reason" label="变更原因" rules={[{ required: true, min: 3 }]}>
              <Input.TextArea rows={2} maxLength={500} placeholder="说明为何调整这组规则"/>
            </Form.Item>
            <Space><Button onClick={() => { setDirty(false); setReloadCount((n) => n + 1); }}>放弃本次修改</Button><Button type="primary" loading={saving} htmlType="submit">保存新版本</Button></Space>
          </>
        ) : (
          <Alert type="warning" showIcon message={record.storage_ready ? "当前账号没有规则编辑权限" : "仅只读预览；请先在隔离开发库初始化存储"} />
        )}
      </Form>
    );
  };

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
      {record && !record.storage_ready && (
        <Alert type="warning" showIcon message="只读预览：规则配置表尚未初始化"
          description="当前显示的是内置V1.0默认值，并非数据库中的生效版本。固定启动脚本使用生产数据库隧道，不允许迁移或保存。请在隔离开发库验收写入。" />
      )}
      {record?.storage_ready && !record?.can_edit && (
        <Alert type="warning" message="当前账号只有查看权限。请通过角色管理授予「配置Listing评级规则」动作权限。" showIcon/>
      )}
    </Form>
  );

  return (
    <>
      {contextHolder}
      <Drawer title="Listing 规则配置" open={open} onClose={handleClose} destroyOnHidden width={760}
        extra={record && <Space><Tag color={!record.storage_ready ? "orange" : record.is_pending ? "gold" : "blue"}>{record.storage_ready ? `v${record.version}${record.is_pending ? " 待生效" : ""}` : "默认规则（只读）"}</Tag><Button onClick={() => { form.setFieldsValue(toForm(record.config)); setDirty(false); setReloadCount((n) => n + 1); }}>重置草稿</Button></Space>}>
        {loading ? <Skeleton active paragraph={{ rows: 10 }}/> : error || !record ? (
          <Alert type="error" showIcon message="规则加载失败" description="无法连接规则配置服务；非缺表故障不会伪装为默认数据。" action={<Button onClick={() => setReloadCount((count) => count + 1)}>重新加载</Button>}/>
        ) : (
          <Tabs activeKey={tab} onChange={(key) => {
            if (dirty && key !== tab) { messageApi.warning("请先保存或恢复当前修改，再切换分组"); return; }
            setTab(key);
            if (key === "history" && record.storage_ready) void loadHistory();
          }} items={[
            { key: "grade", label: "等级评级", children: gradeContent },
            { key: "lifecycle", label: "生命周期", children: sectionEditor("lifecycle") },
            { key: "stock", label: "库存与修复", children: sectionEditor("inventory_repair") },
            { key: "follow", label: "运营跟进", children: sectionEditor("follow_up") },
            { key: "history", label: "变更记录", children: !record.storage_ready ? (
              <Alert type="warning" showIcon message="版本历史尚不可用" description="配置存储未初始化。可预览默认规则，但没有已保存的版本记录。" />
            ) : historyLoading ? <Skeleton active/> : history?.items.length ? (
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
