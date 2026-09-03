/**
 * aiOpsLogReview.ts — AI 运营日志周评 v1.3.1（AI智能人事系统 V1 批次H2）
 *
 * v1.3.1（2026-07-23 需求方拍板放宽一档）：好日志两要素=动作+调整目的/依据；
 *   后续观察计划为鼓励项不判差（首期0好/75差基线后放宽，后续再收紧至三要素）。
 * v1.3（2026-07-23 需求方二次目检后口径调整）：
 *   ① 抽查时间：每周四 23:00；周期 = 上周五 ~ 本周四（默认取最近的周四为周期终点）。
 *   ② 抽中产品看周期内"全部"日志行：有基础行但未填/仅无运营话术的天数由系统直接判差
 *     （reason=当日未填写运营日志，llm_model=rule_unfilled，零LLM），实质日志才送 AI 评三要素。
 *   ③ 抽样改按周期种子的确定性随机：同一周期 dry-run 与正式跑抽中的 ItemID 完全一致。
 * v1.2（2026-07-22 需求方目检后口径调整）：
 *   ① 抽查改 ItemID 维度：每周随机抽 SAMPLE_ITEMS=20 个 ItemID，逐产品诊断其整周日志
 *     （不再全量逐人评）；每产品一次 LLM 小请求，失败重试1次，仍失败仅跳过该产品。
 *   ② 评判标准纠偏：好日志三要素=动作+调整目的/依据+后续观察计划；不要求写调整后的效果；
 *     改进建议只围绕补齐三要素（日志规范性），禁止要求补写效果数据。
 *   ③ 新增 --purge-week：重评同周前清除该周两张 AI 表旧行（仅 AI 层自产快照，口径重置用，
 *     需显式授权使用）。
 * v1.1：分片调用+重试、摘录压缩、超时180s、点评独立小请求带统计兜底。
 *
 * 拍板口径（2026-07-22）：每周评上周全部实质日志；好/差两档；仅页面展示（零飞书发送）；
 * V1 不联动扣分。AI 只写 ai_ops_log_review_item / ai_ops_log_review_summary 两张 AI 层表。
 *
 * 数据输入（只读）：
 *   biz_product_operation_log（实质日志：log_content 非空且不在无运营话术白名单）
 *   biz_product_rule_signal_daily（当日运营提醒，关联口径=log_date=signal_date AND platform
 *     AND store_key AND item_id AND msku，与运营日志 Tab 同源）
 *   dim_feishu_member（评估范围 = 在册 active 成员）
 * LLM：OpenAI 兼容 chat/completions（env AI_BASE_URL / AI_MODEL / AI_API_KEY），
 *   fail-safe 模式（复用 ai_pmc/aiEvaluate 纪律）：单人调用异常 → 该人 status=failed 跳过，
 *   不抛出、不重试风暴、不影响其他人。
 *
 * 用法：
 *   npx ts-node src/aiOpsLogReview.ts                       # dry-run：零 LLM 调用、零写入，仅统计
 *   npx ts-node src/aiOpsLogReview.ts --confirm-write        # 调 LLM + UPSERT 写入
 *   --purge-week                                             # 写入前清除该周旧评级行（配合口径变更重评）
 *   --window-end=YYYY-MM-DD                                  # 指定周期终点（周四），默认=最近的周四
 * cron（H2 人工目检门禁通过后）：每周四 23:00（0 23 * * 4）
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";

const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;

const TASK = "aiOpsLogReview";
const SAMPLE_ITEMS = 20;              // v1.2：每周随机抽查的 ItemID 数（需求方拍板）
const CHUNK_RETRY = 1;                // 每产品调用失败重试 1 次（仍失败仅跳过该产品）
const LOG_EXCERPT_LEN = 400;          // v1.1 压缩：900 → 400
const SIGNALS_EXCERPT_LEN = 300;      // v1.1 压缩：900 → 300
const LLM_TIMEOUT_MS = 180_000;       // v1.1：120s → 180s
const COMMENT_TIMEOUT_MS = 60_000;
// 无实质动作话术白名单（与 checkOpsInactionAlert 同口径）
const NON_SUBSTANTIVE = new Set(["今日无运营", "今日无操作", "无运营", "无操作"]);

interface LogRow extends mysql.RowDataPacket {
  id: number;
  log_date: string;
  platform: string;
  store_id: string;
  store_name: string;
  store_key: string;
  item_id: string;
  msku: string;
  owner: string;
  profit_level_snapshot: string | null;
  log_content: string;
}
interface SignalRow extends mysql.RowDataPacket {
  signal_date: string;
  platform: string;
  store_key: string;
  item_id: string;
  msku: string;
  rule_name: string;
  trigger_reason: string;
  suggested_action: string;
}
interface MemberRow extends mysql.RowDataPacket { name: string; }

function normStr(v: unknown): string { return String(v ?? "").trim(); }

function dbConfig(): mysql.ConnectionOptions {
  return {
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  };
}

function readAiEnv(name: "BASE_URL" | "MODEL" | "API_KEY"): string {
  const v = normStr(process.env[`AI_${name}`]);
  if (!v) throw new Error(`缺少环境变量: AI_${name}`);
  return v;
}

/** 上海时区“最近的周四”（周期终点；当天是周四则取当天） */
function recentThursdayCst(): string {
  const nowCst = new Date(Date.now() + 8 * 3600 * 1000);
  const dow = nowCst.getUTCDay(); // 0=周日..6=周六；周四=4
  const back = (dow - 4 + 7) % 7;
  const d = new Date(nowCst);
  d.setUTCDate(d.getUTCDate() - back);
  return d.toISOString().slice(0, 10);
}

/** 周期种子确定性随机（mulberry32）：同一周期 dry-run 与正式跑抽样一致 */
function seededRng(seedText: string): () => number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < seedText.length; i++) { h ^= seedText.charCodeAt(i); h = Math.imul(h, 16777619); }
  let a = h >>> 0;
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let x = Math.imul(a ^ (a >>> 15), 1 | a);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}
function addDays(ymd: string, n: number): string {
  const [y, m, d] = ymd.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d));
  t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
}
function getArg(name: string): string {
  const f = `--${name}=`;
  const hit = process.argv.find((a) => a.startsWith(f));
  return hit ? hit.slice(f.length) : "";
}

/** 提取错误要点：网络层(code)/HTTP状态/响应体，避免只记到空 message */
function errBrief(e: unknown): string {
  const x = e as { message?: string; code?: string; response?: { status?: number; data?: unknown } };
  const parts: string[] = [];
  if (x && x.code) parts.push("code=" + x.code);
  if (x && x.response && x.response.status) parts.push("http=" + x.response.status);
  const msg = x && x.message ? String(x.message) : "";
  if (msg) parts.push("msg=" + msg);
  if (x && x.response && x.response.data !== undefined) {
    let body = "";
    try { body = typeof x.response.data === "string" ? x.response.data : JSON.stringify(x.response.data); } catch { body = String(x.response.data); }
    if (body) parts.push("body=" + body.slice(0, 200));
  }
  const out = parts.join(" ");
  return out || (e instanceof Error ? e.message : String(e)) || "unknown-error";
}

const ITEM_PROMPT = [
  "你是跨境电商运营主管，评审某个产品(ItemID)本周的运营日志质量。当前阶段的目标是让运营写出规范的日志，不是考核经营结果。",
  "现阶段放宽标准，好日志两要素：①做了什么动作 ②调整目的/依据（为什么动，最好呼应当日系统提醒）。两要素齐=good。",
  "后续观察计划（观察什么指标、多久）目前是鼓励项：缺观察计划不判差。",
  "对每条日志给出 verdict：good 或 bad（只有这两档）。只有动作没有目的/依据、空泛话术（如'继续观察'无原因）、与当日提醒无关、复制粘贴=bad。",
  "注意：不要求也不应要求运营在日志里写'调整后的效果/结果数据'——suggestion 严禁出现要求补写效果、数据变化、复盘结果之类的内容。",
  "suggestion 只围绕补齐两要素，例如：'补充降竞价的原因'。good 的 suggestion 为空串（缺观察计划时可温和提示'可补充观察计划'）。",
  "严格只输出 JSON，不要任何解释文字，格式：{\"items\":[{\"id\":123,\"verdict\":\"good\",\"reason\":\"30字内\",\"suggestion\":\"30字内\"}]}",
  "items 必须覆盖输入的每一条 id，不得新增或遗漏。reason/suggestion 必须简短。",
].join("\n");

const COMMENT_PROMPT = [
  "你是跨境电商运营主管。根据某负责人本周被抽查产品的日志评审统计与代表样例，写一段点评（120字内）：",
  "点评聚焦日志规范性：动作+调整目的/依据两要素的完整度（后续观察计划为鼓励项，不强制）；先肯定优点，再指出最主要的1-2个改进点，语气建设性。",
  "不要要求运营在日志里写调整后的效果/结果数据。只输出点评正文，不要 JSON、不要前缀。",
].join("\n");

type LlmLog = { id: number; date: string; msku: string; itemId: string; profitLevel: string; signals: string; log: string };
type VerdictMap = Map<number, { verdict: string; reason: string; suggestion: string }>;

async function llmChat(system: string, user: string, timeoutMs: number): Promise<string> {
  const AI_BASE_URL = readAiEnv("BASE_URL").replace(/\/+$/, "");
  const AI_MODEL = readAiEnv("MODEL");
  const AI_API_KEY = readAiEnv("API_KEY");
  const resp = await axios.post(
    `${AI_BASE_URL}/chat/completions`,
    { model: AI_MODEL, messages: [{ role: "system", content: system }, { role: "user", content: user }], temperature: 0.2 },
    { headers: { "Content-Type": "application/json", Authorization: `Bearer ${AI_API_KEY}` }, timeout: timeoutMs },
  );
  return normStr(resp.data?.choices?.[0]?.message?.content ?? "");
}

function parseJsonBlock(content: string): unknown {
  const jsonText = content.replace(/^```json\s*/i, "").replace(/^```\s*/, "").replace(/```\s*$/, "").trim();
  return JSON.parse(jsonText);
}

/** v1.2 单产品(ItemID)整周日志判定，失败重试 CHUNK_RETRY 次 */
async function llmReviewItem(itemLabel: string, ownerName: string, logs: LlmLog[]): Promise<VerdictMap> {
  const userPrompt = `产品：${itemLabel} ｜ 负责人：${ownerName}\n该产品本周日志（JSON数组，共${logs.length}条，signals为当日系统提醒）：\n${JSON.stringify(logs)}`;
  let lastErr: unknown = null;
  for (let attempt = 0; attempt <= CHUNK_RETRY; attempt++) {
    try {
      const content = await llmChat(ITEM_PROMPT, userPrompt, LLM_TIMEOUT_MS);
      const parsed = parseJsonBlock(content) as { items?: Array<{ id?: unknown; verdict?: unknown; reason?: unknown; suggestion?: unknown }> };
      if (!Array.isArray(parsed.items)) throw new Error("LLM 输出缺少 items 数组");
      const map: VerdictMap = new Map();
      for (const it of parsed.items) {
        const id = Number(it.id);
        const verdict = normStr(it.verdict).toLowerCase();
        if (!Number.isFinite(id) || (verdict !== "good" && verdict !== "bad")) continue;
        map.set(id, { verdict, reason: normStr(it.reason).slice(0, 490), suggestion: normStr(it.suggestion).slice(0, 490) });
      }
      const missing = logs.filter((l) => !map.has(l.id)).length;
      if (missing > 0) throw new Error(`LLM 输出遗漏 ${missing} 条 id`);
      return map;
    } catch (e) {
      lastErr = e;
      if (attempt < CHUNK_RETRY) console.warn(`   [重试] ${itemLabel} 调用失败一次: ${errBrief(e)}`);
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error(String(lastErr));
}

/** v1.1 每人点评单独小请求；失败用统计兜底文案，不拖垮整人 */
async function llmComment(ownerName: string, good: number, bad: number, badSamples: string[]): Promise<string> {
  const fallback = `本周抽查你的日志 ${good + bad} 条：好 ${good} 条、待改进 ${bad} 条。${bad > 0 ? "请补齐待改进日志的调整目的/依据与后续观察计划。" : "日志规范性良好，请保持。"}`;
  try {
    const user = `负责人：${ownerName}\n本周抽查评审统计：好=${good}，待改进=${bad}\n待改进代表样例：\n${badSamples.slice(0, 3).join("\n") || "（无）"}`;
    const c = await llmChat(COMMENT_PROMPT, user, COMMENT_TIMEOUT_MS);
    return (c || fallback).slice(0, 1990);
  } catch {
    return fallback;
  }
}

async function main(): Promise<void> {
  const startedAt = Date.now();
  const confirmWrite = process.argv.includes("--confirm-write");
  const purgeWeek = process.argv.includes("--purge-week");
  const windowEnd = getArg("window-end") || recentThursdayCst();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(windowEnd)) { console.log("[错误] --window-end 必须为 YYYY-MM-DD"); process.exit(1); }
  const weekStart = addDays(windowEnd, -6); // 周期起点=上周五（week_start 列语义=周期起点）
  const weekEnd = windowEnd;
  const model = normStr(process.env.AI_MODEL);

  console.log("=".repeat(60));
  console.log(`AI 运营日志周评 v1.3（周四23点·ItemID抽查×${SAMPLE_ITEMS}·周期五~四） ｜ 窗口 ${weekStart} ~ ${weekEnd} ｜ 模式: ${confirmWrite ? "confirm-write" : "dry-run（零LLM零写入）"}${purgeWeek ? " + purge-week" : ""}`);
  console.log("=".repeat(60));

  const db = await mysql.createConnection(dbConfig());
  let itemsSampled = 0, itemsFailed = 0, itemsWritten = 0, goodTotal = 0, badTotal = 0, ownersWritten = 0;
  try {
    const [members] = await db.query<MemberRow[]>(
      `SELECT name FROM dim_feishu_member WHERE employment_status = 'active' AND COALESCE(name,'') <> ''`,
    );
    const activeSet = new Set(members.map((m) => normStr(m.name)));

    const [logs] = await db.query<LogRow[]>(
      `SELECT id, DATE_FORMAT(log_date,'%Y-%m-%d') AS log_date, platform, store_id, store_name, store_key,
              item_id, msku, COALESCE(owner,'') AS owner, profit_level_snapshot, COALESCE(log_content,'') AS log_content
       FROM biz_product_operation_log
       WHERE log_date BETWEEN ? AND ? AND platform = 'walmart'`,
      [weekStart, weekEnd],
    );
    const [signals] = await db.query<SignalRow[]>(
      `SELECT DATE_FORMAT(signal_date,'%Y-%m-%d') AS signal_date, platform, store_key, item_id, msku,
              rule_name, trigger_reason, suggested_action
       FROM biz_product_rule_signal_daily
       WHERE signal_date BETWEEN ? AND ? AND platform = 'walmart'`,
      [weekStart, weekEnd],
    );
    const sigMap = new Map<string, string[]>();
    for (const s of signals) {
      const k = [s.signal_date, s.platform, normStr(s.store_key), normStr(s.item_id), normStr(s.msku)].join("|");
      if (!sigMap.has(k)) sigMap.set(k, []);
      sigMap.get(k)!.push(`${normStr(s.rule_name)}：${normStr(s.trigger_reason)}（建议：${normStr(s.suggested_action)}）`);
    }

    // 每人整周统计（供 summary 上下文列）
    const totalByOwner = new Map<string, number>();
    const substantiveByOwner = new Map<string, number>();
    const isSubstantive = (l: LogRow): boolean => {
      const c = normStr(l.log_content);
      return !!c && !NON_SUBSTANTIVE.has(c);
    };
    // v1.3：全部日志行按产品分组（含未填/无运营话术行——"该有的天数"一起看）
    const byItem = new Map<string, LogRow[]>();
    const substantiveItems = new Set<string>();
    for (const l of logs) {
      const o = normStr(l.owner);
      if (!o || !activeSet.has(o)) continue;
      totalByOwner.set(o, (totalByOwner.get(o) ?? 0) + 1);
      const ik = [normStr(l.store_key), normStr(l.item_id), normStr(l.msku)].join("|");
      if (!byItem.has(ik)) byItem.set(ik, []);
      byItem.get(ik)!.push(l);
      if (isSubstantive(l)) {
        substantiveByOwner.set(o, (substantiveByOwner.get(o) ?? 0) + 1);
        substantiveItems.add(ik);
      }
    }
    // v1.3：抽样池=周期内有过实质日志的产品；周期种子确定性洗牌（dry-run 与正式跑一致）
    const allKeys = Array.from(substantiveItems).sort();
    const rng = seededRng(`ops-log-review|${weekStart}`);
    for (let i = allKeys.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [allKeys[i], allKeys[j]] = [allKeys[j], allKeys[i]];
    }
    const sampled = allKeys.slice(0, SAMPLE_ITEMS);
    itemsSampled = sampled.length;
    console.log(`窗口日志行=${logs.length} ｜ 有实质日志产品=${allKeys.length} ｜ 抽查=${itemsSampled} 个 ItemID（种子=${weekStart}）`);

    if (!confirmWrite) {
      for (const ik of sampled) {
        const rows = byItem.get(ik)!;
        const subN = rows.filter((r) => isSubstantive(r)).length;
        console.log(`— [抽中] ${normStr(rows[0].msku)} ｜ ItemID ${normStr(rows[0].item_id)} ｜ ${normStr(rows[0].owner)} ｜ 行 ${rows.length}（实质 ${subN}，未填 ${rows.length - subN}）`);
      }
      console.log("[dry-run] 零 LLM 调用、零写入");
      return;
    }

    if (purgeWeek) {
      const [d1] = await db.query<mysql.ResultSetHeader>(`DELETE FROM ai_ops_log_review_item WHERE week_start = ?`, [weekStart]);
      const [d2] = await db.query<mysql.ResultSetHeader>(`DELETE FROM ai_ops_log_review_summary WHERE week_start = ?`, [weekStart]);
      console.log(`[purge-week] 已清除该周旧评级：item=${d1.affectedRows} summary=${d2.affectedRows}（AI层自产快照，口径重置）`);
    }

    // 逐产品评审
    const verdictByLogId: VerdictMap = new Map();
    const sampledLogsByOwner = new Map<string, LogRow[]>();
    for (const ik of sampled) {
      const rows = byItem.get(ik)!.sort((a, b) => a.log_date.localeCompare(b.log_date));
      const itemLabel = `${normStr(rows[0].msku)}(ItemID ${normStr(rows[0].item_id)})`;
      const owner = normStr(rows[rows.length - 1].owner);
      const subRows = rows.filter((r) => isSubstantive(r));
      const emptyRows = rows.filter((r) => !isSubstantive(r));
      // v1.3：未填/无运营话术行 → 系统直接判差（零LLM）
      for (const l of emptyRows) {
        verdictByLogId.set(l.id, {
          verdict: "bad",
          reason: normStr(l.log_content) ? "当日仅填无运营话术，未说明原因" : "当日未填写运营日志",
          suggestion: "补填当日动作、调整目的/依据与后续观察计划",
        });
      }
      const llmLogs: LlmLog[] = subRows.map((l) => {
        const k = [l.log_date, l.platform, normStr(l.store_key), normStr(l.item_id), normStr(l.msku)].join("|");
        return {
          id: l.id, date: l.log_date, msku: normStr(l.msku), itemId: normStr(l.item_id),
          profitLevel: normStr(l.profit_level_snapshot),
          signals: ((sigMap.get(k) ?? []).join("；") || "（当日无系统提醒）").slice(0, SIGNALS_EXCERPT_LEN),
          log: normStr(l.log_content).slice(0, LOG_EXCERPT_LEN),
        };
      });
      try {
        if (llmLogs.length > 0) {
          const part = await llmReviewItem(`${itemLabel}｜周期内有基础行${rows.length}天，实质填写${subRows.length}天，未填${emptyRows.length}天`, owner, llmLogs);
          for (const [k2, v2] of part) verdictByLogId.set(k2, v2);
        }
        for (const l of rows) {
          if (!sampledLogsByOwner.has(normStr(l.owner))) sampledLogsByOwner.set(normStr(l.owner), []);
          sampledLogsByOwner.get(normStr(l.owner))!.push(l);
        }
        console.log(`   ✓ ${itemLabel} ｜ ${owner} ｜ 实质${subRows.length}条AI评+未填${emptyRows.length}条规则判差`);
      } catch (e) {
        itemsFailed += 1;
        for (const l of emptyRows) verdictByLogId.delete(l.id); // 该产品整体跳过，未填行判定一并回收
        console.warn(`   [跳过] ${itemLabel}: ${errBrief(e)}`);
      }
    }

    // 写入明细
    for (const [owner, rows] of sampledLogsByOwner) {
      for (const l of rows) {
        const r0 = verdictByLogId.get(l.id);
        if (!r0) continue;
        const k = [l.log_date, l.platform, normStr(l.store_key), normStr(l.item_id), normStr(l.msku)].join("|");
        await db.query(
          `INSERT INTO ai_ops_log_review_item
             (week_start, owner_name, src_log_id, log_date, platform, store_id, store_name, item_id, msku,
              log_excerpt, signals_excerpt, verdict, reason, suggestion, llm_model)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON DUPLICATE KEY UPDATE
             verdict=VALUES(verdict), reason=VALUES(reason), suggestion=VALUES(suggestion),
             log_excerpt=VALUES(log_excerpt), signals_excerpt=VALUES(signals_excerpt), llm_model=VALUES(llm_model)`,
          [weekStart, owner, l.id, l.log_date, l.platform, normStr(l.store_id), normStr(l.store_name),
           normStr(l.item_id), normStr(l.msku), normStr(l.log_content).slice(0, LOG_EXCERPT_LEN),
           ((sigMap.get(k) ?? []).join("；")).slice(0, SIGNALS_EXCERPT_LEN),
           r0.verdict, r0.reason, r0.suggestion,
           r0.reason.startsWith("当日未填写") || r0.reason.startsWith("当日仅填") ? "rule_unfilled" : model],
        );
        itemsWritten += 1;
        if (r0.verdict === "good") goodTotal += 1; else badTotal += 1;
      }
    }

    // 每人汇总（仅本周被抽中的负责人）
    for (const [owner, rows] of sampledLogsByOwner) {
      const judged = rows.filter((l) => verdictByLogId.has(l.id));
      const good = judged.filter((l) => verdictByLogId.get(l.id)!.verdict === "good").length;
      const bad = judged.length - good;
      const badSamples = judged
        .filter((l) => verdictByLogId.get(l.id)!.verdict === "bad")
        .slice(0, 3)
        .map((l) => `${normStr(l.msku)}：${normStr(l.log_content).slice(0, 80)}（${verdictByLogId.get(l.id)!.reason}）`);
      const comment = await llmComment(owner, good, bad, badSamples);
      await db.query(
        `INSERT INTO ai_ops_log_review_summary
           (week_start, owner_name, total_logs, substantive_logs, reviewed_logs, good_count, bad_count, ai_comment, status, llm_model)
         VALUES (?,?,?,?,?,?,?,?,?,?)
         ON DUPLICATE KEY UPDATE
           total_logs=VALUES(total_logs), substantive_logs=VALUES(substantive_logs), reviewed_logs=VALUES(reviewed_logs),
           good_count=VALUES(good_count), bad_count=VALUES(bad_count), ai_comment=VALUES(ai_comment),
           status=VALUES(status), llm_model=VALUES(llm_model)`,
        [weekStart, owner, totalByOwner.get(owner) ?? 0, substantiveByOwner.get(owner) ?? 0, judged.length, good, bad,
         comment, "success", model],
      );
      ownersWritten += 1;
      console.log(`   汇总 ${owner}: 抽中 ${judged.length} 条 good=${good} bad=${bad}`);
    }
  } finally {
    await db.end().catch(() => undefined);
    console.log(`SUMMARY_JSON=${JSON.stringify({
      task: TASK, version: "v1.3.1_two_elements", weekStart, weekEnd, confirmWrite,
      itemsSampled, itemsFailed, ownersWritten, itemsWritten, goodTotal, badTotal,
      durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(1)),
    })}`);
  }
  if (itemsFailed > 0) process.exitCode = 1;
}

main().catch((e) => {
  console.error(`[${TASK}] 运行失败:`, e instanceof Error ? e.message : String(e));
  process.exit(1);
});
