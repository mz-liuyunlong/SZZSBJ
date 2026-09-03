/**
 * checkSemNamingCompliance.ts — SEM广告命名合规检测+群卡片通报（2026-08-12 需求方拍板）
 *
 * 规则：
 *   - 不合规 = fact_ads_product_daily(campaign_type='sem') 中最新数据日 item_id='' 的campaign。
 *   - 整改判定 = 该campaign最新数据日 item_id<>''（改名后重新导入自动修复）→ status='resolved'。
 *   - 人工归属兜底（2026-08-13）：dim_sem_campaign_item 中 source='manual' 的 campaign 视为已合规，
 *     不再通报、且不扣分（resolve 时预结算 penalty=0）；名字不改也认，系统永不覆盖 manual 行。
 *   - 负责人：不合规期间产品未知→负责人未知→**不猜测任何归属**（需求方2026-08-12纠正）；
 *     只有改名重导、ItemID解析成功后才100%确定负责人（ItemID→dim_product.owner），扣分在那一刻执行。
 *   - 通报 = 群卡片，按店铺分组（需求方2026-08-12定稿：不设确认按钮——负责人未知时确认无意义）。
 *   - 催办 = --remind：仍存在 open 且 last_push_at<=NOW()-5h → 重发；整改是停止通报的唯一方式；
 *     发送窗口 08:00-22:00（CST），窗口外自动跳过（挂cron后零改动生效；cron按需求方口径最后统一挂）。
 *
 * 发送三档（通报测试铁律）：
 *   npx ts-node src/checkSemNamingCompliance.ts                # dry-run：扫描+写台账+卡片预览，零发送
 *   npx ts-node src/checkSemNamingCompliance.ts --test-send    # 仅发测试群（按钮带test=1，回调不落库）
 *   npx ts-node src/checkSemNamingCompliance.ts --send-group   # 真发运营群（需求方批准后才用；今日禁用）
 *   附加 --remind = 5小时催办模式（只重发未确认部分）；--no-scan = 跳过台账刷新只发送
 *
 * 写入范围：event_sem_naming_alert（台账upsert/整改标记/推送时间）。零触碰其他表。
 * 运营群chat_id读环境变量 SEM_NAMING_CHAT_ID（缺省=需求方提供的运营群），不硬编码密钥。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { NotifyTarget, getTestChatId, sendCardToTarget } from "./feishuNotify";

const GROUP_CHAT_ID = (process.env.SEM_NAMING_CHAT_ID ?? "oc_f995c8554d2bf71abf4703396203c9f6").trim();
const PAGE_URL = "http://42.193.254.170:3000/walmart-sem";
const REMIND_HOURS = 5;
const WINDOW_START = 8;   // CST
const WINDOW_END = 22;    // CST，>=22点不发（需求方：通报时间不超过22:00）
const MAX_LIST_PER_OWNER = 12;

function dbConfig(): mysql.ConnectionOptions {
  return { host: process.env.DB_HOST ?? "127.0.0.1", port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "", password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data", dateStrings: true };
}
function cstNow(): Date { return new Date(Date.now() + 8 * 3600 * 1000); }
function cstHour(): number { return cstNow().getUTCHours(); }
function todayCst(): string { return cstNow().toISOString().slice(0, 10); }

interface AlertRow {
  id: number; store_id: string; store_name: string; campaign_id: string; campaign_name: string;
  owner_name: string; owner_open_id: string; first_seen_date: string; last_seen_date: string;
  ack_status: string; last_push_at: string | null;
}

/** 台账刷新：不合规upsert + 整改标记（只动系统列，不碰remark人工列） */
async function scan(db: mysql.Connection): Promise<{ opened: number; resolved: number }> {
  // 每campaign最新数据日的归属状态
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT f.store_id, MAX(f.store_name) AS store_name, f.campaign_id,
            SUBSTRING_INDEX(GROUP_CONCAT(f.campaign_name ORDER BY f.stat_date DESC), ',', 1) AS campaign_name,
            MAX(f.stat_date) AS last_date,
            SUBSTRING_INDEX(GROUP_CONCAT(COALESCE(f.item_id,'') ORDER BY f.stat_date DESC), ',', 1) AS latest_item
       FROM fact_ads_product_daily f
      WHERE f.platform='walmart' AND f.campaign_type='sem'
      GROUP BY f.store_id, f.campaign_id`);
  // 扩展（2026-08-13 需求方拍板）：不合规 = item_id 无法识别到真实产品。
  //   包括 ①item_id 为空（名里没 ItemID）②item_id 非空但该店 dim_product 查无（填了错的 ItemID）。
  //   整改 = item_id 变成该店 dim_product 里真实存在的 ID。
  const pairs = rows.map((r) => ({ store: String(r.store_id), item: String(r.latest_item ?? "") }))
    .filter((p) => p.item !== "");
  const validProd = new Set<string>();
  if (pairs.length) {
    const uniqItems = Array.from(new Set(pairs.map((p) => p.item)));
    const [pv] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, item_id FROM dim_product
        WHERE platform='walmart' AND COALESCE(item_id,'')<>'' AND item_id IN (${uniqItems.map(() => "?").join(",")})`,
      uniqItems);
    for (const r of pv) validProd.add(`${String(r.store_id)}||${String(r.item_id)}`);
  }
  // 人工归属兜底（2026-08-13 需求方拍板）：dim_sem_campaign_item 中 source='manual' 的 campaign 视为已合规——
  //   即便名字里无 ItemID、fact_ads_product_daily.item_id 仍为空，也因已人工归属到真实 ItemID 而不再通报；
  //   且人工归属不扣分（resolve 时预结算 penalty_points=0/penalty_at 落定，扣分脚本永不结算此行）。
  //   系统永不覆盖 manual 行（映射表 source 语义）；auto_name 走原逻辑不变。
  const manualMap = new Set<string>();
  {
    const [mm] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, campaign_id FROM dim_sem_campaign_item
        WHERE platform='walmart' AND source='manual' AND COALESCE(item_id,'')<>''`);
    for (const r of mm) manualMap.add(`${String(r.store_id)}||${String(r.campaign_id)}`);
  }
  let opened = 0, resolved = 0;
  for (const r of rows) {
    const storeId = String(r.store_id), campId = String(r.campaign_id);
    const campName = String(r.campaign_name ?? ""), lastDate = String(r.last_date).slice(0, 10);
    const latestItem = String(r.latest_item ?? "");
    const hasManual = manualMap.has(`${storeId}||${campId}`);
    const compliant = hasManual || (latestItem !== "" && validProd.has(`${storeId}||${latestItem}`));
    if (!compliant) {
      // 需求方2026-08-12纠正：不合规期间产品未知，负责人一律不猜测（owner_name留空，整改后由扣分脚本按ItemID实锤回填）
      // 2026-08-19 方案B（实证口径）：last_open_check_date=本轮检测日，每轮仍不合规就刷新——
      // 结算只对"有观测证据"的天数计费，消除检测流水线滞后造成的+1天误扣（当天整改被记拖1天）。
      await db.query(
        `INSERT INTO event_sem_naming_alert
           (platform, store_id, store_name, campaign_id, campaign_name, owner_name, first_seen_date, last_seen_date, status, last_open_check_date)
         VALUES ('walmart', ?, ?, ?, ?, '', ?, ?, 'open', ?)
         ON DUPLICATE KEY UPDATE
           store_name=VALUES(store_name), campaign_name=VALUES(campaign_name),
           last_seen_date=VALUES(last_seen_date), last_open_check_date=VALUES(last_open_check_date),
           status='open', resolved_at=IF(status='resolved', NULL, resolved_at)`,
        [storeId, String(r.store_name ?? ""), campId, campName.slice(0, 250), todayCst(), lastDate, todayCst()]);
      opened++;
    } else if (hasManual) {
      // 人工归属兜底 resolve：预结算0分（penalty_at 非空→checkSemNamingDeduction 永不结算此行），幂等
      const [u] = await db.query(
        `UPDATE event_sem_naming_alert
            SET status='resolved', resolved_at=COALESCE(resolved_at, NOW()),
                penalty_points=0, penalty_at=COALESCE(penalty_at, NOW())
          WHERE platform='walmart' AND store_id=? AND campaign_id=? AND status='open'`,
        [storeId, campId]);
      resolved += (u as mysql.ResultSetHeader).affectedRows;
    } else {
      // 改名重导正常整改 resolve：penalty_at 留空，交 checkSemNamingDeduction 按拖延天数结算
      const [u] = await db.query(
        `UPDATE event_sem_naming_alert SET status='resolved', resolved_at=NOW()
          WHERE platform='walmart' AND store_id=? AND campaign_id=? AND status='open'`,
        [storeId, campId]);
      resolved += (u as mysql.ResultSetHeader).affectedRows;
    }
  }
  return { opened, resolved };
}

function buildGroupCard(byStore: Map<string, AlertRow[]>, test: boolean, remind: boolean):
  { card: Record<string, unknown>; fb: string } {
  const elements: Array<Record<string, unknown>> = [];
  elements.push({ tag: "div", text: { tag: "lark_md", content:
    (remind ? "🔔 **催办**（距上次通报已超5小时未确认）\n" : "") +
    "以下SEM广告活动名**不符合命名规范**（名称中缺少有效ItemID、或ItemID有误无法归属到真实产品与负责人）。\n" +
    "规范：campaign名必须含**真实存在的商品ItemID**，建议格式 **SKU+ItemID** 前缀。\n" +
    "改名后次日重新导入即自动修复归属；**归属确认后按拖延天数执行扣分（每天5分）**。\n" +
    `导入工具：[SEM导入页](${PAGE_URL})` } });
  elements.push({ tag: "hr" });
  for (const [store, list] of byStore) {
    const shown = list.slice(0, MAX_LIST_PER_OWNER);
    const lines = shown.map((a) => `· ${a.campaign_name}`).join("\n")
      + (list.length > shown.length ? `\n· …等共${list.length}个` : "");
    elements.push({ tag: "div", text: { tag: "lark_md", content: `**店铺：${store}**（${list.length}个campaign）\n${lines}` } });
    elements.push({ tag: "hr" });
  }
  elements.push({ tag: "note", elements: [{ tag: "plain_text", content:
    "本通报每5小时重发一次（22:00后静默），改名并重新导入（整改）后自动停止；整改归属实锤后按拖延天数结算扣分。" }] });
  const totalCnt = [...byStore.values()].reduce((s, l) => s + l.length, 0);
  const card = {
    config: { wide_screen_mode: true },
    header: { template: remind ? "orange" : "red",
      title: { tag: "plain_text", content: `${test ? "【测试】" : ""}📣 SEM广告命名不合规通报（${totalCnt}个）` } },
    elements,
  };
  const fb = `【SEM命名不合规通报】共${totalCnt}个campaign名缺少/填错ItemID（无法归属真实产品/负责人），涉及店铺：` +
    [...byStore.keys()].join("、") + "。请按SKU+ItemID规范改名后重新导入（整改后通报自动停止）。";
  return { card, fb };
}

async function main(): Promise<void> {
  const testSend = process.argv.includes("--test-send");
  const groupSend = process.argv.includes("--send-group");
  const remind = process.argv.includes("--remind");
  const noScan = process.argv.includes("--no-scan");
  const doSend = testSend || groupSend;
  const mode = remind ? "remind(5h催办)" : "push(检测+首发)";
  console.log("=".repeat(64));
  console.log(`SEM命名合规通报 | ${mode} | ${groupSend ? "真发运营群" : testSend ? "仅测试群(回调test模式)" : "dry-run(零发送)"}`);
  console.log("=".repeat(64));

  const db = await mysql.createConnection(dbConfig());
  try {
    if (!noScan) {
      const { opened, resolved } = await scan(db);
      console.log(`台账刷新：不合规(open) upsert=${opened}  本轮判定整改(resolved)=${resolved}`);
    }

    // 待通报集合：open 且 pending；remind模式额外要求 last_push_at<=NOW()-5h（或从未推过）
    const cond = remind
      ? `AND (a.last_push_at IS NULL OR a.last_push_at <= NOW() - INTERVAL ${REMIND_HOURS} HOUR)` : "";
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT a.id, a.store_id, a.store_name, a.campaign_id, a.campaign_name, a.owner_name, a.owner_open_id,
              DATE_FORMAT(a.first_seen_date,'%Y-%m-%d') AS first_seen_date,
              DATE_FORMAT(a.last_seen_date,'%Y-%m-%d') AS last_seen_date, a.ack_status, a.last_push_at
         FROM event_sem_naming_alert a
        WHERE a.status='open' ${cond}
        ORDER BY a.owner_name, a.store_id, a.campaign_name`);
    const alerts = rows as unknown as AlertRow[];
    if (!alerts.length) { console.log(remind ? "无需催办（全部已确认或不足5小时）。" : "无不合规campaign，无需通报。"); return; }

    const byStore = new Map<string, AlertRow[]>();
    for (const a of alerts) {
      const key = a.store_name || a.store_id;
      if (!byStore.has(key)) byStore.set(key, []);
      byStore.get(key)!.push(a);
    }
    console.log(`待通报：${alerts.length}个campaign，涉及店铺${byStore.size}家（负责人待整改后按ItemID实锤，不猜测）`);

    // 发送窗口（仅真实发送时限制；dry-run不限）
    const h = cstHour();
    if (doSend && (h >= WINDOW_END || h < WINDOW_START)) {
      console.log(`当前CST ${h}点在发送窗口(${WINDOW_START}-${WINDOW_END})外，跳过发送（挂cron后自动等下个窗口）。`);
      return;
    }

    const isTestCard = !groupSend; // 只要不是真发运营群，按钮一律test=1（回调不落库）
    const { card, fb } = buildGroupCard(byStore, isTestCard, remind);
    const target: NotifyTarget = groupSend
      ? { type: "chat", label: "运营群", id: GROUP_CHAT_ID }
      : { type: "chat", label: "测试群", id: getTestChatId() };
    const result = await sendCardToTarget(target, card, fb, doSend);
    console.log(`发送结果：${result.ok ? "✅" : "❌ " + (result.error ?? "")}（${target.label}）`);

    if (doSend && result.ok) {
      await db.query(
        `UPDATE event_sem_naming_alert SET last_push_at=NOW(), push_count=push_count+1
          WHERE id IN (${alerts.map(() => "?").join(",")})`, alerts.map((a) => a.id));
      console.log(`已更新 last_push_at/push_count（${alerts.length}行）`);
    }
    console.log("SUMMARY_JSON=" + JSON.stringify({
      mode, channel: groupSend ? "group" : testSend ? "test" : "dry-run",
      alerts: alerts.length, stores: byStore.size, sent: doSend && result.ok,
    }));
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((err) => { console.error("SEM命名合规通报失败：", err); process.exit(1); });
