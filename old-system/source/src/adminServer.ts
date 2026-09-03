/**
 * adminServer.ts — Admin 后台聚合入口（运营数据中台）
 *
 * 启动：npm run admin:server（= npx ts-node src/adminServer.ts）；生产 systemd lingxing-admin
 * 端口：3001（ADMIN_SERVER_PORT 可覆盖）；静态托管 admin-frontend/dist/
 *
 * 职责：统一登录/鉴权网关（authMiddleware，app_session JWT）+ 挂载全部业务路由：
 *   销售明细/产品管理/运营日志(feishuRawSalesRoutes)、经营分析/月度规划(aiBusinessRoutes)、
 *   清货中心(clearanceCenterRoutes)、AI人力(hrRoutes/attendanceRoutes/rosterRoutes)、
 *   帮助中心(helpRoutes)、API文档(apiDocRoutes)、飞书卡片回调(feishuCardCallbackRoutes)、
 *   internal-readonly 只读API(internalReadonlyApi)、AI问答(/api/chat) 等。
 * 模块↔路由↔表 权威对照见 context/SYSTEM_MAP.md「模块视图」。
 * （历史注：本文件早期仅为"AI 问答后端"，已演进为聚合入口；2026-07-31 更新此注释。）
 */

import "dotenv/config";
import express, { Request, Response } from "express";
import path from "path";
import { fetchDataForQuestion } from "./adminDataFetcher";
import aiBusinessRoutes from "./aiBusinessRoutes";
import clearanceCenterRoutes from "./clearanceCenterRoutes";
import pmcRoutes from "./pmcRoutes";
import pmcInventoryRoutes from "./pmcInventoryRoutes";
import pmcWfsFeeRoutes from "./pmcWfsFeeRoutes";
import pmcFeeDetailRoutes from "./pmcFeeDetailRoutes";
import aiFinanceRoutes from "./aiFinanceRoutes";
import adsFeeReportRoutes from "./adsFeeReportRoutes"; // 2026-08-19 广告费用报表（财务月度取数，隔离只读模块）
import aiFinanceIcpV2Routes from "./aiFinanceIcpV2Routes"; // 批13 单品现金利润v2（按店铺+ITEMID，隔离新接口）
import orderProfitV2Routes from "./orderProfitV2Routes"; // 批3a 订单利润V2 一次查询（隔离新路由，旧Beta零改动）
import salesDetailV2Routes from "./salesDetailV2Routes"; // 批C-1 每日销售明细V2（FACT层，服务端分页）
import feishuCardCallbackRoutes from "./feishuCardCallbackRoutes";
import feishuRawSalesRoutes from "./feishuRawSalesRoutes";
import helpRoutes from "./helpRoutes";
import hrRoutes from "./hrRoutes";
import attendanceRoutes from "./attendanceRoutes";
import internalReadonlyApi from "./internalReadonlyApi";
import lingxingSalesRoutes from "./lingxingSalesRoutes";
import authRoutes from "./authRoutes";
import rosterRoutes from "./rosterRoutes";
import apiDocRoutes from "./apiDocRoutes";
import { resolveUser } from "./authMiddleware";

const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;

// ── 配置 ─────────────────────────────────────────────────────────────────────

const PORT = Number(process.env.ADMIN_SERVER_PORT ?? 3001);
const AI_BASE_URL = (process.env.AI_BASE_URL ?? "https://api.tokensea.world/v1").replace(/\/$/, "");
const AI_API_KEY = process.env.AI_API_KEY ?? "";
const AI_MODEL = process.env.AI_MODEL ?? "gpt-5.5";
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD ?? "";

if (!AI_API_KEY) {
  console.warn("[server] ⚠️  AI_API_KEY 未配置，AI 问答将失败");
}

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

interface ChatRequestBody {
  messages: ChatMessage[];
  days?: number;
}

// ── AI 调用 ───────────────────────────────────────────────────────────────────

async function callAI(messages: ChatMessage[], maxRetries = 2): Promise<string> {
  let lastError: unknown;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    if (attempt > 0) {
      const delay = attempt * 3000;
      console.log(`[chat] AI 重试 ${attempt}/${maxRetries}，等待 ${delay / 1000}s...`);
      await new Promise((r) => setTimeout(r, delay));
    }

    try {
      const resp = await axios.post(
        `${AI_BASE_URL}/chat/completions`,
        { model: AI_MODEL, messages, temperature: 0.3, max_tokens: 2048 },
        {
          headers: {
            Authorization: `Bearer ${AI_API_KEY}`,
            "Content-Type": "application/json",
          },
          timeout: 90000,
        },
      );

      const data = resp.data as {
        choices?: Array<{ message?: { content?: string } }>;
        error?: { message?: string };
      };

      if (data.error) throw new Error(`AI API 错误: ${data.error.message}`);

      const content = data.choices?.[0]?.message?.content?.trim() ?? "";
      if (!content) {
        lastError = new Error("AI 返回内容为空");
        continue; // 空内容也重试
      }

      return content;
    } catch (e: unknown) {
      lastError = e;
      const msg = e instanceof Error ? e.message : String(e);
      console.warn(`[chat] AI 请求失败 (attempt ${attempt + 1}): ${msg}`);
    }
  }

  throw lastError ?? new Error("AI 请求失败");
}

// ── Express 应用 ──────────────────────────────────────────────────────────────

const app = express();
app.use(express.json({ limit: "10mb" }));

// ── 内部只读 API：Bearer Token 鉴权，仅允许 GET 查询 ───────────────────────────

app.use("/", internalReadonlyApi);
app.use("/api/internal-readonly", internalReadonlyApi);

// ── 飞书卡片回调：位于 Basic Auth 之前（飞书服务器直连），安全依赖验签 ─────────

app.use("/api/feishu-card-callback", feishuCardCallbackRoutes);

// ── 应用登录接口（公开于网关之前）─────────────────────────────────────────────
app.use("/api/auth", authRoutes);

// ── 全站登录网关（Phase 2a，AUTH_ENABLED=1 启用；关闭时同现状；取代原 Basic Auth）──

const AUTH_ENABLED = process.env.AUTH_ENABLED === "1";
const LOGIN_PAGE = path.join(__dirname, "../admin-frontend/dist/login.html");

app.get(["/login", "/login.html"], (_req: Request, res: Response) => {
  res.sendFile(LOGIN_PAGE);
});

if (AUTH_ENABLED) {
  app.use(async (req: Request, res: Response, next: () => void) => {
    const p = req.path;
    // 放行：登录接口 / 登录页 / favicon（internal-readonly、飞书回调已在上方各自鉴权）
    if (p === "/login" || p === "/login.html" || p.startsWith("/api/auth/") || p === "/favicon.ico") { next(); return; }
    if (await resolveUser(req)) { next(); return; }
    if (p.startsWith("/api/")) { res.status(401).json({ error: "未登录或登录已失效" }); return; }
    res.redirect(302, "/login.html");
  });
}

// ── 接口：健康检查 ─────────────────────────────────────────────────────────────

app.get("/api/status", (_req: Request, res: Response) => {
  res.json({ ok: true, time: new Date().toISOString(), model: AI_MODEL });
});

// ── 接口：AI 问答 ──────────────────────────────────────────────────────────────

app.post("/api/chat", async (req: Request, res: Response): Promise<void> => {
  try {
    const { messages, days } = req.body as ChatRequestBody;

    if (!Array.isArray(messages) || messages.length === 0) {
      res.status(400).json({ error: "messages 不能为空" });
      return;
    }

    const latestQuestion = messages[messages.length - 1]?.content ?? "";
    console.log(`\n[chat] ▶ 问题: ${latestQuestion.slice(0, 100)}`);

    // 1. 拉取飞书数据
    const context = await fetchDataForQuestion(latestQuestion, days ?? 7);
    console.log(`[chat] 数据源: ${context.sources.join(", ") || "无"}`);

    // 2. 构建 AI Prompt
    const today = new Date().toISOString().slice(0, 10);
    const systemPrompt = [
      `你是一个跨境电商数据分析助手，专门分析沃尔玛店铺运营数据。`,
      `今日日期（服务器北京时间参考）：${today}`,
      ``,
      `回答要求：`,
      `- 用中文回答，简洁直接`,
      `- 有具体数字和洞察，不泛泛而谈`,
      `- 如果数据中没有相关信息，直接说明`,
      `- 如有明显异常（ACOS 过高、负利润、库存告急等），主动指出`,
      ``,
      `以下是从飞书实时读取的数据（数据源：${context.sources.join("、") || "无"}）：`,
      ``,
      context.markdown || "（当前未获取到有效数据）",
    ].join("\n");

    const aiMessages: ChatMessage[] = [
      { role: "system", content: systemPrompt },
      // 保留最近 10 条对话历史（含当前问题）
      ...messages.slice(-10),
    ];

    // 3. 调用 AI
    const answer = await callAI(aiMessages);
    console.log(`[chat] ✅ 回答长度: ${answer.length} 字`);

    res.json({ answer, sources: context.sources });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("[chat] ❌ 错误:", msg);
    res.status(500).json({ error: msg });
  }
});

// ── 路由：飞书原始数据 API ─────────────────────────────────────────────────────

app.use("/api/feishu-raw-sales", feishuRawSalesRoutes);
app.use("/api/clearance-center", clearanceCenterRoutes); // 2026-07-20 批② 清货中心（隔离新模块）
app.use("/api/pmc", pmcRoutes); // 2026-07-21 批④ AI智能PMC（隔离新模块）
app.use("/api/pmc/inventory", pmcInventoryRoutes); // 2026-08-02 智能PMC·库存一览表（隔离新模块，只读；挂 /api/pmc/ 下复用现有 nginx 代理）
app.use("/api/pmc/wfs-fee", pmcWfsFeeRoutes); // 2026-08-12 智能PMC·WFS费用异常跟进（隔离新模块）
app.use("/api/pmc/fee-detail", pmcFeeDetailRoutes); // 2026-08-18 智能PMC·仓储费/入库运输明细（隔离新模块，只读）
app.use("/api/finance/ads-fee", adsFeeReportRoutes); // 2026-08-19 广告费用报表（隔离只读模块；更具体先挂，复用 /api/finance nginx 代理）
app.use("/api/finance", aiFinanceRoutes); // 2026-08-12 AI财务系统 批1（隔离新模块，只读；新顶层前缀需nginx代理，部署单含核查步骤）
app.use("/api/finance", aiFinanceIcpV2Routes); // 2026-08-14 批13：仅新增 /item-cash-profit-v2，旧路由零改动
app.use("/api/profit-v2", orderProfitV2Routes); // 2026-08-18 批3a：订单利润V2，仅新增路由
app.use("/api/sales-detail-v2", salesDetailV2Routes); // 2026-08-19 批C-1：每日销售明细V2，仅新增路由
app.use("/api/help", helpRoutes); // 2026-07-20 帮助中心+下载权限（隔离新模块）
app.use("/api/hr/attendance", attendanceRoutes); // 2026-07-29 考勤(权限hr_attendance,更具体先挂)
app.use("/api/hr", hrRoutes); // 2026-07-22 AI智能人事系统 V1（隔离新模块）
app.use("/api/lingxing-sales", lingxingSalesRoutes);
app.use("/api/ai-business", aiBusinessRoutes);
app.use("/api/roster", rosterRoutes); // 2026-07-27 批4 花名册·角色管理
app.use("/api/api-doc", apiDocRoutes); // 2026-07-27 内部 API 接口文档（超管+白名单门控）

// ── /api 兜底：未命中的 API 路径返回 404 JSON，不落 SPA fallback ───────────────

app.use("/api", (_req: Request, res: Response) => {
  res.status(404).json({ error: "接口不存在" });
});

// ── 静态文件：React 前端 ───────────────────────────────────────────────────────

const FRONTEND_DIST = path.join(__dirname, "../admin-frontend/dist");
app.use(express.static(FRONTEND_DIST));

// SPA fallback
app.use((_req: Request, res: Response) => {
  res.sendFile(path.join(FRONTEND_DIST, "index.html"));
});

// ── 启动 ──────────────────────────────────────────────────────────────────────

app.listen(PORT, "0.0.0.0", () => {
  console.log(`✅ Admin 服务器已启动: http://0.0.0.0:${PORT}`);
  console.log(`   AI 模型: ${AI_MODEL}`);
  console.log(`   前端目录: ${FRONTEND_DIST}`);
});
