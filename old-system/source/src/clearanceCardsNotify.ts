/**
 * clearanceCardsNotify.ts - 清货三张自动卡（批③，2026-07-21 需求方定稿）
 *
 * --type=tail    清尾卡：清货中且库存≤60天可卖量 → 负责人一人一卡逐品确认
 *                【继续清货】抑制14天 /【转稳定期】出清货期
 * --type=archive 归档卡：库存+在途清零满7天 → 一品一卡
 *                【确认归档】走审计+库存拦截 /【暂不归档】抑制7天
 * --type=revive  复活卡：清货期产品出现新货件（近2天创建）→ 一件一卡
 *                【转上升期】/【转稳定期】；每个货件只提醒一次（uq去重）
 *
 * 模式：默认 dry-run；--send 发负责人（镜像自动）；--test-send 全部进测试群（按钮test=1）
 * 事件：event_clearance_card 先落行再发卡（按钮带行id）；发送失败标 failed（同日不重发，
 *       次日/下周期新 biz_key 自然重试）
 * cron（批③部署时加）：
 *   16 10 * * 5 --type=tail --send
 *   5 10 * * *  --type=archive --send
 *   50 8 * * *  --type=revive --send
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { getTestChatId, resolveActiveMembers, sendCardToTarget, NotifyTarget, SendResult } from "./feishuNotify";
import {
  buildClearanceTailCard, buildClearanceArchiveCard, buildClearanceReviveCard,
  ClearanceTailItem,
} from "./notifyRules/reminderCards";

const SCRIPT_NAME = "clearanceCardsNotify";
const TAIL_THRESHOLD_DAYS = Number(process.env.CLEARANCE_TAIL_DAYS ?? 60);   // 清尾线（与补货目标70天为独立参数）
const ARCHIVE_ZERO_DAYS = 7;

const doSend = process.argv.includes("--send");
const testSend = process.argv.includes("--test-send");
const typeArg = (process.argv.find((a) => a.startsWith("--type=")) ?? "").slice("--type=".length);
if (doSend && testSend) { console.log("[错误] --send 与 --test-send 禁止同时使用"); process.exit(1); }
if (!["tail", "archive", "revive"].includes(typeArg)) {
  console.log("[错误] 需要 --type=tail|archive|revive");
  process.exit(1);
}

function cstToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(new Date());
}

interface ClearItem {
  store_id: string; store_name: string; item_id: string; mskus: string; sku: string; owner: string;
  stock: number; inbound: number; daily7: number;
}

async function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  });
}

/** 清货期在营 item 全集（含店铺名三层兜底、库存/在途、近7数据日日销） */
async function loadClearanceItems(db: mysql.Connection): Promise<ClearItem[]> {
  const nameMap = new Map<string, string>();
  const mergeNames = (rows: mysql.RowDataPacket[]): void => {
    for (const r of rows) {
      const id = String(r.store_id ?? "").trim();
      const nm = String(r.store_name ?? "").trim();
      if (id && nm && !nameMap.has(id)) nameMap.set(id, nm);
    }
  };
  const [n1] = await db.query<mysql.RowDataPacket[]>(
    `SELECT store_id, MAX(NULLIF(TRIM(store_name),'')) AS store_name FROM dim_product
     WHERE store_id IS NOT NULL AND store_id<>'' GROUP BY store_id`);
  mergeNames(n1);
  try {
    const [n2] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, store_name FROM dim_store_config WHERE store_id IS NOT NULL AND store_id<>''`);
    mergeNames(n2);
  } catch { /* 忽略 */ }

  const [items] = await db.query<mysql.RowDataPacket[]>(
    `SELECT p.store_id,
            COALESCE(MAX(NULLIF(TRIM(p.store_name),'')),'') AS store_name,
            p.item_id,
            SUBSTRING(GROUP_CONCAT(DISTINCT NULLIF(TRIM(p.msku),'') SEPARATOR '/'),1,500) AS mskus,
            COALESCE(MAX(NULLIF(TRIM(p.sku),'')),'') AS sku,
            COALESCE(MAX(NULLIF(TRIM(p.owner),'')),'') AS owner
     FROM dim_product p
     LEFT JOIN dim_product_business_state bs
       ON bs.platform = p.platform AND bs.store_id = p.store_id AND bs.item_id = p.item_id
      AND COALESCE(bs.msku,'') = COALESCE(p.msku,'')
      AND bs.stat_date = (SELECT MAX(stat_date) FROM dim_product_business_state WHERE platform='walmart')
     WHERE p.platform='walmart'
       AND COALESCE(p.product_management_status,'active') <> 'archived'
       AND COALESCE(NULLIF(TRIM(p.manual_lifecycle_stage),''), bs.lifecycle_stage, bs.system_lifecycle_stage, '') = '清货期'
     GROUP BY p.store_id, p.item_id`,
  );
  const [inv] = await db.query<mysql.RowDataPacket[]>(
    `SELECT inv.store_id, inv.item_id,
            SUM(COALESCE(inv.wfs_available_stock,0)) AS wfs,
            SUM(COALESCE(inv.inbound_stock,0)) AS inbound
     FROM fact_inventory_daily inv
     JOIN (SELECT store_id, item_id, msku, MAX(snapshot_date) AS d FROM fact_inventory_daily
           WHERE platform='walmart' GROUP BY store_id, item_id, msku) li
       ON li.store_id=inv.store_id AND li.item_id=inv.item_id AND li.msku=inv.msku AND inv.snapshot_date=li.d
     WHERE inv.platform='walmart' GROUP BY inv.store_id, inv.item_id`,
  );
  const invMap = new Map(inv.map((r) => [`${r.store_id}|${r.item_id}`, { wfs: Number(r.wfs ?? 0), inbound: Number(r.inbound ?? 0) }]));
  const [dateRows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT DISTINCT DATE_FORMAT(stat_date,'%Y-%m-%d') AS d FROM fact_sales_daily
     WHERE platform='walmart' ORDER BY d DESC LIMIT 7`,
  );
  const dates = dateRows.map((r) => String(r.d));
  const salesMap = new Map<string, number>();
  if (dates.length) {
    const [s] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, item_id, SUM(COALESCE(sales_qty,0)) AS qty FROM fact_sales_daily
       WHERE platform='walmart' AND stat_date IN (${dates.map(() => "?").join(",")})
       GROUP BY store_id, item_id`, dates,
    );
    for (const r of s) salesMap.set(`${r.store_id}|${r.item_id}`, Number(r.qty ?? 0));
  }
  const dayCount = Math.max(dates.length, 1);
  return items.map((r) => {
    const key = `${r.store_id}|${r.item_id}`;
    const iv = invMap.get(key) ?? { wfs: 0, inbound: 0 };
    return {
      store_id: String(r.store_id),
      store_name: String(r.store_name || "").trim() || nameMap.get(String(r.store_id)) || String(r.store_id),
      item_id: String(r.item_id),
      mskus: String(r.mskus || "-"),
      sku: String(r.sku || ""),
      owner: String(r.owner || "").trim(),
      stock: iv.wfs,
      inbound: iv.inbound,
      daily7: Math.round((salesMap.get(key) ?? 0) / dayCount * 100) / 100,
    };
  });
}

/** 抑制中的 item 集合（suppress_until >= 今天） */
async function loadSuppressed(db: mysql.Connection, cardType: string): Promise<Set<string>> {
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT DISTINCT store_id, item_id FROM event_clearance_card
     WHERE card_type = ? AND suppress_until IS NOT NULL AND suppress_until >= CURDATE()`,
    [cardType],
  );
  return new Set(rows.map((r) => `${r.store_id}|${r.item_id}`));
}

async function insertCardEvent(
  db: mysql.Connection, cardType: string, it: ClearItem, bizKey: string, metrics: Record<string, unknown>,
): Promise<number | null> {
  try {
    const [r] = await db.query<mysql.ResultSetHeader>(
      `INSERT INTO event_clearance_card
         (card_type, platform, store_id, store_name, item_id, mskus, sku, owner, biz_key, metrics_json, status)
       VALUES (?, 'walmart', ?, ?, ?, ?, ?, ?, ?, ?, 'sent')`,
      [cardType, it.store_id, it.store_name, it.item_id, it.mskus, it.sku, it.owner, bizKey, JSON.stringify(metrics)],
    );
    return r.insertId;
  } catch (e) {
    if ((e as { code?: string }).code === "ER_DUP_ENTRY") return null; // 已发过（幂等）
    throw e;
  }
}

async function markFailed(db: mysql.Connection, ids: number[]): Promise<void> {
  if (!ids.length) return;
  await db.query(`UPDATE event_clearance_card SET status='failed' WHERE id IN (${ids.map(() => "?").join(",")})`, ids);
}

async function main(): Promise<void> {
  const mode = testSend ? "test-send" : doSend ? "真实发送" : "dry-run";
  const today = cstToday();
  console.log("=".repeat(60));
  console.log(`清货自动卡 type=${typeArg} 模式=${mode} 日期=${today} 清尾线=${TAIL_THRESHOLD_DAYS}天`);
  console.log("=".repeat(60));
  const db = await getDb();
  const results: SendResult[] = [];
  let anyFail = false;
  try {
    const all = await loadClearanceItems(db);
    console.log(`清货期在营 item: ${all.length}`);
    const suppressed = await loadSuppressed(db, typeArg);
    const testTarget: NotifyTarget = { type: "chat", label: "测试群", id: getTestChatId() };

    const resolveOwnerTarget = async (owner: string): Promise<NotifyTarget | null> => {
      if (testSend) return testTarget;
      const { targets, warnings } = await resolveActiveMembers([owner]);
      for (const w of warnings) console.log(`  [花名册] ${w}`);
      return targets.find((t) => t.label === owner) ?? null;
    };

    if (typeArg === "tail") {
      const cands = all.filter((it) => it.stock > 0 && it.daily7 > 0
        && Math.round(it.stock / it.daily7) <= TAIL_THRESHOLD_DAYS
        && !suppressed.has(`${it.store_id}|${it.item_id}`) && it.owner);
      console.log(`清尾候选（≤${TAIL_THRESHOLD_DAYS}天且未抑制）: ${cands.length}`);
      // 预计清货结束时间（人工）一并展示
      const expectMap = new Map<string, string>();
      try {
        const [exp] = await db.query<mysql.RowDataPacket[]>(
          `SELECT row_key, DATE_FORMAT(expect_end,'%Y-%m-%d') AS d FROM biz_clearance_expect_date`);
        for (const r of exp) expectMap.set(String(r.row_key), String(r.d));
      } catch { /* 忽略 */ }
      const byOwner = new Map<string, ClearItem[]>();
      for (const it of cands) {
        if (!byOwner.has(it.owner)) byOwner.set(it.owner, []);
        byOwner.get(it.owner)!.push(it);
      }
      for (const [owner, list] of byOwner) {
        const cardItems: ClearanceTailItem[] = [];
        const ids: number[] = [];
        for (const it of list) {
          const bizKey = `tail:${it.store_id}:${it.item_id}:${today}`;
          const daysToClear = Math.round(it.stock / it.daily7);
          if (!doSend && !testSend) {
            console.log(`[dry-run] ${owner} ← ${it.mskus}（${daysToClear}天清完）`);
            continue;
          }
          const id = await insertCardEvent(db, "tail", it, bizKey, { stock: it.stock, daily7: it.daily7, daysToClear });
          if (id === null) continue; // 今日已发（重跑幂等）
          ids.push(id);
          cardItems.push({
            id, storeName: it.store_name, itemId: it.item_id, mskus: it.mskus,
            stock: it.stock, daily7: it.daily7, daysToClear,
            expectEnd: expectMap.get(`auto:${it.store_id}:${it.item_id}`) ?? "",
          });
        }
        if (!cardItems.length) continue;
        const bundle = buildClearanceTailCard(today, owner, cardItems, { testMode: testSend });
        const target = await resolveOwnerTarget(owner);
        if (!target) { console.log(`  [跳过] ${owner} 花名册未命中`); await markFailed(db, ids); anyFail = true; continue; }
        const r = await sendCardToTarget(testSend ? { ...target, label: `测试群(清尾-${owner})` } : target, bundle.card, bundle.fallbackText, true);
        results.push(r);
        if (!r.ok) { await markFailed(db, ids); anyFail = true; }
      }
    }

    if (typeArg === "archive") {
      const zeroItems = all.filter((it) => it.stock <= 0 && it.inbound <= 0
        && !suppressed.has(`${it.store_id}|${it.item_id}`) && it.owner);
      console.log(`清零候选: ${zeroItems.length}`);
      for (const it of zeroItems) {
        const [lastPos] = await db.query<mysql.RowDataPacket[]>(
          `SELECT DATE_FORMAT(MAX(snapshot_date),'%Y-%m-%d') AS d FROM (
             SELECT snapshot_date, SUM(COALESCE(wfs_available_stock,0)) + SUM(COALESCE(inbound_stock,0)) AS q
             FROM fact_inventory_daily
             WHERE platform='walmart' AND store_id=? AND item_id=?
             GROUP BY snapshot_date HAVING q > 0
           ) t`,
          [it.store_id, it.item_id],
        );
        const lastPositive = lastPos[0]?.d ? String(lastPos[0].d) : "";
        if (!lastPositive) continue; // 无历史正库存，不判定
        const zeroDays = Math.floor((new Date(`${today}T00:00:00Z`).getTime() - new Date(`${lastPositive}T00:00:00Z`).getTime()) / 86400000);
        if (zeroDays < ARCHIVE_ZERO_DAYS) continue;
        if (!doSend && !testSend) { console.log(`[dry-run] ${it.owner} ← 归档卡 ${it.mskus}（清零${zeroDays}天）`); continue; }
        const bizKey = `archive:${it.store_id}:${it.item_id}:${today}`;
        const id = await insertCardEvent(db, "archive", it, bizKey, { zeroDays, lastPositive });
        if (id === null) continue;
        const bundle = buildClearanceArchiveCard(
          { id, storeName: it.store_name, itemId: it.item_id, mskus: it.mskus, zeroDays }, { testMode: testSend });
        const target = await resolveOwnerTarget(it.owner);
        if (!target) { console.log(`  [跳过] ${it.owner} 花名册未命中`); await markFailed(db, [id]); anyFail = true; continue; }
        const r = await sendCardToTarget(testSend ? { ...target, label: `测试群(归档-${it.mskus})` } : target, bundle.card, bundle.fallbackText, true);
        results.push(r);
        if (!r.ok) { await markFailed(db, [id]); anyFail = true; }
      }
    }

    if (typeArg === "revive") {
      const clearMap = new Map(all.map((it) => [`${it.store_id}|${it.item_id}`, it]));
      const [ships] = await db.query<mysql.RowDataPacket[]>(
        `SELECT s.store_id, s.shipment_id, si.msku, SUM(COALESCE(si.declare_num,0)) AS qty
         FROM fact_wfs_shipment s
         JOIN fact_wfs_shipment_item si ON si.platform=s.platform AND si.store_id=s.store_id AND si.shipment_id=s.shipment_id
         WHERE s.platform='walmart' AND s.cargo_create_date >= DATE_SUB(CURDATE(), INTERVAL 2 DAY)
         GROUP BY s.store_id, s.shipment_id, si.msku`,
      );
      console.log(`近2天新货件明细行: ${ships.length}`);
      const [mskuMap] = await db.query<mysql.RowDataPacket[]>(
        `SELECT store_id, msku, item_id FROM dim_product
         WHERE platform='walmart' AND msku IS NOT NULL AND TRIM(msku)<>''`,
      );
      const itemByMsku = new Map(mskuMap.map((r) => [`${r.store_id}|${String(r.msku).trim()}`, String(r.item_id)]));
      // 按 (shipment,item) 聚合数量
      const agg = new Map<string, { it: ClearItem; shipmentId: string; qty: number }>();
      for (const s of ships) {
        const itemId = itemByMsku.get(`${s.store_id}|${String(s.msku).trim()}`);
        if (!itemId) continue;
        const it = clearMap.get(`${s.store_id}|${itemId}`);
        if (!it || !it.owner) continue;
        const k = `${s.shipment_id}|${s.store_id}|${itemId}`;
        const cur = agg.get(k) ?? { it, shipmentId: String(s.shipment_id), qty: 0 };
        cur.qty += Number(s.qty ?? 0);
        agg.set(k, cur);
      }
      console.log(`清货期产品新货件命中: ${agg.size}`);
      // ── 2026-07-21 批④：新采购单触发（SKU 关联）──
      // v3 修复：判定"新"必须用领星单据自身的 create_time（YYYY-MM-DD 前缀字典序比较），
      // 不能用我们的入库时间 created_at——首拉会把全部历史单标成"新"（07-21 实测 165 假阳性）。
      // 熔断阀：CLEARANCE_REVIVE_PO_DISABLED=1 可单独关掉采购触发（货件触发不受影响）。
      try {
        if ((process.env.CLEARANCE_REVIVE_PO_DISABLED ?? "").trim() === "1") {
          throw new Error("CLEARANCE_REVIVE_PO_DISABLED=1，采购触发已熔断");
        }
        const [pos] = await db.query<mysql.RowDataPacket[]>(
          `SELECT o.order_sn, i.sku, SUM(COALESCE(i.quantity_real,0)) AS qty
           FROM fact_purchase_order o
           JOIN fact_purchase_order_item i ON i.order_sn = o.order_sn
           WHERE NULLIF(TRIM(o.create_time),'') IS NOT NULL
             AND o.create_time >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 2 DAY), '%Y-%m-%d')
             AND o.status_text NOT LIKE '%作废%'
           GROUP BY o.order_sn, i.sku`,
        );
        const bySku = new Map<string, ClearItem[]>();
        for (const it of all) {
          if (!it.sku || !it.owner) continue;
          if (!bySku.has(it.sku)) bySku.set(it.sku, []);
          bySku.get(it.sku)!.push(it);
        }
        let poHits = 0;
        for (const r of pos) {
          for (const it of bySku.get(String(r.sku ?? "").trim()) ?? []) {
            poHits += 1;
            if (!doSend && !testSend) {
              console.log(`[dry-run] ${it.owner} ← 复活卡(采购) ${it.mskus}（${r.order_sn} ${r.qty}件）`);
              continue;
            }
            const bizKey = `revivepo:${r.order_sn}:${it.store_id}:${it.item_id}`;
            const id = await insertCardEvent(db, "revive", it, bizKey,
              { orderSn: String(r.order_sn), qty: Number(r.qty ?? 0), source: "purchase" });
            if (id === null) continue;
            const bundle = buildClearanceReviveCard(
              { id, storeName: it.store_name, itemId: it.item_id, mskus: it.mskus,
                shipmentId: String(r.order_sn), shipmentQty: Number(r.qty ?? 0), sourceLabel: "新采购单" },
              { testMode: testSend });
            const target = await resolveOwnerTarget(it.owner);
            if (!target) { console.log(`  [跳过] ${it.owner} 花名册未命中`); await markFailed(db, [id]); anyFail = true; continue; }
            const rr = await sendCardToTarget(
              testSend ? { ...target, label: `测试群(复活PO-${it.mskus})` } : target,
              bundle.card, bundle.fallbackText, true);
            results.push(rr);
            if (!rr.ok) { await markFailed(db, [id]); anyFail = true; }
          }
        }
        console.log(`采购单触发命中: ${poHits}`);
      } catch (e) {
        console.log(`[提示] 采购触发跳过（采购表未建或查询失败）: ${e instanceof Error ? e.message : String(e)}`);
      }
      for (const { it, shipmentId, qty } of agg.values()) {
        if (!doSend && !testSend) { console.log(`[dry-run] ${it.owner} ← 复活卡 ${it.mskus}（货件${shipmentId} ${qty}件）`); continue; }
        const bizKey = `revive:${shipmentId}:${it.store_id}:${it.item_id}`;
        const id = await insertCardEvent(db, "revive", it, bizKey, { shipmentId, qty });
        if (id === null) continue; // 该货件已提醒过
        const bundle = buildClearanceReviveCard(
          { id, storeName: it.store_name, itemId: it.item_id, mskus: it.mskus, shipmentId, shipmentQty: qty }, { testMode: testSend });
        const target = await resolveOwnerTarget(it.owner);
        if (!target) { console.log(`  [跳过] ${it.owner} 花名册未命中`); await markFailed(db, [id]); anyFail = true; continue; }
        const r = await sendCardToTarget(testSend ? { ...target, label: `测试群(复活-${it.mskus})` } : target, bundle.card, bundle.fallbackText, true);
        results.push(r);
        if (!r.ok) { await markFailed(db, [id]); anyFail = true; }
      }
    }

    console.log(`发送 ${results.filter((r) => r.ok).length}/${results.length} 张卡`);
    if (testSend && !anyFail && results.length) console.log("NOTIFY_TEST_SENT=1");
    if (!doSend && !testSend) console.log("[dry-run] 零发送零写库（事件行也不落）。");
    if (anyFail) process.exitCode = 1;
  } finally {
    await db.end().catch(() => {});
  }
}

main().catch((e) => {
  console.error(`${SCRIPT_NAME} 失败:`, e instanceof Error ? e.message : String(e));
  process.exit(1);
});
