import { Alert, Button, Drawer, Form, Input, InputNumber, Select, Space, Switch, message } from "antd";
import { useEffect, useState } from "react";
import { backendRequest } from "@/api/backendApi";
import {
  saveBusinessConnector, type BusinessConnector, type ConnectorKind, type ConnectorWrite,
} from "@/api/businessConnectorsApi";
import {
  BUSINESS_PROVIDERS, METERING_OPTIONS, newDraftId, readBrowserDrafts, writeBrowserDrafts,
  type DraftCategory, type ServiceDraft,
} from "./businessConfigDrafts";

type Choice = ConnectorKind | "draft";
type SkillVersion = {id:string;connector_id:string;scene:string;version:number;status:string;instructions:string};
const SKILL_SCENES = [
  {value:"keyword_launch",label:"关键词投放"},
  {value:"ai_assistant",label:"AI 助手"},
  {value:"listing_optimization",label:"Listing 优化"},
  {value:"ads_optimization",label:"广告优化（预留）"},
  {value:"product_research",label:"智能选品（预留）"},
] as const;
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
  const [skillScene,setSkillScene]=useState<string>("keyword_launch");
  const [skillText,setSkillText]=useState("");
  const [pendingSkillTexts,setPendingSkillTexts]=useState<Record<string,string>>({});
  const [skillList,setSkillList]=useState<SkillVersion[]>([]);
  const [skillBusy,setSkillBusy]=useState(false);
  const [skillError,setSkillError]=useState("");
  const [savedConnectorId,setSavedConnectorId]=useState<string>();
  const choice = Form.useWatch("choice", form);
  const draftCategory = Form.useWatch("draft_category", form);
  const metering = Form.useWatch("metering", form);
  const skillConnectorId=connector?.id ?? savedConnectorId;
  const openAiSelected=connector?.kind==="openai" || choice==="openai";
  const loadSkills=async(id:string)=>{
    setSkillError("");
    try{
      const result=await backendRequest<SkillVersion[]>(`/api/ai-runtime/skills?connector_id=${encodeURIComponent(id)}`);
      setSkillList(result.data);
      return true;
    }catch{
      setSkillError("Skill 加载失败，请检查数据库迁移、管理员权限或后端日志。");
      return false;
    }
  };
  useEffect(()=>{
    if(open && skillConnectorId && openAiSelected){
      let active=true;
      setSkillError("");
      void backendRequest<SkillVersion[]>(`/api/ai-runtime/skills?connector_id=${encodeURIComponent(skillConnectorId)}`)
        .then(result=>{if(active)setSkillList(result.data)})
        .catch(()=>{if(active){setSkillList([]);setSkillError("Skill 加载失败，请检查数据库迁移、管理员权限或后端日志。")}});
      return()=>{active=false};
    }
  },[open,skillConnectorId,openAiSelected]);
  const saveSkillDraft=async()=>{
    if(!skillText.trim())return;
    if(skillText.trim().length>3000){messageApi.warning("Skill 最多 3000 个字符");return;}
    if(!skillConnectorId){
      setPendingSkillTexts(old=>({...old,[skillScene]:skillText.trim()}));
      messageApi.info("Skill 已暂存于当前编辑窗口；保存 OpenAI 服务后才能同步并发布");
      return;
    }
    setSkillBusy(true);
    try{
      await backendRequest('/api/ai-runtime/skills/drafts',{method:'POST',body:JSON.stringify({
        connector_id:skillConnectorId,scene:skillScene,instructions:skillText.trim(),
      })});
      setPendingSkillTexts(old=>{const next={...old};delete next[skillScene];return next;});
      setSkillText("");
      await loadSkills(skillConnectorId);
      messageApi.success("Skill 草稿已保存");
    }catch{messageApi.error("Skill 草稿保存失败");}
    finally{setSkillBusy(false);}
  };
  const publishSkill=async(id:string)=>{
    if(!skillConnectorId)return;
    setSkillBusy(true);
    try{
      await backendRequest(`/api/ai-runtime/skills/${id}/publish`,{method:'POST'});
      await loadSkills(skillConnectorId);
      messageApi.success("Skill 已发布，新任务将使用该版本");
    }catch{messageApi.error("Skill 发布失败");}
    finally{setSkillBusy(false);}
  };
  const [messageApi, context] = message.useMessage();

  useEffect(() => {
    if (!open) return;
    const base: ServiceForm = {
      choice: connector?.kind ?? (draft ? "draft" : preferredCategory === "bots" ? "feishu_webhook" : preferredCategory === "ai" ? "openai" : "feishu_webhook"),
      kind: connector?.kind ?? "feishu_webhook",
      name: connector?.name ?? draft?.name ?? "",
      enabled: connector?.enabled ?? false,
      endpoint: "",
      credential: "",
      signing_secret: "",
      default_model: "gpt-6-luna",
      backup_model: "",
      model_allowlist: ["gpt-6-luna"],
      application_scenes: connector?.config.application_scenes ?? ["keyword_launch", "ai_assistant", "listing_optimization"],
      daily_limit: connector?.config.daily_limit ?? 100,
      monthly_budget_usd: Number(connector?.config.monthly_budget_usd ?? 0),
      max_output_tokens: connector?.config.max_output_tokens ?? 1024,
      input_price_per_million: Number(connector?.config.input_price_per_million ?? 0),
      output_price_per_million: Number(connector?.config.output_price_per_million ?? 0),
      draft_category: draft?.category ?? (categories.find((entry) => entry.value === preferredCategory)?.value ?? "ai"),
      provider: draft?.provider ?? "OpenAI",
      instanceKey: draft?.instanceKey ?? "",
      purpose: draft?.purpose ?? "",
      description: draft?.description ?? "",
      metering: draft?.metering ?? "none",
      dailyBudget: draft?.dailyBudget ?? 0,
    };
    form.setFieldsValue(base);
  }, [open, connector, draft, preferredCategory, form]);

  const close = () => {
    setPendingSkillTexts({});setSkillText("");setSkillList([]);setSkillScene("keyword_launch");setSkillError("");setSavedConnectorId(undefined);
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
          default_model: data.choice === "openai" ? data.default_model : undefined,
          backup_model: data.choice === "openai" ? data.backup_model : undefined,
          model_allowlist: data.choice === "openai" ? ["gpt-6-luna"] : [],
          application_scenes: data.choice === "openai" ? data.application_scenes ?? [] : [],
          daily_limit: data.daily_limit,
          monthly_budget_usd: data.monthly_budget_usd ?? 0,
          max_output_tokens: data.max_output_tokens,
          input_price_per_million: data.input_price_per_million ?? 0,
          output_price_per_million: data.output_price_per_million ?? 0,
        };
        const savedConnector = await saveBusinessConnector(payload, connector?.id ?? savedConnectorId);
        if(!connector?.id && !savedConnectorId)setSavedConnectorId(savedConnector.id);
        if(data.choice==="openai" && Object.keys(pendingSkillTexts).length){
          let savedCount=0;
          const failedSkills:Record<string,string>={};
          for(const [scene,instructions] of Object.entries(pendingSkillTexts)){
            if(!instructions.trim())continue;
            try{
              await backendRequest('/api/ai-runtime/skills/drafts',{method:'POST',body:JSON.stringify({
                connector_id:savedConnector.id,scene,instructions,
              })});
              savedCount++;
            }catch{
              failedSkills[scene]=instructions;
            }
          }
          setPendingSkillTexts(failedSkills);
          if(Object.keys(failedSkills).length){
            setSkillError("OpenAI 服务已保存，但部分 Skill 草稿未同步。请检查错误后重试；服务不会重复创建。");
            messageApi.warning("OpenAI 服务已保存，但有 Skill 草稿未同步；可在此重试");
            return;
          }
          if(savedCount)messageApi.success(`已保存 ${savedCount} 个 Skill 草稿`);
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
    <Drawer
      title={connector ? "编辑服务配置" : draft ? "编辑配置草稿" : "新增服务配置"}
      className="business-config__editor" open={open} width={560} destroyOnHidden
      maskClosable={!saving} onClose={close}
      extra={<Space>
        <Button disabled={saving} onClick={close}>取消</Button>
        <Button type="primary" loading={saving} onClick={() => void save()}>保存配置</Button>
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
          <Form.Item name="credential" label="API Key"
            rules={connector ? [] : [{ required: true, message: "首次创建需要填写 API Key" }]}>
            <Input.Password autoComplete="new-password" placeholder="已配置时可留空，保持原密钥" />
          </Form.Item>
          <Form.Item name="default_model" label="默认模型" rules={[{ required: true }]}>
            <Input readOnly />
          </Form.Item>
          <Form.Item name="application_scenes" label="应用场景（多选）">
            <Select mode="multiple" options={[
              { value: "keyword_launch", label: "关键词投放" },
              { value: "ai_assistant", label: "AI 助手" },
              { value: "listing_optimization", label: "Listing 优化" },
              { value: "ads_optimization", label: "广告优化（预留）" },
              { value: "product_research", label: "智能选品（预留）" },
            ]} />
          </Form.Item>
          <Form.Item name="backup_model" hidden><Input /></Form.Item>
          <Form.Item name="model_allowlist" hidden><Select mode="tags" /></Form.Item>
          <Form.Item name="max_output_tokens" label="最大输出 Token">
            <InputNumber min={1} max={16384} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="input_price_per_million" label="每百万输入 Token 单价 USD">
            <InputNumber min={0} precision={6} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="output_price_per_million" label="每百万输出 Token 单价 USD">
            <InputNumber min={0} precision={6} style={{ width: "100%" }} />
          </Form.Item>
          {<div style={{paddingTop:12,borderTop:"1px solid #eef1f5"}}>
            <strong>AI Skills · 版本管理</strong>
            <div style={{fontSize:12,color:"#98a2b3",margin:"8px 0"}}>{skillConnectorId ? "已连接服务：草稿支持保存及发布；正在执行的任务保持其已选版本。" : "首次创建：可编辑并暂存 Skill，保存 OpenAI 服务后自动尝试同步；未保存时不会发布或调用 AI。"}</div>
            {skillError ? <Alert type="error" showIcon message={skillError} style={{marginBottom:8}} /> : null}
            <Select value={skillScene} onChange={next=>{setPendingSkillTexts(old=>({...old,[skillScene]:skillText}));setSkillText(pendingSkillTexts[next]??"");setSkillScene(next)}} options={[...SKILL_SCENES]} style={{width:"100%",marginBottom:8}} />
            <Input.TextArea rows={4} value={skillText} onChange={ev=>{setSkillText(ev.target.value);setPendingSkillTexts(old=>({...old,[skillScene]:ev.target.value}))}}
              placeholder="填写对应场景的 AI 工作说明；商品事实与关键词硬规则仍由后端校验" maxLength={3000}/>
            <Button size="small" style={{marginTop:8}} disabled={!skillText.trim()||skillBusy} loading={skillBusy}
              onClick={()=>void saveSkillDraft()}>{skillConnectorId?"保存 Skill 草稿":"暂存 Skill 草稿"}</Button>
            {skillList.filter(s=>s.scene===skillScene).map(s=><div key={s.id}
              style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"8px 0",borderBottom:"1px solid #f0f0f0"}}>
              <span>V{s.version} · {s.status}</span>
              <Space size={4}>
                <Button size="small" onClick={()=>setSkillText(s.instructions)}>查看 / 复制配置</Button>
                {s.status!=="published" ? <Button size="small" disabled={s.status==="retired"} loading={skillBusy}
                  onClick={()=>void publishSkill(s.id)}>发布</Button> : null}
              </Space>
            </div>)}
          </div>}
        </> : null}
        {choice !== "draft" && <>
          <Form.Item name="daily_limit" label="每日请求上限">
            <InputNumber min={1} max={100000} style={{ width: "100%" }} />
          </Form.Item>
          {choice === "openai" && <Form.Item name="monthly_budget_usd" label="月度预算 USD">
            <InputNumber min={0} precision={2} style={{ width: "100%" }} />
          </Form.Item>}
          <Form.Item name="enabled" label="启用连接" valuePropName="checked">
            <Switch />
          </Form.Item>
        </>}
      </Form>
    </Drawer>
  </>;
}
