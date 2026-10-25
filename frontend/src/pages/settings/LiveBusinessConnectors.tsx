import { Alert, Button, Drawer, Form, Input, InputNumber, Select, Space, Switch, Table, Tag, message } from "antd";
import { useCallback, useEffect, useState } from "react";
import {
  disableBusinessConnector, listBusinessConnectors, listFeishuRoutes, listNotificationDeliveries,
  listNotificationTemplates, saveBusinessConnector, saveFeishuRoute, saveNotificationTemplate,
  type BusinessConnector, type ConnectorWrite, type FeishuRoute, type NotificationDelivery,
  type NotificationTemplate,
} from "@/api/businessConnectorsApi";

const events = [
  { value: "inventory_alert", label: "库存预警" },
  { value: "sync_failed", label: "接口同步失败" },
  { value: "ads_alert", label: "广告异常" },
  { value: "approval_pending", label: "审批待处理" },
  { value: "ai_completed", label: "AI 任务完成" },
  { value: "finance_completed", label: "财务任务完成" },
];

type FormConnector = ConnectorWrite;

export default function LiveBusinessConnectors({ canManage }: { canManage: boolean }) {
  const [messageApi, context] = message.useMessage();
  const [items, setItems] = useState<BusinessConnector[]>([]);
  const [routes, setRoutes] = useState<FeishuRoute[]>([]);
  const [templates, setTemplates] = useState<NotificationTemplate[]>([]);
  const [deliveries, setDeliveries] = useState<NotificationDelivery[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [drawer, setDrawer] = useState<"connector" | "route" | "template" | null>(null);
  const [editing, setEditing] = useState<BusinessConnector | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<FormConnector>();
  const [routeForm] = Form.useForm<Omit<FeishuRoute, "id">>();
  const [templateForm] = Form.useForm<Omit<NotificationTemplate, "id">>();
  const kind = Form.useWatch("kind", form);
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [connectors, loadedRoutes, loadedTemplates, loadedDeliveries] = await Promise.all([
        listBusinessConnectors(), listFeishuRoutes(), listNotificationTemplates(), listNotificationDeliveries(),
      ]);
      setItems(connectors); setRoutes(loadedRoutes); setTemplates(loadedTemplates); setDeliveries(loadedDeliveries);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void Promise.all([
      listBusinessConnectors(), listFeishuRoutes(), listNotificationTemplates(), listNotificationDeliveries(),
    ]).then(([connectors, loadedRoutes, loadedTemplates, loadedDeliveries]) => {
      setItems(connectors); setRoutes(loadedRoutes); setTemplates(loadedTemplates); setDeliveries(loadedDeliveries);
      setError(false);
    }).catch(() => setError(true)).finally(() => setLoading(false));
  }, []);
  const openConnector = (item?: BusinessConnector) => {
    setEditing(item ?? null);
    form.resetFields();
    form.setFieldsValue({
      kind: item?.kind ?? "feishu_webhook",
      name: item?.name ?? "", enabled: item?.enabled ?? false,
      endpoint: "", credential: "", signing_secret: "",
      default_model: item?.config.default_model ?? "gpt-4.1-mini",
      backup_model: item?.config.backup_model ?? "",
      model_allowlist: item?.config.model_allowlist ?? ["gpt-4.1-mini"],
      daily_limit: item?.config.daily_limit ?? 100,
      monthly_budget_usd: Number(item?.config.monthly_budget_usd ?? 0),
      max_output_tokens: item?.config.max_output_tokens ?? 1024,
    });
    setDrawer("connector");
  };
  const submitConnector = async () => {
    let values: FormConnector;
    try { values = await form.validateFields(); } catch { return; }
    setSaving(true);
    try {
      const payload = { ...values,
        endpoint: values.endpoint?.trim() || undefined,
        credential: values.credential?.trim() || undefined,
        signing_secret: values.signing_secret?.trim() || undefined,
      };
      await saveBusinessConnector(payload, editing?.id);
      form.setFieldsValue({ credential: "", signing_secret: "", endpoint: "" });
      setDrawer(null);
      messageApi.success("配置已保存；密钥不会回显");
      await refresh();
    } catch { messageApi.error("保存失败，请检查权限、密钥配置或服务端迁移状态"); }
    finally { setSaving(false); }
  };
  const submitRoute = async () => {
    try { setSaving(true); const values = await routeForm.validateFields(); await saveFeishuRoute(values);
      messageApi.success("通知路由已保存"); setDrawer(null); await refresh(); }
    catch { messageApi.error("通知路由保存失败"); }
    finally { setSaving(false); }
  };
  const submitTemplate = async () => {
    try { setSaving(true); const values = await templateForm.validateFields(); await saveNotificationTemplate(values);
      messageApi.success("通知模板已保存"); setDrawer(null); await refresh(); }
    catch { messageApi.error("模板保存失败"); }
    finally { setSaving(false); }
  };
  return <div className="business-config__live">
    {context}
    <div className="business-config__draft-heading">
      <div><strong>正式服务连接管理</strong><p>服务端加密保存；可管理飞书群 Webhook 与 OpenAI 配置。默认关闭外发。</p></div>
      <Space><Button size="small" onClick={() => void refresh()}>刷新</Button>
        {canManage && <Button type="primary" onClick={() => openConnector()}>新增真实连接</Button>}</Space>
    </div>
    {error && <Alert type="error" showIcon message="真实连接服务尚不可用" description="请检查后端路由、数据库迁移及权限；本页面不会回退到虚拟连接。" />}
    <Table<BusinessConnector> loading={loading} size="small" rowKey="id" dataSource={items} pagination={false}
      columns={[
        { title: "连接名称", dataIndex: "name" },
        { title: "服务类型", dataIndex: "kind", render: (v: string) => v === "feishu_webhook" ? "飞书群机器人" : "OpenAI" },
        { title: "状态", dataIndex: "enabled", render: (v: boolean) => <Tag color={v ? "success" : "default"}>{v ? "已启用" : "已停用"}</Tag> },
        { title: "凭据状态", dataIndex: "credential_configured", render: (v: boolean, row) =>
          <Tag color={v || row.kind === "feishu_webhook" ? "success" : "warning"}>{v || row.kind === "feishu_webhook" ? "配置已保存" : "未配置"}</Tag> },
        { title: "操作", key: "actions", render: (_, row) => canManage ? <Space>
          <Button type="link" size="small" onClick={() => openConnector(row)}>编辑</Button>
          {row.enabled && <Button danger type="link" size="small" onClick={() => void disableBusinessConnector(row.id)
            .then(refresh).catch(() => messageApi.error("停用失败"))}>停用</Button>}
        </Space> : null },
      ]} />
    <div className="business-config__draft-heading"><strong>飞书通知路由</strong>
      {canManage && <Button size="small" onClick={() => { routeForm.resetFields(); routeForm.setFieldsValue({
        enabled: false, cooldown_seconds: 60, daily_limit: 100,
      }); setDrawer("route"); }}>新增通知路由</Button>}</div>
    <Table<FeishuRoute> size="small" rowKey="id" dataSource={routes} pagination={{ pageSize: 8 }}
      columns={[{ title: "通知事件", dataIndex: "event_key", render: (v: string) => events.find(x => x.value === v)?.label ?? v },
        { title: "目标飞书群", dataIndex: "connector_id", render: (id: string) => items.find(x => x.id === id)?.name ?? id },
        { title: "状态", dataIndex: "enabled", render: (v: boolean) => v ? "已启用" : "已停用" },
        { title: "冷却秒数", dataIndex: "cooldown_seconds" }, { title: "每日上限", dataIndex: "daily_limit" },
        { title: "操作", key: "edit", render: (_, row) => canManage ? <Button type="link" onClick={() => {
          routeForm.setFieldsValue(row); setDrawer("route"); }}>编辑</Button> : null },
      ]}/>
    <div className="business-config__draft-heading"><strong>通知模板</strong>
      {canManage && <Button size="small" onClick={() => { templateForm.resetFields(); templateForm.setFieldsValue({ enabled: true }); setDrawer("template"); }}>新增模板</Button>}</div>
    <Table<NotificationTemplate> size="small" rowKey="event_key" dataSource={templates} pagination={{ pageSize: 8 }}
      columns={[{ title: "事件", dataIndex: "event_key" }, { title: "标题", dataIndex: "title" },
        { title: "启用", dataIndex: "enabled", render: (v: boolean) => v ? "是" : "否" },
        { title: "操作", key: "edit", render: (_, row) => canManage ? <Button type="link" onClick={() => {
          templateForm.setFieldsValue(row); setDrawer("template"); }}>编辑</Button> : null }]}/>
    <div className="business-config__draft-heading"><strong>发送记录</strong></div>
    <Table<NotificationDelivery> size="small" rowKey="id" dataSource={deliveries} pagination={{ pageSize: 10 }}
      columns={[{ title: "事件", dataIndex: "event_key" }, { title: "状态", dataIndex: "status" },
        { title: "尝试", dataIndex: "attempts" }, { title: "失败码", dataIndex: "error_code" }, { title: "创建时间", dataIndex: "created_at" }]}/>
    <Drawer title={editing ? "编辑正式连接" : "新增正式连接"} open={drawer === "connector"} width={540}
      onClose={() => { form.setFieldsValue({credential:"",signing_secret:"",endpoint:""}); setDrawer(null); }}
      extra={<Space><Button onClick={() => setDrawer(null)}>取消</Button><Button type="primary" loading={saving} onClick={() => void submitConnector()}>保存配置</Button></Space>}>
      <Alert showIcon type="warning" message="请仅在受控环境中填写凭据" description="密钥发送到本系统后端加密存储，不在接口响应中回显。新连接默认停用；保存不会自动发送通知或调用 AI。" />
      <Form<FormConnector> form={form} layout="vertical" style={{ marginTop: 18 }}>
        <Form.Item name="kind" label="连接类型" rules={[{required:true}]}><Select disabled={Boolean(editing)} options={[
          {value:"feishu_webhook",label:"飞书群 Webhook"}, {value:"openai",label:"OpenAI"}]} /></Form.Item>
        <Form.Item name="name" label="连接名称" rules={[{required:true}]}><Input maxLength={100} /></Form.Item>
        {kind === "feishu_webhook" ? <>
          <Form.Item name="endpoint" label="群机器人 Webhook 地址" extra={editing ? "留空则保留原地址" : "仅允许飞书官方 Webhook 地址"}>
            <Input.Password autoComplete="new-password" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." />
          </Form.Item>
          <Form.Item name="signing_secret" label="签名密钥（可选）"><Input.Password autoComplete="new-password" placeholder="留空保留原签名密钥" /></Form.Item>
        </> : <>
          <Form.Item name="credential" label="OpenAI API Key"><Input.Password autoComplete="new-password" placeholder="留空保留原 API Key" /></Form.Item>
          <Form.Item name="default_model" label="默认模型" rules={[{required:true}]}><Input maxLength={100} /></Form.Item>
          <Form.Item name="backup_model" label="备用模型"><Input maxLength={100} /></Form.Item>
          <Form.Item name="model_allowlist" label="模型白名单" rules={[{required:true}]}><Select mode="tags" tokenSeparators={[","]} /></Form.Item>
          <Form.Item name="max_output_tokens" label="最大输出 Token"><InputNumber min={1} max={16384}/></Form.Item>
        </>}
        <Form.Item name="daily_limit" label="每日次数上限"><InputNumber min={1} max={100000}/></Form.Item>
        <Form.Item name="monthly_budget_usd" label="月度美元预算（仅 AI 适用）"><InputNumber min={0} max={1000000} precision={2}/></Form.Item>
        <Form.Item name="enabled" label="是否启用" valuePropName="checked"><Switch /></Form.Item>
      </Form>
    </Drawer>
    <Drawer title="飞书通知路由" width={520} open={drawer === "route"} onClose={() => setDrawer(null)}
      extra={<Button type="primary" loading={saving} onClick={() => void submitRoute()}>保存路由</Button>}>
      <Form form={routeForm} layout="vertical">
        <Form.Item name="event_key" label="通知事件" rules={[{required:true}]}><Select options={events}/></Form.Item>
        <Form.Item name="connector_id" label="目标飞书群" rules={[{required:true}]}><Select options={items.filter(x => x.kind === "feishu_webhook")
          .map(x => ({value:x.id,label:x.name}))}/></Form.Item>
        <Form.Item name="cooldown_seconds" label="冷却秒数"><InputNumber min={0} max={86400}/></Form.Item>
        <Form.Item name="daily_limit" label="每日发送上限"><InputNumber min={1} max={10000}/></Form.Item>
        <Form.Item name="enabled" label="是否启用" valuePropName="checked"><Switch /></Form.Item>
      </Form>
    </Drawer>
    <Drawer title="通知模板" width={520} open={drawer === "template"} onClose={() => setDrawer(null)}
      extra={<Button type="primary" loading={saving} onClick={() => void submitTemplate()}>保存模板</Button>}>
      <Form form={templateForm} layout="vertical">
        <Form.Item name="event_key" label="通知事件" rules={[{required:true}]}><Select options={events} /></Form.Item>
        <Form.Item name="title" label="通知标题" rules={[{required:true}]}><Input maxLength={120}/></Form.Item>
        <Form.Item name="body_template" label="消息正文" rules={[{required:true}]}><Input.TextArea rows={5} maxLength={2000}/></Form.Item>
        <Form.Item name="enabled" label="启用" valuePropName="checked"><Switch /></Form.Item>
      </Form>
    </Drawer>
  </div>;
}
