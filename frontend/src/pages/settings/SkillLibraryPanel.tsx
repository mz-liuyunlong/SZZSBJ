import {
  BookOutlined, CheckCircleOutlined, CloudUploadOutlined, DeleteOutlined,
  EditOutlined, FileTextOutlined, PlusOutlined, ReloadOutlined,
} from "@ant-design/icons";
import {
  Alert, Button, Card, Empty, Input, Modal, Popconfirm, Select, Space, Table, Tag, Upload,
  message,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { UploadProps } from "antd";
import { backendRequest } from "@/api/backendApi";
import "./SkillLibraryPanel.css";

type Skill = {
  id: string; name: string; slug: string; scene: string; description: string;
  latest_version: number | null; published_version: number | null; updated_at: string;
};
type Revision = {
  id: string; version: number; status: "draft" | "published" | "retired";
  instructions: string; runtime_instructions: string | null; created_at: string;
};
type CreatedSkill = { id: string; revision_id: string; version: number };
type SkillForm = { name: string; slug: string; scene: string; description: string; instructions: string; runtime: string };
const SCENES = [
  { value: "ai_assistant", label: "AI 助手" },
  { value: "keyword_launch", label: "关键词投放" },
  { value: "listing_optimization", label: "Listing 优化" },
  { value: "ads_optimization", label: "广告优化" },
  { value: "product_research", label: "智能选品" },
];
const EMPTY: SkillForm = { name: "", slug: "", scene: "ai_assistant", description: "", instructions: "", runtime: "" };
const EXAMPLE = `---\nname: walmart-ads-optimizer\ndescription: 当用户上传沃尔玛广告报表或要求优化广告时使用。\n---\n\n# 沃尔玛广告优化\n\n## 输入\n- 最近7天或30天的广告数据\n- 目标ACOS和商品利润（如有）\n\n## 执行\n1. 核对报表字段、时间范围和数据完整性。\n2. 计算广告花费、订单、ACOS、ROAS。\n3. 识别高花费低转化词和有订单的高效词。\n4. 输出可以复核的调整建议。\n\n## 边界\n- 不编造缺失数据，不未经授权操作广告。`;

async function encodeFile(file: File): Promise<{ name: string; content_base64: string }> {
  if (file.size > 2 * 1024 * 1024) throw new Error("文件不能超过 2MB");
  const data = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let offset = 0; offset < data.length; offset += 8192) {
    binary += String.fromCharCode(...data.subarray(offset, offset + 8192));
  }
  return { name: file.name, content_base64: btoa(binary) };
}

export default function SkillLibraryPanel({ canEdit }: { canEdit: boolean }) {
  const [messageApi, holder] = message.useMessage();
  const [rows, setRows] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [scene, setScene] = useState("all");
  const [selected, setSelected] = useState<Skill | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<SkillForm>(EMPTY);
  const [versions, setVersions] = useState<Revision[]>([]);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const result = await backendRequest<Skill[]>("/api/ai-runtime/skill-library");
      setRows(result.data);
      setError("");
    } catch {
      setError("Skill 列表读取失败。请检查管理员权限、后端是否重启及本地数据库迁移。");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active) void refresh();
    });
    return () => { active = false; };
  }, [refresh]);

  const reloadVersions = async (skillId: string) => {
    const result = await backendRequest<Revision[]>(`/api/ai-runtime/skill-library/${skillId}/versions`);
    setVersions(result.data);
  };
  const openNew = () => {
    setCreating(true); setSelected(null); setVersions([]); setDraftId(null); setActiveId(null);
    setForm({ ...EMPTY });
  };
  const openEdit = async (skill: Skill) => {
    setCreating(false); setSelected(skill); setDraftId(null); setActiveId(null);
    setForm({ name: skill.name, slug: skill.slug, scene: skill.scene, description: skill.description, instructions: "", runtime: "" });
    try {
      const result = await backendRequest<Revision[]>(`/api/ai-runtime/skill-library/${skill.id}/versions`);
      setVersions(result.data);
      const current = result.data.find(v => v.status === "published") ?? result.data[0];
      if (current) {
        setForm(v => ({ ...v, instructions: current.instructions, runtime: current.runtime_instructions ?? "" }));
        setActiveId(current.id);
        setDraftId(current.status === "draft" ? current.id : null);
      }
    } catch { void messageApi.error("读取 Skill 版本失败"); }
  };
  const patch = (next: Partial<SkillForm>) => setForm(before => ({ ...before, ...next }));
  const saveDraft = async () => {
    if (!canEdit || !form.name.trim() || !form.description.trim() || !form.instructions.trim()) {
      void messageApi.warning("请填写名称、触发说明与执行规则"); return;
    }
    if (creating && !/^[a-z][a-z0-9-]{1,62}$/.test(form.slug)) {
      void messageApi.warning("标识需为小写英文字母、数字和短横线，以字母开头"); return;
    }
    setBusy(true);
    try {
      if (creating) {
        const result = await backendRequest<CreatedSkill>("/api/ai-runtime/skill-library", {
          method: "POST", body: JSON.stringify({ name: form.name.trim(), slug: form.slug, scene: form.scene,
            description: form.description.trim(), instructions: form.instructions, runtime_instructions: form.runtime.trim() || null }),
        });
        setCreating(false); setDraftId(result.data.revision_id); setActiveId(result.data.revision_id);
        setSelected({ id: result.data.id, name: form.name, slug: form.slug, scene: form.scene,
          description: form.description, latest_version: 1, published_version: null, updated_at: new Date().toISOString() });
        await reloadVersions(result.data.id);
      } else if (selected) {
        const result = await backendRequest<{ id: string; version: number }>(
          `/api/ai-runtime/skill-library/${selected.id}/drafts`, {
            method: "POST", body: JSON.stringify({ instructions: form.instructions,
              runtime_instructions: form.runtime.trim() || null, description: form.description.trim() }),
          });
        setDraftId(result.data.id); setActiveId(result.data.id);
        await reloadVersions(selected.id);
      }
      await refresh();
      void messageApi.success("Skill 草稿已保存（新版本不影响当前已发布版本）");
    } catch { void messageApi.error("保存失败，请检查字段、唯一标识和数据库权限"); }
    finally { setBusy(false); }
  };
  const publish = async (revisionId: string) => {
    if (!selected) return;
    setBusy(true);
    try {
      await backendRequest(`/api/ai-runtime/skill-library/${selected.id}/versions/${revisionId}/publish`, { method: "POST" });
      await reloadVersions(selected.id); await refresh(); setDraftId(null);
      void messageApi.success("Skill 版本已发布，可在 OpenAI 服务配置中选择");
    } catch { void messageApi.error("发布失败。长规则文档必须填写不超过 3000 字的精简运行指令。"); }
    finally { setBusy(false); }
  };
  const remove = async (skill: Skill) => {
    setBusy(true);
    try {
      await backendRequest(`/api/ai-runtime/skill-library/${skill.id}`, { method: "DELETE" });
      if (selected?.id === skill.id) { setSelected(null); setCreating(false); }
      await refresh(); void messageApi.success("Skill 已停用并从列表移除；历史任务版本保留");
    } catch { void messageApi.error("Skill 删除失败"); }
    finally { setBusy(false); }
  };
  const uploadFile = async (file: File, isZip: boolean) => {
    setBusy(true);
    try {
      const body = await encodeFile(file);
      if (isZip) {
        const result = await backendRequest<CreatedSkill>("/api/ai-runtime/skill-library/import", {
          method: "POST", body: JSON.stringify(body),
        });
        void messageApi.success("已从 SKILL.md 导入为草稿；请检查场景和运行指令后发布");
        await refresh();
        const resultList = await backendRequest<Skill[]>("/api/ai-runtime/skill-library");
        const imported = resultList.data.find(x => x.id === result.data.id);
        if (imported) await openEdit(imported);
      } else {
        if (!selected || !draftId) {
          void messageApi.warning("先保存一个 Skill 草稿版本，再上传文档"); return;
        }
        await backendRequest(`/api/ai-runtime/skill-library/${selected.id}/versions/${draftId}/documents`, {
          method: "POST", body: JSON.stringify(body),
        });
        const result = await backendRequest<Revision[]>(`/api/ai-runtime/skill-library/${selected.id}/versions`);
        setVersions(result.data);
        const updated = result.data.find(v => v.id === draftId);
        if (updated) patch({ instructions: updated.instructions });
        void messageApi.success("文档已解析并加入当前草稿规则，发布前请核对内容");
      }
    } catch { void messageApi.error("上传失败：检查文件格式、大小、文字可提取性与管理员权限"); }
    finally { setBusy(false); }
  };
  const documentUpload: UploadProps = {
    accept: ".pdf,.docx,.xlsx,.md,.txt,.csv", showUploadList: false, disabled: busy || !draftId || !canEdit,
    beforeUpload: file => { void uploadFile(file as File, false); return false; },
  };
  const zipUpload: UploadProps = {
    accept: ".zip", showUploadList: false, disabled: busy || !canEdit,
    beforeUpload: file => { void uploadFile(file as File, true); return false; },
  };
  const filtered = useMemo(() => rows.filter(x =>
    (scene === "all" || x.scene === scene) &&
    (x.name + " " + x.slug + " " + x.description).toLowerCase().includes(query.toLowerCase().trim())), [rows, scene, query]);

  return <div className="business-config__body skill-library">
    {holder}
    <div className="skill-library__top">
      <div><h2>Skill 管理</h2><p>统一创建、上传和发布业务规则；OpenAI 服务只选择已发布的 Skill。</p></div>
      <Space>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void refresh()}>刷新</Button>
        {canEdit && <Upload {...zipUpload}><Button icon={<CloudUploadOutlined />}>导入 Skill ZIP</Button></Upload>}
        {canEdit && <Button type="primary" icon={<PlusOutlined />} onClick={openNew}>新建 Skill</Button>}
      </Space>
    </div>
    {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }}/>}
    <Card className="business-config__list-card skill-library__table">
      <div className="business-config__filters">
        <Input.Search aria-label="搜索 Skill" allowClear placeholder="搜索 Skill 名称、标识或用途" className="business-config__search"
          value={query} onChange={e => setQuery(e.target.value)} />
        <Select aria-label="场景筛选" value={scene} style={{ width: 166 }} onChange={setScene}
          options={[{ value: "all", label: "全部场景" }, ...SCENES]}/>
        <span className="business-config__filter-spacer"/>
        <span className="business-config__muted">共 {filtered.length} 条</span>
      </div>
      <Table<Skill> rowKey="id" size="small" dataSource={filtered} loading={loading} pagination={{ pageSize: 10 }}
        locale={{ emptyText: <Empty description="暂无 Skill，可从新建或导入开始"/> }}
        columns={[
          { title: "Skill 名称", dataIndex: "name", render: (_: string, skill: Skill) => <Space>
            <span className="skill-library__symbol"><BookOutlined/></span>
            <div><strong>{skill.name}</strong><div className="skill-library__slug">{skill.slug}</div></div>
          </Space> },
          { title: "业务场景", dataIndex: "scene", width: 125, render: (v: string) => SCENES.find(x => x.value === v)?.label ?? v },
          { title: "已发布版本", dataIndex: "published_version", width: 130, render: (v: number|null) => v ? <Tag color="success">V{v} 已发布</Tag> : <Tag>尚未发布</Tag> },
          { title: "最新版本", dataIndex: "latest_version", width: 95, render: (v: number|null) => v ? `V${v}` : "—" },
          { title: "最近修改", dataIndex: "updated_at", width: 170, render: (v: string) => v?.slice(0,16).replace("T", " ") },
          { title: "操作", width: 190, render: (_: unknown, skill: Skill) => <Space size={0}>
            <Button type="link" size="small" icon={<EditOutlined/>} onClick={() => void openEdit(skill)}>查看 / 编辑</Button>
            {canEdit && <Popconfirm title="删除此 Skill？" description="停止新任务使用并解除服务绑定；历史版本保留。"
              okText="删除" cancelText="取消" okButtonProps={{ danger:true }} onConfirm={() => void remove(skill)}>
              <Button type="link" danger size="small" icon={<DeleteOutlined/>}>删除</Button>
            </Popconfirm>}
          </Space> },
        ]} />
    </Card>
    <Modal
      className="skill-library__modal"
      title={
        <Space>
          <FileTextOutlined />
          {creating ? "新建 Skill" : `查看 / 编辑 Skill · ${selected?.name ?? ""}`}
        </Space>
      }
      open={creating || selected !== null}
      width={1100}
      centered
      destroyOnHidden
      maskClosable={!busy}
      closable={!busy}
      onCancel={() => {
        if (!busy) {
          setSelected(null);
          setCreating(false);
        }
      }}
      footer={
        <Space>
          <Button
            disabled={busy}
            onClick={() => {
              setSelected(null);
              setCreating(false);
            }}
          >
            关闭
          </Button>
          {canEdit && (
            <Button
              type="primary"
              loading={busy}
              onClick={() => void saveDraft()}
            >
              保存为新草稿版本
            </Button>
          )}
        </Space>
      }
    >
      <div className="skill-library__form-grid">
        <div className="skill-library__edit-pane">
          <h3>基础信息</h3>
          <div className="skill-library__two">
            <label>Skill 名称<Input disabled={!canEdit || !creating} value={form.name} maxLength={100} onChange={e=>patch({ name:e.target.value })}/></label>
            <label>唯一标识<Input disabled={!canEdit || !creating} value={form.slug} placeholder="walmart-ads-optimizer" maxLength={63} onChange={e=>patch({slug:e.target.value})}/></label>
          </div>
          <label>适用业务场景<Select disabled={!canEdit || !creating} value={form.scene} options={SCENES} style={{width:"100%"}}
            onChange={v=>patch({scene:v})}/></label>
          <label>触发说明<Input.TextArea disabled={!canEdit} value={form.description} maxLength={1000} rows={2}
            placeholder="例如：用户上传沃尔玛广告报表或要求分析广告投放时使用" onChange={e=>patch({description:e.target.value})}/></label>
          <div className="skill-library__divider"/>
          <h3>Skill 执行规则</h3>
          <p className="skill-library__hint">完整规则可以包含标题、步骤、输入约束和输出格式；保存为草稿，不会立刻影响在线任务。</p>
          <Input.TextArea aria-label="完整 Skill 规则" disabled={!canEdit} rows={12} maxLength={150000} value={form.instructions}
            onChange={e=>patch({instructions:e.target.value})} placeholder="使用 Markdown 编写 Skill 执行规则"/>
          <div className="skill-library__count">{form.instructions.length.toLocaleString()} / 150,000</div>
          <h3>精简运行指令</h3>
          <p className="skill-library__hint">仅此段会随模型调用注入提示词。长规则请提炼为最多 3000 字的执行约束。</p>
          <Input.TextArea aria-label="精简运行指令" disabled={!canEdit} rows={5} maxLength={3000} value={form.runtime}
            onChange={e=>patch({runtime:e.target.value})} placeholder="简要描述模型每次实际必须执行的步骤"/>
          <div className="skill-library__count">{form.runtime.length} / 3,000</div>
          {canEdit && <Space style={{marginTop:12}}>
            <Button
              disabled={busy}
              onClick={() => patch({instructions:EXAMPLE})}
            >
              填入写法示例
            </Button>
          </Space>}
        </div>
        <div className="skill-library__right-pane">
          <h3>文档上传</h3>
          <p className="skill-library__hint">保存草稿后可上传 PDF、Word、Excel、Markdown 或文本，系统提取内容并追加到草稿。扫描 PDF 需先转换为可检索版本。</p>
          <Upload.Dragger {...documentUpload}>
            <div className="skill-library__upload-icon"><CloudUploadOutlined/></div>
            <strong>{draftId ? "点击或拖入参考文档" : "先保存草稿版本后上传"}</strong>
            <div className="skill-library__hint">单文件 ≤2MB · 每版本最多 5 个 · 不自动发布</div>
          </Upload.Dragger>
          <div className="skill-library__divider"/>
          <h3>版本记录</h3>
          <div className="skill-library__versions-scroll">
          {!versions.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无历史版本"/>}
          {versions.map(version=><div className="skill-library__version" key={version.id}>
            <div><strong>V{version.version}</strong> <Tag color={version.status==="published"?"success":version.status==="draft"?"processing":"default"}>
              {version.status==="published"?"已发布":version.status==="draft"?"草稿":"历史版本"}</Tag></div>
            <Space>
              <Button size="small" onClick={()=>{setForm(x=>({...x,instructions:version.instructions,runtime:version.runtime_instructions??""}));
                setActiveId(version.id);setDraftId(version.status==="draft"?version.id:null);}}>
                查看 / 复制</Button>
              {canEdit && version.status==="draft" && <Popconfirm title={`发布 V${version.version}？`}
                description="发布后可在 OpenAI 服务配置中选择，原已发布版本成为历史版本。" onConfirm={()=>void publish(version.id)}>
                <Button type="primary" ghost size="small" icon={<CheckCircleOutlined/>}>发布</Button>
              </Popconfirm>}
            </Space>
          </div>)}
          </div>
          {!!activeId && <p className="skill-library__hint">正在查看版本 ID：{activeId.slice(0,8)}。修改后点击“保存为新草稿版本”生成新的不可变版本。</p>}
          <Alert type="info" showIcon style={{marginTop:16}} message="Skill 与模型工具分离"
            description="Skill 约束执行规则；联网、查询真实业务数据和修改广告仍必须由系统的对应工具及权限控制。"/>
        </div>
      </div>
    </Modal>
  </div>;
}
