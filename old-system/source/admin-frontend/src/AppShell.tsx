/**
 * AppShell.tsx — 运营数据中台 统一外壳（阶段1，2026-07-25）
 *
 * 谷歌 Material / Workspace 风格：白底、胶囊导航、5 大板块各配 Google 品牌色（蓝/红/黄/绿）。
 * 只负责“外壳 chrome”，不碰任何业务页内部逻辑：内容区由父级(App.tsx)按 activeKey 决定渲染什么。
 *
 * 模块类型：native(admin原生页) / iframe(会议:8081·LLM:3456) / newtab(广告:3000) / external(ChatGPT) / placeholder(待做)
 */
import { useState, useEffect } from "react";
import type { CSSProperties, ReactNode, MouseEvent as ReactMouseEvent } from "react";

const C = {
  bg: "#f6f8fc", card: "#ffffff", side: "#f6f8fc",
  txt: "#202124", txt2: "#5f6368", txt3: "#9aa0a6",
  line: "#dadce0", line2: "#e8eaed",
  blue: "#1a73e8", blueSoft: "#e8f0fe", blueTxt: "#1967d2",
  neg: "#d93025", gRed: "#ea4335",
  sh1: "0 1px 2px 0 rgba(60,64,67,.10), 0 1px 3px 1px rgba(60,64,67,.06)",
  sh2: "0 1px 3px 0 rgba(60,64,67,.15), 0 4px 8px 3px rgba(60,64,67,.08)",
};

export type ModType = "native" | "iframe" | "newtab" | "external" | "placeholder";
export interface Mod { key: string; label: string; type: ModType; url?: string; state?: "red" | "ext"; }
export interface Section { ic: string; nm: string; short: string; c: string; sc: string; open?: boolean; kids: Mod[]; }

// 5 大板块（key 与 App.tsx activeKey 一致；c/sc = Google 品牌色+浅色底）
export const SECTIONS: Section[] = [
  { ic: "▦", nm: "运营中心", short: "运营", c: "#4285f4", sc: "#e8f0fe", open: true, kids: [
    { key: "sales-dashboard", label: "数据看板", type: "native" },
    { key: "feishu-raw:<REDACTED_FEISHU_SHEET_ID>", label: "每日销售明细", type: "native" },
    { key: "feishu-raw:order_profit_daily", label: "订单利润 Beta", type: "native" },
    { key: "profit:order-v2", label: "订单利润 V2", type: "native" },
    { key: "sales-detail-v2", label: "每日销售明细 V2", type: "native" },
    { key: "feishu-raw:cs_test_analysis", label: "CS测品分析", type: "native" },
    { key: "feishu-raw:product_management", label: "产品管理", type: "native" },
    { key: "feishu-raw:operation_log", label: "运营日志", type: "native" },
    { key: "monthly-plan", label: "目标管理", type: "native" },
    { key: "business-analysis", label: "经营分析", type: "native" },
    { key: "feishu-raw:__clearance__", label: "清货中心", type: "native" },
  ]},
  { ic: "◉", nm: "广告系统", short: "广告", c: "#ea4335", sc: "#fce8e6", kids: [
    { key: "ads:all", label: "全部广告（周期聚合）", type: "iframe", url: "http://42.193.254.170:3000/walmart-ads-data?tab=all" },
    { key: "ads:auto", label: "自动广告", type: "iframe", url: "http://42.193.254.170:3000/walmart-ads-data?tab=auto" },
    { key: "ads:manual", label: "手动广告", type: "iframe", url: "http://42.193.254.170:3000/walmart-ads-data?tab=manual" },
    { key: "ads:import", label: "导入任务", type: "iframe", url: "http://42.193.254.170:3000/walmart-ads-data?tab=tasks" },
    { key: "ads:upload", label: "自动广告导入", type: "iframe", url: "http://42.193.254.170:3000/walmart-ads" },
    { key: "ads:sem-upload", label: "SEM广告导入", type: "iframe", url: "http://42.193.254.170:3000/walmart-sem" },
    { key: "ads:connect-invoice", label: "广告发票导入", type: "iframe", url: "http://42.193.254.170:3000/walmart-connect-invoice" },
    { key: "ads:sem-data", label: "SEM广告数据", type: "iframe", url: "http://42.193.254.170:3000/walmart-sem-data" },
    { key: "ads:sbsv-data", label: "SB/SV广告数据", type: "iframe", url: "http://42.193.254.170:3000/walmart-sbsv-data" },
    { key: "ads:fee-report", label: "广告费用报表", type: "native" },
    { key: "ads:bill-fee", label: "广告账单扣费", type: "native" },
  ]},
  { ic: "¥", nm: "AI财务", short: "财务", c: "#188038", sc: "#e6f4ea", kids: [
    { key: "finance:tools", label: "财务工具", type: "native" },
    { key: "finance:item-cash-profit", label: "单品现金利润", type: "placeholder" },
    { key: "finance:item-cash-profit-v2", label: "单品现金利润·ITEMID", type: "native" },
    { key: "finance:reports", label: "利润报表", type: "placeholder" },
    { key: "finance:credits", label: "返还明细", type: "native" },
  ]},
  { ic: "✦", nm: "智能PMC", short: "PMC", c: "#ea8600", sc: "#fef7e0", kids: [
    { key: "feishu-raw:__pmc__", label: "PMC 看板", type: "native" },
    { key: "pmc-inventory", label: "库存一览表", type: "native" },
    { key: "pmc-wfs-fee", label: "WFS费用异常", type: "native" },
    { key: "pmc-storage-fee", label: "仓储费", type: "native" },
    { key: "pmc-inbound-freight", label: "入库运输", type: "native" },
  ]},
  { ic: "☺", nm: "AI人力", short: "人力", c: "#34a853", sc: "#e6f4ea", kids: [
    { key: "hr-performance", label: "绩效台账", type: "native" },
    { key: "hr-performance#review", label: "AI 运营日志评级", type: "native" },
    { key: "attendance", label: "考勤", type: "native" },
    { key: "roster", label: "用户管理", type: "native" },
  ]},
  { ic: "⚙", nm: "AI工具", short: "工具", c: "#4285f4", sc: "#e8f0fe", kids: [
    { key: "meeting", label: "会议分析", type: "iframe", url: "http://42.193.254.170:8081/" },
    { key: "llm", label: "LLM 模型切换", type: "iframe", url: "http://42.193.254.170:3456/" },
    { key: "api-doc", label: "API 接口文档", type: "native" },
    { key: "help", label: "帮助中心", type: "native" },
    { key: "gpt-ops", label: "AI广告分析", type: "external", url: "https://chatgpt.com/g/g-6a54fe5395108191b7df3a30e2205558-walmart-yan-gao-fen-xi-zhu-shou-v1-5" },
    { key: "gpt-ads", label: "AI关键词文案", type: "external", url: "https://chatgpt.com/g/g-6a6acb21bd5c8191873d4b6838ddc78e-zi-dong-hua-guan-jian-ci-wen-an-gong-ju" },
    { key: "gpt-patent", label: "美国专利检索", type: "external", url: "https://chatgpt.com/g/g-6a7b0b3f2388819187293f3c3d8c5866-mei-guo-wai-guan-zhuan-li-kuai-shai-v1-1" },
  ]},
];

export const MOD_BY_KEY: Record<string, Mod> = {};
export const SEC_OF: Record<string, { c: string; sc: string }> = {};
for (const s of SECTIONS) for (const k of s.kids) { MOD_BY_KEY[k.key] = k; SEC_OF[k.key] = { c: s.c, sc: s.sc }; }

interface Me { username: string; role: string; is_superadmin?: boolean; }

// 2026-08-20 需求方拍板：旧版页面仅超管可见（V2已接棒；旧页留作对账，不对普通用户开放）
export const SUPERADMIN_ONLY_KEYS = new Set<string>(["feishu-raw:<REDACTED_FEISHU_SHEET_ID>", "feishu-raw:order_profit_daily"]);
const ROLE_CN: Record<string, string> = { admin: "管理员", supervisor: "主管", team_lead: "组长", member: "成员" };

interface Props { activeKey: string; onNavigate: (key: string) => void; children: ReactNode; }

export default function AppShell({ activeKey, onNavigate, children }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const [secOpen, setSecOpen] = useState<Record<number, boolean>>({});
  const [openTabs, setOpenTabs] = useState<string[]>(() => (MOD_BY_KEY[activeKey] ? [activeKey] : []));
  const [userMenu, setUserMenu] = useState(false);
  const [me, setMe] = useState<Me>({ username: "", role: "" });
  const [apiDocAllowed, setApiDocAllowed] = useState(false);

  useEffect(() => {
    fetch("/api/auth/me", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d && d.username) setMe({ username: d.username, role: d.role || "", is_superadmin: Boolean(d.is_superadmin) }); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetch("/api/api-doc/access", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setApiDocAllowed(Boolean(d.allowed)); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const m = MOD_BY_KEY[activeKey];
    if (m && m.type !== "newtab" && m.type !== "external") {
      setOpenTabs((prev) => (prev.includes(activeKey) ? prev : [...prev, activeKey]));
    }
  }, [activeKey]);

  function clickMod(m: Mod) {
    if (m.type === "newtab" || m.type === "external") {
      if (m.url) window.open(m.url, "_blank", "noopener");
      else window.alert(`${m.label} 在 ChatGPT 中，暂无 admin 内入口`);
      return;
    }
    onNavigate(m.key);
  }
  function closeTab(e: ReactMouseEvent, key: string) {
    e.stopPropagation();
    setOpenTabs((prev) => {
      const next = prev.filter((k) => k !== key);
      if (key === activeKey) { const fb = next[next.length - 1]; if (fb) onNavigate(fb); }
      return next;
    });
  }
  async function logout() {
    try { await fetch("/api/auth/logout", { method: "POST", credentials: "include" }); } catch { /* ignore */ }
    window.location.href = "/login.html";
  }

  const sideW = collapsed ? 74 : 230;
  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden", fontFamily: '"Roboto","Google Sans",-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif', fontSize: 13, color: C.txt, background: C.bg }}>
      {/* 左侧导航 */}
      <aside style={{ width: sideW, background: C.side, flexShrink: 0, display: "flex", flexDirection: "column", transition: "width .18s" }}>
        <div style={{ height: 64, display: "flex", alignItems: "center", gap: 12, padding: collapsed ? 0 : "0 18px", justifyContent: collapsed ? "center" : "flex-start", whiteSpace: "nowrap", overflow: "hidden" }}>
          <div style={{ width: 34, height: 34, borderRadius: 9, display: "grid", placeItems: "center", color: "#fff", fontWeight: 700, fontSize: 15, flexShrink: 0, background: "conic-gradient(from 135deg,#4285f4,#34a853,#fbbc04,#ea4335,#4285f4)" }}>运</div>
          {!collapsed && <span style={{ fontWeight: 500, fontSize: 16, color: "#3c4043" }}>运营数据中台</span>}
        </div>
        <nav style={{ flex: 1, overflowY: "auto", padding: "4px 8px" }}>
          {SECTIONS.map((sec, i) => {
            const visKids = sec.kids.filter((k) => (k.key !== "api-doc" || apiDocAllowed) && (!SUPERADMIN_ONLY_KEYS.has(k.key) || me.is_superadmin));
            const hasActive = visKids.some((k) => k.key === activeKey);
            const isOpen = collapsed ? false : (secOpen[i] ?? Boolean(sec.open || hasActive));
            const redCount = visKids.filter((k) => k.state === "red").length;
            return (
              <div key={sec.nm}>
                <div onClick={() => { if (!collapsed) setSecOpen((p) => ({ ...p, [i]: !isOpen })); }}
                     style={collapsed
                       ? { display: "flex", flexDirection: "column", gap: 2, height: 56, margin: "2px 6px", borderRadius: 14, justifyContent: "center", alignItems: "center", cursor: "pointer", background: (collapsed && hasActive) ? sec.sc : "transparent" }
                       : { display: "flex", alignItems: "center", gap: 14, height: 44, padding: "0 14px", cursor: "pointer", color: "#3c4043", fontWeight: 500, borderRadius: "0 22px 22px 0" }}>
                  <span style={{ width: 26, height: 26, display: "grid", placeItems: "center", fontSize: 15, flexShrink: 0, color: "#fff", background: sec.c, borderRadius: 8 }}>{sec.ic}</span>
                  {collapsed ? <span style={{ fontSize: 11, color: C.txt2, lineHeight: 1 }}>{sec.short}</span> : (
                    <>
                      <span style={{ flex: 1, fontSize: 13.5 }}>{sec.nm}</span>
                      {redCount > 0 && <span style={{ fontSize: 10, color: "#fff", background: C.gRed, borderRadius: 10, padding: "1px 6px" }}>{redCount}</span>}
                      <span style={{ fontSize: 10, color: C.txt3, transition: "transform .15s", transform: isOpen ? "rotate(90deg)" : "none" }}>▸</span>
                    </>
                  )}
                </div>
                {isOpen && !collapsed && visKids.map((k) => {
                  const active = k.key === activeKey;
                  const base: CSSProperties = { display: "flex", alignItems: "center", gap: 12, height: 40, padding: "0 14px 0 30px", margin: "1px 0", cursor: "pointer", fontSize: 13, whiteSpace: "nowrap", borderRadius: "0 22px 22px 0" };
                  const color = active ? sec.c : k.state === "red" ? C.neg : k.state === "ext" ? C.txt3 : "#444746";
                  const bg = active ? sec.sc : "transparent";
                  const dot = active ? sec.c : k.state === "red" ? C.neg : "#bdc1c6";
                  return (
                    <div key={k.key} onClick={() => clickMod(k)}
                         style={{ ...base, color, background: bg, fontWeight: active ? 600 : 400 }}>
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: dot, flexShrink: 0 }} />
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>{k.label}</span>
                      {k.state === "red" && <span style={{ fontSize: 10, color: C.neg, background: "#fce8e6", padding: "2px 7px", borderRadius: 8 }}>待做</span>}
                      {k.state === "ext" && <span style={{ fontSize: 10, color: C.txt3, background: "#f1f3f4", padding: "2px 7px", borderRadius: 8 }}>ChatGPT ↗</span>}
                      {k.type === "newtab" && <span style={{ fontSize: 10, color: C.txt3, background: "#f1f3f4", padding: "2px 7px", borderRadius: 8 }}>↗</span>}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </nav>
        <div onClick={() => setCollapsed(!collapsed)}
             style={{ height: 52, display: "flex", alignItems: "center", padding: collapsed ? 0 : "0 20px", justifyContent: collapsed ? "center" : "flex-start", cursor: "pointer", color: C.txt2, gap: 12, flexShrink: 0, fontSize: 13, borderTop: `1px solid ${C.line2}` }}>
          <span style={{ fontSize: 16, transition: "transform .18s", transform: collapsed ? "scaleX(-1)" : "none" }}>⇤</span>
          {!collapsed && <span>收起菜单</span>}
        </div>
      </aside>

      {/* 主区 */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <div style={{ height: 64, background: C.bg, display: "flex", alignItems: "center", padding: "0 20px 0 8px", gap: 4 }}>
          <div style={{ display: "flex", alignItems: "center", height: "100%", gap: 2, overflowX: "auto" }}>
            {openTabs.map((key) => {
              const m = MOD_BY_KEY[key]; if (!m) return null;
              const active = key === activeKey; const sc = SEC_OF[key];
              return (
                <div key={key} onClick={() => onNavigate(key)}
                     style={{ display: "flex", alignItems: "center", gap: 8, height: 40, padding: "0 16px", fontSize: 13.5, cursor: "pointer", whiteSpace: "nowrap", borderRadius: 20,
                              color: active ? (sc?.c || C.blueTxt) : C.txt2, background: active ? (sc?.sc || C.blueSoft) : "transparent", fontWeight: active ? 600 : 400 }}>
                  {m.label}
                  <span onClick={(e) => closeTab(e, key)} style={{ color: C.txt3, fontSize: 14, width: 18, height: 18, borderRadius: "50%", display: "grid", placeItems: "center" }}>✕</span>
                </div>
              );
            })}
          </div>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 16, flexShrink: 0, paddingLeft: 14 }}>
            <div onClick={() => onNavigate("chat")} style={{ display: "flex", alignItems: "center", gap: 8, background: C.blue, color: "#fff", height: 40, padding: "0 18px", borderRadius: 20, fontSize: 13.5, fontWeight: 500, cursor: "pointer", boxShadow: C.sh1 }}>✦ AI助手</div>
            <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 9, cursor: "pointer" }} onClick={() => setUserMenu(!userMenu)}>
              <div style={{ width: 36, height: 36, borderRadius: "50%", background: C.blue, display: "grid", placeItems: "center", color: "#fff", fontSize: 14, fontWeight: 500 }}>{(me.username || "用")[0]}</div>
              <span style={{ fontSize: 13.5, color: C.txt, fontWeight: 500 }}>{me.username || "用户"} ▾</span>
              {userMenu && (
                <div onClick={(e) => e.stopPropagation()} style={{ position: "absolute", right: 0, top: 48, width: 200, background: "#fff", border: `1px solid ${C.line2}`, borderRadius: 12, boxShadow: C.sh2, overflow: "hidden", zIndex: 50 }}>
                  <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 3, alignItems: "center", textAlign: "center", borderBottom: `1px solid ${C.line2}` }}>
                    <div style={{ width: 44, height: 44, borderRadius: "50%", background: C.blue, color: "#fff", display: "grid", placeItems: "center", fontSize: 17, marginBottom: 6 }}>{(me.username || "用")[0]}</div>
                    <b style={{ fontSize: 14 }}>{me.username || "用户"}</b>
                    <span style={{ fontSize: 11.5, color: C.txt2 }}>角色：{ROLE_CN[me.role] || me.role || "—"}</span>
                  </div>
                  <div style={ulStyle} onClick={() => onNavigate("hr-performance")}>⚙ 个人设置</div>
                  <div style={{ ...ulStyle, color: C.neg, borderTop: `1px solid ${C.line2}` }} onClick={logout}>⎋ 退出登录</div>
                </div>
              )}
            </div>
          </div>
        </div>
        <div style={{ flex: 1, minHeight: 0, overflow: "auto", position: "relative", padding: "0 16px 16px" }}>{children}</div>
      </div>
    </div>
  );
}

const ulStyle: CSSProperties = { padding: "11px 16px", fontSize: 13, color: C.txt2, cursor: "pointer", display: "flex", alignItems: "center", gap: 10 };
