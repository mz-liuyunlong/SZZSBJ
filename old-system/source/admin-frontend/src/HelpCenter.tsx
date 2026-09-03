/**
 * HelpCenter.tsx — 帮助中心（2026-07-20 新增，领星式布局）
 * 左侧目录树（按业务模块分组）+ 右侧文章正文（Markdown）+ 前往功能按钮。
 * 内容存 dim_page_help，随部署 UPDATE 同步更新，不做在线编辑。
 * 入口：各页面顶栏 "?" → #/help?page=<page_key>
 */
import { useState, useEffect, useCallback } from "react";

interface ArticleMeta {
  page_key: string;
  group_name: string;
  title: string;
  target_url: string;
  updated_at: string;
}

interface ArticleDetail extends ArticleMeta {
  content_md: string;
}

function renderInline(text: string): React.ReactNode {
  // 2026-08-12：新增链接渲染——[文字](url) 与裸 http(s) URL 均转可点链接，外链一律新开标签页
  const parts = text.split(/(<font color="[^"]+">.*?<\/font>|\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s，。；、）」』<]+)/g);
  return parts.map((p, i) => {
    const fontMatch = p.match(/^<font color="([^"]+)">(.*)<\/font>$/);
    if (fontMatch) {
      return <span key={i} style={{ color: fontMatch[1], fontWeight: 700 }}>{renderInline(fontMatch[2])}</span>;
    }
    if (p.startsWith("**") && p.endsWith("**")) return <b key={i}>{p.slice(2, -2)}</b>;
    if (p.startsWith("`") && p.endsWith("`")) {
      return <code key={i} style={{ background: "#f1f5f9", padding: "1px 5px", borderRadius: "4px", fontSize: "0.92em", color: "#4f46e5" }}>{p.slice(1, -1)}</code>;
    }
    const mdLink = p.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
    if (mdLink) {
      return <a key={i} href={mdLink[2]} target="_blank" rel="noreferrer" style={{ color: "#4f46e5", textDecoration: "underline" }}>{mdLink[1]}</a>;
    }
    if (/^https?:\/\//.test(p)) {
      return <a key={i} href={p} target="_blank" rel="noreferrer" style={{ color: "#4f46e5", textDecoration: "underline", wordBreak: "break-all" }}>{p}</a>;
    }
    return <span key={i}>{p}</span>;
  });
}

function renderMd(md: string): React.ReactNode[] {
  const lines = md.split("\n");
  const out: React.ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    // 表格块
    if (line.trim().startsWith("|") && lines[i + 1]?.trim().startsWith("|")) {
      const tblLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        tblLines.push(lines[i]);
        i += 1;
      }
      const parseRow = (l: string) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const header = parseRow(tblLines[0]);
      const bodyRows = tblLines.slice(2).map(parseRow);
      out.push(
        <table key={`tbl-${i}`} style={{ borderCollapse: "collapse", margin: "10px 0", fontSize: "13px", width: "100%" }}>
          <thead>
            <tr>{header.map((h, hi) => (
              <th key={hi} style={{ border: "1px solid #e5e7eb", background: "#f8fafc", padding: "6px 10px", textAlign: "left", color: "#374151", whiteSpace: "nowrap" }}>{renderInline(h)}</th>
            ))}</tr>
          </thead>
          <tbody>
            {bodyRows.map((r, ri) => (
              <tr key={ri}>{r.map((c, ci) => (
                <td key={ci} style={{ border: "1px solid #e5e7eb", padding: "6px 10px", color: "#4b5563" }}>{renderInline(c)}</td>
              ))}</tr>
            ))}
          </tbody>
        </table>,
      );
      continue;
    }
    const imgMatch = line.trim().match(/^!\[([^\]]*)\]\((.+)\)$/);
    if (imgMatch) {
      out.push(<img key={i} src={imgMatch[2]} alt={imgMatch[1]} style={{ maxWidth: "520px", width: "100%", borderRadius: "10px", border: "1px solid #e5e7eb", margin: "8px 0", display: "block" }} />);
      i += 1;
      continue;
    }
    if (line.startsWith("## ")) {
      out.push(<h2 key={i} id={`h-${i}`} style={{ margin: "22px 0 10px", fontSize: "18px", color: "#111827", borderBottom: "1px solid #f1f5f9", paddingBottom: "6px" }}>{line.slice(3)}</h2>);
    } else if (line.startsWith("### ")) {
      out.push(<h3 key={i} style={{ margin: "16px 0 6px", fontSize: "15px", color: "#1f2937" }}>{line.slice(4)}</h3>);
    } else if (/^[-*]\s/.test(line)) {
      out.push(
        <div key={i} style={{ paddingLeft: "14px", marginBottom: "4px", display: "flex", gap: "8px", fontSize: "13.5px", color: "#374151", lineHeight: 1.7 }}>
          <span style={{ color: "#6366f1", flexShrink: 0 }}>•</span>
          <span>{renderInline(line.replace(/^[-*]\s/, ""))}</span>
        </div>,
      );
    } else if (/^\d+\.\s/.test(line)) {
      const idx = line.indexOf(". ");
      out.push(
        <div key={i} style={{ paddingLeft: "14px", marginBottom: "4px", display: "flex", gap: "8px", fontSize: "13.5px", color: "#374151", lineHeight: 1.7 }}>
          <span style={{ color: "#6366f1", flexShrink: 0, minWidth: "18px" }}>{line.slice(0, idx + 1)}</span>
          <span>{renderInline(line.slice(idx + 2))}</span>
        </div>,
      );
    } else if (/^[-*_]{3,}$/.test(line.trim())) {
      out.push(<hr key={i} style={{ border: "none", borderTop: "1px solid #e5e7eb", margin: "14px 0" }} />);
    } else if (line.trim() === "") {
      out.push(<div key={i} style={{ height: "8px" }} />);
    } else {
      out.push(<div key={i} style={{ marginBottom: "4px", fontSize: "13.5px", color: "#374151", lineHeight: 1.7 }}>{renderInline(line)}</div>);
    }
    i += 1;
  }
  return out;
}

export default function HelpCenter({ onNavigate }: { onNavigate?: (key: string) => void } = {}) {
  const [articles, setArticles] = useState<ArticleMeta[]>([]);
  const [activeKey, setActiveKey] = useState<string>("");
  const [detail, setDetail] = useState<ArticleDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/help/articles");
        const data = await res.json();
        const list: ArticleMeta[] = data.articles ?? [];
        setArticles(list);
        // 支持 #/help?page=xxx 直达
        const m = window.location.hash.match(/[?&]page=([^&]+)/);
        const wanted = m ? decodeURIComponent(m[1]) : "";
        const first = list.find((a) => a.page_key === wanted) ?? list[0];
        if (first) setActiveKey(first.page_key);
      } catch {
        setArticles([]);
      }
    })();
  }, []);

  // 2026-08-04 修复：帮助中心作为常驻 Tab,首挂载后不再读 hash → 从其它页点“?”会停在上一次看的文章。
  // 加 hashchange 监听：#/help?page=xxx 变化时重读并切到目标文章。
  useEffect(() => {
    function onHash() {
      const m = window.location.hash.match(/[?&]page=([^&]+)/);
      const wanted = m ? decodeURIComponent(m[1]) : "";
      if (wanted) setActiveKey(wanted);
    }
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const loadDetail = useCallback(async (key: string) => {
    if (!key) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/help/article?key=${encodeURIComponent(key)}`);
      const data = await res.json();
      setDetail(data.error ? null : data);
    } catch {
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadDetail(activeKey); }, [activeKey, loadDetail]);

  const groups: Array<{ name: string; items: ArticleMeta[] }> = [];
  for (const a of articles) {
    let g = groups.find((x) => x.name === a.group_name);
    if (!g) {
      g = { name: a.group_name, items: [] };
      groups.push(g);
    }
    g.items.push(a);
  }

  return (
    <div style={{ display: "flex", height: "calc(100vh - 48px)", background: "#fff" }}>
      {/* 左侧目录树 */}
      <div style={{ width: "250px", flexShrink: 0, borderRight: "1px solid #f1f5f9", overflowY: "auto", padding: "16px 0" }}>
        {groups.map((g) => (
          <div key={g.name} style={{ marginBottom: "14px" }}>
            <div style={{ padding: "4px 18px", fontSize: "12px", fontWeight: 700, color: "#9ca3af" }}>{g.name}</div>
            {g.items.map((a) => (
              <div
                key={a.page_key}
                onClick={() => setActiveKey(a.page_key)}
                style={{
                  padding: "8px 18px", fontSize: "13.5px", cursor: "pointer",
                  color: activeKey === a.page_key ? "#4f46e5" : "#374151",
                  background: activeKey === a.page_key ? "#eef2ff" : "transparent",
                  borderRight: activeKey === a.page_key ? "3px solid #6366f1" : "3px solid transparent",
                  fontWeight: activeKey === a.page_key ? 600 : 400,
                }}
              >
                {a.title}
              </div>
            ))}
          </div>
        ))}
        {articles.length === 0 && (
          <div style={{ padding: "20px", fontSize: "13px", color: "#9ca3af" }}>暂无帮助文章</div>
        )}
      </div>

      {/* 右侧正文 */}
      <div style={{ flex: 1, overflowY: "auto", padding: "28px 48px", maxWidth: "980px" }}>
        {loading && <div style={{ color: "#9ca3af", fontSize: "13px" }}>加载中…</div>}
        {!loading && detail && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: "14px", marginBottom: "4px" }}>
              <h1 style={{ margin: 0, fontSize: "24px", color: "#111827" }}>{detail.title}</h1>
              {detail.target_url && (
                <a
                  href={detail.target_url}
                  onClick={(e) => { e.preventDefault(); const u = detail.target_url || ""; if (u.startsWith("shell:")) { if (onNavigate) { onNavigate(u.slice(6)); } return; } if (/\/walmart-ads-data/.test(u)) { onNavigate && onNavigate("ads:all"); return; } if (/:8081/.test(u)) { onNavigate && onNavigate("meeting"); return; } if (/:3456/.test(u)) { onNavigate && onNavigate("llm"); return; } const hm = u.match(/#\/([a-z-]+)/); const map: Record<string, string> = { "feishu-raw-sales-data": "feishu-raw:<REDACTED_FEISHU_SHEET_ID>", "business-analysis": "business-analysis", "hr-performance": "hr-performance", "roster": "roster" }; if (hm && onNavigate && map[hm[1]]) { onNavigate(map[hm[1]]); return; } window.location.href = u; window.location.reload(); }}
                  style={{ fontSize: "13px", color: "#fff", background: "#6366f1", padding: "5px 14px", borderRadius: "6px", textDecoration: "none", whiteSpace: "nowrap" }}
                >
                  前往该功能 →
                </a>
              )}
            </div>
            <div style={{ fontSize: "12px", color: "#9ca3af", marginBottom: "16px" }}>
              口径更新于 {detail.updated_at}（文档随每次口径变更同步上线）
            </div>
            {renderMd(detail.content_md)}
          </>
        )}
        {!loading && !detail && articles.length > 0 && (
          <div style={{ color: "#9ca3af", fontSize: "13px" }}>请选择左侧文章</div>
        )}
      </div>
    </div>
  );
}
