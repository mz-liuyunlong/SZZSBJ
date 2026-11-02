import { Alert, Button, Form, Input, InputNumber, Modal, Select, Space, Switch, message } from "antd";
import { useEffect, useState } from "react";
import { OPENAI_DEFAULT_SCENES, OPENAI_FIXED_MODEL, OPENAI_INPUT_USD_PER_MTOK, OPENAI_OUTPUT_USD_PER_MTOK, resolveOpenAIBillingRates } from "./openaiConnectorDefaults";
import "./BusinessConfigServiceEditor.css";
import { backendRequest } from "@/api/backendApi";
import SkillBindingPicker from "./SkillBindingPicker";
import { SCENES as SKILL_SCENES } from "./skillSceneOptions";
import {
  saveBusinessConnector, type BusinessConnector, type ConnectorKind, type ConnectorWrite,
} from "@/api/businessConnectorsApi";
import {
  BUSINESS_PROVIDERS, METERING_OPTIONS, newDraftId, readBrowserDrafts, writeBrowserDrafts,
  type DraftCategory, type ServiceDraft,
} from "./businessConfigDrafts";

type Choice = ConnectorKind | "draft";
type ServiceForm = ConnectorWrite & {
  choice: Choice;
  draft_category: DraftCategory;
  provider: string;
  instanceKey: string;
  purpose: string;
  description: string;
  metering: ServiceDraft["metering"];
  dailyBudget: number;
};
const categories: { value: DraftCategory; label: string }[] = [
  { value: "crawler", label: "爬虫与代理" },
  { value: "ai", label: "AI 服务" },
  { value: "communication", label: "企业通讯" },
  { value: "bots", label: "群机器人与通知" },
  { value: "commerce", label: "电商平台" },
  { value: "erp", label: "ERP 与数据服务" },
  { value: "logistics", label: "物流与仓储" },
];

interface Props {
  open: boolean;
  connector?: BusinessConnector | null;
  draft?: ServiceDraft | null;
  preferredCategory?: string;
  onClose: () => void;
  onSaved: () => void;
}

export default function BusinessConfigServiceEditor({
  open, connector, draft, preferredCategory, onClose, onSaved,
}: Props) {
  const [form] = Form.useForm<ServiceForm>();
  const [saving, setSaving] = useState(false);
  const [savedConnectorId,setSavedConnectorId]=useState<string>();
  const [skillBindings,setSkillBindings]=useState<Record<string,string|null>>({});
  const [skillBindingsReady,setSkillBindingsReady]=useState(true);
  const choice = Form.useWatch("choice", form);
  const draftCategory = Form.useWatch("draft_category", form);
  const metering = Form.useWatch("metering", form);
  const [applicationScenes] = [Form.useWatch("application_scenes", form) as string[] | undefined];
  const [messageApi, context] = message.useMessage();
  useEffect(() => {
    let active = true;
    if (!open || connector?.kind !== "openai") {
      void Promise.resolve().then(() => {
        if (active) { setSkillBindings({}); setSkillBindingsReady(true); }
      });
      return () => { active = false; };
    }
    void Promise.resolve().then(() => {
      if (active) setSkillBindingsReady(false);
    });
    void backendRequest<Array<{scene:string;revision_id:string|null}>>(
      `/api/ai-runtime/skill-library/bindings?connector_id=${encodeURIComponent(connector.id)}`)
      .then(response => { if (active) {
        setSkillBindings(Object.fromEntries(response.data.map(item=>[item.scene,item.revision_id])));
        setSkillBindingsReady(true);
      }})
      .catch(() => { if (active) messageApi.error("Skill 绑定读取失败，已禁止覆盖现有配置"); });
    return () => { active = false; };
  }, [open, connector?.id, connector?.kind, messageApi]);

  useEffect(() => {
    if (!open) return;
    let rates;
    try {
      rates = resolveOpenAIBillingRates(connector?.config);
    } catch {
      messageApi.error("已保存的 OpenAI 单价格式无效，已阻止编辑保存以保护原计费配置");
      return;
    }
    const base: ServiceForm = {
      choice: connector?.kind ?? (draft ? "draft" : preferredCategory === "bots" ? "feishu_webhook" : preferredCategory === "ai" ? "openai" : "feishu_webhook"),
      kind: connector?.kind ?? "feishu_webhook",
      name: connector?.name ?? draft?.name ?? "",
      enabled: connector?.enabled ?? false,
      endpoint: "",
      credential: "",
      signing_secret: "",
      default_model: OPENAI_FIXED_MODEL,
      backup_model: "",
      model_allowlist: [OPENAI_FIXED_MODEL],
      application_scenes: connector?.config.application_scenes ?? [...OPENAI_DEFAULT_SCENES],
      daily_limit: connector?.config.daily_limit ?? 100,
      monthly_budget_usd: Number(connector?.config.monthly_budget_usd ?? 0),
      max_output_tokens: connector?.config.max_output_tokens ?? 1024,
      input_price_per_million: rates.input_price_per_million,
      output_price_per_million: rates.output_price_per_million,
      draft_category: draft?.category ?? (categories.find((entry) => entry.value === preferredCategory)?.value ?? "ai"),
      provider: draft?.provider ?? "OpenAI",
      instanceKey: draft?.instanceKey ?? "",
      purpose: draft?.purpose ?? "",
      description: draft?.description ?? "",
      metering: draft?.metering ?? "none",
      dailyBudget: draft?.dailyBudget ?? 0,
    };
    form.setFieldsValue(base);
  }, [open, connector, draft, preferredCategory, form, messageApi]);

  const close = () => {
    setSkillBindings({});setSavedConnectorId(undefined);
    form.setFieldsValue({ credential: "", signing_secret: "", endpoint: "" });
    onClose();
  };
  const save = async () => {
    let data: ServiceForm;
    try {
      data = await form.validateFields();
    } catch {
      return;
    }
    if (data.choice === "openai") {
      try {
        resolveOpenAIBillingRates(connector?.config);
      } catch {
        messageApi.error("现有计费单价无效，禁止保存覆盖");
        return;
      }
    }
    setSaving(true);
    try {
      if (data.choice === "draft") {
        const key = data.instanceKey.trim();
        const store = readBrowserDrafts();
        if (store.services.some((item) => item.id !== draft?.id && item.instanceKey === key)) {
          messageApi.error("实例标识已存在");
          return;
        }
        const item: ServiceDraft = {
          id: draft?.id ?? newDraftId(),
          category: data.draft_category,
          provider: data.provider,
          name: data.name.trim(),
          instanceKey: key,
          purpose: data.purpose?.trim() ?? "",
          description: data.description?.trim() ?? "",
          metering: data.metering,
          dailyBudget: data.metering === "none" ? 0 : (data.dailyBudget ?? 0),
          status: "draft",
          updatedAt: new Date().toISOString(),
        };
        writeBrowserDrafts({
          ...store,
          services: draft
            ? store.services.map((entry) => entry.id === draft.id ? item : entry)
            : [item, ...store.services],
        });
        messageApi.success("已保存设计草稿（仅限当前浏览器会话）");
      } else {
        const payload: ConnectorWrite = {
          kind: data.choice,
          name: data.name.trim(),
          enabled: data.enabled,
          endpoint: data.endpoint?.trim() || undefined,
          credential: data.credential?.trim() || undefined,
          signing_secret: data.signing_secret?.trim() || undefined,
          default_model: data.choice === "openai" ? OPENAI_FIXED_MODEL : undefined,
          backup_model: data.choice === "openai" ? undefined : data.backup_model,
          model_allowlist: data.choice === "openai" ? [OPENAI_FIXED_MODEL] : [],
          application_scenes: data.choice === "openai" ? data.application_scenes ?? [] : [],
          daily_limit: data.daily_limit,
          monthly_budget_usd: data.monthly_budget_usd ?? 0,
          max_output_tokens: data.max_output_tokens,
          input_price_per_million: data.input_price_per_million ?? 0,
          output_price_per_million: data.output_price_per_million ?? 0,
        };
        if (data.choice === "openai" && !skillBindingsReady) {
          messageApi.error("Skill 绑定尚未读取成功；为避免覆盖旧配置，已阻止保存");
          return;
        }
        const savedConnector = await saveBusinessConnector(payload, connector?.id ?? savedConnectorId);
        if(!connector?.id && !savedConnectorId)setSavedConnectorId(savedConnector.id);
        if (data.choice === "openai") {
          const bindings = Object.fromEntries(SKILL_SCENES.map(item => [item.value,
            (data.application_scenes ?? []).includes(item.value) ? (skillBindings[item.value] ?? null) : null]));
          await backendRequest(`/api/ai-runtime/skill-library/bindings/${savedConnector.id}`,
            { method:"PUT", body: JSON.stringify({ bindings }) });
        }
        messageApi.success("服务端配置已保存，密钥不会回显");
      }
      close();
      onSaved();
    } catch {
      messageApi.error("保存失败，请检查服务端接口、数据库迁移及权限");
    } finally {
      setSaving(false);
    }
  };

  return <>
    {context}
    <Modal
      title={connector ? "编辑服务配置" : draft ? "编辑配置草稿" : "新增服务配置"}
      className="business-config__editor-modal" open={open} centered width={960} destroyOnHidden
      maskClosable={!saving} onCancel={close}
      footer={<Space>
        <Button disabled={saving} onClick={close}>取消</Button>
        <Button type="primary" loading={saving} disabled={saving} onClick={() => void save()}>保存配置</Button>
      </Space>}
    >
      <Alert
        type="info" showIcon
        message={choice === "draft" ? "浏览器内的设计草稿" : "正式服务配置 · 服务端加密存储"}
        description={choice === "draft"
          ? "草稿不能连接第三方服务，不要填写 API Key、Token、Webhook 或其他敏感信息。"
          : "保存不会自动发送通知或调用 AI。凭据只有在新建或轮换时填写，已保存的密钥不会回显。"}
      />
      <Form<ServiceForm> layout="vertical" form={form} className="business-config__editor-form">
        <div className="business-config__editor-section-heading"><strong>基础信息</strong><span>服务标识和连接类型</span></div>
        <Form.Item name="choice" label="服务类型" rules={[{ required: true }]}>
          <Select disabled={Boolean(connector || draft)} options={[
            { value: "feishu_webhook", label: "飞书群机器人（正式连接）" },
            { value: "openai", label: "OpenAI 模型服务（正式连接）" },
            { value: "draft", label: "其他服务（仅设计草稿）" },
          ]} />
        </Form.Item>
        {choice === "draft" ? <>
          <Form.Item name="draft_category" label="服务分类" rules={[{ required: true }]}>
            <Select options={categories} onChange={(value: DraftCategory) => form.setFieldValue("provider", BUSINESS_PROVIDERS[value][0])} />
          </Form.Item>
          <Form.Item name="provider" label="服务商" rules={[{ required: true }]}>
            <Select options={(BUSINESS_PROVIDERS[draftCategory as DraftCategory] ?? BUSINESS_PROVIDERS.ai)
              .map((name) => ({ value: name, label: name }))} />
          </Form.Item>
        </> : null}
        <Form.Item name="name" label="配置名称" rules={[{ required: true, whitespace: true, max: 100 }]}>
          <Input placeholder="为此连接设置易识别的名称" maxLength={100} />
        </Form.Item>
        {choice === "draft" ? <>
          <Form.Item name="instanceKey" label="实例标识" rules={[
            { required: true, pattern: /^[A-Za-z0-9_-]{2,48}$/, message: "2–48 位字母、数字、下划线或短横线" },
          ]}><Input placeholder="例如：feishu-alert-draft" /></Form.Item>
          <Form.Item name="purpose" label="业务用途"><Input maxLength={150} /></Form.Item>
          <Form.Item name="description" label="备注"><Input.TextArea rows={3} maxLength={240} /></Form.Item>
          <Form.Item name="metering" label="计量方式"><Select options={METERING_OPTIONS} /></Form.Item>
          {metering !== "none" && <Form.Item name="dailyBudget" label="计划日预算（USD，仅草稿）">
            <InputNumber min={0} precision={2} style={{ width: "100%" }} />
          </Form.Item>}
        </> : choice === "feishu_webhook" ? <>
          <Form.Item name="endpoint" label="飞书群 Webhook"
            rules={connector ? [] : [{ required: true, message: "首次创建需要填写飞书群 Webhook" }]}
            extra={connector ? "留空保留原地址，不会显示已保存的 Webhook。" : "仅接受官方飞书群机器人地址。"}>
            <Input.Password autoComplete="new-password" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." />
          </Form.Item>
          <Form.Item name="signing_secret" label="签名密钥（如有）">
            <Input.Password autoComplete="new-password" placeholder="留空表示不更换" />
          </Form.Item>
        </> : choice === "openai" ? <>
          <section className="business-config__editor-panel">
            <div className="business-config__editor-panel-head">
              <div><strong>模型与授权</strong><p>固定使用 GPT-6 Luna，已保存的密钥不会回显</p></div>
              <span className="business-config__editor-chip">固定模型</span>
            </div>
            <div className="business-config__editor-two-col">
              <Form.Item name="credential" label="OpenAI API Key"
                rules={connector ? [] : [{ required: true, message: "首次创建需要填写 API Key" }]}
                extra={connector ? "留空保留已保存的 Key" : "仅保存在服务端加密存储中"}>
                <Input.Password autoComplete="new-password" placeholder="sk-..." />
              </Form.Item>
              <Form.Item label="模型（不可修改）" extra="当前系统仅允许 gpt-6-luna">
                <Input value={OPENAI_FIXED_MODEL} disabled />
              </Form.Item>
            </div>
            <Form.Item name="default_model" hidden><Input /></Form.Item>
            <Form.Item name="backup_model" hidden><Input /></Form.Item>
            <Form.Item name="model_allowlist" hidden><Select mode="tags" /></Form.Item>
            <Form.Item name="application_scenes" label="启用的 AI 应用场景">
              <Select mode="multiple" options={[
                { value: "keyword_launch", label: "关键词投放" },
                { value: "ai_assistant", label: "AI 助手" },
                { value: "listing_optimization", label: "Listing 优化" },
                { value: "ads_optimization", label: "广告优化（预留）" },
                { value: "product_research", label: "智能选品（预留）" },
              ]} />
            </Form.Item>
          </section>
          <section className="business-config__editor-panel">
            <div className="business-config__editor-panel-head">
              <div><strong>模型计价</strong><p>官方标准短上下文价格，按每百万 Token 计价</p></div>
              <span className="business-config__editor-chip">自动配置 · 只读</span>
            </div>
            <div className="business-config__editor-prices">
              <div><span>输入 Token</span><strong>${Number(connector?.config.input_price_per_million ?? OPENAI_INPUT_USD_PER_MTOK).toFixed(2)}</strong><small>USD / 100 万 Token</small></div>
              <div><span>输出 Token</span><strong>${Number(connector?.config.output_price_per_million ?? OPENAI_OUTPUT_USD_PER_MTOK).toFixed(2)}</strong><small>USD / 100 万 Token</small></div>
            </div>
            <p className="business-config__editor-price-note">此处用于系统内部费用估算；长上下文、缓存、服务层级及供应商实际账单可能不同。编辑时保留连接器已保存的单价；价格调整须通过另行批准的计费配置流程。</p>
            <Form.Item name="input_price_per_million" hidden><InputNumber /></Form.Item>
            <Form.Item name="output_price_per_million" hidden><InputNumber /></Form.Item>
            <Form.Item name="max_output_tokens" label="单次最大输出 Token">
              <InputNumber min={1} max={16384} style={{ width: 240 }} />
            </Form.Item>
          </section>
          <SkillBindingPicker scenes={applicationScenes ?? []} values={skillBindings} onChange={setSkillBindings} />
        </> : null}
        {choice !== "draft" && <>
          <section className="business-config__editor-panel">
            <div className="business-config__editor-panel-head">
              <div><strong>调用控制</strong><p>管理每日请求上限、月度预算和服务开关</p></div>
            </div>
          <div className="business-config__editor-two-col">
          <Form.Item name="daily_limit" label="每日请求上限">
            <InputNumber min={1} max={100000} style={{ width: "100%" }} />
          </Form.Item>
          {choice === "openai" && <Form.Item name="monthly_budget_usd" label="月度预算 USD">
            <InputNumber min={0} precision={2} style={{ width: "100%" }} />
          </Form.Item>}
          </div>
          <Form.Item name="enabled" label="启用连接" valuePropName="checked">
            <Switch />
          </Form.Item>
          </section>
        </>}
      </Form>
    </Modal>
  </>;
}
