import { useState, useRef, useEffect, useCallback } from "react";
import BusinessAnalysis from "./BusinessAnalysis";
import FeishuRawSalesData from "./FeishuRawSalesData";
import LingxingSalesData from "./LingxingSalesData";
import SalesDashboard from "./SalesDashboard";
import HelpCenter from "./HelpCenter";
import HrPerformance from "./HrPerformance";
import Attendance from "./Attendance";
import AppShell, { MOD_BY_KEY } from "./AppShell";
import MeetingAnalysis from "./MeetingAnalysis";
import RosterAdmin from "./RosterAdmin";
import ApiDocPage from "./ApiDocPage";
import MonthlyPlanPanel from "./MonthlyPlanPanel";
import PmcInventoryOverview from "./PmcInventoryOverview";
import PmcWfsFeeCase from "./PmcWfsFeeCase";
import PmcFeeDetail from "./PmcFeeDetail"; // 2026-08-18 智能PMC·仓储费/入库运输明细（两个入口共用组件）
import AdsFeeReport from "./AdsFeeReport"; // 2026-08-19 广告系统·广告费用报表（财务月度取数）
import AdsBillFee from "./AdsBillFee"; // 2026-08-19 广告系统·广告账单扣费（发票级扣款方式，自费用报表拆分）
import AiFinanceCredits from "./AiFinanceCredits";
import AiFinanceTools from "./AiFinanceTools";
import AiFinanceItemCashProfit from "./AiFinanceItemCashProfit";
import AiFinanceItemCashProfitV2 from "./AiFinanceItemCashProfitV2"; // 批13：按店铺+ITEMID 的新页，旧页不动
import OrderProfitV2 from "./OrderProfitV2"; // 批3a：订单利润V2 新Tab，旧Beta页不动
import SalesDetailV2 from "./SalesDetailV2"; // 批C-1：每日销售明细V2，旧明细Tab不动
import { SUPERADMIN_ONLY_KEYS } from "./AppShell"; // 2026-08-20：旧版页面仅超管可见（菜单+路由双拦截）

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  isError?: boolean;
}

interface ApiResponse {
  answer?: string;
  sources?: string[];
  error?: string;
}

// ── 快捷问题 ──────────────────────────────────────────────────────────────────

const QUICK_QUESTIONS = [
  "今天各店铺的销量和利润怎么样？",
  "最近7天哪些产品的广告ACOS最高？",
  "有哪些产品存在产品数据问题需要关注？",
  "悦斯测品有哪些产品最近表现最好？",
  "哪些产品库存不足需要补货？",
];

// ── Markdown 简易渲染 ─────────────────────────────────────────────────────────

function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split("\n");
  const result: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // 标题
    if (line.startsWith("### ")) {
      result.push(<h4 key={i} style={{ margin: "10px 0 4px", fontSize: "14px", color: "#1a1a2e" }}>{line.slice(4)}</h4>);
    } else if (line.startsWith("## ")) {
      result.push(<h3 key={i} style={{ margin: "12px 0 6px", fontSize: "15px", color: "#1a1a2e" }}>{line.slice(3)}</h3>);
    } else if (line.startsWith("# ")) {
      result.push(<h2 key={i} style={{ margin: "14px 0 8px", fontSize: "16px", color: "#1a1a2e" }}>{line.slice(2)}</h2>);
    }
    // 分割线
    else if (/^[-*_]{3,}$/.test(line.trim())) {
      result.push(<hr key={i} style={{ border: "none", borderTop: "1px solid #e5e7eb", margin: "8px 0" }} />);
    }
    // 列表项
    else if (/^[-*•]\s/.test(line)) {
      result.push(
        <div key={i} style={{ paddingLeft: "16px", marginBottom: "2px", display: "flex", gap: "6px" }}>
          <span style={{ color: "#6366f1", flexShrink: 0 }}>•</span>
          <span>{renderInline(line.replace(/^[-*•]\s/, ""))}</span>
        </div>
      );
    }
    // 数字列表
    else if (/^\d+\.\s/.test(line)) {
      const [num, ...rest] = line.split(". ");
      result.push(
        <div key={i} style={{ paddingLeft: "16px", marginBottom: "2px", display: "flex", gap: "6px" }}>
          <span style={{ color: "#6366f1", flexShrink: 0, minWidth: "18px" }}>{num}.</span>
          <span>{renderInline(rest.join(". "))}</span>
        </div>
      );
    }
    // 空行
    else if (line.trim() === "") {
      result.push(<div key={i} style={{ height: "6px" }} />);
    }
    // 普通行
    else {
      result.push(<div key={i} style={{ marginBottom: "2px" }}>{renderInline(line)}</div>);
    }

    i++;
  }

  return result;
}

function renderInline(text: string): React.ReactNode {
  // 处理 **bold** 和 `code`
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return <strong key={i}>{part.slice(2, -2)}</strong>;
        }
        if (part.startsWith("`") && part.endsWith("`")) {
          return (
            <code key={i} style={{ background: "#f1f5f9", padding: "1px 5px", borderRadius: "4px", fontSize: "13px", fontFamily: "monospace" }}>
              {part.slice(1, -1)}
            </code>
          );
        }
        return part;
      })}
    </>
  );
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

export default function App() {
  const [isSuperadmin, setIsSuperadmin] = useState(false); // 2026-08-20 旧版页面权限闸门
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(7);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || loading) return;

      const userMsg: Message = { role: "user", content: q };
      const newMessages: Message[] = [...messages, userMsg];
      setMessages(newMessages);
      setInput("");
      setLoading(true);

      try {
        const resp = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: newMessages.map((m) => ({ role: m.role, content: m.content })),
            days,
          }),
        });

        const data = (await resp.json()) as ApiResponse;

        if (!resp.ok || data.error) {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: `请求失败：${data.error ?? resp.statusText}`, isError: true },
          ]);
        } else {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: data.answer ?? "", sources: data.sources },
          ]);
        }
      } catch (e: unknown) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `网络错误：${e instanceof Error ? e.message : String(e)}`,
            isError: true,
          },
        ]);
      } finally {
        setLoading(false);
        setTimeout(() => textareaRef.current?.focus(), 50);
      }
    },
    [messages, loading, days],
  );

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  // hash 路由：#/feishu-raw-sales-data 切换到原始数据查看器（历史路径保留）
  // #/sales-dashboard 销售驾驶舱（新增）；#/lingxing-sales-data 旧明细页（保留不删）
  const [currentPage, setCurrentPage] = useState(() => {
    if (window.location.hash === "#/feishu-raw-sales-data") return "feishu-raw:<REDACTED_FEISHU_SHEET_ID>";
    if (window.location.hash === "#/lingxing-sales-data") return "lingxing-sales";
    if (window.location.hash === "#/sales-dashboard") return "sales-dashboard";
    if (window.location.hash === "#/business-analysis") return "business-analysis";
    if (window.location.hash.startsWith("#/help")) return "help";
    if (window.location.hash.startsWith("#/hr-performance")) return "hr-performance";
    if (window.location.hash.startsWith("#/attendance")) return "attendance";
    if (window.location.hash.startsWith("#/pmc/wfs-fee")) return "pmc-wfs-fee";
    if (window.location.hash.startsWith("#/pmc/storage-fee")) return "pmc-storage-fee";
    if (window.location.hash.startsWith("#/pmc/inbound-freight")) return "pmc-inbound-freight";
    if (window.location.hash.startsWith("#/profit/order-v2")) return "profit:order-v2";
    if (window.location.hash.startsWith("#/sales-detail-v2")) return "sales-detail-v2";
    // 2026-08-12 §9：AI财务子tab独立hash后缀（#/finance/<子键>，如 #/finance/credits）
    if (window.location.hash.startsWith("#/finance/")) return "finance:" + window.location.hash.slice("#/finance/".length).split("?")[0];
    // 2026-08-12 §9：广告系统子tab独立hash后缀（#/ads/<子键>，如 #/ads/sem-upload）
    if (window.location.hash.startsWith("#/ads/")) return "ads:" + window.location.hash.slice("#/ads/".length);
    return "chat";
  });

  function navTo(page: string) {
    setCurrentPage(page);
    const b = page.split(/[:#]/)[0];
    window.location.hash =
      b === "feishu-raw" ? "#/feishu-raw-sales-data"
      : b === "lingxing-sales" ? "#/lingxing-sales-data"
      : b === "sales-dashboard" ? "#/sales-dashboard"
      : b === "business-analysis" ? "#/business-analysis"
      : b === "help" ? (window.location.hash.startsWith("#/help") ? window.location.hash : "#/help") // 2026-08-18 修复：保留 ?page= 直达参数，各页"?"跳帮助能定位到本页文章
      : b === "hr-performance" ? "#/hr-performance"
      : b === "attendance" ? "#/attendance"
      : b === "pmc-wfs-fee" ? "#/pmc/wfs-fee"
      : b === "pmc-storage-fee" ? "#/pmc/storage-fee"
      : b === "pmc-inbound-freight" ? "#/pmc/inbound-freight"
      : b === "sales-detail-v2" ? "#/sales-detail-v2"
      : b === "profit" ? "#/profit/" + (page.split(":")[1] ?? "")
      : b === "ads" ? "#/ads/" + (page.split(":")[1] ?? "")
      : b === "finance" ? "#/finance/" + (page.split(":")[1] ?? "")
      : "";
  }

  // 2026-08-20 §2：iframe 子页（asin-kw-mvp :3000）的「帮助」按钮跨窗跳转到外壳帮助中心。
  // 子页发 postMessage({type:"lx-nav-help", page:"<page_key>"})，外壳收到后跳 #/help?page=<page_key>。
  // 安全约束：① 只认 :3000 这一个来源，其余 origin 一律忽略；② 只认这一种 type，不提供任何其它跨窗指令；
  //          ③ page_key 走字符白名单，非法值直接丢弃（不做导航、不进 URL）。
  // 2026-08-21 修复：白名单原为 /^[a-z0-9-]{1,64}$/，**漏了下划线**。批1 时页面 key 恰好全是连字符
  //   （ads-sem-data / ads-sbsv-data）所以没暴露；批2 的四个 key 是历史下划线命名
  //   （ads_period_agg / ads_auto / ads_manual / ads_import_tasks），被这条正则静默丢弃，
  //   表现为"点帮助没反应、也不报错"。dim_page_help.page_key 全表实际用的就是 [a-z0-9_-]，故补上下划线。
  //   origin 与 type 两道校验**不动**（本次故障与来源无关，AppShell 九个入口实测都是 :3000）。
  useEffect(() => {
    const ALLOW_ORIGIN = "http://42.193.254.170:3000";
    const onMsg = (ev: MessageEvent) => {
      if (ev.origin !== ALLOW_ORIGIN) return;
      const d = ev.data as { type?: string; page?: string } | null;
      if (!d || typeof d !== "object" || d.type !== "lx-nav-help") return;
      const key = String(d.page ?? "");
      if (!/^[a-z0-9_-]{1,64}$/.test(key)) {
        // 2026-08-21：这条 warn 是本次故障的直接教训——上一版被白名单丢掉的消息**完全无声**，
        // 表现为"点了没反应也不报错"，只能靠读码才发现。现在起被拒的 lx-nav-help 一律留痕，便于下次一眼定位。
        console.warn("[lx-nav-help] page_key 不合法，已丢弃：", key);
        return;
      }
      window.location.hash = `#/help?page=${key}`;
      navTo("help");
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 内容分发（统一在 AppShell 外壳内渲染；旧全屏页顶栏去掉，导航归壳）──
  useEffect(() => {
    void fetch("/api/auth/me", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setIsSuperadmin(Boolean(d.is_superadmin)); })
      .catch(() => undefined);
  }, []);

  const base = currentPage.split(/[:#]/)[0];
  const sub = currentPage.includes(":") ? currentPage.split(":")[1] : "";
  let content: React.ReactNode;
  if (base === "sales-dashboard") content = <SalesDashboard />;
  else if (base === "feishu-raw") content = <FeishuRawSalesData key={sub || "<REDACTED_FEISHU_SHEET_ID>"} initialTab={sub || undefined} embedded onNavigate={navTo} />;
  else if (base === "business-analysis") content = <BusinessAnalysis />;
  else if (base === "lingxing-sales") content = <LingxingSalesData />;
  else if (base === "hr-performance") content = <HrPerformance key={currentPage.includes("#review") ? "review" : "ledger"} embedded initialTab={currentPage.includes("#review") ? "review" : "ledger"} />;
  else if (base === "attendance") content = <Attendance onNavigate={navTo} />;
  else if (base === "help") content = <HelpCenter onNavigate={navTo} />;
  else if (base === "meeting") content = <MeetingAnalysis />;
  else if (base === "llm") content = <iframe title="LLM 模型切换" src="http://42.193.254.170:3456/" style={{ width: "100%", height: "100%", border: "none" }} />;
  else if (currentPage === "ads:fee-report") content = <AdsFeeReport onNavigate={navTo} />; // 2026-08-19 广告费用报表（native，须在 ads iframe 分支之前）
  else if (currentPage === "ads:bill-fee") content = <AdsBillFee onNavigate={navTo} />; // 2026-08-19 广告账单扣费（native，须在 ads iframe 分支之前）
  else if (base === "ads") content = <iframe title="广告系统" src={MOD_BY_KEY[currentPage]?.url || "http://42.193.254.170:3000/walmart-ads-data"} style={{ width: "100%", height: "100%", border: "none" }} />;
  else if (base === "roster") content = <RosterAdmin onNavigate={navTo} />;
  else if (base === "api-doc") content = <ApiDocPage onNavigate={navTo} />;
  else if (base === "monthly-plan") content = <MonthlyPlanPanel onNavigate={navTo} />;
  else if (base === "pmc-inventory") content = <PmcInventoryOverview onNavigate={navTo} />;
  else if (base === "pmc-wfs-fee") content = <PmcWfsFeeCase onNavigate={navTo} />;
  else if (base === "pmc-storage-fee") content = <PmcFeeDetail key="storage" kind="storage" onNavigate={navTo} />;
  else if (base === "pmc-inbound-freight") content = <PmcFeeDetail key="inbound" kind="inbound" onNavigate={navTo} />;
  else if (currentPage === "finance:credits") content = <AiFinanceCredits onNavigate={navTo} />;
  else if (currentPage === "finance:tools") content = <AiFinanceTools onNavigate={navTo} />;
  else if (currentPage === "finance:item-cash-profit") content = <AiFinanceItemCashProfit onNavigate={navTo} />;
  else if (currentPage === "finance:item-cash-profit-v2") content = <AiFinanceItemCashProfitV2 onNavigate={navTo} />;
  else if (currentPage === "profit:order-v2") content = <OrderProfitV2 onNavigate={navTo} />;
  else if (currentPage === "sales-detail-v2") content = <SalesDetailV2 onNavigate={navTo} />;
  else if (MOD_BY_KEY[currentPage] && MOD_BY_KEY[currentPage].type === "placeholder") content = (
    <div style={{ display: "grid", placeItems: "center", height: "100%", color: "#9aa0a6", fontSize: 15, textAlign: "center", padding: 40, lineHeight: 1.8 }}>
      「{MOD_BY_KEY[currentPage].label}」建设中<br />后端 / 数据已就绪，前端待开发
    </div>
  );
  else content = (
    <div style={{ ...S.root, height: "100%" }}>
      <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10, padding: "10px 2px" }}>
        <span style={{ fontSize: 13, color: "#5f6368" }}>数据范围</span>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} style={{ border: "1px solid #dadce0", borderRadius: 8, padding: "5px 10px", fontSize: 13, background: "#fff" }}>
          <option value={3}>3 天</option>
          <option value={7}>7 天</option>
          <option value={14}>14 天</option>
          <option value={30}>30 天</option>
        </select>
        {messages.length > 0 && (
          <button style={{ border: "1px solid #dadce0", background: "#fff", color: "#5f6368", padding: "5px 12px", borderRadius: 8, fontSize: 12, cursor: "pointer" }} onClick={() => setMessages([])}>清空</button>
        )}
      </div>
      <main style={S.main}>
        {messages.length === 0 ? (
          <div style={S.welcome}>
            <div style={{ fontSize: 56 }}>🤖</div>
            <h2 style={S.welcomeTitle}>你好，管理员</h2>
            <p style={S.welcomeDesc}>我可以帮你分析店铺销量、广告效果、利润和产品问题</p>
            <div style={S.quickGrid}>
              {QUICK_QUESTIONS.map((q, i) => (
                <button key={i} style={S.quickBtn} onClick={() => sendMessage(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} style={msg.role === "user" ? S.userRow : S.aiRow}>
              {msg.role === "assistant" && <div style={S.avatarAI}>AI</div>}
              <div
                style={{
                  ...(msg.role === "user" ? S.userBubble : S.aiBubble),
                  ...(msg.isError ? S.errorBubble : {}),
                }}
              >
                {msg.role === "user" ? (
                  <div style={{ whiteSpace: "pre-wrap" }}>{msg.content}</div>
                ) : (
                  <div style={{ lineHeight: 1.65 }}>{renderMarkdown(msg.content)}</div>
                )}
                {msg.sources && msg.sources.length > 0 && (
                  <div style={S.sourcesRow}>
                    <span style={{ fontSize: 11, color: "#94a3b8" }}>数据来源：</span>
                    {msg.sources.map((s, j) => (
                      <span key={j} style={S.sourceTag}>{s}</span>
                    ))}
                  </div>
                )}
              </div>
              {msg.role === "user" && <div style={S.avatarUser}>我</div>}
            </div>
          ))
        )}

        {loading && (
          <div style={S.aiRow}>
            <div style={S.avatarAI}>AI</div>
            <div style={S.aiBubble}>
              <div style={{ display: "flex", gap: 5, padding: "4px 0" }}>
                <span className="dot" />
                <span className="dot" />
                <span className="dot" />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </main>

      <footer style={S.footer}>
        <div style={S.inputRow}>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入问题，按 Enter 发送 · Shift+Enter 换行"
            style={S.textarea}
            rows={2}
            disabled={loading}
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || loading}
            style={{
              ...S.sendBtn,
              opacity: !input.trim() || loading ? 0.5 : 1,
              cursor: !input.trim() || loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "分析中..." : "发送"}
          </button>
        </div>
      </footer>
    </div>
  );

  // 2026-08-20 旧版页面权限闸门（覆盖式，置于整条渲染链之后；
  // 教训：此前写成链中独立 if，截断了 else-if 链导致所有页面兜底成AI助手页 —— 禁止在 if/else 链中间插独立 if）
  if (SUPERADMIN_ONLY_KEYS.has(currentPage) && !isSuperadmin) {
    content = (
      <div style={{ display: "grid", placeItems: "center", height: "100%", color: "#9aa0a6", fontSize: 15, textAlign: "center", padding: 40, lineHeight: 1.8 }}>
        该页面已限制为超级管理员可见<br />
        <span style={{ fontSize: 13 }}>请使用「订单利润 V2」或「每日销售明细 V2」</span>
      </div>
    );
  }

  return (
    <AppShell activeKey={currentPage} onNavigate={navTo}>
      {content}
    </AppShell>
  );
}

// ── 样式 ──────────────────────────────────────────────────────────────────────

const S: Record<string, React.CSSProperties> = {
  root: {
    display: "flex",
    flexDirection: "column",
    height: "100vh",
    overflow: "hidden",
  },
  header: {
    background: "linear-gradient(135deg, #1e1b4b 0%, #312e81 100%)",
    color: "white",
    padding: "14px 24px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    boxShadow: "0 2px 12px rgba(0,0,0,0.25)",
    flexShrink: 0,
    zIndex: 10,
  },
  headerLeft: { display: "flex", alignItems: "center", gap: 12 },
  headerTitle: { fontSize: 17, fontWeight: 700, letterSpacing: "-0.3px" },
  headerSub: { fontSize: 12, opacity: 0.65, marginTop: 2 },
  headerRight: { display: "flex", alignItems: "center", gap: 10 },
  select: {
    background: "rgba(255,255,255,0.12)",
    border: "1px solid rgba(255,255,255,0.25)",
    color: "white",
    padding: "5px 10px",
    borderRadius: 8,
    fontSize: 13,
    cursor: "pointer",
    outline: "none",
  },
  clearBtn: {
    background: "rgba(255,255,255,0.12)",
    border: "1px solid rgba(255,255,255,0.25)",
    color: "rgba(255,255,255,0.8)",
    padding: "5px 12px",
    borderRadius: 8,
    fontSize: 12,
    cursor: "pointer",
  },
  main: {
    flex: 1,
    overflowY: "auto",
    padding: "24px 20px",
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  welcome: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    flex: 1,
    gap: 12,
    padding: "40px 20px",
    textAlign: "center",
  },
  welcomeTitle: { fontSize: 22, color: "#1e1b4b", fontWeight: 700 },
  welcomeDesc: { color: "#64748b", fontSize: 14 },
  quickGrid: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    width: "100%",
    maxWidth: 560,
    marginTop: 8,
  },
  quickBtn: {
    background: "white",
    border: "1px solid #e2e8f0",
    borderRadius: 10,
    padding: "11px 16px",
    cursor: "pointer",
    textAlign: "left",
    fontSize: 14,
    color: "#374151",
    transition: "all 0.15s",
    boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
  },
  userRow: {
    display: "flex",
    justifyContent: "flex-end",
    alignItems: "flex-start",
    gap: 10,
  },
  aiRow: {
    display: "flex",
    justifyContent: "flex-start",
    alignItems: "flex-start",
    gap: 10,
  },
  avatarAI: {
    width: 36,
    height: 36,
    background: "linear-gradient(135deg, #4f46e5, #7c3aed)",
    color: "white",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 11,
    fontWeight: 700,
    flexShrink: 0,
    boxShadow: "0 2px 8px rgba(79,70,229,0.35)",
  },
  avatarUser: {
    width: 36,
    height: 36,
    background: "#0ea5e9",
    color: "white",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 11,
    fontWeight: 700,
    flexShrink: 0,
  },
  userBubble: {
    maxWidth: "70%",
    background: "#0ea5e9",
    color: "white",
    padding: "10px 16px",
    borderRadius: "18px 4px 18px 18px",
    fontSize: 14,
    lineHeight: 1.65,
    boxShadow: "0 2px 8px rgba(14,165,233,0.3)",
  },
  aiBubble: {
    maxWidth: "80%",
    background: "white",
    padding: "12px 16px",
    borderRadius: "4px 18px 18px 18px",
    fontSize: 14,
    lineHeight: 1.65,
    boxShadow: "0 1px 6px rgba(0,0,0,0.08)",
    color: "#1e293b",
  },
  errorBubble: {
    background: "#fff5f5",
    color: "#dc2626",
    border: "1px solid #fecaca",
  },
  sourcesRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 4,
    marginTop: 10,
    alignItems: "center",
  },
  sourceTag: {
    background: "#f1f5f9",
    color: "#64748b",
    fontSize: 11,
    padding: "2px 8px",
    borderRadius: 10,
    border: "1px solid #e2e8f0",
  },
  footer: {
    background: "white",
    padding: "14px 20px",
    boxShadow: "0 -2px 12px rgba(0,0,0,0.06)",
    flexShrink: 0,
  },
  inputRow: {
    display: "flex",
    gap: 10,
    alignItems: "flex-end",
  },
  textarea: {
    flex: 1,
    resize: "none",
    border: "1.5px solid #e2e8f0",
    borderRadius: 12,
    padding: "10px 14px",
    fontSize: 14,
    outline: "none",
    fontFamily: "inherit",
    lineHeight: 1.5,
    color: "#1e293b",
    background: "#f8fafc",
    transition: "border-color 0.2s",
  },
  sendBtn: {
    background: "linear-gradient(135deg, #4f46e5, #7c3aed)",
    color: "white",
    border: "none",
    padding: "0 24px",
    borderRadius: 12,
    fontSize: 14,
    fontWeight: 600,
    flexShrink: 0,
    height: 58,
    boxShadow: "0 2px 8px rgba(79,70,229,0.35)",
    transition: "opacity 0.15s",
  },
};
