import { Alert, Empty, Select, Space, Tag } from "antd";
import { useEffect, useState } from "react";
import { backendRequest } from "@/api/backendApi";
import { SCENES } from "./skillSceneOptions";

type Published = { skill_id: string; name: string; scene: string; revision_id: string; version: number };

export default function SkillBindingPicker({ scenes, values, onChange }: {
  scenes: string[]; values: Record<string, string | null>;
  onChange: (values: Record<string, string | null>) => void;
}) {
  const [published, setPublished] = useState<Published[]>([]);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    void backendRequest<Published[]>("/api/ai-runtime/skill-library/published")
      .then(result => { if (active) { setPublished(result.data); setError(false); }})
      .catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, []);
  return <section className="business-config__editor-panel">
    <div className="business-config__editor-panel-head">
      <div><strong>场景 Skill 绑定</strong><p>这里只选择已发布版本；新增、编辑和上传请到业务配置 → Skill 管理。</p></div>
      <span className="business-config__editor-chip">选择 Skill</span>
    </div>
    {error && <Alert type="error" showIcon message="已发布的 Skill 读取失败，请检查接口和数据库迁移" style={{ marginBottom: 12 }} />}
    {!scenes.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请先选择启用的应用场景" />}
    {SCENES.filter(item => scenes.includes(item.value)).map(scene => <div key={scene.value}
      style={{ display: "flex", alignItems: "center", gap: 16, justifyContent: "space-between", borderBottom: "1px solid #eef1f5", padding: "12px 0" }}>
      <Space direction="vertical" size={2}>
        <strong style={{fontSize:13}}>{scene.label}</strong>
        <span style={{fontSize:11,color:"#98a2b3"}}>按业务场景加载规则</span>
      </Space>
      <Select aria-label={scene.label + " Skill"} style={{ width: "64%" }} showSearch optionFilterProp="label"
        value={values[scene.value] ?? "none"} onChange={v => onChange({...values, [scene.value]: v === "none" ? null : v})}
        options={[{ value:"none", label:"不绑定 Skill" },
          ...published.filter(p => p.scene === scene.value).map(p => ({
            value:p.revision_id, label:`${p.name} · V${p.version}`,
          }))]} />
    </div>)}
    <p style={{ fontSize: 12, color: "#8592a5", marginTop: 12 }}>
      <Tag color="blue">规则复用</Tag> Skill 的发布版本不会随当前弹窗修改；历史任务仍使用其锁定的版本。
    </p>
  </section>;
}
