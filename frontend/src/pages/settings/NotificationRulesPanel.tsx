import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Checkbox, Divider, Form, Input, InputNumber, message, Modal,
  Popconfirm, Select, Space, Table, Tabs, Tag, Typography } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  defaultNotificationRule, emptyRecipients, getNotificationDeliveries, getNotificationFields,
  getNotificationRules, getNotificationTargets, getNotificationRevisions, putNotificationRule, saveNotificationPerson,
  restoreNotificationRevision, simulateNotificationRule, type NotificationRuleRevision, type Condition, type Expression, type NotificationDelivery,
  type NotificationRule, type NotificationTarget, type RecipientSet, type Simulation,
  type StoredNotificationRule,
} from "@/api/notificationRulesApi";
import "./NotificationRulesPanel.css";

const EVENT_LABELS: Record<string, string> = {
  inventory_alert: "库存预警", sync_failed: "接口同步失败", ads_alert: "广告异常",
  approval_pending: "审批待处理", ai_completed: "AI 任务完成", finance_completed: "财务任务完成",
  purchase_alert: "采购异常", shipping_alert: "物流履约异常", listing_alert: "Listing 异常",
  sales_alert: "销售异常",
};
const FIELD_LABELS: Record<string, string> = {
  platform: "平台", store: "店铺", warehouse: "仓库", sku: "SKU", owner: "负责人",
  available_stock: "可售库存", inbound_stock: "在途库存", days_to_stockout: "预计断货天数",
  daily_sales_7d: "近7天日均销量", risk_level: "风险等级", job_type: "同步任务类型",
  failed_minutes: "失败时长（分钟）", retry_count: "重试次数", spend_7d: "近7天广告费",
  acos_7d: "近7天 ACOS", roas_7d: "近7天 ROAS", clicks_7d: "近7天点击",
  orders_7d: "近7天订单", zero_order_days: "连续无转化天数", approval_type: "审批类型",
  wait_hours: "等待小时", amount: "金额", task_type: "任务类型", duration_seconds: "运行秒数",
  profit: "净利润", margin_percent: "利润率（%）", refund_amount: "退款金额",
  supplier: "供应商", overdue_days: "逾期天数", purchase_qty: "采购数量",
  carrier: "物流商", unshipped_hours: "未发货小时", no_tracking_days: "无轨迹天数",
  rating: "评分", review_count: "评价数", has_buybox: "是否有购物车",
  sales_7d: "近7天销售额", sales_change_pct: "7天销量变化（%）",
  profit_7d: "近7天利润", margin_7d: "近7天利润率（%）",
};
const ROLE_LABELS: Record<string, string> = {
  sku_owner: "SKU 负责人", store_owner: "店铺负责人", buyer: "采购员",
  approver: "当前审批人", warehouse_owner: "仓库负责人", supervisor: "主管",
};
const OP_OPTIONS = [
  { label: "等于", value: "eq" }, { label: "不等于", value: "ne" },
  { label: "大于", value: "gt" }, { label: "≥", value: "gte" },
  { label: "小于", value: "lt" }, { label: "≤", value: "lte" },
  { label: "包含", value: "contains" }, { label: "属于", value: "in" },
  { label: "不属于", value: "not_in" }, { label: "介于", value: "between" },
];
const freshCondition = (field: string, kind = "text"): Condition => ({ field, op: kind === "number" ? "lte" : "eq", value: kind === "number" ? 0 : kind === "bool" ? false : "" });
const FIELDS_FALLBACK = { inventory_alert: { available_stock: "number", risk_level: "enum" } };

function CopyJson<T>(x: T): T { return JSON.parse(JSON.stringify(x)) as T; }

function ReceiverEditor({ value, onChange, targets, targetsError }: {
  value: RecipientSet; onChange: (x: RecipientSet) => void;
  targets: NotificationTarget; targetsError: string | null;
}) {
  const change = (p: Partial<RecipientSet>) => onChange({ ...value, ...p });
  const groupOptions = targets.groups.filter(g => g.enabled).map(g => ({ label: g.name, value: g.id }));
  const personOptions = targets.people.filter(p => p.enabled && p.mapped).map(p => ({ label: p.name, value: p.id }));
  // NOTIFICATION_TARGETS_REPAIR_V2: failures and empty configuration have distinct UI states.
  return <div className="nr-receivers">
    {targetsError && <Alert type="error" showIcon message="通知对象加载失败"
      description="无法读取候选数据。请检查 Network 中的 /api/business-rules/notification-rules/targets 接口状态码。"/>}
    <div><Typography.Text strong>飞书群（可搜索、多选）</Typography.Text>
      <Select mode="multiple" showSearch optionFilterProp="label" placeholder="选择已配置的飞书群" style={{ width: "100%" }}
        value={value.group_ids} onChange={(group_ids) => change({ group_ids })}
        options={groupOptions} notFoundContent={targetsError ? "接口加载失败" : "暂无可选飞书群"}/>
      {!targetsError && groupOptions.length === 0 && <Typography.Text type="secondary">
        暂无已启用的飞书群 Webhook。请先在「服务配置」完成配置；Webhook 无法自动列出所有飞书群。
      </Typography.Text>}
    </div>
    <div><Typography.Text strong>指定人员（可搜索、多选）</Typography.Text>
      <Select mode="multiple" showSearch optionFilterProp="label" placeholder="选择已登记飞书身份的员工" style={{ width: "100%" }}
        value={value.people_ids} onChange={(people_ids) => change({ people_ids })}
        options={personOptions} notFoundContent={targetsError ? "接口加载失败" : "暂无已映射员工"}/>
      {!targetsError && personOptions.length === 0 && <Typography.Text type="secondary">
        暂无飞书 Open ID 人员映射。可关闭规则编辑框，在「通知规则」页面点击「人员映射」登记。
      </Typography.Text>}
    </div>
    <div><Typography.Text strong>动态业务负责人</Typography.Text>
      <Checkbox.Group value={value.dynamic_roles} onChange={(a) => change({ dynamic_roles: a.map(String) })}
        options={Object.entries(ROLE_LABELS).map(([k, v]) => ({ value: k, label: v }))}/>
    </div>
    <Checkbox checked={value.group_mention} onChange={e => change({ group_mention: e.target.checked })}>
      群消息标记需要 @ 负责人（当前 Webhook 仅支持纯文本，不支持真实 @）
    </Checkbox>
  </div>;
}

function ConditionEditor({ value, onChange, fieldTypes }: {
  value: Expression; onChange: (x: Expression) => void; fieldTypes: Record<string, string>;
}) {
  const fieldKeys = Object.keys(fieldTypes);
  const setGroup = (i: number, patch: Partial<Expression["groups"][number]>) =>
    onChange({ ...value, groups: value.groups.map((x, j) => i === j ? { ...x, ...patch } : x) });
  const setCondition = (i: number, j: number, patch: Partial<Condition>) => setGroup(i, {
    conditions: value.groups[i].conditions.map((x, k) => k === j ? { ...x, ...patch } : x),
  });
  return <div className="nr-conditions">
    <Space><Typography.Text>条件组之间满足</Typography.Text>
      <Select style={{ width: 130 }} value={value.logic} onChange={logic => onChange({ ...value, logic })}
        options={[{ label: "全部（且）", value: "and" }, { label: "任意（或）", value: "or" }]}/></Space>
    {value.groups.map((g, i) => <div key={i} className="nr-group">
      <div className="nr-group-head">
        <Typography.Text strong>条件组 {i + 1}</Typography.Text>
        <Space><Select size="small" value={g.logic} style={{ width: 90 }}
          onChange={logic => setGroup(i, { logic })}
          options={[{ label: "且 AND", value: "and" }, { label: "或 OR", value: "or" }]}/>
          <Button size="small" type="text" danger icon={<DeleteOutlined />} disabled={value.groups.length === 1}
            onClick={() => onChange({ ...value, groups: value.groups.filter((_, k) => k !== i) })}/></Space>
      </div>
      {g.conditions.map((c, j) => {
        const kind = fieldTypes[c.field] ?? "text";
        const allowed = kind === "number" ? ["eq", "ne", "gt", "gte", "lt", "lte", "between"] :
          kind === "bool" ? ["eq", "ne"] : ["eq", "ne", "contains", "in", "not_in"];
        return <div className="nr-condition" key={`${i}-${j}`}>
          <Select showSearch optionFilterProp="label" value={c.field} style={{ flex: "2 1 150px", minWidth: 140 }}
            options={fieldKeys.map(f => ({ value: f, label: FIELD_LABELS[f] ?? f }))}
            onChange={field => setCondition(i, j, { field, op: fieldTypes[field] === "number" ? "lte" : "eq", value: fieldTypes[field] === "number" ? 0 : "" })}/>
          <Select value={c.op} style={{ flex: "1 1 110px", minWidth: 100 }}
            options={OP_OPTIONS.filter(op => allowed.includes(op.value))}
            onChange={op => setCondition(i, j, { op, value: op === "between" ? [0, 0] : op === "in" || op === "not_in" ? [] : kind === "number" ? 0 : "" })}/>
          <div className="nr-condition-value">
            {kind === "bool" ? <Select value={c.value} onChange={value => setCondition(i, j, { value })}
              options={[{ value: true, label: "是" }, { value: false, label: "否" }]}/> :
            c.op === "between" ? <Space.Compact block>
              {[0, 1].map(k => <InputNumber key={k} style={{ width: "50%" }} placeholder={k ? "最大" : "最小"}
                value={Array.isArray(c.value) ? Number(c.value[k]) : 0}
                onChange={v => { const a = Array.isArray(c.value) ? [...c.value] as number[] : [0, 0]; a[k] = v ?? 0; setCondition(i, j, { value: a }); }}/>)}</Space.Compact> :
            c.op === "in" || c.op === "not_in" ? <Select mode="tags" tokenSeparators={[","]} style={{ width: "100%" }}
              placeholder="输入值并回车" value={Array.isArray(c.value) ? c.value.map(String) : []}
              onChange={value => setCondition(i, j, { value })}/> :
            kind === "enum" && c.field === "risk_level" ?
              <Select style={{ width: "100%" }} value={c.value} onChange={v => setCondition(i, j, { value: v })}
                options={["low", "medium", "high", "critical"].map(v => ({ value: v, label: v }))}/> :
            kind === "number" ? <InputNumber style={{ width: "100%" }} value={Number(c.value)}
              onChange={v => setCondition(i, j, { value: v ?? 0 })}/> :
              <Input value={String(c.value)} onChange={e => setCondition(i, j, { value: e.target.value })} placeholder="比较值"/>}
          </div>
          <Button type="text" danger icon={<DeleteOutlined />} disabled={g.conditions.length === 1}
            onClick={() => setGroup(i, { conditions: g.conditions.filter((_, k) => k !== j) })}/>
        </div>;
      })}
      <Button type="dashed" size="small" icon={<PlusOutlined />}
        onClick={() => setGroup(i, { conditions: [...g.conditions, freshCondition(fieldKeys[0] ?? "available_stock", fieldTypes[fieldKeys[0]] ?? "number")] })}>添加条件</Button>
    </div>)}
    <Button size="small" icon={<PlusOutlined />} onClick={() => onChange({ ...value, groups: [...value.groups,
      { logic: "and", conditions: [freshCondition(fieldKeys[0] ?? "available_stock", fieldTypes[fieldKeys[0]] ?? "number")] }] })}>添加条件组</Button>
  </div>;
}

function PreviewText({ rule }: { rule: NotificationRule }) {
  return <div className="nr-preview"><Typography.Text type="secondary">示意预览（不发送）</Typography.Text>
    <pre>{rule.group_template.replaceAll("{event_key}", EVENT_LABELS[rule.event_key] ?? rule.event_key)
      .replaceAll("{message}", "示例业务异常").replaceAll("{sku}", "SKU-DEMO")}</pre></div>;
}

export default function NotificationRulesPanel({ canManage }: { canManage: boolean }) {
  const [messageApi, messageContext] = message.useMessage();
  const [rows, setRows] = useState<StoredNotificationRule[]>([]);
  const [fields, setFields] = useState<Record<string, Record<string, string>>>(FIELDS_FALLBACK);
  const [targets, setTargets] = useState<NotificationTarget>({ groups: [], people: [] });
  const [targetsError, setTargetsError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [editor, setEditor] = useState<NotificationRule | null>(null);
  const [editingId, setEditingId] = useState<string | undefined>();
  const [editorTab, setEditorTab] = useState("basic");
  const [saving, setSaving] = useState(false);
  const [personModal, setPersonModal] = useState(false);
  const [personName, setPersonName] = useState("");
  const [employeeKey, setEmployeeKey] = useState("");
  const [openId, setOpenId] = useState("");
  const [deliveries, setDeliveries] = useState<NotificationDelivery[]>([]);
  const [logOpen, setLogOpen] = useState(false);
  const [historyId, setHistoryId] = useState<string | null>(null);
  const [revisions, setRevisions] = useState<NotificationRuleRevision[]>([]);
  const [sample, setSample] = useState<Record<string, string | number | boolean>>({});
  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [sampleBusy, setSampleBusy] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rules, defs, choices] = await Promise.allSettled([
        getNotificationRules(), getNotificationFields(), getNotificationTargets(),
      ]);
      if (rules.status === "fulfilled") setRows(rules.value);
      else messageApi.error("规则列表加载失败，请检查后端及现有数据库表");
      if (defs.status === "fulfilled") setFields(defs.value);
      else messageApi.error("规则字段加载失败，请检查接口权限");
      if (choices.status === "fulfilled") {
        setTargets(choices.value);
        setTargetsError(null);
      } else {
        setTargets({ groups: [], people: [] });
        setTargetsError("TARGETS_API_FAILED");
        messageApi.error("通知对象加载失败，请检查 /notification-rules/targets 接口");
      }
    } catch {
      messageApi.error("规则数据处理失败，请检查控制台错误");
    } finally {
      setLoading(false);
    }
  }, [messageApi]);
  useEffect(() => {
    // Defer the state-changing refresh outside the synchronous effect body.
    let active = true;
    void Promise.resolve().then(() => { if (active) void load(); });
    return () => { active = false; };
  }, [load]);
  const edit = (rule?: StoredNotificationRule) => {
    const first = Object.keys(fields)[0] ?? "inventory_alert";
    const field = Object.keys(fields[first] ?? {}).find(k => fields[first][k] === "number") ?? Object.keys(fields[first] ?? {})[0] ?? "available_stock";
    const spec = rule ? { ...CopyJson(rule.spec), enabled: false } : defaultNotificationRule(first, field);
    if (!rule) spec.name = "";
    setEditor(spec); setEditingId(rule?.id); setEditorTab("basic"); setSample({}); setSimulation(null);
  };
  const change = (patch: Partial<NotificationRule>) => setEditor(v => v ? { ...v, ...patch } : v);
  const fieldTypes = editor ? fields[editor.event_key] ?? {} : {};
  const eventOptions = useMemo(() => Object.keys(fields).map(k => ({ value: k, label: EVENT_LABELS[k] ?? k })), [fields]);
  const receiverSummary = (rule: NotificationRule) => {
    const count = rule.recipients.group_ids.length;
    const num = rule.recipients.people_ids.length;
    const dynamic = rule.recipients.dynamic_roles.length;
    return [count ? `${count} 个群` : "", num ? `${num} 人` : "", dynamic ? `${dynamic} 个动态角色` : ""].filter(Boolean).join(" + ") || "未配置";
  };
  const save = async () => {
    if (!editor) return;
    if (!editor.name.trim()) { messageApi.warning("请填写规则名称"); setEditorTab("basic"); return; }
    setSaving(true);
    try {
      await putNotificationRule({ ...editor, enabled: false }, editingId);
      messageApi.success("通知规则已保存"); setEditor(null); await load();
    } catch { messageApi.error("保存失败，请检查条件值、权限与数据库状态"); }
    finally { setSaving(false); }
  };
  const runSimulation = async () => {
    if (!editor) return;
    setSampleBusy(true);
    try {
      const r = await simulateNotificationRule(editor, [{ object_key: "UI_TEST_SAMPLE", facts: sample }]);
      setSimulation(r);
    } catch { messageApi.error("模拟验证失败：请检查字段或条件配置"); }
    finally { setSampleBusy(false); }
  };
  const activeFieldNames = editor ? Array.from(new Set([
    ...editor.condition.groups.flatMap(g => g.conditions.map(c => c.field)),
    ...editor.branches.flatMap(b => b.when.groups.flatMap(g => g.conditions.map(c => c.field))),
    ...Object.keys(editor.scope),
  ])) : [];
  return <Card className="nr-panel" title="通知规则" loading={loading} extra={<Space>
    <Button size="small" icon={<ReloadOutlined />} onClick={() => void load()}>刷新列表</Button>
    <Button size="small" disabled title="无迁移模式暂不执行通知发送；当前没有新规则发送记录"
      onClick={() => { setLogOpen(true); void getNotificationDeliveries().then(setDeliveries).catch(() => messageApi.error("运行存储尚未启用")); }}>发送记录</Button>
    {canManage && <Button size="small" onClick={() => setPersonModal(true)}>人员映射</Button>}
    {canManage && <Button type="primary" icon={<PlusOutlined />} onClick={() => edit()}>新增规则</Button>}
  </Space>}>
    {messageContext}
    <Alert type="warning" showIcon style={{ marginBottom: 12 }}
      message="无迁移安全模式：规则保存和模拟可用，真实通知发送暂不可用"
      description="规则只保存为草稿；不会在服务器建表或执行迁移，也不会自动发群消息或私聊。请勿将配置完成视为通知生效。" />
    <Table rowKey="id" size="small" dataSource={rows} pagination={{ pageSize: 10 }} scroll={{ x: 900 }} columns={[
      { title: "规则名称", dataIndex: "name", width: 210, render: (v: string, r: StoredNotificationRule) =>
        <Space direction="vertical" size={0}><Typography.Text strong>{v}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>V{r.version}</Typography.Text></Space> },
      { title: "业务事件", dataIndex: "event_key", width: 150, render: (v: string) => EVENT_LABELS[v] ?? v },
      { title: "触发规则", width: 120, render: (_: unknown, r: StoredNotificationRule) =>
        `${r.spec.condition.groups.length} 个条件组` },
      { title: "通知对象", render: (_: unknown, r: StoredNotificationRule) => receiverSummary(r.spec) },
      { title: "发送策略", width: 105, render: (_: unknown, r: StoredNotificationRule) =>
        ({ immediate: "立即", daily: "定时", aggregate: "合并" })[r.spec.policy.mode] },
      { title: "状态", dataIndex: "enabled", width: 95, render: () =>
        <Tag color="default">草稿</Tag> },
      { title: "操作", width: 150, fixed: "right" as const, render: (_: unknown, r: StoredNotificationRule) => <Space size={0}>
        <Button type="link" size="small" icon={<EditOutlined />} onClick={() => edit(r)}>编辑</Button>
        {canManage && <Button type="link" size="small" onClick={() => edit({ ...r, id: "", spec: { ...CopyJson(r.spec), name: r.name + "（副本）", enabled: false } })}>复制</Button>}
        <Button type="link" size="small" onClick={() => { setHistoryId(r.id); void getNotificationRevisions(r.id).then(setRevisions).catch(() => messageApi.error("版本记录读取失败")); }}>版本</Button>
      </Space> },
    ]}/>
    <Modal className="nr-modal" title={editingId ? "编辑通知规则" : "新增通知规则"} width={1050}
      open={!!editor} centered destroyOnHidden maskClosable={!saving} closable={!saving}
      onCancel={() => setEditor(null)}
      footer={<Space><Button disabled={saving} onClick={() => setEditor(null)}>取消</Button>
        {canManage && <Button type="primary" loading={saving} onClick={() => void save()}>保存配置</Button>}</Space>}>
      {editor && <div className="nr-editor">
        <Tabs activeKey={editorTab} onChange={setEditorTab} items={[
          { key: "basic", label: "基本信息" }, { key: "condition", label: "触发条件" },
          { key: "recipient", label: "通知对象" }, { key: "policy", label: "发送策略" },
          { key: "template", label: "通知内容" }, { key: "simulate", label: "模拟验证" },
        ]}/>
        {editorTab === "basic" && <div className="nr-section">
          <label>规则名称</label><Input value={editor.name} maxLength={120} placeholder="例如：库存低于7天通知负责人"
            onChange={e => change({ name: e.target.value })}/>
          <label>业务事件</label><Select value={editor.event_key} options={eventOptions} showSearch optionFilterProp="label"
            onChange={v => { const first = Object.keys(fields[v]).find(k => fields[v][k] === "number") ?? Object.keys(fields[v])[0]; change({ event_key: v, scope: {},
              condition: { logic: "and", groups: [{ logic: "and", conditions: [freshCondition(first, fields[v][first])] }] }, branches: [] }); }}/>
          <label>适用范围（可选，按平台、店铺等限制）</label>
          {Object.entries(fieldTypes).filter(([, t]) => t === "text").slice(0, 5).map(([key]) => <div className="nr-scope-row" key={key}>
            <Typography.Text>{FIELD_LABELS[key] ?? key}</Typography.Text>
            <Select mode="tags" style={{ flex: 1 }} placeholder="留空表示不限；输入值回车"
              value={editor.scope[key] ?? []}
              onChange={v => change({ scope: { ...editor.scope, [key]: v } })}/>
          </div>)}
          <Checkbox checked={false} disabled>通知发送暂不可启用（无迁移模式）</Checkbox>
          <Typography.Text type="secondary">新规则默认停用。启用不代表自动接入业务事件，需由后端按接口推送标准化业务数据。</Typography.Text>
        </div>}
        {editorTab === "condition" && <div className="nr-section">
          <Alert type="info" showIcon message="条件按受控业务字段判断；数据缺失会返回“无法判断”，不会视为零。"/>
          <ConditionEditor value={editor.condition} fieldTypes={fieldTypes} onChange={condition => change({ condition })}/>
          <Divider style={{ margin: "8px 0" }}/>
          <Checkbox checked={!!editor.recovery_condition} onChange={e => change({ recovery_condition:
            e.target.checked ? CopyJson(editor.condition) : null })}>单独设置恢复阈值（避免指标在边界波动）</Checkbox>
          {editor.recovery_condition && <Card size="small" title="恢复条件：符合时解除当前异常">
            <ConditionEditor fieldTypes={fieldTypes} value={editor.recovery_condition}
              onChange={recovery_condition => change({ recovery_condition })}/>
          </Card>}
          <Divider style={{ margin: "8px 0" }}/>
          <Typography.Text strong>条件分支（可选：根据严重程度发送给不同对象）</Typography.Text>
          {editor.branches.map((branch, i) => <Card size="small" key={i} title={<Input size="small" style={{ width: 220 }} value={branch.label} onChange={e =>
            change({ branches: editor.branches.map((b, j) => i === j ? { ...b, label: e.target.value } : b) })}/>} extra={<Button danger type="text" icon={<DeleteOutlined />} onClick={() => change({ branches: editor.branches.filter((_, j) => j !== i) })}/> }>
            <ConditionEditor fieldTypes={fieldTypes} value={branch.when} onChange={when => change({ branches: editor.branches.map((b, j) => j === i ? { ...b, when } : b) })}/>
            <Divider/><ReceiverEditor targets={targets} targetsError={targetsError} value={branch.recipients}
              onChange={recipients => change({ branches: editor.branches.map((b, j) => j === i ? { ...b, recipients } : b) })}/>
            <Input.TextArea rows={2} style={{ marginTop: 12 }} value={branch.group_template}
              onChange={e => change({ branches: editor.branches.map((b, j) => j === i ? { ...b, group_template: e.target.value } : b) })}/>
            <Input.TextArea rows={2} style={{ marginTop: 8 }} value={branch.personal_template}
              onChange={e => change({ branches: editor.branches.map((b, j) => j === i ? { ...b, personal_template: e.target.value } : b) })}/>
          </Card>)}
          <Button icon={<PlusOutlined />} size="small" disabled={editor.branches.length >= 8} onClick={() => change({
            branches: [...editor.branches, { label: "严重分支", when: { logic: "and", groups: [{ logic: "and", conditions: [{ field: fieldTypes.risk_level ? "risk_level" : Object.keys(fieldTypes)[0], op: "eq", value: "critical" }] }] },
              recipients: emptyRecipients(), group_template: editor.group_template, personal_template: editor.personal_template }],
          })}>添加条件分支</Button>
        </div>}
        {editorTab === "recipient" && <div className="nr-section">
          <ReceiverEditor value={editor.recipients} onChange={recipients => change({ recipients })} targets={targets} targetsError={targetsError}/>
          <Typography.Text type="secondary">指定人员与动态负责人均基于服务端已登记的飞书 Open ID；若仅配置 Webhook，个人私聊不会自动可用。</Typography.Text>
        </div>}
        {editorTab === "policy" && <div className="nr-section">
          <div className="nr-pair"><div><label>发送方式</label><Select value={editor.policy.mode}
            options={[{ label: "立即发送", value: "immediate" }, { label: "指定时间发送", value: "daily" }, { label: "延后合并窗口", value: "aggregate" }]}
            onChange={mode => change({ policy: { ...editor.policy, mode } })}/></div>
            <div><label>时区</label><Select value={editor.policy.timezone}
              options={[{ label: "北京时间", value: "Asia/Shanghai" }, { label: "美国东部", value: "America/New_York" }, { label: "UTC", value: "UTC" }]}
              onChange={timezone => change({ policy: { ...editor.policy, timezone } })}/></div></div>
          <div className="nr-pair"><div><label>定时发送时间（HH:MM）</label><Input value={editor.policy.daily_time} placeholder="09:00" onChange={e => change({ policy: { ...editor.policy, daily_time: e.target.value } })}/></div>
            <div><label>延后窗口（分钟）</label><InputNumber min={5} max={1440} value={editor.policy.aggregate_minutes} onChange={v => change({ policy: { ...editor.policy, aggregate_minutes: v ?? 30 } })}/></div></div>
          <div className="nr-pair"><div><label>冷却时间（分钟）</label><InputNumber min={0} max={10080} value={editor.policy.cooldown_minutes} onChange={v => change({ policy: { ...editor.policy, cooldown_minutes: v ?? 0 } })}/></div>
            <div><label>每日发送上限（按规则）</label><InputNumber min={1} max={10000} value={editor.policy.daily_limit} onChange={v => change({ policy: { ...editor.policy, daily_limit: v ?? 100 } })}/></div></div>
          <div className="nr-pair"><div><label>触发方式</label><Select value={editor.policy.trigger}
            options={[{ label: "首次进入异常状态", value: "on_enter" }, { label: "持续异常允许重复", value: "repeat" }]}
            onChange={trigger => change({ policy: { ...editor.policy, trigger } })}/></div>
            <div><label>连续命中次数（防抖）</label><InputNumber min={1} max={10} value={editor.policy.debounce_samples} onChange={v => change({ policy: { ...editor.policy, debounce_samples: v ?? 1 } })}/></div></div>
          <Checkbox checked={editor.policy.send_recovery} onChange={e => change({ policy: { ...editor.policy, send_recovery: e.target.checked } })}>恢复正常时发送通知</Checkbox>
          <div className="nr-pair"><div><label>免打扰开始（可空）</label><Input placeholder="22:00" value={editor.policy.quiet_from ?? ""} onChange={e => change({ policy: { ...editor.policy, quiet_from: e.target.value || null } })}/></div>
            <div><label>免打扰结束（可空）</label><Input placeholder="08:00" value={editor.policy.quiet_until ?? ""} onChange={e => change({ policy: { ...editor.policy, quiet_until: e.target.value || null } })}/></div></div>
          <Divider/><Typography.Text strong>逾期升级</Typography.Text>
          <div><label>未处理多少分钟后升级（0 表示不升级）</label><InputNumber min={0} max={10080} value={editor.policy.escalation_minutes} onChange={v => change({ policy: { ...editor.policy, escalation_minutes: v ?? 0 } })}/></div>
          {editor.policy.escalation_minutes > 0 && <ReceiverEditor value={editor.policy.escalation_recipients} targets={targets} targetsError={targetsError}
            onChange={escalation_recipients => change({ policy: { ...editor.policy, escalation_recipients } })}/>}
          <Typography.Text type="secondary">升级基于后台异常状态和确认记录，不以飞书消息已发送当作已处理。</Typography.Text>
        </div>}
        {editorTab === "template" && <div className="nr-section">
          <label>群通知模板</label><Input.TextArea rows={5} value={editor.group_template} onChange={e => change({ group_template: e.target.value })}/>
          <label>个人私聊模板</label><Input.TextArea rows={5} value={editor.personal_template} onChange={e => change({ personal_template: e.target.value })}/>
          <Typography.Text type="secondary">支持字段变量，例如 {"{sku}"}、{"{available_stock}"}、{"{message}"}。无值字段显示“—”。</Typography.Text>
          <PreviewText rule={editor}/>
        </div>}
        {editorTab === "simulate" && <div className="nr-section">
          <Alert type="info" showIcon message="离线样本模拟，不产生发送记录，也不会通知飞书。"/>
          {activeFieldNames.map(field => <div className="nr-sample" key={field}><Typography.Text>{FIELD_LABELS[field] ?? field}</Typography.Text>
            {fieldTypes[field] === "number" ? <InputNumber value={sample[field] as number | undefined} placeholder="输入测试数据"
              onChange={v => setSample(s => ({ ...s, [field]: v ?? 0 }))}/> :
              fieldTypes[field] === "bool" ? <Checkbox checked={Boolean(sample[field])}
                onChange={e => setSample(s => ({ ...s, [field]: e.target.checked }))}>是</Checkbox> :
              <Input value={String(sample[field] ?? "")} onChange={e => setSample(s => ({ ...s, [field]: e.target.value }))}/>}
          </div>)}
          <Button type="primary" loading={sampleBusy} onClick={() => void runSimulation()}>模拟验证</Button>
          {simulation && <Alert type={simulation.matches ? "success" : simulation.unknowns ? "warning" : "info"} showIcon
            message={simulation.matches ? "规则命中" : simulation.unknowns ? "部分字段缺失，无法判断" : "规则未命中"}
            description={`匹配 ${simulation.matches}，数据缺失 ${simulation.unknowns}，不匹配 ${simulation.no_matches}`}/>}
        </div>}
      </div>}
    </Modal>
    <Modal title="历史版本" open={historyId !== null} onCancel={() => setHistoryId(null)} footer={null} width={650}>
      <Table size="small" rowKey="version" dataSource={revisions} pagination={{ pageSize: 10 }} columns={[
        { title: "版本", dataIndex: "version", render: (v: number) => `V${v}` },
        { title: "修改时间", dataIndex: "created_at" },
        { title: "操作", render: (_: unknown, rev: NotificationRuleRevision) => canManage && <Popconfirm
          title="恢复该版本？" description="恢复后默认停用，需要检查并再次启用。"
          onConfirm={() => historyId && restoreNotificationRevision(historyId, rev.version)
            .then(() => { setHistoryId(null); messageApi.success("版本已恢复（已停用）"); void load(); })
            .catch(() => messageApi.error("历史版本恢复失败"))}
        ><Button type="link" size="small">恢复</Button></Popconfirm> },
      ]}/>
    </Modal>
    <Modal title="人员飞书身份映射" open={personModal} onCancel={() => setPersonModal(false)} footer={null} width={610}>
      <Alert type="info" showIcon message="用于向员工发送私聊通知。需具备可用的飞书应用机器人和发送权限；不要粘贴个人 access token。"/>
      <Table size="small" style={{ marginTop: 12 }} rowKey="id" dataSource={targets.people}
        pagination={{ pageSize: 5 }} columns={[{ title: "员工", dataIndex: "name" },
          { title: "员工标识", dataIndex: "employee_key" }, { title: "飞书映射", dataIndex: "mapped", render: (v: boolean) => v ? "已配置" : "缺失" }]}/>
      <Form layout="vertical" onFinish={async () => {
        try { await saveNotificationPerson({ name: personName, employee_key: employeeKey, feishu_open_id: openId });
          setPersonName(""); setEmployeeKey(""); setOpenId(""); messageApi.success("人员映射已保存"); await load(); }
        catch { messageApi.error("人员映射保存失败"); }
      }}>
        <Form.Item label="员工姓名" required><Input value={personName} onChange={e => setPersonName(e.target.value)}/></Form.Item>
        <Form.Item label="内部员工标识" required><Input value={employeeKey} onChange={e => setEmployeeKey(e.target.value)}/></Form.Item>
        <Form.Item label="飞书 Open ID" required><Input.Password autoComplete="off" value={openId} onChange={e => setOpenId(e.target.value)}/></Form.Item>
        <Button htmlType="submit" type="primary" disabled={!personName.trim() || !employeeKey.trim() || !openId.trim()}>保存人员映射</Button>
      </Form>
    </Modal>
    <Modal title="通知发送记录" open={logOpen} onCancel={() => setLogOpen(false)} footer={null} width={800}>
      <Table size="small" rowKey="id" dataSource={deliveries} pagination={{ pageSize: 10 }} columns={[
        { title: "消息事件", dataIndex: "event_id", ellipsis: true },
        { title: "对象", dataIndex: "kind", width: 70, render: (k: string) => k === "group" ? "群" : "个人" },
        { title: "状态", dataIndex: "status", width: 85 },
        { title: "重试", dataIndex: "attempts", width: 60 },
        { title: "失败代码", dataIndex: "error_code", ellipsis: true },
      ]}/>
    </Modal>
  </Card>;
}
