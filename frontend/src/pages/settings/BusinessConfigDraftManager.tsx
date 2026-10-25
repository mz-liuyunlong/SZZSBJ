import { PlusOutlined } from "@ant-design/icons";
import { Alert, Button, Drawer, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, message } from "antd";
import { useState } from "react";
import {
  BUSINESS_PROVIDERS, METERING_OPTIONS, newDraftId, readBrowserDrafts, writeBrowserDrafts,
  type BrowserDraftStore, type DraftCategory, type ServiceDraft, type PolicyDraft,
} from "./businessConfigDrafts";

const CATEGORIES: { value: DraftCategory; label: string }[] = [
  { value: "crawler", label: "爬虫与代理" }, { value: "ai", label: "AI 服务" },
  { value: "communication", label: "企业通讯" }, { value: "bots", label: "群机器人与通知" },
  { value: "commerce", label: "电商平台" }, { value: "erp", label: "ERP 与数据服务" },
  { value: "logistics", label: "物流与仓储" },
];
type ServiceForm = Pick<ServiceDraft, "category" | "provider" | "name" | "instanceKey" | "purpose" | "description" | "metering" | "dailyBudget">;
type PolicyForm = Pick<PolicyDraft, "name" | "scene" | "primaryInstance" | "fallbackInstance" | "dailyLimit" | "dailyBudget">;

export default function BusinessConfigDraftManager({
  section, category, keyword, status, canManage,
}: {
  section: "connections" | "policies";
  category: string;
  keyword: string;
  status: string;
  canManage: boolean;
}) {
  const [store, setStore] = useState(readBrowserDrafts);
  const [drawer, setDrawer] = useState<"service" | "policy" | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [serviceForm] = Form.useForm<ServiceForm>();
  const [policyForm] = Form.useForm<PolicyForm>();
  const serviceCategory = Form.useWatch("category", serviceForm);
  const metering = Form.useWatch("metering", serviceForm);
  const [messageApi, context] = message.useMessage();
  const [modal, modalContext] = Modal.useModal();
  const update = (next: BrowserDraftStore) => {
    setStore(next);
    writeBrowserDrafts(next);
  };
  const openService = (row?: ServiceDraft) => {
    setEditId(row?.id ?? null);
    serviceForm.resetFields();
    serviceForm.setFieldsValue(row ?? {
      category: category === "all" ? "ai" : category as DraftCategory,
      provider: category === "crawler" ? "Decodo" : "OpenAI",
      name: "", instanceKey: "", purpose: "", description: "", metering: "none", dailyBudget: 0,
    });
    setDrawer("service");
  };
  const saveService = async () => {
    let value: ServiceForm;
    try { value = await serviceForm.validateFields(); } catch { return; }
    const key = value.instanceKey.trim();
    if (store.services.some(row => row.instanceKey === key && row.id !== editId)
      || key === "decodo" || key === "system-default") {
      messageApi.error("实例标识已存在或属于系统保留标识"); return;
    }
    const item: ServiceDraft = {
      ...value,
      id: editId ?? newDraftId(),
      instanceKey: key,
      name: value.name.trim(),
      purpose: value.purpose?.trim() ?? "",
      description: value.description?.trim() ?? "",
      dailyBudget: value.metering === "none" ? 0 : (value.dailyBudget ?? 0),
      status: "draft",
      updatedAt: new Date().toISOString(),
    };
    update({ ...store, services: editId
      ? store.services.map(row => row.id === editId ? item : row)
      : [item, ...store.services] });
    setDrawer(null);
    messageApi.success("设计草稿已保存到当前浏览器会话；未建立真实 API 连接");
  };
  const deleteService = async (row: ServiceDraft) => {
    if (!await modal.confirm({ title: "删除该配置草稿？", content: "不会影响真实 Decodo 配置。",
      okType: "danger", okText: "删除", cancelText: "取消" })) return;
    update({ ...store, services: store.services.filter(item => item.id !== row.id) });
  };
  const toggleArchive = (row: ServiceDraft) => {
    update({ ...store, services: store.services.map(item => item.id === row.id
      ? { ...item, status: item.status === "draft" ? "archived" : "draft" } : item) });
  };
  const openPolicy = (row?: PolicyDraft) => {
    setEditId(row?.id ?? null);
    policyForm.resetFields();
    policyForm.setFieldsValue(row ?? {
      name: "", scene: "", primaryInstance: "decodo",
      fallbackInstance: "", dailyLimit: 1000, dailyBudget: 0,
    });
    setDrawer("policy");
  };
  const savePolicy = async () => {
    let value: PolicyForm;
    try { value = await policyForm.validateFields(); } catch { return; }
    if (value.fallbackInstance && value.primaryInstance === value.fallbackInstance) {
      messageApi.error("备用服务不能与主服务相同"); return;
    }
    const item: PolicyDraft = { ...value, id: editId ?? newDraftId(), status: "draft" };
    update({ ...store, policies: editId
      ? store.policies.map(row => row.id === editId ? item : row)
      : [item, ...store.policies] });
    setDrawer(null);
    messageApi.success("策略草稿已保存；不会限制或转发真实 API 请求");
  };
  const deletePolicy = async (row: PolicyDraft) => {
    if (!await modal.confirm({ title: "删除策略草稿？", okType: "danger", okText: "删除", cancelText: "取消" })) return;
    update({ ...store, policies: store.policies.filter(item => item.id !== row.id) });
  };
  const services = store.services.filter(row =>
    (category === "all" || category === row.category)
    && (status === "all" || (status === "未配置" && row.status === "draft"))
    && [row.name, row.provider, row.instanceKey, row.purpose].join(" ").toLowerCase().includes(keyword.toLowerCase().trim()));
  const choices = [
    { value: "decodo", label: "Decodo · 现有真实配置" },
    ...store.services.filter(s => s.status === "draft").map(s => ({ value: s.id, label: s.name + " · 草稿" })),
  ];
  return <>
    {context}{modalContext}
    <div className="business-config__draft-heading">
      <div>
        <strong>{section === "connections" ? "其他服务配置草稿" : "使用策略草稿"}</strong>
        <p>此区域保存浏览器会话中的设计草稿，刷新后保留、关闭会话后可能清除；不接收密钥、不连接外部服务。</p>
      </div>
      {canManage && <Button icon={<PlusOutlined />} type="primary"
        onClick={() => section === "connections" ? openService() : openPolicy()}>
        {section === "connections" ? "新增服务配置" : "新增使用策略"}
      </Button>}
    </div>
    {section === "connections" ? <Table<ServiceDraft> rowKey="id" size="small" dataSource={services}
      pagination={{ pageSize: 8 }} locale={{ emptyText: "暂无配置草稿，可以新增服务配置" }}
      columns={[
        { title: "服务 / 配置名称", dataIndex: "name", render: (name: string, row) =>
          <><strong>{name}</strong><div className="business-config__subline">{row.provider}</div></> },
        { title: "分类", dataIndex: "category", render: (key: DraftCategory) => CATEGORIES.find(c => c.value === key)?.label },
        { title: "实例标识", dataIndex: "instanceKey" },
        { title: "用途", dataIndex: "purpose" },
        { title: "计量方式", dataIndex: "metering", render: (key: string) => METERING_OPTIONS.find(m => m.value === key)?.label },
        { title: "状态", dataIndex: "status", render: (value: string) =>
          <Tag color={value === "draft" ? "warning" : "default"}>{value === "draft" ? "配置草稿" : "已归档"}</Tag> },
        { title: "操作", key: "action", render: (_, row) => canManage ? <Space size={0}>
          <Button size="small" type="link" onClick={() => openService(row)}>编辑</Button>
          <Button size="small" type="link" onClick={() => toggleArchive(row)}>{row.status === "draft" ? "归档" : "恢复"}</Button>
          <Button size="small" type="link" danger onClick={() => void deleteService(row)}>删除</Button>
        </Space> : null },
      ]} /> : <>
      <div className="business-config__draft-cards">
        {store.policies.map(row => <div className="business-config__draft-card" key={row.id}>
          <Tag color="warning">策略草稿 · 不执行</Tag>
          <h4>{row.name}</h4><p>使用场景：{row.scene || "未填写"}</p>
          <p>主服务：{choices.find(c => c.value === row.primaryInstance)?.label ?? "实例不存在"}</p>
          <p>每日额度：{row.dailyLimit} 次 · 计划预算：USD {row.dailyBudget}</p>
          {canManage && <Space><Button size="small" onClick={() => openPolicy(row)}>编辑</Button>
            <Button size="small" danger onClick={() => void deletePolicy(row)}>删除</Button></Space>}
        </div>)}
      </div>
    </>}

    <Drawer title={editId ? "编辑服务配置草稿" : "新增服务配置"} width={560} open={drawer === "service"}
      onClose={() => setDrawer(null)} extra={<Space><Button onClick={() => setDrawer(null)}>取消</Button>
        <Button type="primary" onClick={() => void saveService()}>保存草稿</Button></Space>}>
      <Alert type="warning" showIcon message="不会创建真实 API 连接"
        description="此处不接收密钥、Token、授权头或 Webhook URL。真实集成需要单独开发安全的后端凭据接口。" />
      <Form<ServiceForm> layout="vertical" form={serviceForm} className="business-config__draft-form">
        <Form.Item name="category" label="服务分类" rules={[{ required: true }]}>
          <Select options={CATEGORIES} onChange={(key: DraftCategory) => serviceForm.setFieldValue("provider", BUSINESS_PROVIDERS[key][0])} />
        </Form.Item>
        <Form.Item name="provider" label="服务商" rules={[{ required: true }]}>
          <Select options={(BUSINESS_PROVIDERS[serviceCategory as DraftCategory] ?? BUSINESS_PROVIDERS.ai)
            .map(name => ({ label: name, value: name }))} />
        </Form.Item>
        <Form.Item name="name" label="配置名称" rules={[{ required: true, whitespace: true, max: 60 }]}>
          <Input maxLength={60} placeholder="例如：Listing 文案 AI 服务"/>
        </Form.Item>
        <Form.Item name="instanceKey" label="实例标识" rules={[{ required: true, pattern: /^[A-Za-z0-9_-]{2,48}$/, message: "需要 2–48 位字母、数字、下划线或短横线" }]}>
          <Input placeholder="ai-listing"/>
        </Form.Item>
        <Form.Item name="purpose" label="业务用途"><Input maxLength={150} /></Form.Item>
        <Form.Item name="description" label="备注"><Input.TextArea rows={3} maxLength={240} /></Form.Item>
        <Form.Item name="metering" label="计量方式"><Select options={METERING_OPTIONS}/></Form.Item>
        {metering && metering !== "none" && <Form.Item name="dailyBudget" label="计划日预算（USD）"
          extra="仅草稿字段，不执行预算限制"><InputNumber min={0} precision={2} style={{ width: "100%" }}/></Form.Item>}
      </Form>
    </Drawer>

    <Drawer title={editId ? "编辑使用策略草稿" : "新增使用策略"} width={520} open={drawer === "policy"}
      onClose={() => setDrawer(null)} extra={<Space><Button onClick={() => setDrawer(null)}>取消</Button>
        <Button type="primary" onClick={() => void savePolicy()}>保存草稿</Button></Space>}>
      <Alert type="info" showIcon message="仅设计策略，不控制真实接口" />
      <Form<PolicyForm> layout="vertical" form={policyForm} className="business-config__draft-form">
        <Form.Item name="name" label="策略名称" rules={[{ required: true, whitespace: true }]}>
          <Input maxLength={60} />
        </Form.Item>
        <Form.Item name="scene" label="使用场景"><Input maxLength={150}/></Form.Item>
        <Form.Item name="primaryInstance" label="默认服务" rules={[{ required: true }]}>
          <Select options={choices}/>
        </Form.Item>
        <Form.Item name="fallbackInstance" label="备用服务"><Select allowClear options={choices}/></Form.Item>
        <Form.Item name="dailyLimit" label="计划每日额度"><InputNumber min={0} precision={0} style={{ width: "100%" }}/></Form.Item>
        <Form.Item name="dailyBudget" label="计划每日预算（USD）"><InputNumber min={0} precision={2} style={{ width: "100%" }}/></Form.Item>
      </Form>
    </Drawer>
  </>;
}
