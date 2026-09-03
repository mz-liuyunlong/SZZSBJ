/**
 * gptKwOwnerSummary.ts — 🔍 关键词分析链接·一次性按负责人汇总提醒（2026-07-29 需求方拍板）
 *
 * 背景：关键词链接监督上线时存量约 1097 个产品无链接，一次性全量按 ItemID 扣分不合理。
 * 拍板口径：
 *   - 存量先发"一次性、按负责人汇总"的提醒（每人名下多少产品、已填/待补多少），本次【不扣分】。
 *   - 归档产品不算、CS 产品要算（与循环监督 fetchGptKwMissing 口径一致：active + 有负责人 + 未配 keyword 链接）。
 *   - 本次提醒同时"起表"（在 event_gpt_kw_missing_alert 建首轮 first_notified），
 *     使下一个正式 cron（周四）把仍未补的升二次提醒并扣 5 分（=达标周四扣分）。
 *   - 通道复用 FEISHU_UNMATCHED_CHAT_IDS（两个管理群，应用机器人）。
 *
 * 用法：
 *   npx ts-node src/gptKwOwnerSummary.ts               # dry-run：汇总预览，零发送零写入
 *   npx ts-node src/gptKwOwnerSummary.ts --send        # 真实发送 + 起表(建首轮，不扣分)
 *   npx ts-node src/gptKwOwnerSummary.ts --test-card   # 卡片只发测试群，零写入
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";
import {
  getTestChatId, mirrorToTestEnabled, parseListEnv, sendCardWithFallbackToChat,
} from "./feishuNotify";

const PRODUCT_MANAGEMENT_URL = "http://42.193.254.170/admin/#/feishu-raw-sales-data";
const DEDUCT_POINTS = 5;
const CHAT_IDS_ENV = "FEISHU_UNMATCHED_CHAT_IDS";
const DETAIL_LIMIT = 80;

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
function getErrorMessage(e: unknown): string { return e instanceof Error ? e.message : String(e); }
function normStr(v: unknown): string { return String(v ?? "").trim(); }
function todayCst(): string { return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(new Date()); }

interface OwnerStat extends mysql.RowDataPacket { owner_name: string; total: number; filled: number; }
interface MissRow extends mysql.RowDataPacket {
  platform: string; store_id: string; store_name: string | null;
  item_id: string; msku: string; product_name: string | null;
}

// 与 unmatchedOwnerNotify.fetchGptKwMissing 口径一致：active + 非UNPUBLISHED + 有负责人 + 未配 keyword 链接
const KW_MISSING_EXISTS = `NOT EXISTS (SELECT 1 FROM dim_product_gpt_link g
  WHERE g.item_id = p.item_id AND g.link_type = 'keyword' AND g.url IS NOT NULL AND g.url <> '')`;
const OWNED_ACTIVE = `p.item_id IS NOT NULL AND p.item_id <> ''
  AND COALESCE(p.product_management_status,'active')='active'
  AND COALESCE(p.walmart_publish_status,'') <> 'UNPUBLISHED'
  AND p.owner IS NOT NULL AND TRIM(p.owner) <> '' AND p.owner <> '未分配'`;

async function fetchOwnerStats(db: mysql.Connection): Promise<OwnerStat[]> {
  const [rows] = await db.query<OwnerStat[]>(
    `SELECT p.owner AS owner_name,
            COUNT(*) AS total,
            SUM(CASE WHEN EXISTS (SELECT 1 FROM dim_product_gpt_link g
                 WHERE g.item_id = p.item_id AND g.link_type='keyword' AND g.url IS NOT NULL AND g.url <> '')
                 THEN 1 ELSE 0 END) AS filled
     FROM dim_product p
     WHERE ${OWNED_ACTIVE}
     GROUP BY p.owner
     HAVING (total - filled) > 0
     ORDER BY (total - filled) DESC, total DESC`,
  );
  return rows;
}

async function fetchMissing(db: mysql.Connection): Promise<MissRow[]> {
  const [rows] = await db.query<MissRow[]>(
    `SELECT p.platform, p.store_id, p.store_name, p.item_id, p.msku,
            COALESCE(p.product_name, p.item_name, '') AS product_name
     FROM dim_product p
     WHERE ${OWNED_ACTIVE} AND ${KW_MISSING_EXISTS}
     ORDER BY p.owner, p.item_id, p.msku`,
  );
  return rows;
}

function buildCard(dateStr: string, chargeHint: string, stats: OwnerStat[], missTotal: number, testPrefix: boolean): { card: Record<string, unknown>; fallbackText: string } {
  const prefix = testPrefix ? "【测试】" : "";
  const title = `${prefix}📋 产品管理提醒通知 · 关键词分析链接待补（一次性提醒） ｜ ${dateStr}`;
  const elements: Record<string, unknown>[] = [];
  const fb: string[] = [title];
  const totalOwners = stats.length;
  const meta = `**待补关键词链接** <font color='red'>**${missTotal}**</font> 个 · 涉及 **${totalOwners}** 位负责人`;
  elements.push({ tag: "div", text: { tag: "lark_md", content: meta } });
  elements.push({ tag: "div", text: { tag: "lark_md", content: `请到「产品管理页 · GPT分析」为名下产品补齐 🔍 关键词分析链接；**${chargeHint} 起，未补的每个产品扣 ${DEDUCT_POINTS} 分（归负责人）**。归档产品无需处理，CS 测品同样需要。` } });
  elements.push({ tag: "hr" });
  fb.push(`待补关键词链接 ${missTotal} 个 · ${totalOwners} 位负责人 · ${chargeHint}起未补每个扣${DEDUCT_POINTS}分`);

  const lines: string[] = ["**按负责人（待补多的在前）**"];
  fb.push("", "按负责人：");
  let shown = 0;
  for (const s of stats) {
    if (shown >= DETAIL_LIMIT) break;
    const total = Number(s.total), filled = Number(s.filled), miss = total - filled;
    lines.push(`**${normStr(s.owner_name) || "-"}**：共 ${total} 个 · 已填 ${filled} · <font color='red'>**待补 ${miss}**</font>`);
    fb.push(`${normStr(s.owner_name) || "-"}：共 ${total} · 已填 ${filled} · 待补 ${miss}`);
    shown += 1;
  }
  if (stats.length > DETAIL_LIMIT) lines.push(`…其余 ${stats.length - DETAIL_LIMIT} 位负责人请到产品管理页查看`);
  elements.push({ tag: "div", text: { tag: "lark_md", content: lines.join("\n") } });
  elements.push({ tag: "hr" });
  elements.push({ tag: "action", actions: [{ tag: "button", text: { tag: "plain_text", content: "去产品管理页补链接" }, type: "primary", url: PRODUCT_MANAGEMENT_URL }] });
  elements.push({ tag: "note", elements: [{ tag: "plain_text", content: `口径：active（排除归档）且有负责人的产品需在 GPT分析 配置关键词分析链接；CS 测品同样需要。本次仅提醒不扣分，${chargeHint}起正式扣分。` }] });
  fb.push("", `页面：${PRODUCT_MANAGEMENT_URL}`);

  return {
    card: { config: { wide_screen_mode: true }, header: { template: "orange", title: { tag: "plain_text", content: title } }, elements },
    fallbackText: fb.join("\n"),
  };
}

// 起表：为待补产品在 event_gpt_kw_missing_alert 建首轮（first_notified），使周四正式cron升二提扣分。不扣分、不改已有轮次的 first_notified。
async function seedCycles(db: mysql.Connection, miss: MissRow[]): Promise<number> {
  const today = todayCst();
  let n = 0;
  for (const it of miss) {
    const [r] = await db.query<mysql.ResultSetHeader>(
      `INSERT INTO event_gpt_kw_missing_alert
         (platform, store_id, store_name, item_id, msku, product_name, cycle_start_date, first_notified_at, status)
       VALUES (?, ?, ?, ?, ?, ?, ?, NOW(), 'open')
       ON DUPLICATE KEY UPDATE first_notified_at = COALESCE(first_notified_at, NOW())`,
      [normStr(it.platform) || "walmart", normStr(it.store_id), normStr(it.store_name), normStr(it.item_id), normStr(it.msku), normStr(it.product_name), today],
    );
    n += r.affectedRows > 0 ? 1 : 0;
  }
  return n;
}

async function main(): Promise<void> {
  const startedAt = Date.now();
  const doSend = process.argv.includes("--send");
  const testCard = process.argv.includes("--test-card");
  if (testCard && doSend) { console.log("[错误] --test-card 与 --send 禁止同时使用"); process.exit(1); }
  const dateStr = todayCst();
  // 周四扣分提示（本次为周三一次性提醒，下一个正式cron=周四）
  const chargeHint = "周四(07-30)";
  console.log("=".repeat(56));
  console.log(`🔍 关键词链接一次性按负责人汇总 · ${testCard ? "test-card" : doSend ? "真实发送+起表" : "dry-run"}`);
  console.log("=".repeat(56));

  let status = doSend ? "success" : "dry-run"; let errorMessage = ""; let extra: Record<string, unknown> = {};
  const db = await mysql.createConnection(dbConfig());
  try {
    const stats = await fetchOwnerStats(db);
    const miss = await fetchMissing(db);
    const missTotal = miss.length;
    console.log(`待补关键词链接=${missTotal} ｜ 负责人=${stats.length}`);
    const bundle = buildCard(dateStr, chargeHint, stats, missTotal, testCard);

    if (testCard) {
      const r = await sendCardWithFallbackToChat("关键词汇总-测试预览", getTestChatId(), bundle.card, bundle.fallbackText);
      console.log(`[test-card] ok=${r.ok} cardOk=${r.cardOk} fallbackUsed=${r.fallbackUsed}${r.error ? ` error=${r.error}` : ""}`);
      if (r.ok) console.log("NOTIFY_TEST_SENT=1"); else { status = "failed"; process.exitCode = 1; }
      return;
    }
    if (!doSend) {
      console.log("\n[dry-run] 卡片降级文本预览：");
      console.log("─".repeat(56)); console.log(bundle.fallbackText); console.log("─".repeat(56));
      console.log(`[dry-run] 将起表(建首轮)=${missTotal} 行（零写入）`);
      return;
    }
    const chatIds = parseListEnv(CHAT_IDS_ENV);
    if (chatIds.length === 0) throw new Error(`缺少 ${CHAT_IDS_ENV}（CSV 管理群 chat_id）`);
    let okCount = 0;
    for (let i = 0; i < chatIds.length; i++) {
      const r = await sendCardWithFallbackToChat(`关键词汇总-群${i + 1}`, chatIds[i], bundle.card, bundle.fallbackText);
      console.log(`  群${i + 1}: ok=${r.ok} cardOk=${r.cardOk}${r.error ? ` error=${r.error}` : ""}`);
      if (r.ok) okCount += 1;
    }
    if (mirrorToTestEnabled()) {
      const m = await sendCardWithFallbackToChat("关键词汇总-监督副本", getTestChatId(), bundle.card, bundle.fallbackText);
      console.log(`  [镜像] ${m.ok ? "副本已发测试群" : `副本失败(${m.error ?? "-"})`}`);
    }
    if (okCount === 0) throw new Error("两个群通道全部发送失败，零起表（下次运行重试）");
    const seeded = await seedCycles(db, miss);
    console.log(`  起表：建首轮=${seeded}（不扣分；周四cron将对仍未补的升二提扣分）`);
    if (okCount < chatIds.length) { status = "partial"; process.exitCode = 1; }
    extra = { chatPlanned: chatIds.length, chatOk: okCount, seeded, missTotal };
  } catch (e) {
    status = "failed"; errorMessage = getErrorMessage(e); console.log(`[错误] ${errorMessage}`); process.exitCode = 1;
  } finally {
    await db.end().catch(() => undefined);
    console.log(`SUMMARY_JSON=${JSON.stringify({ task: "gptKwOwnerSummary", status, errorMessage, durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)), ...extra })}`);
  }
}
if (require.main === module) {
  main().catch((e) => { console.log(`[致命错误] ${getErrorMessage(e)}`); process.exit(1); });
}
