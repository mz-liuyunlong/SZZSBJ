/**
 * 会议分析（原生页 · 阶段2）
 * 替代原 :8081 iframe（无源码前端），直接调 meetingServer :3457 API。
 * 接口（真实核查自 src/meetingServer.ts）：
 *   GET  /api/meetings/list?days=&profile=   → { ok, data: MinuteSummary[] }
 *   POST /api/meetings/analyze (multipart)   → { ok, result }  body: minuteTokens(JSON) / prompt / profile / files[]
 * 同源前提：admin nginx 需将 /api/meetings/ 反代到 127.0.0.1:3457（跨域已验证被拦）。
 */
import React, { useCallback, useEffect, useState } from "react";

interface MinuteSummary {
  token: string;
  title: string;
  url: string;
  duration: number; // 秒
  createTime: string;
  owner: string;
}

const C = {
  bg: "#f6f8fc", card: "#fff", txt: "#202124", txt2: "#5f6368",
  line: "#dadce0", blue: "#1a73e8", blueSoft: "#e8f0fe", neg: "#d93025",
  green: "#188038", greenSoft: "#e6f4ea",
};

const PROFILES: { key: string; label: string }[] = [
  { key: "default", label: "JIM" },
  { key: "company2", label: "掌上便捷" },
];
const DAY_OPTS = [7, 30, 90, 400];
const DEFAULT_PROMPT = "请总结这次会议的核心内容、决策和行动项。";

// —— 极简 Markdown 渲染（无第三方依赖）——
function renderMarkdown(md: string): React.ReactNode {
  const lines = md.split("\n");
  const out: React.ReactNode[] = [];
  let list: string[] = [];
  const flush = (i: number) => {
    if (list.length) {
      out.push(
        <ul key={`ul${i}`} style={{ margin: "6px 0", paddingLeft: 22 }}>
          {list.map((li, j) => <li key={j} style={{ marginBottom: 4 }}>{inline(li)}</li>)}
        </ul>
      );
      list = [];
    }
  };
  const inline = (s: string): React.ReactNode => {
    const parts = s.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
    return parts.map((p, k) => {
      if (p.startsWith("**") && p.endsWith("**")) return <strong key={k}>{p.slice(2, -2)}</strong>;
      if (p.startsWith("`") && p.endsWith("`")) return <code key={k} style={{ background: "#f1f3f4", padding: "1px 5px", borderRadius: 4, fontSize: 12 }}>{p.slice(1, -1)}</code>;
      return <span key={k}>{p}</span>;
    });
  };
  lines.forEach((raw, i) => {
    const line = raw.replace(/\s+$/, "");
    if (/^\s*[-*]\s+/.test(line)) { list.push(line.replace(/^\s*[-*]\s+/, "")); return; }
    flush(i);
    if (/^#{1,6}\s/.test(line)) {
      const lvl = (line.match(/^#+/)?.[0].length) || 1;
      const txt = line.replace(/^#+\s/, "");
      out.push(<div key={i} style={{ fontWeight: 700, fontSize: lvl <= 2 ? 16 : 14, margin: "12px 0 4px", color: C.txt }}>{inline(txt)}</div>);
    } else if (line.trim() === "") {
      out.push(<div key={i} style={{ height: 6 }} />);
    } else {
      out.push(<div key={i} style={{ margin: "3px 0", lineHeight: 1.7 }}>{inline(line)}</div>);
    }
  });
  flush(lines.length);
  return out;
}

function fmtDuration(sec: number): string {
  if (!sec || sec <= 0) return "—";
  const m = Math.round(sec / 60);
  return m >= 60 ? `${Math.floor(m / 60)}h${m % 60}m` : `${m}分`;
}
function fmtTime(s: string): string {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function MeetingAnalysis() {
  const [profile, setProfile] = useState("default");
  const [days, setDays] = useState(30);
  const [meetings, setMeetings] = useState<MinuteSummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [listLoading, setListLoading] = useState(false);
  const [listErr, setListErr] = useState("");

  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [files, setFiles] = useState<File[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState("");
  const [analyzeErr, setAnalyzeErr] = useState("");

  const loadList = useCallback(async () => {
    setListLoading(true); setListErr(""); setSelected(new Set());
    try {
      const r = await fetch(`/api/meetings/list?days=${days}&profile=${profile}`);
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || "接口返回失败");
      setMeetings(Array.isArray(j.data) ? j.data : []);
    } catch (e: any) {
      setMeetings([]);
      setListErr(e?.message || String(e));
    } finally {
      setListLoading(false);
    }
  }, [days, profile]);

  useEffect(() => { loadList(); }, [loadList]);

  const toggle = (token: string) => {
    setSelected((prev) => {
      const n = new Set(prev);
      n.has(token) ? n.delete(token) : n.add(token);
      return n;
    });
  };

  const analyze = async () => {
    if (selected.size === 0 && files.length === 0) { setAnalyzeErr("请至少勾选一个会议或上传一个文件"); return; }
    setAnalyzing(true); setAnalyzeErr(""); setResult("");
    try {
      const fd = new FormData();
      fd.append("minuteTokens", JSON.stringify(Array.from(selected)));
      fd.append("prompt", prompt || DEFAULT_PROMPT);
      fd.append("profile", profile);
      files.forEach((f) => fd.append("files", f));
      const r = await fetch(`/api/meetings/analyze`, { method: "POST", body: fd });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || "分析失败");
      setResult(j.result || "（无输出）");
    } catch (e: any) {
      setAnalyzeErr(e?.message || String(e));
    } finally {
      setAnalyzing(false);
    }
  };

  const btn = (bg: string, disabled?: boolean): React.CSSProperties => ({
    background: disabled ? "#c6d4ee" : bg, color: "#fff", border: "none", borderRadius: 8,
    padding: "8px 18px", fontSize: 13, fontWeight: 600, cursor: disabled ? "not-allowed" : "pointer",
  });
  const sel: React.CSSProperties = { border: `1px solid ${C.line}`, borderRadius: 8, padding: "6px 10px", fontSize: 13, background: "#fff" };

  return (
    <div style={{ height: "100%", overflow: "auto", background: C.bg, padding: 20, boxSizing: "border-box", fontFamily: "-apple-system,'PingFang SC','Microsoft YaHei',sans-serif", color: C.txt }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <div style={{ fontSize: 18, fontWeight: 700 }}>📋 会议分析</div>
        <span style={{ color: C.txt2, fontSize: 12 }}>飞书妙记 + 附件 → AI 提炼重点/决策/行动项</span>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: C.txt2 }}>账号</span>
        <select value={profile} onChange={(e) => setProfile(e.target.value)} style={sel}>
          {PROFILES.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
        </select>
        <span style={{ fontSize: 12, color: C.txt2 }}>范围</span>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} style={sel}>
          {DAY_OPTS.map((d) => <option key={d} value={d}>近 {d} 天</option>)}
        </select>
        <button onClick={loadList} style={btn(C.blue, listLoading)} disabled={listLoading}>{listLoading ? "加载中…" : "刷新"}</button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(360px, 1fr) minmax(420px, 1.2fr)", gap: 16, alignItems: "start" }}>
        {/* 左：会议列表 */}
        <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, overflow: "hidden" }}>
          <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.line}`, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontWeight: 600, fontSize: 13 }}>妙记列表</span>
            <span style={{ color: C.txt2, fontSize: 12 }}>共 {meetings.length} · 已选 {selected.size}</span>
          </div>
          <div style={{ maxHeight: 520, overflow: "auto" }}>
            {listLoading && <div style={{ padding: 24, textAlign: "center", color: C.txt2, fontSize: 13 }}>加载中…</div>}
            {!listLoading && listErr && (
              <div style={{ padding: 16, fontSize: 12.5, lineHeight: 1.7, background: "#fef7e0", margin: 12, borderRadius: 8, color: C.txt }}>
                <div style={{ fontWeight: 700, color: "#b06000", marginBottom: 4 }}>会议列表暂时读不到</div>
                {/token|authoriz/i.test(listErr)
                  ? <div style={{ color: C.txt2 }}>服务端飞书妙记令牌缺失/过期（与前端无关）。需运维在会议服务所在机执行 <code style={{ background: "#f1f3f4", padding: "1px 5px", borderRadius: 4 }}>lark-cli auth login</code> 用对应飞书账号重新授权（授予 minutes:minutes.search:read 权限）后即可恢复；上传附件做分析不受影响。</div>
                  : <div style={{ color: C.txt2 }}>数据源返回异常，可稍后重试或联系运维。</div>}
                <details style={{ marginTop: 8 }}>
                  <summary style={{ cursor: "pointer", color: C.txt2 }}>技术详情</summary>
                  <div style={{ marginTop: 6, color: C.neg, whiteSpace: "pre-wrap", fontSize: 11.5 }}>{listErr}</div>
                </details>
              </div>
            )}
            {!listLoading && !listErr && meetings.length === 0 && (
              <div style={{ padding: 24, textAlign: "center", color: C.txt2, fontSize: 13 }}>该范围内暂无妙记</div>
            )}
            {!listLoading && meetings.map((m) => {
              const on = selected.has(m.token);
              return (
                <label key={m.token} style={{ display: "flex", gap: 10, padding: "10px 14px", borderBottom: `1px solid #f1f3f4`, cursor: "pointer", background: on ? C.blueSoft : "transparent" }}>
                  <input type="checkbox" checked={on} onChange={() => toggle(m.token)} style={{ marginTop: 3 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: C.txt, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.title || "无标题"}</div>
                    <div style={{ fontSize: 11.5, color: C.txt2, marginTop: 3, display: "flex", gap: 10, flexWrap: "wrap" }}>
                      <span>{fmtTime(m.createTime)}</span>
                      {m.owner && <span>所有者 {m.owner}</span>}
                      <span>{fmtDuration(m.duration)}</span>
                      {m.url && <a href={m.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} style={{ color: C.blue, textDecoration: "none" }}>打开 ↗</a>}
                    </div>
                  </div>
                </label>
              );
            })}
          </div>
        </div>

        {/* 右：提示词 + 附件 + 结果 */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: 14 }}>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>分析指令</div>
            <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3}
              style={{ width: "100%", boxSizing: "border-box", border: `1px solid ${C.line}`, borderRadius: 8, padding: 10, fontSize: 13, resize: "vertical", fontFamily: "inherit" }} />
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
              <label style={{ ...btn("#fff"), color: C.txt, border: `1px solid ${C.line}`, fontWeight: 500, cursor: "pointer" }}>
                + 附件
                <input type="file" multiple style={{ display: "none" }}
                  onChange={(e) => setFiles(Array.from(e.target.files || []))} />
              </label>
              {files.length > 0 && <span style={{ fontSize: 12, color: C.txt2 }}>{files.map((f) => f.name).join("、")}</span>}
              <div style={{ flex: 1 }} />
              <button onClick={analyze} style={btn(C.green, analyzing)} disabled={analyzing}>{analyzing ? "分析中…（可能需1-3分钟）" : "开始分析"}</button>
            </div>
            {analyzeErr && <div style={{ marginTop: 10, fontSize: 12.5, color: C.neg, background: "#fce8e6", padding: 10, borderRadius: 8 }}>{analyzeErr}</div>}
          </div>

          <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: 14, minHeight: 200 }}>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8, color: C.txt2 }}>分析结果</div>
            {analyzing && <div style={{ color: C.txt2, fontSize: 13 }}>AI 正在阅读会议内容并提炼，请稍候…</div>}
            {!analyzing && !result && <div style={{ color: "#9aa0a6", fontSize: 13 }}>勾选左侧妙记或上传附件后点「开始分析」，结果显示在此。</div>}
            {!analyzing && result && <div style={{ fontSize: 13.5 }}>{renderMarkdown(result)}</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
