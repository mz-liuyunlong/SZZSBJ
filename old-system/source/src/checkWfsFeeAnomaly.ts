/**
 * checkWfsFeeAnomaly.ts — 智能PMC·WFS费用异常检测（2026-08-11 需求方定稿）
 *
 * 判定：dim_product_wfs_fee_auto.fee(实收单件费率,Walmart结算口径,周一刷新)
 *       > dim_product_cost_config.delivery_fee(人工WFS配送费) 即多收，自动立案。
 * 粒度：店铺+MSKU（与实收费率表同粒度）；CS测品(msku LIKE 'CS%')不参与。
 * 预估追回 = (实收-人工) × fact_sales_daily 全历史累计销量（估算口径，逐单精算二期）。
 * 流程：立案(waiting)→卡片通知负责人→需要跟进(Case号页面必填)→following；
 *       无需跟进→点击直接送林翔审批(approving,不需理由,2026-08-12拍板)。done/closed 不自动重开（v1记档）。
 *
 * cron（部署时挂）：10 10 * * * --detect --send   # 每日检测（周一04:40费率刷新后）
 * 用法：
 *   npx ts-node src/checkWfsFeeAnomaly.ts                         # dry-run：只打印，零写库零发送
 *   npx ts-node src/checkWfsFeeAnomaly.ts --send                  # 真实：写事件+发卡给负责人
 *   npx ts-node src/checkWfsFeeAnomaly.ts --test-send --send      # 全发测试群(卡带test:1)，零写库
 *
 * 铁律：只写 event_wfs_fee_case（系统列），人工列(status流转由卡片/页面驱动、case_nos/reason/
 *       follow_log/金额/remark)本脚本永不触碰；已有事件仅刷新 manual/actual/units/est 四列。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import {
  NotifyTarget, getTestChatId, resolveActiveMembers, sendCardToTarget,
} from "./feishuNotify";

const FALLBACK_NOTIFY = (process.env.WFS_FEE_NOTIFY_FALLBACK ?? "陈佳聪").trim();
const EPS = 0.0001;

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

interface Anomaly {
  id: number;                 // 事件id（新立案真写后回填；dry/test 为 0）
  storeId: string; storeName: string; itemId: string; msku: string; owner: string;
  manualFee: number; actualFee: number; totalUnits: number; estRecover: number;
  isNew: boolean;
}

async function one(db: mysql.Connection, sql: string, params: Array<string | number>): Promise<Record<string, unknown> | null> {
  const [rows] = await db.execute(sql, params);
  return (rows as Array<Record<string, unknown>>)[0] ?? null;
}

/** 人工费解析：优先 店铺+msku 级，回退 msku(item)级；均取最新 effective_date/updated_at/id */
async function manualFee(db: mysql.Connection, storeId: string, msku: string): Promise<number | null> {
  const byStore = await one(db,
    `SELECT delivery_fee f FROM dim_product_cost_config
     WHERE platform='walmart' AND status='active' AND delivery_fee IS NOT NULL AND delivery_fee>0
       AND store_id=? AND msku=?
     ORDER BY effective_date DESC, updated_at DESC, id DESC LIMIT 1`, [storeId, msku]);
  if (byStore) return Number(byStore.f);
  const byItem = await one(db,
    `SELECT delivery_fee f FROM dim_product_cost_config
     WHERE platform='walmart' AND status='active' AND delivery_fee IS NOT NULL AND delivery_fee>0
       AND msku=?
     ORDER BY effective_date DESC, updated_at DESC, id DESC LIMIT 1`, [msku]);
  return byItem ? Number(byItem.f) : null;
}

function buildCard(a: Anomaly, test: boolean): { card: Record<string, unknown>; fb: string } {
  const diff = a.actualFee - a.manualFee;
  const card = {
    config: { wide_screen_mode: true },
    header: { template: "red", title: { tag: "plain_text", content: "💰 WFS费用异常 · 发现多收，请确认" } },
    elements: [
      { tag: "div", text: { tag: "lark_md", content:
        `**产品**：${a.msku}（${a.itemId || "无ItemID"}）｜ **店铺**：${a.storeName || a.storeId}\n` +
        `**人工配送费**：$${a.manualFee.toFixed(2)}／件 ｜ **实收费率(结算)**：$${a.actualFee.toFixed(2)}／件\n` +
        `**单件多收**：<font color='red'>+$${diff.toFixed(2)}</font> × 累计 ${a.totalUnits} 件 = **预估追回 <font color='red'>$${a.estRecover.toFixed(2)}</font>**\n` +
        `**负责人**：${a.owner || "（空缺）"}` } },
      { tag: "div", text: { tag: "lark_md", content:
        `疑因 Walmart 记录尺寸/重量偏大导致费率虚高，可开 Case 追回（已有单品追回 $544.16 案例）。\n开Case教程：智能PMC → WFS费用异常 → 帮助中心（简版SOP）` } },
      { tag: "action", actions: [
        { tag: "button", text: { tag: "plain_text", content: "✅ 需要跟进（去填Case号）" }, type: "primary",
          value: Object.assign({ biz: "wfs_fee", id: a.id, choice: "follow" }, test ? { test: 1 } : {}) },
        { tag: "button", text: { tag: "plain_text", content: "🚫 无需跟进（送林翔审批）" }, type: "default",
          value: Object.assign({ biz: "wfs_fee", id: a.id, choice: "nofollow" }, test ? { test: 1 } : {}) },
      ] },
      { tag: "note", elements: [{ tag: "plain_text",
        content: "跟进中每周必写跟进日志（未更新扣绩效）；无需跟进点击即送林翔审批（无需填理由），中途放弃同样须审批。" }] },
    ],
  };
  const fb = `【WFS费用异常】${a.msku}｜人工$${a.manualFee.toFixed(2)} vs 实收$${a.actualFee.toFixed(2)}｜预估追回$${a.estRecover.toFixed(2)}；请在卡片确认。`;
  return { card, fb };
}

async function main(): Promise<void> {
  const argv = process.argv.slice(2);
  const send = argv.includes("--send");
  const testSend = argv.includes("--test-send") || (process.env.BUSINESS_REPORT_FORCE_TEST ?? "").trim() === "1";
  const db = await getDb();
  let scanned = 0, noManual = 0, anomalies = 0, created = 0, refreshed = 0, skippedClosed = 0, sentOk = 0, sentFail = 0;
  const toSend: Anomaly[] = [];
  try {
    const [feeRows] = await db.execute(
      `SELECT store_id, msku, fee FROM dim_product_wfs_fee_auto
       WHERE fee IS NOT NULL AND msku NOT LIKE 'CS%' ORDER BY store_id, msku`);
    for (const r of feeRows as Array<Record<string, unknown>>) {
      scanned++;
      const storeId = String(r.store_id), msku = String(r.msku), actualFee = Number(r.fee);
      const manual = await manualFee(db, storeId, msku);
      if (manual === null) { noManual++; continue; }
      if (actualFee <= manual + EPS) continue;
      anomalies++;
      const u = await one(db,
        `SELECT COALESCE(SUM(sales_qty),0) q FROM fact_sales_daily
         WHERE platform='walmart' AND store_id=? AND msku=?`, [storeId, msku]);
      const totalUnits = Number(u?.q ?? 0);
      const estRecover = Math.round((actualFee - manual) * totalUnits * 100) / 100;
      const dp = await one(db,
        `SELECT item_id, COALESCE(owner,'') owner FROM dim_product
         WHERE platform='walmart' AND store_id=? AND msku=?
         ORDER BY (product_management_status='active') DESC, updated_at DESC LIMIT 1`, [storeId, msku]);
      const st = await one(db,
        `SELECT store_name FROM dim_store_config WHERE store_id=? LIMIT 1`, [storeId]);
      const a: Anomaly = {
        id: 0, storeId, storeName: String(st?.store_name ?? ""), itemId: String(dp?.item_id ?? ""),
        msku, owner: String(dp?.owner ?? ""), manualFee: manual, actualFee, totalUnits, estRecover, isNew: false,
      };
      const ex = await one(db,
        `SELECT id, status, first_alert_at FROM event_wfs_fee_case
         WHERE platform='walmart' AND store_id=? AND msku=?`, [storeId, msku]);
      if (ex) {
        if (["done", "closed"].includes(String(ex.status))) { skippedClosed++; continue; }
        a.id = Number(ex.id);
        if (send && !testSend) {
          await db.execute(
            `UPDATE event_wfs_fee_case SET manual_fee=?, actual_fee=?, total_units=?, est_recover=? WHERE id=?`,
            [manual, actualFee, totalUnits, estRecover, a.id]);
        }
        refreshed++;
        if (String(ex.status) === "waiting" && !ex.first_alert_at) toSend.push(a);
      } else {
        a.isNew = true;
        if (send && !testSend) {
          const [ret] = await db.execute(
            `INSERT INTO event_wfs_fee_case
               (platform, store_id, store_name, item_id, msku, owner_name,
                manual_fee, actual_fee, total_units, est_recover, status)
             VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'waiting')`,
            [storeId, a.storeName, a.itemId, msku, a.owner, manual, actualFee, totalUnits, estRecover]);
          a.id = Number((ret as mysql.ResultSetHeader).insertId);
        }
        created++;
        toSend.push(a);
      }
    }
    // ── 发卡 ──
    for (const a of toSend) {
      const { card, fb } = buildCard(a, testSend);
      if (!send) { console.log(`[dry-run] 卡片 →\n${fb}`); sentOk++; continue; }
      let target: NotifyTarget | null = null;
      if (testSend) {
        target = { type: "chat", label: `测试群(原目标:${a.owner || FALLBACK_NOTIFY})`, id: getTestChatId() };
      } else {
        const { targets } = await resolveActiveMembers([a.owner || FALLBACK_NOTIFY]);
        target = targets[0] ?? null;
        if (!target && a.owner) {
          const fbk = await resolveActiveMembers([FALLBACK_NOTIFY]);
          target = fbk.targets[0] ?? null;
        }
      }
      if (!target) { console.log(`[WARN] 找不到通知目标：${a.owner || FALLBACK_NOTIFY}（${a.msku}）`); sentFail++; continue; }
      const r = await sendCardToTarget(target, card, fb, true);
      if (r.ok) {
        sentOk++;
        if (!testSend && a.id) {
          await db.execute(`UPDATE event_wfs_fee_case SET first_alert_at=NOW() WHERE id=? AND first_alert_at IS NULL`, [a.id]);
        }
      } else sentFail++;
    }
  } finally { await db.end().catch(() => undefined); }
  console.log("SUMMARY_JSON=" + JSON.stringify({
    mode: send ? (testSend ? "test" : "send") : "dry-run", action: "detect",
    scanned, no_manual_fee: noManual, anomalies, created, refreshed, skipped_closed: skippedClosed,
    sent_ok: sentOk, sent_fail: sentFail, status: "success",
  }));
}

main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
