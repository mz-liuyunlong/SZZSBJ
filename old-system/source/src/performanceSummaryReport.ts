import "dotenv/config";
const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;
import currentReport from "../config/currentReportFieldMapping.json";
import { FeishuSheetWriter } from "./feishuSheetWriter";
import { TableOperationLogger } from "./tableOperationLogger";
import * as mysql from "mysql2/promise";

// ── 常量 ──────────────────────────────────────────────────────────────────────
// 下游迁移（脱离飞书 5月销售明细_复盘 / sheet_id=<REDACTED_FEISHU_SHEET_ID>）：
// 改读 raw_feishu_table（sheet_id='<REDACTED_FEISHU_SHEET_ID>'），该数据由 syncOrderProfitDaily.ts
// 每日生成，负责人字段已是 dim_product.owner 当前值，字段口径与旧飞书表一致（日期/店铺/负责人/
// 今日销量/今日销售额（$）/毛利润（$）），不再调用飞书 API 读取活的飞书表。
const DATA_SOURCE_LABEL = "raw_feishu_table(sheet_id=order_profit_daily)";
const EXCLUDED_STORES = ["CN2502-悦斯电子(陈文胜）"];
// 批B(2026-07-11): webhook 迁至环境变量（原硬编码违反密钥统一读环境变量铁律，
// 部署时需在 .env 增加 FEISHU_PERF_WEBHOOK_URL=原值）
const FEISHU_WEBHOOK = (process.env.FEISHU_PERF_WEBHOOK_URL ?? "").trim();
// 批B: 统一发送模块（重试/降级）；测试模式与App机器人路径(2026-07-11)
import { sendWithRetry, sendCardWithFallbackToChat, getTestChatId } from "./feishuNotify";
// 发送路径开关：app=应用机器人发 FEISHU_PERF_CHAT_ID；webhook 或留空=现有 webhook 路径（回滚通道）
const PERF_PROVIDER = (process.env.FEISHU_PERF_PROVIDER ?? "").trim().toLowerCase();
const PERF_CHAT_ID = (process.env.FEISHU_PERF_CHAT_ID ?? "").trim();
// 批B收口: 重试/降级为可关开关（1=启用；留空或0=保持原单次卡片发送逻辑，即行为回滚开关）
// 注意: FEISHU_PERF_WEBHOOK_URL 是必需的密钥迁移配置，不属于回滚开关
const RETRY_ENABLED = (process.env.FEISHU_PERF_RETRY_ENABLED ?? "").trim() === "1";
// 批B收口: 显式 --dry-run——查询聚合正常、输出卡片结构摘要与纯文本预览、
// 不调用飞书接口、不写表格操作日志；cron 现有无参数行为=真实发送（不改cron）
const DRY_RUN = process.argv.includes("--dry-run");
// 测试模式：--test-send 强制只发 FEISHU_NOTIFY_TEST_CHAT_ID（应用机器人），不走 webhook/生产群
const TEST_SEND = process.argv.includes("--test-send");
if (DRY_RUN && TEST_SEND) {
  console.log("[错误] --dry-run 与 --test-send 禁止同时使用（语义歧义）");
  process.exit(1);
}
if (TEST_SEND && process.argv.includes("--send")) {
  console.log("[错误] --send 与 --test-send 禁止同时使用");
  process.exit(1);
}
if (process.argv.includes("--force-preview-test") && !TEST_SEND) {
  console.log("[错误] --force-preview-test 必须配合 --test-send 使用");
  process.exit(1);
}
const SPREADSHEET_TOKEN = currentReport.spreadsheetToken;
const TIME_ZONE = "Asia/Shanghai";

function dbConfig() {
  return {
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  };
}

type ReportMode = "daily" | "weekly" | "monthly";

// ── 工具函数 ──────────────────────────────────────────────────────────────────
function unwrapCell(value: unknown): unknown {
  if (Array.isArray(value)) return value.map((v) => String(unwrapCell(v) ?? "")).join("");
  if (value && typeof value === "object") {
    const r = value as Record<string, unknown>;
    for (const k of ["text", "value", "formattedValue", "string", "number", "result"]) {
      if (r[k] !== undefined && r[k] !== null) return unwrapCell(r[k]);
    }
    return "";
  }
  return value;
}

function toText(value: unknown): string {
  return String(unwrapCell(value) ?? "").trim();
}

function toNumber(value: unknown): number {
  const s = toText(value).replace(/,/g, "");
  const n = parseFloat(s);
  return isNaN(n) ? 0 : n;
}

function parseDateText(value: unknown): string | null {
  const text = toText(value);
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(text);
  return m ? `${m[1]}-${m[2]}-${m[3]}` : null;
}

function getChinaDateText(date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const y = parts.find((p) => p.type === "year")?.value ?? "";
  const mo = parts.find((p) => p.type === "month")?.value ?? "";
  const d = parts.find((p) => p.type === "day")?.value ?? "";
  return `${y}-${mo}-${d}`;
}

function addDays(dateText: string, days: number): string {
  const [y, m, d] = dateText.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + days);
  return dt.toISOString().slice(0, 10);
}

/** 向前找最近一个周五（业务周结束日）*/
function getLastFriday(todayShanghai: string): string {
  const [y, m, d] = todayShanghai.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  for (let i = 1; i <= 14; i++) {
    dt.setUTCDate(dt.getUTCDate() - 1);
    if (dt.getUTCDay() === 5) return dt.toISOString().slice(0, 10); // 5=Friday
  }
  throw new Error("无法找到最近一个周五");
}

/** 业务周起始：上周五往前6天 = 上周六 */
function getWeekStart(lastFriday: string): string {
  return addDays(lastFriday, -6);
}

/** 上个月第一天 */
function getPrevMonthStart(todayShanghai: string): string {
  const [y, m] = todayShanghai.split("-").map(Number);
  const prevMonth = m === 1 ? 12 : m - 1;
  const prevYear = m === 1 ? y - 1 : y;
  return `${prevYear}-${String(prevMonth).padStart(2, "0")}-01`;
}

/** 上个月最后一天 */
function getPrevMonthEnd(todayShanghai: string): string {
  const [y, m] = todayShanghai.split("-").map(Number);
  // 本月第一天的前一天 = 上个月最后一天
  const dt = new Date(Date.UTC(y, m - 1, 1));
  dt.setUTCDate(dt.getUTCDate() - 1);
  return dt.toISOString().slice(0, 10);
}

// ── 数据行接口 ─────────────────────────────────────────────────────────────────
interface DataRow {
  date: string;
  store: string;
  owner: string;
  orders: number;
  revenue: number;
  profit: number;
}

interface Summary {
  orders: number;
  revenue: number;
  profit: number;
}

function emptySummary(): Summary {
  return { orders: 0, revenue: 0, profit: 0 };
}

function addToSummary(s: Summary, row: DataRow): void {
  s.orders += row.orders;
  s.revenue += row.revenue;
  s.profit += row.profit;
}

// ── 读数据（MySQL：raw_feishu_table, sheet_id='<REDACTED_FEISHU_SHEET_ID>'）──────────────
interface OrderProfitDailyRowJson {
  "日期"?: unknown;
  "店铺"?: unknown;
  "负责人"?: unknown;
  "今日销量"?: unknown;
  "今日销售额（$）"?: unknown;
  "毛利润（$）"?: unknown;
}

async function readDetailRows(startDate: string, endDate: string): Promise<DataRow[]> {
  const db = await mysql.createConnection(dbConfig());
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT row_json FROM raw_feishu_table
       WHERE sheet_id = '<REDACTED_FEISHU_SHEET_ID>'
         AND data_date BETWEEN ? AND ?
       ORDER BY data_date`,
      [startDate, endDate],
    );

    const result: DataRow[] = [];
    for (const r of rows) {
      const rawJson = (r as { row_json: unknown }).row_json;
      const json: OrderProfitDailyRowJson =
        typeof rawJson === "string" ? JSON.parse(rawJson) : (rawJson as OrderProfitDailyRowJson) ?? {};

      const date = parseDateText(json["日期"]);
      const store = toText(json["店铺"]);
      if (!date || !store) continue;

      result.push({
        date,
        store,
        owner: toText(json["负责人"]) || "未分配",
        orders: toNumber(json["今日销量"]),
        revenue: toNumber(json["今日销售额（$）"]),
        profit: toNumber(json["毛利润（$）"]),
      });
    }

    console.log(`读取 ${DATA_SOURCE_LABEL}，日期范围 ${startDate}~${endDate}，有效行=${result.length}`);
    return result;
  } finally {
    await db.end();
  }
}

// ── 格式化 & 输出 ──────────────────────────────────────────────────────────────
function fmt(n: number, decimals = 2): string {
  return n.toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function printSection(
  title: string,
  dateRange: string,
  byStore: Map<string, Summary>,
  byOwner: Map<string, Summary>,
): void {
  const LINE = "─".repeat(62);
  console.log(`\n${"═".repeat(62)}`);
  console.log(`  ${title}  (${dateRange})`);
  console.log(`${"═".repeat(62)}`);

  const storeEntries = [...byStore.entries()].sort((a, b) => b[1].revenue - a[1].revenue);
  let totalOrders = 0, totalRevenue = 0, totalProfit = 0;

  console.log("\n【店铺业绩与利润】");
  console.log(LINE);
  console.log(`${"店铺".padEnd(28)}${"订单".padStart(8)}${"销售额($)".padStart(14)}${"毛利润($)".padStart(14)}${"毛利率".padStart(8)}`);
  console.log(LINE);
  for (const [store, s] of storeEntries) {
    const margin = s.revenue > 0 ? (s.profit / s.revenue) * 100 : 0;
    const name = store.length > 14 ? store.slice(0, 13) + "…" : store;
    console.log(`${name.padEnd(28)}${String(s.orders).padStart(8)}${fmt(s.revenue).padStart(14)}${fmt(s.profit).padStart(14)}${(fmt(margin, 1) + "%").padStart(8)}`);
    totalOrders += s.orders;
    totalRevenue += s.revenue;
    totalProfit += s.profit;
  }
  const totalMargin = totalRevenue > 0 ? (totalProfit / totalRevenue) * 100 : 0;
  console.log(LINE);
  console.log(`${"合计".padEnd(28)}${String(totalOrders).padStart(8)}${fmt(totalRevenue).padStart(14)}${fmt(totalProfit).padStart(14)}${(fmt(totalMargin, 1) + "%").padStart(8)}`);

  const ownerEntries = [...byOwner.entries()].sort((a, b) => b[1].revenue - a[1].revenue);
  console.log("\n【个人业绩与利润】");
  console.log(LINE);
  console.log(`${"负责人".padEnd(16)}${"订单".padStart(8)}${"销售额($)".padStart(14)}${"毛利润($)".padStart(14)}${"毛利率".padStart(8)}`);
  console.log(LINE);
  for (const [owner, s] of ownerEntries) {
    const margin = s.revenue > 0 ? (s.profit / s.revenue) * 100 : 0;
    console.log(`${owner.padEnd(16)}${String(s.orders).padStart(8)}${fmt(s.revenue).padStart(14)}${fmt(s.profit).padStart(14)}${(fmt(margin, 1) + "%").padStart(8)}`);
  }
  console.log(LINE);
  console.log(`${"合计".padEnd(16)}${String(totalOrders).padStart(8)}${fmt(totalRevenue).padStart(14)}${fmt(totalProfit).padStart(14)}${(fmt(totalMargin, 1) + "%").padStart(8)}`);
}

/** 构建飞书互动卡片并发送 */
async function sendFeishuCard(
  title: string,
  dateRange: string,
  byStore: Map<string, Summary>,
  byOwner: Map<string, Summary>,
): Promise<void> {
  const storeEntries = [...byStore.entries()].sort((a, b) => b[1].revenue - a[1].revenue);
  let totalOrders = 0, totalRevenue = 0, totalProfit = 0;

  // 店铺业绩行
  const storeLines: string[] = [];
  for (const [store, s] of storeEntries) {
    const margin = s.revenue > 0 ? (s.profit / s.revenue) * 100 : 0;
    const shortName = store.replace(/[（(][^）)]*[）)]/g, "").trim();
    storeLines.push(`**${shortName}**　订单 ${s.orders}　销售 $${fmt(s.revenue)}　利润 $${fmt(s.profit)}　毛利率 ${fmt(margin, 1)}%`);
    totalOrders += s.orders;
    totalRevenue += s.revenue;
    totalProfit += s.profit;
  }
  const totalMargin = totalRevenue > 0 ? (totalProfit / totalRevenue) * 100 : 0;
  storeLines.push(`**合计**　订单 **${totalOrders}**　销售 **$${fmt(totalRevenue)}**　利润 **$${fmt(totalProfit)}**　毛利率 **${fmt(totalMargin, 1)}%**`);

  // 个人业绩行
  const ownerEntries = [...byOwner.entries()].sort((a, b) => b[1].revenue - a[1].revenue);
  const ownerLines: string[] = [];
  for (const [owner, s] of ownerEntries) {
    const margin = s.revenue > 0 ? (s.profit / s.revenue) * 100 : 0;
    ownerLines.push(`**${owner}**　订单 ${s.orders}　销售 $${fmt(s.revenue)}　利润 $${fmt(s.profit)}　毛利率 ${fmt(margin, 1)}%`);
  }
  ownerLines.push(`**合计**　订单 **${totalOrders}**　销售 **$${fmt(totalRevenue)}**　利润 **$${fmt(totalProfit)}**　毛利率 **${fmt(totalMargin, 1)}%**`);

  const card = {
    header: {
      title: { tag: "plain_text", content: `📊 业绩${title} | ${dateRange}` },
      template: title === "日报" ? "blue" : title === "周报" ? "green" : "orange",
    },
    elements: [
      { tag: "markdown", content: "**📦 店铺业绩**" },
      { tag: "markdown", content: storeLines.join("\n") },
      { tag: "hr" },
      { tag: "markdown", content: "**👤 个人业绩**" },
      { tag: "markdown", content: ownerLines.join("\n") },
      {
        tag: "note",
        elements: [{ tag: "plain_text", content: `生成时间: ${new Date().toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}` }],
      },
    ],
  };

  const plainText = [
    `📊 业绩${title} | ${dateRange}`,
    "",
    "📦 店铺业绩",
    ...storeLines.map((l) => l.replace(/\*\*/g, "")),
    "",
    "👤 个人业绩",
    ...ownerLines.map((l) => l.replace(/\*\*/g, "")),
  ].join("\n");

  // ── 批B收口: --dry-run 零发送零写入 ──
  if (DRY_RUN) {
    console.log("\n[dry-run] 卡片结构摘要:");
    console.log(`  header.title=${(card.header.title as { content: string }).content} | template=${card.header.template}`);
    console.log(`  elements=${card.elements.length} 个(markdown x${card.elements.filter((e) => (e as { tag: string }).tag === "markdown").length}, hr, note)`);
    console.log("[dry-run] 纯文本降级预览:");
    console.log("─".repeat(60));
    console.log(plainText);
    console.log("─".repeat(60));
    console.log("[dry-run] 不调用飞书接口。");
    return;
  }

  // ── 测试模式：只发测试群（应用机器人），卡片失败降级纯文本，不走 webhook ──
  if (TEST_SEND) {
    (card.header.title as { content: string }).content = `【测试】📊 业绩${title} | ${dateRange}`;
    const testChat = getTestChatId();
    if (!testChat) throw new Error("缺少 FEISHU_NOTIFY_TEST_CHAT_ID 环境变量");
    const r = await sendCardWithFallbackToChat(`【测试】业绩${title}`, testChat,
      card as unknown as Record<string, unknown>, `【测试】${plainText}`);
    console.log(`测试发送计数: ${JSON.stringify({ cardOk: r.cardOk, fallbackUsed: r.fallbackUsed, retryCount: r.retryCount, ambiguousDelivery: r.ambiguousDelivery })}`);
    if (!r.ok) throw new Error(`测试群发送失败: ${r.error ?? ""}`);
    console.log("NOTIFY_TEST_SENT=1");
    return;
  }

  // ── App机器人生产路径（FEISHU_PERF_PROVIDER=app）；webhook/留空=原路径（回滚通道） ──
  if (PERF_PROVIDER === "app") {
    if (!PERF_CHAT_ID) throw new Error("FEISHU_PERF_PROVIDER=app 但缺少 FEISHU_PERF_CHAT_ID 环境变量");
    const r = await sendCardWithFallbackToChat(`业绩${title}(App)`, PERF_CHAT_ID,
      card as unknown as Record<string, unknown>, plainText);
    console.log(`发送计数: ${JSON.stringify({ provider: "app", cardOk: r.cardOk, fallbackUsed: r.fallbackUsed, retryCount: r.retryCount, ambiguousDelivery: r.ambiguousDelivery })}`);
    if (!r.ok) throw new Error(`飞书发送失败(App卡片与纯文本降级均失败): ${r.error ?? ""}`);
    return;
  }

  // ── 批B: 行为开关——RETRY_ENABLED 未启用时保持原单次卡片发送逻辑 ──
  if (!RETRY_ENABLED) {
    const res = await axios.post(FEISHU_WEBHOOK, { msg_type: "interactive", card }, { timeout: 15000 });
    const d = res.data as Record<string, unknown>;
    if (d?.code !== 0 && d?.StatusCode !== 0) {
      throw new Error(`飞书发送失败: code=${d?.code} msg=${d?.msg}`);
    }
    console.log("飞书群消息发送成功（互动卡片，原单次发送路径）");
    return;
  }

  // ── 批B: 19006/11232/429 修复——分类重试 + 卡片失败降级纯文本 + 计数 ──
  // 重复发送边界：收到明确成功响应后绝不重复发送；网络超时类结果未知场景属
  // at-least-once，理论上存在重复送达可能（ambiguousDelivery=true 标记，不承诺绝对幂等）。
  const counters = {
    card_success: 0, card_failed: 0,
    text_fallback_success: 0, text_fallback_failed: 0,
    retry_count: 0, ambiguousDelivery: false,
  };
  const postCard = async () => {
    const res = await axios.post(FEISHU_WEBHOOK, { msg_type: "interactive", card }, { timeout: 15000 });
    const d = res.data as Record<string, unknown>;
    if (d?.code !== 0 && d?.StatusCode !== 0) {
      const err: Error & { feishuCode?: unknown } = new Error("card send failed");
      err.feishuCode = d?.code;
      (err as unknown as { response: unknown }).response = { data: d };
      throw err;
    }
  };
  const r1 = await sendWithRetry(`业绩${title}卡片`, postCard);
  counters.retry_count += r1.retryCount;
  counters.ambiguousDelivery = counters.ambiguousDelivery || r1.ambiguousDelivery;
  if (r1.ok) {
    counters.card_success = 1;
    console.log("飞书群消息发送成功（互动卡片）");
  } else {
    counters.card_failed = 1;
    console.log(`卡片最终失败(${r1.error})，降级为纯文本摘要`);
    const fallbackText = `${plainText}\n（卡片发送失败，降级纯文本）`;
    const postText = async () => {
      const res = await axios.post(FEISHU_WEBHOOK, { msg_type: "text", content: { text: fallbackText } }, { timeout: 15000 });
      const d = res.data as Record<string, unknown>;
      if (d?.code !== 0 && d?.StatusCode !== 0) {
        const err: Error & { feishuCode?: unknown } = new Error("text fallback failed");
        err.feishuCode = d?.code;
        (err as unknown as { response: unknown }).response = { data: d };
        throw err;
      }
    };
    const r2 = await sendWithRetry(`业绩${title}纯文本降级`, postText);
    counters.retry_count += r2.retryCount;
    counters.ambiguousDelivery = counters.ambiguousDelivery || r2.ambiguousDelivery;
    if (r2.ok) {
      counters.text_fallback_success = 1;
      console.log("飞书群消息发送成功（纯文本降级）");
    } else {
      counters.text_fallback_failed = 1;
      console.log(`发送计数: ${JSON.stringify(counters)}`);
      throw new Error(`飞书发送失败(卡片与纯文本降级均失败): ${r2.error}`);
    }
  }
  console.log(`发送计数: ${JSON.stringify(counters)}`);
}

function aggregate(rows: DataRow[]): { byStore: Map<string, Summary>; byOwner: Map<string, Summary> } {
  const byStore = new Map<string, Summary>();
  const byOwner = new Map<string, Summary>();

  for (const row of rows) {
    if (!byStore.has(row.store)) byStore.set(row.store, emptySummary());
    if (!byOwner.has(row.owner)) byOwner.set(row.owner, emptySummary());
    addToSummary(byStore.get(row.store)!, row);
    addToSummary(byOwner.get(row.owner)!, row);
  }

  return { byStore, byOwner };
}

function parseMode(): ReportMode {
  const arg = process.argv.find((a) => a.startsWith("--mode="));
  const value = arg ? arg.replace("--mode=", "") : "daily";
  if (value === "daily" || value === "weekly" || value === "monthly") return value;
  throw new Error(`未知 --mode=${value}，支持: daily / weekly / monthly`);
}

function createRunId(): string {
  return `run_${new Date().toISOString().replace(/[-:.TZ]/g, "")}_${Math.random().toString(36).slice(2, 8)}`;
}

// ── 主函数 ────────────────────────────────────────────────────────────────────
async function main(): Promise<void> {
  const startedAt = Date.now();
  const runId = createRunId();
  const mode = parseMode();
  const todayShanghai = getChinaDateText();

  let title: string;
  let startDate: string;
  let endDate: string;

  if (mode === "daily") {
    startDate = addDays(todayShanghai, -3);
    endDate = startDate;
    title = "日报";
  } else if (mode === "weekly") {
    const lastFriday = getLastFriday(todayShanghai);
    startDate = getWeekStart(lastFriday);
    endDate = lastFriday;
    title = "周报";
  } else {
    startDate = getPrevMonthStart(todayShanghai);
    endDate = getPrevMonthEnd(todayShanghai);
    title = "月报";
  }

  const dateRange = startDate === endDate ? startDate : `${startDate} ~ ${endDate}`;

  console.log(`业绩汇总播报 [${title}]`);
  console.log(`生成时间(上海): ${todayShanghai}`);
  console.log(`播报范围: ${dateRange}`);
  console.log(`读取数据源: ${DATA_SOURCE_LABEL}`);
  if (TEST_SEND) console.log("模式: test-send（仅应用机器人测试群）");

  const writer = new FeishuSheetWriter();
  const logger = new TableOperationLogger(writer, {
    spreadsheetToken: SPREADSHEET_TOKEN,
    logSheetId: (currentReport.sheets as Record<string, string>)["表格操作日志"],
    dryRun: false,
    confirmWrite: true,
  });

  let status = "success";
  let errorMessage = "";
  let fetchedCount = 0;

  try {
    const allRows = await readDetailRows(startDate, endDate);
    console.log(`共读取有效行: ${allRows.length}`);
    fetchedCount = allRows.length;

    const filtered = allRows.filter((r) => r.date >= startDate && r.date <= endDate && !EXCLUDED_STORES.includes(r.store));
    console.log(`范围内有效行: ${filtered.length}`);

    if (filtered.length === 0) {
      if (TEST_SEND) {
        // 空状态也必须发送一条测试消息（验证发送通道），不伪造业务明细
        const testChat = getTestChatId();
        if (!testChat) throw new Error("缺少 FEISHU_NOTIFY_TEST_CHAT_ID 环境变量");
        const emptyText = [
          `【测试】业绩${title} | ${dateRange}`,
          "当前统计日期无有效数据。",
          "此消息仅用于验证应用机器人发送通道。",
        ].join("\n");
        const r0 = await sendCardWithFallbackToChat(`【测试】业绩${title}(空状态)`, testChat, {
          header: { title: { tag: "plain_text", content: `【测试】📊 业绩${title} | ${dateRange}` }, template: "grey" },
          elements: [{ tag: "markdown", content: emptyText }],
        }, emptyText);
        if (!r0.ok) throw new Error(`测试群发送失败: ${r0.error ?? ""}`);
        console.log("NOTIFY_TEST_SENT=1");
        status = "test_send_success";
        return;
      }
      console.log(`\n${title} (${dateRange}): 无数据`);
      status = "success";
      return;
    }

    const { byStore, byOwner } = aggregate(filtered);
    printSection(title, dateRange, byStore, byOwner);

    if (!DRY_RUN && !TEST_SEND && PERF_PROVIDER !== "app" && !FEISHU_WEBHOOK) {
      throw new Error("缺少 FEISHU_PERF_WEBHOOK_URL 环境变量（业绩播报群 webhook，部署时从原硬编码值迁入 .env）");
    }
    console.log(DRY_RUN ? "\n[dry-run] 生成消息预览..." : "\n正在发送飞书群消息...");
    await sendFeishuCard(title, dateRange, byStore, byOwner);

    console.log(`\n${title}播报完成`);
  } catch (err) {
    status = "failed";
    errorMessage = err instanceof Error ? err.message : String(err);
    console.error("业绩汇总播报失败:", errorMessage);
    process.exitCode = 1;
  } finally {
    if (DRY_RUN || TEST_SEND) {
      console.log(`[${DRY_RUN ? "dry-run" : "test-send"}] 跳过表格操作日志写入。`);
      return;
    }
    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: `业绩汇总播报(${title})`,
        targetSheet: "飞书机器人",
        operationType: "notify:send",
        dataSource: DATA_SOURCE_LABEL,
        dateRange,
        fetchedCount,
        writtenCount: 0,
        updatedCount: 0,
        skippedCount: 0,
        failedCount: status === "failed" ? 1 : 0,
        status,
        errorMessage,
        durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
        runId,
        environment: "server",
        remark: `业绩${title}播报，范围=${dateRange}，读取行数=${fetchedCount}` +
          (errorMessage ? `，失败原因=${errorMessage}` : ""),
      });
    } catch (logError) {
      console.log(`记录操作日志失败: ${logError instanceof Error ? logError.message : String(logError)}`);
    }
  }
}

main().catch((err) => {
  console.error("业绩汇总播报失败:", err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
