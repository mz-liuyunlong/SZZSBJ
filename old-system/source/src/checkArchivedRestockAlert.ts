/**
 * checkArchivedRestockAlert.ts — 归档产品到货提醒·交互卡片版（2026-08-05，需求方拍板）
 *
 * 背景：归档后又有新货到仓的产品（如 JJ8044-1U 93件）会游离在目标管理/催办/扣分之外。
 * 规则（需求方 2026-08-04/05 定稿）：
 *   - 归档(product_management_status='archived') 且 最新快照 WFS 库存 > 5 件；
 *   - 飞书【交互卡片】按产品逐张发送，卡片按钮：✅恢复在售 / 📦继续归档(不再提醒)；
 *     按钮回调见 feishuCardCallbackRoutes(biz='archived_restock')，事件表 event_archived_restock_alert(SQL039)。
 *   - 发对应负责人(owner DM)；负责人为空或不可达 → 发群(BUSINESS_REPORT_CHAT_ID)兜底；
 *   - 已点「继续归档」(decision='keep') 的产品暂停提醒；【库存较确认时基线增长】则重新提醒并要求再次确认
 *     （需求方 2026-08-05 修正：不永久静默）。「恢复在售」后转 active 自然移出扫描。
 *   - 本脚本只发卡+登记事件，不改产品状态（状态变更仅由卡片按钮回调执行）。
 *
 * 用法：
 *   npx ts-node src/checkArchivedRestockAlert.ts                 # dry-run（只打印，零发送零写入）
 *   npx ts-node src/checkArchivedRestockAlert.ts --send          # 真实发送（登记事件+发卡）
 *   npx ts-node src/checkArchivedRestockAlert.ts --test-send --send  # 全发测试群（卡片带 test:1，按钮只应答不落库；不登记事件）
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import {
  NotifyTarget, getTestChatId, resolveActiveMembers, sendCardToTarget,
} from "./feishuNotify";

const MIN_WFS = Number(process.env.ARCHIVED_RESTOCK_MIN_WFS ?? 5); // 严格大于该值才提醒

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

interface Row {
  store_id: string; item_id: string; owner: string; mskus: string;
  store_name: string; reason: string; status_at: string; wfs: number;
  prev_decision: string; prev_qty: number;
}

async function fetchArchivedWithStock(db: mysql.Connection): Promise<Row[]> {
  const [rows] = await db.execute(
    `SELECT d.store_id, d.item_id, d.owner_raw AS owner, d.mskus,
            COALESCE(NULLIF(ds.store_name,''), d.store_id) AS store_name,
            d.reason, d.status_at, i.wfs,
            COALESCE(e.decision,'') AS prev_decision, COALESCE(e.wfs_qty,0) AS prev_qty
     FROM (
       SELECT store_id, item_id,
              MAX(COALESCE(NULLIF(owner,''),'')) AS owner_raw,
              SUBSTRING(GROUP_CONCAT(DISTINCT NULLIF(msku,'') ORDER BY msku SEPARATOR '/'),1,120) AS mskus,
              MAX(COALESCE(product_management_status_reason,'')) AS reason,
              DATE_FORMAT(MAX(product_management_status_updated_at),'%Y-%m-%d') AS status_at
       FROM dim_product
       WHERE platform='walmart' AND product_management_status='archived'
       GROUP BY store_id, item_id
     ) d
     JOIN (
       SELECT store_id, item_id, SUM(COALESCE(wfs_available_stock,0)) AS wfs
       FROM fact_inventory_daily
       WHERE platform='walmart'
         AND snapshot_date=(SELECT MAX(snapshot_date) FROM fact_inventory_daily WHERE platform='walmart')
       GROUP BY store_id, item_id
       HAVING SUM(COALESCE(wfs_available_stock,0)) > ?
     ) i ON i.store_id=d.store_id AND i.item_id=d.item_id
     LEFT JOIN dim_store ds ON ds.platform='walmart' AND ds.store_id=d.store_id
     LEFT JOIN event_archived_restock_alert e
       ON e.platform='walmart' AND e.store_id=d.store_id AND e.item_id=d.item_id
     WHERE (COALESCE(e.decision,'') <> 'keep' OR i.wfs > COALESCE(e.wfs_qty,0))
     ORDER BY d.owner_raw, i.wfs DESC`,
    [MIN_WFS],
  );
  return (rows as Array<Record<string, unknown>>).map((r) => ({
    store_id: String(r.store_id), item_id: String(r.item_id),
    owner: String(r.owner ?? "").trim(), mskus: String(r.mskus ?? ""),
    store_name: String(r.store_name ?? ""), reason: String(r.reason ?? ""),
    status_at: String(r.status_at ?? ""), wfs: Number(r.wfs ?? 0),
    prev_decision: String(r.prev_decision ?? ""), prev_qty: Number(r.prev_qty ?? 0),
  }));
}

/** 登记/刷新事件行，返回事件 id（卡片按钮回调据此定位产品） */
async function upsertEvent(db: mysql.Connection, r: Row): Promise<number> {
  const [ret] = await db.execute(
    `INSERT INTO event_archived_restock_alert
       (platform, store_id, item_id, mskus, owner_name, wfs_qty, first_alert_date, last_alert_date)
     VALUES ('walmart', ?, ?, ?, ?, ?, CURDATE(), CURDATE())
     ON DUPLICATE KEY UPDATE
       id=LAST_INSERT_ID(id), mskus=VALUES(mskus), owner_name=VALUES(owner_name),
       wfs_qty=VALUES(wfs_qty), last_alert_date=VALUES(last_alert_date),
       decision=IF(decision='keep','',decision)`, // keep后库存增长重新入列→清空决策使按钮可用(历史决策人留decided_by/at)
    [r.store_id, r.item_id, r.mskus, r.owner, r.wfs],
  );
  return Number((ret as mysql.ResultSetHeader).insertId ?? 0);
}

function buildCard(r: Row, evId: number, test: boolean): { card: Record<string, unknown>; fb: string } {
  const card = {
    config: { wide_screen_mode: true },
    header: { template: "orange", title: { tag: "plain_text", content: "📦 归档产品有库存提醒" } },
    elements: [
      { tag: "div", text: { tag: "lark_md", content:
        `**店铺**：${r.store_name}\n**ItemID**：${r.item_id}\n**MSKU**：${r.mskus || "-"}\n` +
        `**WFS 库存**：<font color='red'>${r.wfs} 件</font>\n**归档时间**：${r.status_at || "-"}\n**归档原因**：${r.reason || "-"}` +
        (r.prev_decision === "keep" ? `\n**库存变化**：<font color='red'>上次确认继续归档时 ${r.prev_qty} 件 → 现 ${r.wfs} 件（有增长，需重新确认）</font>` : "") } },
      { tag: "div", text: { tag: "lark_md", content:
        "该产品处于归档状态但有 WFS 库存，请选择：<font color='grey'>恢复在售＝转回在营（自动进入目标管理/考核）；继续归档＝确认现状，暂停提醒（库存再增长时会重新提醒）。</font>" } },
      { tag: "action", actions: [
        { tag: "button", text: { tag: "plain_text", content: "✅ 恢复在售" }, type: "primary",
          value: Object.assign({ biz: "archived_restock", id: evId, choice: "restore" }, test ? { test: 1 } : {}) },
        { tag: "button", text: { tag: "plain_text", content: "📦 继续归档（暂停提醒）" }, type: "default",
          value: Object.assign({ biz: "archived_restock", id: evId, choice: "keep" }, test ? { test: 1 } : {}) },
      ] },
      { tag: "note", elements: [{ tag: "plain_text", content: `每日 09:40 自动检测（WFS>${MIN_WFS}）。仅负责人/超管可操作按钮。` }] },
    ],
  };
  const fb = `【归档产品有库存提醒】${r.store_name}｜ItemID ${r.item_id}｜${r.mskus || "-"}｜WFS ${r.wfs}件｜归档:${r.status_at} ${r.reason || "-"}；请在卡片选择 恢复在售/继续归档。`;
  return { card, fb };
}

async function main(): Promise<void> {
  const a = process.argv.slice(2);
  const send = a.includes("--send");
  const testSend = a.includes("--test-send") || (process.env.BUSINESS_REPORT_FORCE_TEST ?? "").trim() === "1";

  const db = await getDb();
  let list: Row[] = [];
  let ok = 0, fail = 0;
  const warnings: string[] = [];
  try {
    list = await fetchArchivedWithStock(db);
    if (list.length === 0) {
      console.log(`ARCHIVED_RESTOCK_SKIP 无「归档且WFS>${MIN_WFS}且未确认继续归档」产品`);
      console.log("SUMMARY_JSON=" + JSON.stringify({ count: 0, min_wfs: MIN_WFS, status: "success" }));
      return;
    }

    const groupChatId = (process.env.BUSINESS_REPORT_CHAT_ID ?? "").trim();
    // 负责人一次性解析（去重）
    const ownerNames = [...new Set(list.map((r) => r.owner).filter(Boolean))];
    const ownerTargets = new Map<string, NotifyTarget>();
    if (send && !testSend && ownerNames.length > 0) {
      const { targets } = await resolveActiveMembers(ownerNames);
      for (const t of targets) ownerTargets.set(t.label, t);
    }

    for (const r of list) {
      // 事件登记：仅真实发送时写库（test/dry-run 零写入，test 卡 id=0 且 test:1 → 回调只应答）
      const evId = send && !testSend ? await upsertEvent(db, r) : 0;
      const { card, fb } = buildCard(r, evId, testSend);
      if (!send) { // dry-run：不解析负责人、不产生兜底 warning
        console.log(`[dry-run] 卡片 → ${r.owner ? `私聊「${r.owner}」` : "群「经营周报群」"}\n${fb}\n`);
        ok++;
        continue;
      }
      let target: NotifyTarget | null = null;
      let plannedLabel = "";
      if (testSend) {
        target = { type: "chat", label: `测试群(原目标:${r.owner || "经营周报群"})`, id: getTestChatId() };
        plannedLabel = target.label;
      } else if (r.owner && ownerTargets.has(r.owner)) {
        target = ownerTargets.get(r.owner) as NotifyTarget;
        plannedLabel = `私聊「${r.owner}」`;
      } else {
        if (r.owner) warnings.push(`负责人「${r.owner}」不可达，转发群`);
        if (groupChatId) { target = { type: "chat", label: "经营周报群", id: groupChatId }; plannedLabel = "群「经营周报群」"; }
        else { warnings.push("缺少 BUSINESS_REPORT_CHAT_ID，群消息跳过"); }
      }
      if (!target) { fail++; continue; }
      const rr = await sendCardToTarget(target, card, fb, true);
      if (rr.ok) ok++; else { fail++; warnings.push(`发送失败:${plannedLabel}(${rr.error ?? ""})`); }
    }
  } finally {
    await db.end().catch(() => undefined);
  }

  console.log("SUMMARY_JSON=" + JSON.stringify({
    count: list.length, sent_ok: ok, sent_fail: fail, warnings, min_wfs: MIN_WFS,
    mode: !send ? "dry-run" : testSend ? "test" : "send", status: fail === 0 ? "success" : "partial_failed",
  }));
  if (send) process.exit(fail === 0 ? 0 : 1);
}

main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
