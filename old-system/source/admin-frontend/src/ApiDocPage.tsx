/**
 * ApiDocPage.tsx — 内部 API 接口文档（领星风格，数据驱动，2026-07-27）
 *
 * 数据来自 GET /api/api-doc/spec（后端门控：超管或白名单用户才 200，否则 403）。
 * 左目录树 + 中正文（接口信息/参数表/返回字段/示例）+ 复制。无权 → 显示无权访问。
 */
import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";

const C = {
  bg: "#f6f8fc", card: "#ffffff", txt: "#202124", txt2: "#5f6368", txt3: "#9aa0a6",
  line: "#dadce0", line2: "#e8eaed", blue: "#1a73e8", blueSoft: "#e8f0fe", blueTxt: "#1967d2",
  red: "#d93025", redSoft: "#fce8e6", green: "#188038", mono: '"SFMono-Regular",Consolas,"Roboto Mono",monospace',
};

interface Param { name: string; type: string; required: boolean; match: string; range: boolean; multi: string; desc: string; }
interface Endpoint {
  key: string; name: string; method: string; path: string; source: string;
  desc: string; params: Param[]; returns: string; notes: string[]; example: string;
}
interface Group { name: string; endpoints: Endpoint[]; }
interface Common { [k: string]: string; }
interface Spec { title: string; updated_at: string; note?: string; common: Common; groups: Group[]; }

const COMMON_LABELS: Array<[string, string]> = [
  ["base", "Base 前缀"], ["public_base", "公网入口"], ["method", "请求方式"], ["auth", "鉴权"],
  ["pagination", "分页"], ["response_shell", "返回外壳"], ["empty", "空结果"], ["errors", "错误响应"],
  ["and_or", "多条件关系"], ["unknown_params", "未识别参数"], ["sort", "排序"], ["range", "范围查询"],
  ["common_filters", "共享筛选"], ["redaction", "敏感脱敏"],
];

export default function ApiDocPage({ onNavigate }: { onNavigate?: (key: string) => void } = {}) {
  const [spec, setSpec] = useState<Spec | null>(null);
  const [status, setStatus] = useState<"loading" | "forbidden" | "error" | "ok">("loading");
  const [active, setActive] = useState<string>("__common__");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch("/api/api-doc/spec", { credentials: "include" })
      .then(async (r) => {
        if (r.status === 403) { if (alive) setStatus("forbidden"); return null; }
        if (!r.ok) { if (alive) setStatus("error"); return null; }
        return r.json();
      })
      .then((d: Spec | null) => { if (alive && d) { setSpec(d); setStatus("ok"); } })
      .catch(() => { if (alive) setStatus("error"); });
    return () => { alive = false; };
  }, []);

  const byKey = useMemo(() => {
    const m: Record<string, Endpoint> = {};
    spec?.groups.forEach((g) => g.endpoints.forEach((e) => { m[e.key] = e; }));
    return m;
  }, [spec]);

  function copyText(t: string) {
    navigator.clipboard?.writeText(t).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); }).catch(() => undefined);
  }

  if (status === "loading") return <Center>加载中…</Center>;
  if (status === "forbidden") return <Center><b style={{ color: C.red, fontSize: 16 }}>无权访问</b><div style={{ marginTop: 8, color: C.txt2 }}>「API 接口文档」仅对超管及授权同事开放。如需访问请联系管理员。</div></Center>;
  if (status === "error" || !spec) return <Center><span style={{ color: C.red }}>文档加载失败</span><div style={{ marginTop: 8, color: C.txt2 }}>请稍后重试或联系管理员。</div></Center>;

  const ep = active !== "__common__" ? byKey[active] : null;
  const fullPath = (p: string) => `${spec.common.base || "/api/internal-readonly"}${p}`;
  const exampleUrl = (e: Endpoint) => e.example.startsWith("http") ? e.example : `https://gpt-api.giginana.com${e.example}`;

  return (
    <div style={{ display: "flex", height: "100%", background: C.bg, fontSize: 13, color: C.txt, borderRadius: 12, overflow: "hidden", border: `1px solid ${C.line2}` }}>
      {/* 左目录树 */}
      <aside style={{ width: 248, flexShrink: 0, background: C.card, borderRight: `1px solid ${C.line2}`, overflowY: "auto", padding: "14px 0" }}>
        <div style={{ padding: "0 16px 10px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ fontWeight: 600, fontSize: 14 }}>API 接口文档</div>
            <span
              onClick={() => { onNavigate?.("help"); window.location.hash = "#/help?page=api_doc"; }}
              title="查看帮助"
              style={{ cursor: "pointer", width: 20, height: 20, borderRadius: "50%", border: `1px solid ${C.line}`, color: C.txt2, fontSize: 12, display: "grid", placeItems: "center", userSelect: "none", flexShrink: 0 }}
            >?</span>
          </div>
          <div style={{ fontSize: 11, color: C.txt3, marginTop: 3 }}>更新 {spec.updated_at} · 共 {Object.keys(byKey).length} 个接口</div>
        </div>
        <NavItem label="通用规则" active={active === "__common__"} onClick={() => setActive("__common__")} />
        {spec.groups.map((g) => (
          <div key={g.name} style={{ marginTop: 8 }}>
            <div style={{ padding: "6px 16px 2px", fontSize: 11, color: C.txt3, fontWeight: 600, letterSpacing: 0.3 }}>{g.name}</div>
            {g.endpoints.map((e) => (
              <NavItem key={e.key} label={e.name} sub={e.path} active={active === e.key} onClick={() => setActive(e.key)} />
            ))}
          </div>
        ))}
      </aside>

      {/* 正文 */}
      <main style={{ flex: 1, minWidth: 0, overflowY: "auto", padding: "22px 28px" }}>
        {copied && <div style={{ position: "fixed", top: 78, right: 40, background: "#323232", color: "#fff", padding: "8px 14px", borderRadius: 8, fontSize: 12, zIndex: 100 }}>已复制</div>}

        {!ep ? (
          <>
            <H1>通用规则（所有接口共同）</H1>
            {spec.note && <Callout>{spec.note}</Callout>}
            <div style={{ background: C.card, border: `1px solid ${C.line2}`, borderRadius: 12, overflow: "hidden", marginTop: 12 }}>
              {COMMON_LABELS.filter(([k]) => spec.common[k]).map(([k, label], i) => (
                <div key={k} style={{ display: "flex", borderTop: i ? `1px solid ${C.line2}` : "none" }}>
                  <div style={{ width: 120, flexShrink: 0, padding: "10px 14px", color: C.txt2, background: "#fafbfc", fontWeight: 500 }}>{label}</div>
                  <div style={{ padding: "10px 14px", flex: 1, fontFamily: /base|shell|filters/.test(k) ? C.mono : undefined, fontSize: /base|shell|filters/.test(k) ? 12 : 13, wordBreak: "break-word" }}>{spec.common[k]}</div>
                </div>
              ))}
            </div>
          </>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span style={{ background: C.green, color: "#fff", fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 6 }}>{ep.method}</span>
              <H1 inline>{ep.name}</H1>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
              <code style={{ fontFamily: C.mono, fontSize: 13, background: C.blueSoft, color: C.blueTxt, padding: "6px 12px", borderRadius: 8, wordBreak: "break-all" }}>{fullPath(ep.path)}</code>
              <BtnCopy onClick={() => copyText(fullPath(ep.path))} />
            </div>

            <H2>接口信息</H2>
            <InfoTable rows={[["请求方式", ep.method], ["鉴权", "Authorization: Bearer <readonly_admin>"], ["数据源", ep.source]]} />
            {ep.desc && <p style={{ color: C.txt2, lineHeight: 1.7, marginTop: 10 }}>{ep.desc}</p>}

            <H2>请求参数</H2>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, background: C.card, border: `1px solid ${C.line2}`, borderRadius: 8 }}>
              <thead>
                <tr style={{ background: "#fafbfc", color: C.txt2, textAlign: "left" }}>
                  {["参数", "类型", "必填", "匹配", "范围", "说明"].map((h) => (
                    <th key={h} style={{ padding: "8px 10px", borderBottom: `1px solid ${C.line2}`, fontWeight: 600, whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ep.params.map((p, i) => (
                  <tr key={i} style={{ borderTop: i ? `1px solid ${C.line2}` : "none" }}>
                    <td style={{ padding: "8px 10px", fontFamily: C.mono, color: C.blueTxt, whiteSpace: "nowrap" }}>{p.name}</td>
                    <td style={{ padding: "8px 10px", color: C.txt2 }}>{p.type}</td>
                    <td style={{ padding: "8px 10px" }}>{p.required ? <span style={{ color: C.red, fontWeight: 600 }}>必填</span> : "否"}</td>
                    <td style={{ padding: "8px 10px" }}>{p.match !== "-" ? p.match : "—"}</td>
                    <td style={{ padding: "8px 10px" }}>{p.range ? "✓" : "—"}</td>
                    <td style={{ padding: "8px 10px", color: C.txt2 }}>{p.desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {ep.notes.length > 0 && (
              <div style={{ marginTop: 12, background: "#fff8e1", border: "1px solid #fde68a", borderRadius: 8, padding: "10px 14px" }}>
                {ep.notes.map((n, i) => <div key={i} style={{ color: "#8a6d00", lineHeight: 1.6, display: "flex", gap: 6 }}><span>⚠</span><span>{n}</span></div>)}
              </div>
            )}

            <H2>返回字段</H2>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {ep.returns.split(",").map((f) => f.trim()).filter(Boolean).map((f) => (
                <code key={f} style={{ fontFamily: C.mono, fontSize: 12, background: "#f1f3f4", color: "#3c4043", padding: "3px 8px", borderRadius: 6 }}>{f}</code>
              ))}
            </div>
            <div style={{ marginTop: 8, fontSize: 12, color: C.txt3 }}>外壳：{spec.common.response_shell}</div>

            <H2>示例请求</H2>
            <div style={{ position: "relative" }}>
              <pre style={{ fontFamily: C.mono, fontSize: 12.5, background: "#1f2430", color: "#e6e6e6", padding: "14px 16px", borderRadius: 10, overflowX: "auto", margin: 0 }}>
                <span style={{ color: "#7ee787" }}>curl</span> -H <span style={{ color: "#a5d6ff" }}>"Authorization: Bearer &lt;token&gt;"</span> \{"\n"}  <span style={{ color: "#a5d6ff" }}>"{exampleUrl(ep)}"</span>
              </pre>
              <div style={{ position: "absolute", top: 8, right: 8 }}><BtnCopy dark onClick={() => copyText(`curl -H "Authorization: Bearer <token>" "${exampleUrl(ep)}"`)} /></div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function NavItem({ label, sub, active, onClick }: { label: string; sub?: string; active: boolean; onClick: () => void }) {
  return (
    <div onClick={onClick} style={{ padding: "7px 16px", cursor: "pointer", borderLeft: `3px solid ${active ? C.blue : "transparent"}`, background: active ? C.blueSoft : "transparent" }}>
      <div style={{ fontSize: 13, color: active ? C.blueTxt : "#3c4043", fontWeight: active ? 600 : 400 }}>{label}</div>
      {sub && <div style={{ fontSize: 10.5, color: C.txt3, fontFamily: C.mono, marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{sub}</div>}
    </div>
  );
}
function BtnCopy({ onClick, dark }: { onClick: () => void; dark?: boolean }) {
  return <span onClick={onClick} title="复制" style={{ cursor: "pointer", fontSize: 12, color: dark ? "#c9d1d9" : C.blueTxt, border: `1px solid ${dark ? "#444c56" : C.line}`, borderRadius: 6, padding: "3px 9px", userSelect: "none", whiteSpace: "nowrap" }}>复制</span>;
}
function Center({ children }: { children: React.ReactNode }) {
  return <div style={{ display: "grid", placeItems: "center", height: "100%", textAlign: "center", padding: 40, color: C.txt2 }}><div>{children}</div></div>;
}
function H1({ children, inline }: { children: React.ReactNode; inline?: boolean }) {
  return <h2 style={{ fontSize: 19, fontWeight: 600, margin: inline ? 0 : "0 0 4px", color: C.txt }}>{children}</h2>;
}
function H2({ children }: { children: React.ReactNode }) {
  return <h3 style={{ fontSize: 14, fontWeight: 600, margin: "22px 0 10px", color: C.txt, borderLeft: `3px solid ${C.blue}`, paddingLeft: 9 }}>{children}</h3>;
}
function Callout({ children }: { children: React.ReactNode }) {
  return <div style={{ background: C.blueSoft, color: C.blueTxt, borderRadius: 8, padding: "10px 14px", fontSize: 12.5, lineHeight: 1.6, marginTop: 10 }}>{children}</div>;
}
function InfoTable({ rows }: { rows: Array<[string, string]> }) {
  return (
    <div style={{ background: C.card, border: `1px solid ${C.line2}`, borderRadius: 10, overflow: "hidden" }}>
      {rows.map(([k, v], i) => (
        <div key={k} style={{ display: "flex", borderTop: i ? `1px solid ${C.line2}` : "none" }}>
          <div style={{ width: 96, flexShrink: 0, padding: "9px 14px", color: C.txt2, background: "#fafbfc", fontWeight: 500 }}>{k}</div>
          <div style={{ padding: "9px 14px", flex: 1, wordBreak: "break-word" }}>{v}</div>
        </div>
      ))}
    </div>
  );
}
const _unused: CSSProperties = {}; void _unused;
