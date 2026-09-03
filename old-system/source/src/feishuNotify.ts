/**
 * feishuNotify.ts - 统一飞书发送模块（批B，2026-07-11）
 *
 * 职责：
 *   1. tenant token 获取
 *   2. 按在册花名册解析个人接收人（dim_feishu_member: name精确匹配 +
 *      employment_status='active' + open_id非空；查不到/重名 → 告警跳过，禁止猜测发送）
 *   3. 发群消息(chat_id) / 个人消息(open_id) / webhook 文本
 *   4. 失败重试：网络错误/超时/5xx/19006(internal error) 按 2s/5s 重试2次；
 *      11232(frequency limited) 按 30s/60s 重试2次；其他错误不重试
 *   5. 多接收端 fanout：单端失败不阻断其他端，每端独立结果
 *   6. 长文本按 28000 字符分片
 *
 * 测试模式(2026-07-11 新增)：sendTestGroupText/sendCardWithFallbackToChat——
 * 应用机器人发送到 FEISHU_NOTIFY_TEST_CHAT_ID。
 * 凭证隔离（第3版收口）：
 *   getTenantToken()＝现有生产链路（noOrder/lowProfit/checkAutoAd），只读公共
 *   FEISHU_APP_ID/SECRET，绝不读专用变量——写入专用配置不会切换存量生产链路；
 *   getNotifyTenantToken()＝测试群与卡片新路径（sendTestGroupText/
 *   sendCardWithFallbackToChat，含业绩日报 FEISHU_PERF_PROVIDER=app），
 *   优先 FEISHU_NOTIFY_APP_ID/SECRET（必须成对，只配一项报错，禁止交叉混用），
 *   两者均为空才回退公共变量。
 * 节流边界（如实说明）：FEISHU_NOTIFY_MIN_INTERVAL_MS（默认1000ms）为
 * "单进程内串行节流"——notify:test:all 本身严格串行因此测试阶段有效；
 * 不同 cron 进程之间不共享 lastSendAt，本轮不实现跨进程队列/分布式锁；
 * 后续全部生产通报迁移 App 机器人时再独立建设统一发送队列。
 * FEISHU_NOTIFY_PROVIDER 当前仅支持 app（预留扩展位）。
 *
 * 安全纪律：日志禁止输出 token/secret/webhook/open_id/union_id/chat_id，只输出姓名/标签。
 * 接入范围（批B定稿）：noOrderNotify / lowProfitNotify / performanceSummaryReport /
 * checkAutoAdSearchTermImport + 批C新脚本；unmatchedOwnerNotify 本轮零改动，存量渐进迁移。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";

const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;

export interface NotifyTarget {
  type: "user" | "chat";
  label: string; // 仅用于日志展示（姓名/群别名），不含ID
  id: string;
}

export interface SendResult {
  label: string;
  type: string;
  ok: boolean;
  retryCount: number;
  /** true=过程中出现过网络超时类"结果未知"错误后重试——at-least-once语义，理论上存在重复送达可能 */
  ambiguousDelivery: boolean;
  error?: string;
}

const FEISHU_MSG_MAX_LEN = 28000;

// ── 单进程内串行节流（相邻请求至少间隔 FEISHU_NOTIFY_MIN_INTERVAL_MS；跨进程不共享） ──
function minIntervalMs(): number {
  const v = Number(process.env.FEISHU_NOTIFY_MIN_INTERVAL_MS ?? 1000);
  return Number.isFinite(v) && v > 0 ? v : 1000;
}
let lastSendAt = 0;
async function throttleSend(): Promise<void> {
  const wait = lastSendAt + minIntervalMs() - Date.now();
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  lastSendAt = Date.now();
}

export function getTestChatId(): string {
  return (process.env.FEISHU_NOTIFY_TEST_CHAT_ID ?? "").trim();
}

function notifyProvider(): string {
  const p = (process.env.FEISHU_NOTIFY_PROVIDER ?? "app").trim() || "app";
  if (p !== "app") console.log(`  [提示] FEISHU_NOTIFY_PROVIDER=${p} 暂仅支持 app，按 app 发送`);
  return "app";
}

export function parseListEnv(key: string): string[] {
  return String(process.env[key] ?? "")
    .split(/[,，;；\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/** 错误摘要：只保留 code/msg/HTTP 状态，绝不含 token/请求头/接收人ID */
function safeErrText(e: unknown): string {
  const err = e as { feishuCode?: unknown; message?: string; response?: { status?: number; data?: { code?: unknown; msg?: unknown } } };
  const code = err?.feishuCode ?? err?.response?.data?.code;
  const msg = err?.response?.data?.msg;
  if (code !== undefined) return `code=${code} msg=${msg ?? ""}`.trim();
  if (err?.response?.status) return `http=${err.response.status}`;
  return String(err?.message ?? e).slice(0, 200);
}

function classifyError(e: unknown): { retryable: boolean; freqLimited: boolean; unknownOutcome: boolean } {
  const err = e as { feishuCode?: unknown; response?: { status?: number; data?: { code?: unknown } } };
  const code = Number(err?.feishuCode ?? err?.response?.data?.code ?? NaN);
  if (code === 11232) return { retryable: true, freqLimited: true, unknownOutcome: false };  // frequency limited
  if (code === 19006) return { retryable: true, freqLimited: false, unknownOutcome: false }; // feishu internal error
  const st = err?.response?.status;
  if (st === 429) return { retryable: true, freqLimited: true, unknownOutcome: false };      // HTTP 频控
  if (st && st >= 500) return { retryable: true, freqLimited: false, unknownOutcome: false };
  // 网络错误/超时：请求可能已送达（结果未知）——重试后为 at-least-once，存在重复送达可能
  if (!err?.response) return { retryable: true, freqLimited: false, unknownOutcome: true };
  return { retryable: false, freqLimited: false, unknownOutcome: false };                    // 明确业务/格式错误：不重试
}

/**
 * 重试包装：首发失败后最多重试2次；普通可重试错误 2s/5s，频控(11232/HTTP429) 30s/60s。
 * 重复发送边界（如实声明）：收到明确成功响应后绝不重复发送；但网络超时类错误结果未知，
 * 重试属 at-least-once 语义，理论上存在重复送达可能（ambiguousDelivery=true 标记）。
 * 如需绝对幂等需迁移到支持幂等键的发送链路，本模块不承诺。
 */
export async function sendWithRetry(
  label: string,
  fn: () => Promise<void>,
): Promise<{ ok: boolean; retryCount: number; ambiguousDelivery: boolean; error?: string }> {
  const normalDelays = [2000, 5000];
  const freqDelays = [30000, 60000];
  let retryCount = 0;
  let ambiguousDelivery = false;
  for (let attempt = 0; attempt <= 2; attempt++) {
    try {
      await fn();
      if (ambiguousDelivery) console.log(`  [注意] ${label}: ambiguousDelivery=true（曾出现结果未知的网络错误后重试，可能重复送达）`);
      return { ok: true, retryCount, ambiguousDelivery };
    } catch (e) {
      const { retryable, freqLimited, unknownOutcome } = classifyError(e);
      const errText = safeErrText(e);
      if (attempt === 2 || !retryable) {
        console.log(`  [失败] ${label}: ${errText}${retryable ? "（重试次数已用尽）" : "（不可重试错误，不再重发）"} ambiguousDelivery=${ambiguousDelivery || unknownOutcome}`);
        return { ok: false, retryCount, ambiguousDelivery: ambiguousDelivery || unknownOutcome, error: errText };
      }
      if (unknownOutcome) ambiguousDelivery = true;
      const delay = freqLimited ? freqDelays[attempt] : normalDelays[attempt];
      console.log(`  [重试] ${label}: ${errText}，${delay / 1000}s 后第 ${attempt + 1} 次重试`);
      await sleep(delay);
      retryCount += 1;
    }
  }
  return { ok: false, retryCount, ambiguousDelivery, error: "unreachable" };
}

/** 底层 token 请求（凭证由调用方决定；不输出任何凭证/token 值） */
async function fetchTenantToken(appId: string, appSecret: string): Promise<string> {
  const resp = await axios.post(
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    { app_id: appId, app_secret: appSecret },
    { headers: { "Content-Type": "application/json" }, timeout: 15000 },
  );
  const data = resp.data as Record<string, unknown>;
  if (data.code !== 0) throw new Error(`获取飞书 token 失败: code=${data.code}`);
  return data.tenant_access_token as string;
}

/**
 * 现有生产发送链路凭证（第3版收口：只读公共应用 FEISHU_APP_ID/SECRET）。
 * 绝不读取 FEISHU_NOTIFY_APP_ID/SECRET——写入专用通报应用配置
 * 不会切换存量生产链路（noOrder/lowProfit/checkAutoAd 个人与群发送）的应用身份。
 */
export async function getTenantToken(): Promise<string> {
  const appId = process.env.FEISHU_APP_ID?.trim() ?? "";
  const appSecret = process.env.FEISHU_APP_SECRET?.trim() ?? "";
  if (!appId || !appSecret) throw new Error("缺少 FEISHU_APP_ID / FEISHU_APP_SECRET 环境变量");
  return fetchTenantToken(appId, appSecret);
}

/**
 * 通报测试/App新路径专用凭证（第3版收口新增）。
 * 用途：sendTestGroupText、sendCardWithFallbackToChat（含业绩日报
 * FEISHU_PERF_PROVIDER=app 路径）。
 * 规则：优先 FEISHU_NOTIFY_APP_ID/SECRET（必须成对，只配一项立即报错，
 * 禁止专用/公共交叉混用取值）；两个专用变量均为空时才回退 FEISHU_APP_ID/SECRET。
 * 日志只输出"使用专用通报应用"/"使用公共应用回退"，不输出任何 ID/Secret/token 值。
 */
export async function getNotifyTenantToken(): Promise<string> {
  const dedicatedId = process.env.FEISHU_NOTIFY_APP_ID?.trim() ?? "";
  const dedicatedSecret = process.env.FEISHU_NOTIFY_APP_SECRET?.trim() ?? "";
  if (dedicatedId || dedicatedSecret) {
    if (!dedicatedId || !dedicatedSecret) {
      throw new Error("FEISHU_NOTIFY_APP_ID 与 FEISHU_NOTIFY_APP_SECRET 必须成对配置，禁止与公共变量混用");
    }
    console.log("  使用专用通报应用");
    return fetchTenantToken(dedicatedId, dedicatedSecret);
  }
  const appId = process.env.FEISHU_APP_ID?.trim() ?? "";
  const appSecret = process.env.FEISHU_APP_SECRET?.trim() ?? "";
  if (!appId || !appSecret) throw new Error("缺少飞书应用凭证环境变量（专用或公共均未配置）");
  console.log("  使用公共应用回退");
  return fetchTenantToken(appId, appSecret);
}

/**
 * 按在册花名册解析个人接收人。
 * 规则：name 精确匹配 + employment_status='active' + open_id 非空；
 * 查不到/重名 → 告警并跳过（禁止猜测发送）。
 */
export async function resolveActiveMembers(
  names: string[],
): Promise<{ targets: NotifyTarget[]; warnings: string[] }> {
  const targets: NotifyTarget[] = [];
  const warnings: string[] = [];
  if (!names.length) return { targets, warnings };
  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
  try {
    for (const name of names) {
      const [rows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT open_id FROM dim_feishu_member
         WHERE name = ? AND employment_status = 'active' AND COALESCE(open_id, '') <> ''`,
        [name],
      );
      if (rows.length === 0) {
        warnings.push(`${name}: 不在在册花名册（或无飞书ID），已跳过——禁止猜测发送`);
      } else if (rows.length > 1) {
        warnings.push(`${name}: 在册重名 ${rows.length} 条，已跳过——禁止猜测发送`);
      } else {
        targets.push({ type: "user", label: name, id: String(rows[0].open_id) });
      }
    }
    return { targets, warnings };
  } finally {
    await db.end();
  }
}

function chunkText(text: string): string[] {
  const out: string[] = [];
  for (let i = 0; i < text.length; i += FEISHU_MSG_MAX_LEN) {
    out.push(text.slice(i, i + FEISHU_MSG_MAX_LEN));
  }
  return out.length ? out : [""];
}

/** 2026-07-30 上传图片到飞书 im/v1/images → image_key（用于人工绩效卡片内嵌凭证图）。image_type=message。 */
export async function uploadImageToFeishu(imageBuffer: Buffer, token?: string): Promise<string> {
  const tk = token ?? (await getNotifyTenantToken());
  const FormDataNode = require("form-data");
  const form = new FormDataNode();
  form.append("image_type", "message");
  form.append("image", imageBuffer, { filename: "cert.jpg", contentType: "image/jpeg" });
  const resp = await axios.post(
    "https://open.feishu.cn/open-apis/im/v1/images",
    form,
    { headers: { ...form.getHeaders(), Authorization: `Bearer ${tk}` }, maxContentLength: Infinity, maxBodyLength: Infinity },
  );
  const key = resp?.data?.data?.image_key;
  if (!key) throw new Error(`飞书图片上传失败: ${JSON.stringify(resp?.data ?? {})}`);
  return String(key);
}

async function postText(token: string, receiveIdType: "open_id" | "chat_id", id: string, text: string): Promise<void> {
  await throttleSend();
  const resp = await axios.post(
    `https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=${receiveIdType}`,
    { receive_id: id, msg_type: "text", content: JSON.stringify({ text }) },
    { headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, timeout: 15000 },
  );
  const data = resp.data as Record<string, unknown>;
  if (data.code !== 0) {
    const err: Error & { feishuCode?: unknown } = new Error(`feishu send failed`);
    err.feishuCode = data.code;
    (err as unknown as { response: unknown }).response = { data };
    throw err;
  }
}

/** 互动卡片发送（应用机器人，chat_id/open_id 通用），过全局节流 —— 2026-07-20 泛化支持个人 */
async function postCardTo(token: string, receiveIdType: "chat_id" | "open_id", id: string, card: Record<string, unknown>): Promise<void> {
  await throttleSend();
  const resp = await axios.post(
    `https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=${receiveIdType}`,
    { receive_id: id, msg_type: "interactive", content: JSON.stringify(card) },
    { headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, timeout: 15000 },
  );
  const data = resp.data as Record<string, unknown>;
  if (data.code !== 0) {
    const err: Error & { feishuCode?: unknown } = new Error("feishu card send failed");
    err.feishuCode = data.code;
    (err as unknown as { response: unknown }).response = { data };
    throw err;
  }
}

/** 互动卡片发送（应用机器人，chat_id），过全局节流 */
async function postCard(token: string, chatId: string, card: Record<string, unknown>): Promise<void> {
  return postCardTo(token, "chat_id", chatId, card);
}

/**
 * 卡片发送到任意目标（群/个人）—— 2026-07-20 新增，服务私信卡片化：
 * 通报应用凭证+重试节流；卡片失败自动降级纯文本；成功后按镜像开关抄送文本副本；
 * doSend=false 仅打印降级文本预览，零发送。
 */
export async function sendCardToTarget(
  target: NotifyTarget,
  card: Record<string, unknown>,
  fallbackText: string,
  doSend: boolean,
): Promise<SendResult> {
  if (!doSend) {
    console.log(`\n[dry-run] 将发送卡片到 ${target.type === "user" ? "个人" : "群"}「${target.label}」，降级文本预览：`);
    console.log("─".repeat(60));
    console.log(fallbackText.length > 2000 ? `${fallbackText.slice(0, 2000)}\n...（预览截断，共 ${fallbackText.length} 字）` : fallbackText);
    console.log("─".repeat(60));
    return { label: target.label, type: target.type, ok: true, retryCount: 0, ambiguousDelivery: false };
  }
  notifyProvider();
  let token: string;
  try {
    token = await getNotifyTenantToken();
  } catch (e) {
    return { label: target.label, type: target.type, ok: false, retryCount: 0, ambiguousDelivery: false, error: safeErrText(e) };
  }
  const r1 = await sendWithRetry(`${target.label}卡片`, () =>
    postCardTo(token, target.type === "user" ? "open_id" : "chat_id", target.id, card));
  if (r1.ok) {
    console.log(`  ✅ 卡片已发送到「${target.label}」(retryCount=${r1.retryCount}, ambiguousDelivery=${r1.ambiguousDelivery})`);
    if (target.id !== getTestChatId()) {
      await mirrorCopyToTest(token, `卡片·${target.type === "user" ? "个人" : "群"}·${target.label}`, fallbackText);
    }
    return { label: target.label, type: target.type, ok: true, retryCount: r1.retryCount, ambiguousDelivery: r1.ambiguousDelivery };
  }
  console.log(`  「${target.label}」卡片最终失败(${r1.error})，降级纯文本`);
  return sendTextToTarget(token, target, fallbackText, true);
}

/**
 * 测试群文本发送（应用机器人）：只发 FEISHU_NOTIFY_TEST_CHAT_ID，
 * 分片+重试+节流；日志只出现"测试群"标签，不输出 chat_id。
 */
export async function sendTestGroupText(label: string, text: string): Promise<SendResult> {
  const chatId = getTestChatId();
  if (!chatId) {
    return { label, type: "chat", ok: false, retryCount: 0, ambiguousDelivery: false, error: "FEISHU_NOTIFY_TEST_CHAT_ID未配置" };
  }
  notifyProvider();
  try {
    const token = await getNotifyTenantToken(); // 第3版：测试群走专用通报应用凭证
    return await sendTextToTarget(token, { type: "chat", label, id: chatId }, text, true);
  } catch (e) {
    return { label, type: "chat", ok: false, retryCount: 0, ambiguousDelivery: false, error: safeErrText(e) };
  }
}

/**
 * 卡片发送到指定群（应用机器人）+ 失败降级纯文本。
 * 返回各阶段计数；日志只输出 label，不输出 chat_id。
 */
export async function sendCardWithFallbackToChat(
  label: string,
  chatId: string,
  card: Record<string, unknown>,
  fallbackText: string,
): Promise<{ ok: boolean; cardOk: boolean; fallbackUsed: boolean; retryCount: number; ambiguousDelivery: boolean; error?: string }> {
  if (!chatId) return { ok: false, cardOk: false, fallbackUsed: false, retryCount: 0, ambiguousDelivery: false, error: "chat_id未配置" };
  notifyProvider();
  let token: string;
  try {
    token = await getNotifyTenantToken(); // 第3版：卡片新路径走专用通报应用凭证
  } catch (e) {
    return { ok: false, cardOk: false, fallbackUsed: false, retryCount: 0, ambiguousDelivery: false, error: safeErrText(e) };
  }
  const r1 = await sendWithRetry(`${label}卡片`, () => postCard(token, chatId, card));
  if (r1.ok) {
    console.log(`  ✅ 「${label}」卡片发送成功(retryCount=${r1.retryCount}, ambiguousDelivery=${r1.ambiguousDelivery})`);
    if (chatId !== getTestChatId()) {
      await mirrorCopyToTest(token, `卡片·${label}`, fallbackText); // 监督镜像：卡片以纯文本副本抄送
    }
    return { ok: true, cardOk: true, fallbackUsed: false, retryCount: r1.retryCount, ambiguousDelivery: r1.ambiguousDelivery };
  }
  console.log(`  「${label}」卡片最终失败(${r1.error})，降级纯文本`);
  const fb = await sendTextToTarget(token, { type: "chat", label: `${label}纯文本降级`, id: chatId }, fallbackText, true);
  return {
    ok: fb.ok, cardOk: false, fallbackUsed: true,
    retryCount: r1.retryCount + fb.retryCount,
    ambiguousDelivery: r1.ambiguousDelivery || fb.ambiguousDelivery,
    error: fb.ok ? undefined : fb.error,
  };
}

/**
 * 全局监督镜像（2026-07-16 需求方决定：所有通知抄送测试群）：
 * FEISHU_NOTIFY_MIRROR_TO_TEST=1 时，生产发送成功后向测试群补发【监督副本】。
 * 副本发送失败只记日志，绝不影响主发送结果；日志不含任何ID。
 */
export function mirrorToTestEnabled(): boolean {
  return (process.env.FEISHU_NOTIFY_MIRROR_TO_TEST ?? "").trim() === "1";
}

async function mirrorCopyToTest(token: string | null, srcLabel: string, text: string): Promise<void> {
  if (!mirrorToTestEnabled()) return;
  const chatId = getTestChatId();
  if (!chatId) return;
  try {
    const tk = token ?? (await getNotifyTenantToken());
    const pieces = chunkText(`【监督副本→${srcLabel}】\n${text}`);
    for (const p of pieces) {
      const r = await sendWithRetry(`监督副本(${srcLabel})`, () => postText(tk, "chat_id", chatId, p));
      if (!r.ok) { console.log(`  [镜像] 副本发送失败(${r.error})，忽略不影响主发送`); return; }
    }
    console.log(`  [镜像] 已抄送测试群（${srcLabel}）`);
  } catch (e) {
    console.log(`  [镜像] 副本异常(${safeErrText(e)})，忽略不影响主发送`);
  }
}

/** 单接收端发送（自动分片+重试）；dry-run 只输出标签与预览，不输出ID；retryCount 累计全部分片 */
export async function sendTextToTarget(
  token: string,
  target: NotifyTarget,
  text: string,
  doSend: boolean,
): Promise<SendResult> {
  if (!doSend) {
    console.log(`\n[dry-run] 将发送到 ${target.type === "user" ? "个人" : "群"}「${target.label}」（${chunkText(text).length} 片）：`);
    console.log("─".repeat(60));
    console.log(text.length > 2000 ? `${text.slice(0, 2000)}\n...（预览截断，共 ${text.length} 字）` : text);
    console.log("─".repeat(60));
    return { label: target.label, type: target.type, ok: true, retryCount: 0, ambiguousDelivery: false };
  }
  const pieces = chunkText(text);
  let totalRetry = 0;
  let ambiguous = false;
  for (let i = 0; i < pieces.length; i++) {
    const tag = pieces.length > 1 ? `${target.label}(${i + 1}/${pieces.length})` : target.label;
    const r = await sendWithRetry(tag, () =>
      postText(token, target.type === "user" ? "open_id" : "chat_id", target.id, pieces[i]));
    totalRetry += r.retryCount;
    ambiguous = ambiguous || r.ambiguousDelivery;
    if (!r.ok) {
      return { label: target.label, type: target.type, ok: false, retryCount: totalRetry, ambiguousDelivery: ambiguous, error: r.error };
    }
  }
  console.log(`  ✅ 已发送到「${target.label}」(retryCount=${totalRetry}, ambiguousDelivery=${ambiguous})`);
  // 监督镜像：目标本身是测试群时不再抄送，避免自我复制
  if (target.id !== getTestChatId()) {
    await mirrorCopyToTest(token, `${target.type === "user" ? "个人" : "群"}·${target.label}`, text);
  }
  return { label: target.label, type: target.type, ok: true, retryCount: totalRetry, ambiguousDelivery: ambiguous };
}

/** 多接收端 fanout：单端失败不阻断其他端 */
export async function fanoutText(
  token: string,
  targets: NotifyTarget[],
  text: string,
  doSend: boolean,
): Promise<SendResult[]> {
  const results: SendResult[] = [];
  const seen = new Set<string>();
  for (const t of targets) {
    const key = `${t.type}|${t.id}`;
    if (seen.has(key)) {
      console.log(`  [去重] 目标「${t.label}」与已发送目标重复(type+id)，跳过`);
      continue;
    }
    seen.add(key);
    try {
      results.push(await sendTextToTarget(token, t, text, doSend));
    } catch (e) {
      results.push({ label: t.label, type: t.type, ok: false, retryCount: 0, ambiguousDelivery: false, error: safeErrText(e) });
    }
    if (doSend) await sleep(500);
  }
  return results;
}

/**
 * webhook 文本安全发送：dry-run / 分类重试(19006→2s/5s，11232与HTTP429→30s/60s，
 * 网络与5xx可重试) / 只记录 code|msg|http，不输出完整JSON与webhook值。
 */
export async function sendWebhookText(
  webhookUrl: string,
  label: string,
  text: string,
  doSend: boolean,
): Promise<SendResult> {
  if (!doSend) {
    console.log(`\n[dry-run] 将通过 webhook「${label}」发送：`);
    console.log("─".repeat(60));
    console.log(text);
    console.log("─".repeat(60));
    return { label, type: "webhook", ok: true, retryCount: 0, ambiguousDelivery: false };
  }
  if (!webhookUrl) {
    return { label, type: "webhook", ok: false, retryCount: 0, ambiguousDelivery: false, error: "webhook未配置" };
  }
  const r = await sendWithRetry(label, async () => {
    const resp = await axios.post(
      webhookUrl,
      { msg_type: "text", content: { text } },
      { headers: { "Content-Type": "application/json" }, timeout: 15000 },
    );
    const data = resp.data as Record<string, unknown>;
    if (data.StatusCode !== 0 && data.code !== 0) {
      const err: Error & { feishuCode?: unknown } = new Error("webhook send failed");
      err.feishuCode = data.code ?? data.StatusCode;
      (err as unknown as { response: unknown }).response = { data };
      throw err;
    }
  });
  if (r.ok) {
    console.log(`  ✅ webhook「${label}」发送成功(retryCount=${r.retryCount}, ambiguousDelivery=${r.ambiguousDelivery})`);
    await mirrorCopyToTest(null, `webhook·${label}`, text); // 监督镜像（webhook路径无token，副本内部自取）
  }
  return { label, type: "webhook", ok: r.ok, retryCount: r.retryCount, ambiguousDelivery: r.ambiguousDelivery, error: r.error };
}

export function formatResults(results: SendResult[]): string {
  if (!results.length) return "(无接收端)";
  return results
    .map((r) => {
      const kind = r.type === "user" ? "个人" : r.type === "chat" ? "群" : r.type;
      return `${r.label}(${kind})=${r.ok ? "成功" : `失败:${r.error ?? ""}`} retry=${r.retryCount} ambiguous=${r.ambiguousDelivery}`;
    })
    .join(" ｜ ");
}
