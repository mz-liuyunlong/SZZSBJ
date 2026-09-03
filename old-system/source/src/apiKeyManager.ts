/**
 * apiKeyManager.ts - API Key 管理页面
 *
 * 启动：npx ts-node src/apiKeyManager.ts
 * 访问：http://服务器IP:3456
 *
 * 功能：
 *   - 查看当前服务器 .env 中的 AI 配置
 *   - 保存多套 API Key 配置（存 config/apiKeyProfiles.json）
 *   - 测试 API Key 是否可用（后端转发，避免 CORS）
 *   - 一键切换：写入 .env 并立即生效（下次 cron 任务自动使用新 Key）
 *
 * 安全：复用主后台登录（app_session cookie 验签+查库），仅放行 LLM_MANAGER_ALLOW（默认陈佳聪）；无独立密码
 */

import "dotenv/config";
import * as http from "http";
import * as fs from "fs";
import * as path from "path";
import axios from "axios";
import * as mysql from "mysql2/promise";

const PORT = Number(process.env.API_KEY_MANAGER_PORT ?? 3456);
const ENV_FILE = path.resolve(process.cwd(), ".env");
const PROFILES_FILE = path.resolve(process.cwd(), "config/apiKeyProfiles.json");

// ── 访问控制：复用主后台登录（app_session cookie），仅放行指定人（默认陈佳聪）──
// eslint-disable-next-line @typescript-eslint/no-var-requires
const jwt = require("jsonwebtoken");
const COOKIE_NAME = "app_session";
const ALLOW_USERS = (process.env.LLM_MANAGER_ALLOW ?? "陈佳聪").split(",").map((x) => x.trim()).filter(Boolean);
function authDbConfig(): mysql.ConnectionOptions {
  return { host: process.env.DB_HOST ?? "127.0.0.1", port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "", password: process.env.DB_PASSWORD ?? "", database: process.env.DB_NAME ?? "walmart_ai_data" };
}
function parseCookie(req: http.IncomingMessage, name: string): string {
  const raw = req.headers.cookie ?? "";
  for (const part of raw.split(";")) {
    const idx = part.indexOf("=");
    if (idx > 0 && part.slice(0, idx).trim() === name) return decodeURIComponent(part.slice(idx + 1).trim());
  }
  return "";
}
interface AdminUser { username: string; displayName: string; isSuperadmin: boolean; }
async function resolveAdminUser(req: http.IncomingMessage): Promise<AdminUser | null> {
  const token = parseCookie(req, COOKIE_NAME);
  if (!token) return null;
  const secret = (process.env.AUTH_JWT_SECRET ?? "").trim();
  if (!secret) return null;
  let payload: { uid?: number; tv?: number } | null = null;
  try { payload = jwt.verify(token, secret); } catch { return null; }
  if (!payload || !payload.uid) return null;
  let db: mysql.Connection | null = null;
  try {
    db = await mysql.createConnection(authDbConfig());
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT username, display_name, is_active, is_superadmin, token_version FROM dim_app_user WHERE id = ? LIMIT 1", [payload.uid]);
    const u = rows[0];
    if (!u || !u.is_active || Number(u.token_version) !== Number(payload.tv)) return null;
    return { username: String(u.username ?? ""), displayName: String(u.display_name ?? ""), isSuperadmin: !!u.is_superadmin };
  } catch { return null; } finally { if (db) await db.end().catch(() => undefined); }
}
function isAllowedUser(u: AdminUser | null): boolean {
  if (!u) return false;
  return ALLOW_USERS.indexOf(u.username) >= 0 || ALLOW_USERS.indexOf(u.displayName) >= 0;
}
/** 网关：非授权直接 403，返回是否放行 */
async function requireAllowed(req: http.IncomingMessage, res: http.ServerResponse): Promise<boolean> {
  const u = await resolveAdminUser(req);
  if (!isAllowedUser(u)) { json(res, { error: "无权限：仅限 " + ALLOW_USERS.join("/") + " 使用" }, 403); return false; }
  return true;
}

interface ApiKeyProfile {
  name: string;
  baseUrl: string;
  model: string;
  apiKey: string;
  note: string;
  createdAt: string;
}

// ── .env 读写 ──────────────────────────────────────────────────────────

function readEnvFile(): Record<string, string> {
  try {
    const content = fs.readFileSync(ENV_FILE, "utf8");
    const result: Record<string, string> = {};
    for (const line of content.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const idx = trimmed.indexOf("=");
      if (idx < 0) continue;
      result[trimmed.slice(0, idx).trim()] = trimmed.slice(idx + 1).trim();
    }
    return result;
  } catch {
    return {};
  }
}

function updateEnvKey(key: string, value: string): void {
  let content = fs.existsSync(ENV_FILE) ? fs.readFileSync(ENV_FILE, "utf8") : "";
  const lines = content.split("\n");
  const idx = lines.findIndex((l) => l.trim().startsWith(`${key}=`) || l.trim() === key);
  if (idx >= 0) {
    lines[idx] = `${key}=${value}`;
  } else {
    lines.push(`${key}=${value}`);
  }
  fs.writeFileSync(ENV_FILE, lines.join("\n"), "utf8");
}

function maskKey(key: string): string {
  if (!key) return "（未配置）";
  if (key.length <= 12) return "***";
  return key.slice(0, 6) + "****" + key.slice(-4);
}

// ── Profiles 读写 ──────────────────────────────────────────────────────

function loadProfiles(): ApiKeyProfile[] {
  try {
    return JSON.parse(fs.readFileSync(PROFILES_FILE, "utf8")) as ApiKeyProfile[];
  } catch {
    return [];
  }
}

function saveProfiles(profiles: ApiKeyProfile[]): void {
  fs.mkdirSync(path.dirname(PROFILES_FILE), { recursive: true });
  fs.writeFileSync(PROFILES_FILE, JSON.stringify(profiles, null, 2), "utf8");
}

// ── AI 测试 ────────────────────────────────────────────────────────────

async function testApiKey(baseUrl: string, model: string, apiKey: string): Promise<{ ok: boolean; latencyMs: number; message: string }> {
  const start = Date.now();
  try {
    const url = baseUrl.replace(/\/$/, "") + "/chat/completions";
    const resp = await axios.post(
      url,
      { model, messages: [{ role: "user", content: "reply with the single word: ok" }], max_tokens: 10 },
      { headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" }, timeout: 15000 },
    );
    const latencyMs = Date.now() - start;
    const content = (resp.data as any)?.choices?.[0]?.message?.content ?? "";
    return { ok: true, latencyMs, message: `✅ 可用  响应: "${content.trim()}"  延迟: ${latencyMs}ms` };
  } catch (e: any) {
    const latencyMs = Date.now() - start;
    const msg = e?.response?.data?.error?.message ?? e?.message ?? String(e);
    return { ok: false, latencyMs, message: `❌ 失败  ${msg}` };
  }
}

// ── HTTP 路由 ──────────────────────────────────────────────────────────

function readBody(req: http.IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => resolve(body));
  });
}

function json(res: http.ServerResponse, data: unknown, status = 200): void {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(data));
}

async function handleRequest(req: http.IncomingMessage, res: http.ServerResponse): Promise<void> {
  const url = new URL(req.url ?? "/", `http://localhost`);
  const pathname = url.pathname;
  const method = req.method ?? "GET";

  // CORS
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS");
  if (method === "OPTIONS") { res.writeHead(204); res.end(); return; }

  // 前端页面
  if (method === "GET" && pathname === "/") {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(HTML);
    return;
  }

  // GET /api/whoami - 前端判断当前登录人是否有权（不发 403，仅返回布尔）
  if (method === "GET" && pathname === "/api/whoami") {
    const u = await resolveAdminUser(req);
    json(res, { ok: isAllowedUser(u), name: u ? (u.displayName || u.username) : "", allow: ALLOW_USERS.join("/") });
    return;
  }

  // GET /api/status - 当前 .env 配置
  if (method === "GET" && pathname === "/api/status") {
    if (!(await requireAllowed(req, res))) return;
    const env = readEnvFile();
    json(res, {
      baseUrl: env.AI_BASE_URL ?? "",
      model: env.AI_MODEL ?? "",
      maskedKey: maskKey(env.AI_API_KEY ?? ""),
      aiEnabled: env.ENABLE_AI_DIAGNOSIS ?? "false",
    });
    return;
  }

  // GET /api/profiles
  if (method === "GET" && pathname === "/api/profiles") {
    if (!(await requireAllowed(req, res))) return;
    const profiles = loadProfiles().map((p) => ({ ...p, apiKey: maskKey(p.apiKey) }));
    json(res, profiles);
    return;
  }

  // POST /api/profiles - 新增
  if (method === "POST" && pathname === "/api/profiles") {
    if (!(await requireAllowed(req, res))) return;
    const body = JSON.parse(await readBody(req)) as Partial<ApiKeyProfile>;
    if (!body.name || !body.apiKey || !body.baseUrl || !body.model) {
      json(res, { error: "name / baseUrl / model / apiKey 不能为空" }, 400); return;
    }
    const profiles = loadProfiles();
    if (profiles.find((p) => p.name === body.name)) {
      json(res, { error: `配置名 "${body.name}" 已存在` }, 400); return;
    }
    profiles.push({ name: body.name, baseUrl: body.baseUrl, model: body.model, apiKey: body.apiKey, note: body.note ?? "", createdAt: new Date().toISOString() });
    saveProfiles(profiles);
    json(res, { ok: true });
    return;
  }

  // POST /api/profiles/update - 修改已存配置（apiKey 留空则保持不变）
  if (method === "POST" && pathname === "/api/profiles/update") {
    if (!(await requireAllowed(req, res))) return;
    const body = JSON.parse(await readBody(req)) as { name?: string; baseUrl?: string; model?: string; apiKey?: string; note?: string };
    if (!body.name) { json(res, { error: "缺少配置名" }, 400); return; }
    const profiles = loadProfiles();
    const prof = profiles.find((x) => x.name === body.name);
    if (!prof) { json(res, { error: `配置 "${body.name}" 不存在` }, 404); return; }
    if (body.baseUrl !== undefined && body.baseUrl.trim()) prof.baseUrl = body.baseUrl.trim();
    if (body.model !== undefined && body.model.trim()) prof.model = body.model.trim();
    if (body.note !== undefined) prof.note = body.note;
    if (body.apiKey && body.apiKey.trim()) prof.apiKey = body.apiKey.trim();
    saveProfiles(profiles);
    json(res, { ok: true, message: "已更新" });
    return;
  }

  // DELETE /api/profiles/:name
  if (method === "DELETE" && pathname.startsWith("/api/profiles/")) {
    if (!(await requireAllowed(req, res))) return;
    const name = decodeURIComponent(pathname.slice("/api/profiles/".length));
    const profiles = loadProfiles().filter((p) => p.name !== name);
    saveProfiles(profiles);
    json(res, { ok: true });
    return;
  }

  // POST /api/test - 测试某套配置
  if (method === "POST" && pathname === "/api/test") {
    if (!(await requireAllowed(req, res))) return;
    const body = JSON.parse(await readBody(req)) as { baseUrl?: string; model?: string; apiKey?: string; profileName?: string };
    let baseUrl = body.baseUrl ?? "";
    let model = body.model ?? "";
    let apiKey = body.apiKey ?? "";
    // 按名称测试时从 profiles 取真实 key
    if (body.profileName) {
      const p = loadProfiles().find((p) => p.name === body.profileName);
      if (!p) { json(res, { ok: false, message: "找不到该配置" }); return; }
      baseUrl = p.baseUrl; model = p.model; apiKey = p.apiKey;
    }
    // 测试当前服务器配置时
    if (!apiKey) {
      const env = readEnvFile();
      baseUrl = baseUrl || (env.AI_BASE_URL ?? ""); model = model || (env.AI_MODEL ?? ""); apiKey = env.AI_API_KEY ?? "";
    }
    const result = await testApiKey(baseUrl, model, apiKey);
    json(res, result);
    return;
  }

  // POST /api/env - 直接修改当前 .env AI 配置
  if (method === "POST" && pathname === "/api/env") {
    if (!(await requireAllowed(req, res))) return;
    const body = JSON.parse(await readBody(req)) as { baseUrl?: string; model?: string; apiKey?: string };
    if (body.baseUrl !== undefined) updateEnvKey("AI_BASE_URL", body.baseUrl);
    if (body.model !== undefined) updateEnvKey("AI_MODEL", body.model);
    if (body.apiKey && body.apiKey.trim()) updateEnvKey("AI_API_KEY", body.apiKey.trim());
    json(res, { ok: true, message: "已保存到 .env" });
    return;
  }

  // POST /api/switch - 切换到某套配置
  if (method === "POST" && pathname === "/api/switch") {
    if (!(await requireAllowed(req, res))) return;
    const body = JSON.parse(await readBody(req)) as { profileName: string };
    const p = loadProfiles().find((p) => p.name === body.profileName);
    if (!p) { json(res, { error: "找不到该配置" }, 404); return; }
    updateEnvKey("AI_BASE_URL", p.baseUrl);
    updateEnvKey("AI_MODEL", p.model);
    updateEnvKey("AI_API_KEY", p.apiKey);
    json(res, { ok: true, message: `已切换到 "${p.name}"，下次 cron 任务自动使用新 Key` });
    return;
  }

  res.writeHead(404); res.end("Not found");
}

// ── 前端 HTML ──────────────────────────────────────────────────────────

const HTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>API Key 管理器</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; }
  .container { max-width: 900px; margin: 0 auto; padding: 32px 20px; }
  h1 { font-size: 22px; font-weight: 700; color: #fff; margin-bottom: 4px; }
  .subtitle { color: #64748b; font-size: 13px; margin-bottom: 32px; }
  .card { background: #1e2130; border: 1px solid #2d3748; border-radius: 12px; padding: 24px; margin-bottom: 20px; }
  .card-title { font-size: 13px; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 16px; }
  .kv-grid { display: grid; grid-template-columns: 140px 1fr; gap: 8px 16px; align-items: center; }
  .kv-label { color: #64748b; font-size: 13px; }
  .kv-value { font-family: monospace; font-size: 13px; color: #e2e8f0; word-break: break-all; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
  .badge-green { background: #14532d; color: #4ade80; }
  .badge-red { background: #450a0a; color: #f87171; }
  .badge-gray { background: #1e293b; color: #94a3b8; }
  .btn { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 7px; font-size: 13px; font-weight: 500; cursor: pointer; border: none; transition: opacity .15s; }
  .btn:hover { opacity: .85; }
  .btn:disabled { opacity: .4; cursor: not-allowed; }
  .btn-primary { background: #3b82f6; color: #fff; }
  .btn-success { background: #16a34a; color: #fff; }
  .btn-danger { background: #dc2626; color: #fff; }
  .btn-ghost { background: #2d3748; color: #e2e8f0; }
  .btn-sm { padding: 4px 10px; font-size: 12px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; color: #64748b; font-weight: 500; padding: 8px 12px; border-bottom: 1px solid #2d3748; }
  td { padding: 10px 12px; border-bottom: 1px solid #1a2035; vertical-align: middle; }
  tr:last-child td { border-bottom: none; }
  .actions { display: flex; gap: 6px; }
  .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .form-group { display: flex; flex-direction: column; gap: 6px; }
  .form-group.full { grid-column: 1 / -1; }
  label { font-size: 12px; color: #94a3b8; font-weight: 500; }
  input { background: #0f1117; border: 1px solid #2d3748; border-radius: 7px; padding: 8px 12px; color: #e2e8f0; font-size: 13px; outline: none; width: 100%; font-family: monospace; }
  input:focus { border-color: #3b82f6; }
  .result { margin-top: 12px; padding: 10px 14px; border-radius: 7px; font-size: 13px; font-family: monospace; }
  .result-ok { background: #14532d22; border: 1px solid #166534; color: #4ade80; }
  .result-fail { background: #450a0a22; border: 1px solid #7f1d1d; color: #f87171; }
  .result-info { background: #1e293b; border: 1px solid #2d3748; color: #94a3b8; }
  .pw-overlay { position: fixed; inset: 0; background: #0f1117; display: flex; align-items: center; justify-content: center; z-index: 99; }
  .pw-card { background: #1e2130; border: 1px solid #2d3748; border-radius: 12px; padding: 32px; width: 320px; text-align: center; }
  .pw-card h2 { font-size: 18px; margin-bottom: 8px; }
  .pw-card p { color: #64748b; font-size: 13px; margin-bottom: 20px; }
  .pw-card input { margin-bottom: 12px; text-align: center; }
  .section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
  .mono { font-family: monospace; }
  #toast { position: fixed; bottom: 24px; right: 24px; padding: 12px 18px; border-radius: 8px; font-size: 13px; font-weight: 500; opacity: 0; transition: opacity .3s; pointer-events: none; z-index: 100; }
  .modal-overlay { position: fixed; inset: 0; background: rgba(7,9,15,.66); display: flex; align-items: center; justify-content: center; z-index: 200; }
  .modal-card { background: #1e2130; border: 1px solid #2d3748; border-radius: 12px; padding: 22px 22px 18px; width: 360px; max-width: 90vw; box-shadow: 0 12px 40px rgba(0,0,0,.5); }
  .modal-msg { color: #e2e8f0; font-size: 14px; line-height: 1.6; margin-bottom: 18px; word-break: break-all; }
  .modal-actions { display: flex; justify-content: flex-end; gap: 10px; }
</style>
</head>
<body>

<div class="pw-overlay" id="pwOverlay">
  <div class="pw-card">
    <h2>🔐 API Key 管理器</h2>
    <p id="gateMsg">正在校验登录身份…</p>
    <div id="gateHint" style="color:#f87171;font-size:12px;margin-top:8px;line-height:1.6"></div>
  </div>
</div>

<div id="app" style="display:none">
<div class="container">
  <h1>🔑 API Key 管理器</h1>
  <p class="subtitle">管理服务器 AI 配置 · 测试可用性 · 一键切换</p>

  <!-- 当前配置 -->
  <div class="card">
    <div class="section-header">
      <div class="card-title">📡 当前服务器配置（.env）</div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-ghost btn-sm" onclick="loadStatus()">↻ 刷新</button>
        <button class="btn btn-ghost btn-sm" onclick="toggleEdit()" id="editToggleBtn">✏️ 编辑</button>
      </div>
    </div>
    <div class="kv-grid" id="statusGrid">
      <div class="kv-label">加载中...</div>
    </div>
    <!-- 编辑表单（默认隐藏） -->
    <div id="envEditForm" style="display:none;margin-top:16px;border-top:1px solid #2d3748;padding-top:16px">
      <div class="form-grid">
        <div class="form-group">
          <label>Base URL</label>
          <input id="e-url" placeholder="https://api.example.com/v1">
        </div>
        <div class="form-group">
          <label>Model</label>
          <input id="e-model" placeholder="gpt-4o">
        </div>
        <div class="form-group full">
          <label>API Key（留空则不修改）</label>
          <input id="e-key" placeholder="sk-... （留空保持不变）">
        </div>
      </div>
      <div style="margin-top:12px;display:flex;gap:8px">
        <button class="btn btn-success" onclick="saveEnv()">💾 保存到 .env</button>
        <button class="btn btn-ghost" onclick="toggleEdit()">取消</button>
      </div>
      <div id="envSaveResult"></div>
    </div>
    <div style="margin-top:16px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <button class="btn btn-ghost" onclick="testSelected()" id="testCurrentBtn">⚡ 测试</button>
      <select id="testSelect" style="background:#0f1117;border:1px solid #2d3748;border-radius:7px;padding:7px 12px;color:#e2e8f0;font-size:13px;outline:none">
        <option value="">当前 .env 配置</option>
      </select>
    </div>
    <div id="currentTestResult"></div>
  </div>

  <!-- 配置列表 -->
  <div class="card">
    <div class="section-header">
      <div class="card-title">📋 保存的配置</div>
      <button class="btn btn-primary btn-sm" onclick="showAddForm()">+ 新增配置</button>
    </div>
    <div id="profilesTable">
      <div style="color:#64748b;font-size:13px">加载中...</div>
    </div>
  </div>

  <!-- 新增表单 -->
  <div class="card" id="addFormCard" style="display:none">
    <div class="card-title">➕ 新增 API Key 配置</div>
    <div class="form-grid">
      <div class="form-group">
        <label>配置名称 *</label>
        <input id="f-name" placeholder="例：备用Key-01">
      </div>
      <div class="form-group">
        <label>API Key *</label>
        <input id="f-key" placeholder="sk-...">
      </div>
      <div class="form-group">
        <label>Base URL *</label>
        <input id="f-url" placeholder="https://api.example.com/v1">
      </div>
      <div class="form-group">
        <label>Model *</label>
        <input id="f-model" placeholder="gpt-4o">
      </div>
      <div class="form-group full">
        <label>备注</label>
        <input id="f-note" placeholder="可选">
      </div>
    </div>
    <div style="margin-top:16px;display:flex;gap:8px">
      <button class="btn btn-success" onclick="addProfile()">保存配置</button>
      <button class="btn btn-ghost" onclick="hideAddForm()">取消</button>
    </div>
    <div id="addResult"></div>
  </div>

  <!-- 修改表单 -->
  <div class="card" id="editFormCard" style="display:none">
    <div class="card-title">✏️ 修改 API Key 配置</div>
    <div class="form-grid">
      <div class="form-group">
        <label>配置名称（不可改）</label>
        <input id="ed-name" readonly style="opacity:.6">
      </div>
      <div class="form-group">
        <label>API Key（留空保持不变）</label>
        <input id="ed-key" placeholder="留空则保持原 Key 不变">
      </div>
      <div class="form-group">
        <label>Base URL *</label>
        <input id="ed-url" placeholder="https://api.example.com/v1">
      </div>
      <div class="form-group">
        <label>Model *</label>
        <input id="ed-model" placeholder="gpt-4o">
      </div>
      <div class="form-group full">
        <label>备注</label>
        <input id="ed-note" placeholder="可选">
      </div>
    </div>
    <div style="margin-top:16px;display:flex;gap:8px">
      <button class="btn btn-success" onclick="saveEdit()">保存修改</button>
      <button class="btn btn-ghost" onclick="hideEditForm()">取消</button>
    </div>
    <div id="editResult"></div>
  </div>
</div>
</div>

<div id="modalOverlay" class="modal-overlay" style="display:none">
  <div class="modal-card">
    <div class="modal-msg" id="modalMsg"></div>
    <div class="modal-actions">
      <button class="btn btn-ghost" id="modalCancel">取消</button>
      <button class="btn btn-danger" id="modalOk">确定</button>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
const API = "";
let profilesCache = [];

// —— 站内确认弹窗（替代浏览器原生 confirm）——
let _modalResolve = null;
function uiConfirm(message, okText, danger) {
  return new Promise(function (resolve) {
    _modalResolve = resolve;
    document.getElementById("modalMsg").textContent = message;
    var ok = document.getElementById("modalOk");
    ok.textContent = okText || "确定";
    ok.className = "btn " + (danger === false ? "btn-primary" : "btn-danger");
    document.getElementById("modalOverlay").style.display = "flex";
  });
}
function _modalClose(v) {
  document.getElementById("modalOverlay").style.display = "none";
  if (_modalResolve) { var r = _modalResolve; _modalResolve = null; r(v); }
}
document.getElementById("modalCancel").onclick = function () { _modalClose(false); };
document.getElementById("modalOk").onclick = function () { _modalClose(true); };
document.getElementById("modalOverlay").onclick = function (e) { if (e.target.id === "modalOverlay") _modalClose(false); };

function initGate() {
  fetch(API + "/api/whoami").then(r => r.json()).then(d => {
    if (d.ok) {
      document.getElementById("pwOverlay").style.display = "none";
      document.getElementById("app").style.display = "block";
      loadStatus();
      loadProfiles();
    } else {
      document.getElementById("gateMsg").textContent = "无权限访问";
      document.getElementById("gateHint").textContent = "本页仅限 " + (d.allow || "陈佳聪") + " 使用。请先在主后台用你的账号登录，再从「LLM 模型切换」菜单进入。";
    }
  }).catch(() => {
    document.getElementById("gateMsg").textContent = "身份校验失败";
    document.getElementById("gateHint").textContent = "无法连接服务，请刷新重试。";
  });
}

function toast(msg, ok = true) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.style.background = ok ? "#14532d" : "#450a0a";
  el.style.color = ok ? "#4ade80" : "#f87171";
  el.style.opacity = "1";
  setTimeout(() => el.style.opacity = "0", 3000);
}

function loadStatus() {
  fetch(API + "/api/status").then(r => r.json()).then(d => {
    document.getElementById("statusGrid").innerHTML = \`
      <div class="kv-label">Base URL</div><div class="kv-value">\${d.baseUrl || "未配置"}</div>
      <div class="kv-label">Model</div><div class="kv-value">\${d.model || "未配置"}</div>
      <div class="kv-label">API Key</div><div class="kv-value mono">\${d.maskedKey}</div>
      <div class="kv-label">AI 诊断开关</div><div class="kv-value">
        <span class="badge \${d.aiEnabled === 'true' ? 'badge-green' : 'badge-gray'}">\${d.aiEnabled === 'true' ? '已启用' : '已关闭'}</span>
      </div>
    \`;
  });
}

function loadProfiles() {
  fetch(API + "/api/profiles").then(r => r.json()).then(profiles => {
    profilesCache = profiles;
    // 同步填充快速测试下拉
    const sel = document.getElementById("testSelect");
    sel.innerHTML = '<option value="">当前 .env 配置</option>' +
      profiles.map(p => \`<option value="\${p.name}">\${p.name} (\${p.model})</option>\`).join("");

    const el = document.getElementById("profilesTable");
    if (!profiles.length) { el.innerHTML = '<div style="color:#64748b;font-size:13px">暂无保存的配置，点击「新增配置」添加</div>'; return; }
    el.innerHTML = \`<table>
      <thead><tr><th>名称</th><th>Base URL</th><th>Model</th><th>API Key</th><th>备注</th><th>操作</th></tr></thead>
      <tbody>\${profiles.map(p => \`
        <tr id="row-\${p.name}">
          <td><strong>\${p.name}</strong></td>
          <td class="mono" style="font-size:12px">\${p.baseUrl}</td>
          <td class="mono">\${p.model}</td>
          <td class="mono" style="font-size:12px">\${p.apiKey}</td>
          <td style="color:#64748b;font-size:12px">\${p.note || "-"}</td>
          <td>
            <div class="actions">
              <button class="btn btn-ghost btn-sm" onclick="testProfile('\${p.name}')">⚡ 测试</button>
              <button class="btn btn-primary btn-sm" onclick="switchProfile('\${p.name}')">✓ 切换</button>
              <button class="btn btn-ghost btn-sm" onclick="showEditForm('\${p.name}')">✏️ 修改</button>
              <button class="btn btn-danger btn-sm" onclick="deleteProfile('\${p.name}')">删除</button>
            </div>
            <div id="result-\${p.name}"></div>
          </td>
        </tr>
      \`).join("")}</tbody>
    </table>\`;
  });
}

function toggleEdit() {
  const form = document.getElementById("envEditForm");
  const btn = document.getElementById("editToggleBtn");
  const showing = form.style.display !== "none";
  if (showing) {
    form.style.display = "none"; btn.textContent = "✏️ 编辑";
  } else {
    // 预填当前值
    fetch(API + "/api/status").then(r => r.json()).then(d => {
      document.getElementById("e-url").value = d.baseUrl || "";
      document.getElementById("e-model").value = d.model || "";
      document.getElementById("e-key").value = "";
    });
    form.style.display = "block"; btn.textContent = "✕ 取消";
  }
}

function saveEnv() {
  const baseUrl = document.getElementById("e-url").value.trim();
  const model = document.getElementById("e-model").value.trim();
  const apiKey = document.getElementById("e-key").value.trim();
  const resultEl = document.getElementById("envSaveResult");
  resultEl.className = "result result-info"; resultEl.textContent = "保存中...";
  fetch(API + "/api/env", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ baseUrl, model, apiKey })
  }).then(r => r.json()).then(d => {
    if (d.ok) {
      resultEl.className = "result result-ok"; resultEl.textContent = "✅ " + d.message;
      loadStatus();
      setTimeout(() => toggleEdit(), 1200);
    } else {
      resultEl.className = "result result-fail"; resultEl.textContent = "❌ " + (d.error || "保存失败");
    }
  });
}

function testSelected() {
  const profileName = document.getElementById("testSelect").value;
  const btn = document.getElementById("testCurrentBtn");
  const result = document.getElementById("currentTestResult");
  btn.disabled = true; btn.textContent = "测试中...";
  result.className = "result result-info"; result.textContent = "正在连接..."; result.style.display = "block";
  const body = profileName ? { profileName } : {};
  fetch(API + "/api/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
    .then(r => r.json()).then(d => {
      result.className = "result " + (d.ok ? "result-ok" : "result-fail");
      result.textContent = d.message;
    }).finally(() => { btn.disabled = false; btn.textContent = "⚡ 测试"; });
}

function testProfile(name) {
  const el = document.getElementById("result-" + name);
  el.className = "result result-info"; el.textContent = "测试中..."; el.style.marginTop = "6px";
  fetch(API + "/api/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profileName: name }) })
    .then(r => r.json()).then(d => {
      el.className = "result " + (d.ok ? "result-ok" : "result-fail");
      el.textContent = d.message;
    });
}

async function switchProfile(name) {
  if (!(await uiConfirm('切换到 "' + name + '"？这将修改服务器 .env 的 AI_BASE_URL / AI_MODEL / AI_API_KEY。', '切换', false))) return;
  fetch(API + "/api/switch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profileName: name }) })
    .then(r => r.json().then(d => ({ status: r.status, d: d })))
    .then(function (x) {
      if (x.d.ok) { toast("✅ " + x.d.message); loadStatus(); }
      else toast("❌ " + (x.d.error || ("切换失败(" + x.status + ")")), false);
    })
    .catch(function () { toast("❌ 切换失败（网络错误）", false); });
}

async function deleteProfile(name) {
  if (!(await uiConfirm('确认删除配置 "' + name + '"？此操作不可撤销。'))) return;
  fetch(API + "/api/profiles/" + encodeURIComponent(name), { method: "DELETE" })
    .then(r => r.json().then(d => ({ status: r.status, d: d })))
    .then(function (x) {
      if (x.d.ok) { toast("已删除"); loadProfiles(); }
      else toast("❌ " + (x.d.error || ("删除失败(" + x.status + ")")), false);
    })
    .catch(function () { toast("❌ 删除失败（网络错误）", false); });
}

function showAddForm() { document.getElementById("addFormCard").style.display = "block"; }
function hideAddForm() { document.getElementById("addFormCard").style.display = "none"; }

function addProfile() {
  const name = document.getElementById("f-name").value.trim();
  const apiKey = document.getElementById("f-key").value.trim();
  const baseUrl = document.getElementById("f-url").value.trim();
  const model = document.getElementById("f-model").value.trim();
  const note = document.getElementById("f-note").value.trim();
  if (!name || !apiKey || !baseUrl || !model) { document.getElementById("addResult").className = "result result-fail"; document.getElementById("addResult").textContent = "请填写所有必填项"; return; }
  fetch(API + "/api/profiles", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, apiKey, baseUrl, model, note }) })
    .then(r => r.json()).then(d => {
      if (d.ok) { toast("✅ 配置已保存"); hideAddForm(); loadProfiles(); ["f-name","f-key","f-url","f-model","f-note"].forEach(id => document.getElementById(id).value = ""); }
      else { document.getElementById("addResult").className = "result result-fail"; document.getElementById("addResult").textContent = d.error || "保存失败"; }
    });
}

function showEditForm(name) {
  var pf = null;
  for (var i = 0; i < profilesCache.length; i++) { if (profilesCache[i].name === name) { pf = profilesCache[i]; break; } }
  if (!pf) { toast("❌ 找不到该配置", false); return; }
  document.getElementById("ed-name").value = pf.name;
  document.getElementById("ed-url").value = pf.baseUrl || "";
  document.getElementById("ed-model").value = pf.model || "";
  document.getElementById("ed-note").value = pf.note || "";
  document.getElementById("ed-key").value = "";
  document.getElementById("editResult").textContent = "";
  document.getElementById("editFormCard").style.display = "block";
  document.getElementById("editFormCard").scrollIntoView({ behavior: "smooth", block: "center" });
}
function hideEditForm() { document.getElementById("editFormCard").style.display = "none"; }
function saveEdit() {
  var name = document.getElementById("ed-name").value;
  var baseUrl = document.getElementById("ed-url").value.trim();
  var model = document.getElementById("ed-model").value.trim();
  var apiKey = document.getElementById("ed-key").value.trim();
  var note = document.getElementById("ed-note").value.trim();
  var rEl = document.getElementById("editResult");
  if (!baseUrl || !model) { rEl.className = "result result-fail"; rEl.textContent = "Base URL 和 Model 不能为空"; return; }
  fetch(API + "/api/profiles/update", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: name, baseUrl: baseUrl, model: model, apiKey: apiKey, note: note }) })
    .then(function (res) { return res.json().then(function (d) { return { status: res.status, d: d }; }); })
    .then(function (x) {
      if (x.d.ok) { toast("✅ 已更新配置"); hideEditForm(); loadProfiles(); }
      else { rEl.className = "result result-fail"; rEl.textContent = x.d.error || ("修改失败(" + x.status + ")"); }
    })
    .catch(function () { rEl.className = "result result-fail"; rEl.textContent = "修改失败（网络错误）"; });
}
initGate();
</script>
</body>
</html>`;

// ── 启动服务器 ──────────────────────────────────────────────────────────

const server = http.createServer(async (req, res) => {
  try {
    await handleRequest(req, res);
  } catch (e: any) {
    console.error("请求处理出错:", e?.message ?? e);
    if (!res.headersSent) {
      json(res, { error: "内部错误" }, 500);
    }
  }
});

server.listen(PORT, "0.0.0.0", () => {
  const env = readEnvFile();
  console.log(`\nAPI Key 管理器已启动`);
  console.log(`访问地址: http://服务器IP:${PORT}`);
  console.log(`当前配置: ${env.AI_BASE_URL ?? "未配置"} / ${env.AI_MODEL ?? "未配置"}`);
  console.log(`访问控制: 复用主后台登录(app_session)，仅放行 ${ALLOW_USERS.join("/")}`);
  console.log(`按 Ctrl+C 停止\n`);
});
