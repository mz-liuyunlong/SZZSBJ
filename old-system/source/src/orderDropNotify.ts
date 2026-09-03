/**
 * orderDropNotify.ts - 订单异常下滑发送（16:50，读 biz_event 按负责人汇总）
 *
 * 通道（批B规范）：
 *   默认 dry-run（零发送零回写）
 *   --send      生产：负责人私信 + 群（FEISHU_ORDER_DROP_CHAT_ID，未配置跳过群）；
 *               监督镜像由 feishuNotify 全局开关自动生效
 *   --test-send 观察期：全部只进测试群，输出 NOTIFY_TEST_SENT=1
 * 去重：只发 event_date=当日数据日 且 extra_json.notified 未置位的 open 事件；
 *       发送成功后回写 extra_json.notified=1（只动事件自身状态，不碰其他层）。
 *
 * 运行：
 *   npx ts-node src/orderDropNotify.ts               # dry-run
 *   npx ts-node src/orderDropNotify.ts --test-send   # 测试群（观察期用）
 *   npx ts-node src/orderDropNotify.ts --send        # 生产
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import {
  getTenantToken,
  getTestChatId,
  resolveActiveMembers,
  sendCardWithFallbackToChat,
  sendTextToTarget,
  sendTestGroupText,
  formatResults,
  SendResult,
} from "./feishuNotify";
import { buildOwnerMessage, streakLabel, OrderDropItemInfo } from "./notifyRules/orderDropRule";
import { buildOrderDropCard, OrderDropCardItem } from "./notifyRules/reminderCards";
import { toSafeQty } from "./notifyRules/noOrderInventoryRule";

const SCRIPT_NAME = "orderDropNotify";

const doSend = process.argv.includes("--send");
const testSend = process.argv.includes("--test-send");
// 2026-07-18 需求方指令：卡片版预览（🔻 订单异常下滑提醒），只发测试群、不回写 notified、生产路径不动
const testCard = process.argv.includes("--test-card");
if (doSend && testSend) {
  console.log("[错误] --send 与 --test-send 禁止同时使用");
  process.exit(1);
}
if (testCard && (doSend || testSend)) {
  console.log("[错误] --test-card 与 --send/--test-send 禁止同时使用");
  process.exit(1);
}

function pad2(n: number): string { return String(n).padStart(2, "0"); }
function dataDateCst(): string {
  // 与 checkOrderDrop 同口径：当日 = 中国今天-1
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const [y, m, d] = today.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() - 1);
  return `${dt.getUTCFullYear()}-${pad2(dt.getUTCMonth() + 1)}-${pad2(dt.getUTCDate())}`;
}

async function main(): Promise<void> {
  const mode = testSend ? "test-send（仅测试群）" : doSend ? "生产发送" : "dry-run";
  const dataDate = dataDateCst();
  console.log("=".repeat(60));
  console.log(`订单异常下滑发送 模式=${mode} 数据日期=${dataDate}`);
  console.log("=".repeat(60));

  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  });

  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      // 2026-07-18: --test-card 预览含已发送事件（不回写，重复查看无害），生产/test-send 仍只取未发送
      `SELECT event_id, source_key, COALESCE(owner,'') AS owner, extra_json
       FROM biz_event
       WHERE event_type = 'order_drop' AND status = 'open' AND event_date = ?
         ${testCard ? "" : "AND COALESCE(JSON_EXTRACT(extra_json, '$.notified'), 0) = 0"}
       ORDER BY owner, event_id`,
      [dataDate],
    );
    console.log(`待发送事件: ${rows.length}`);
    if (!rows.length) {
      if (testSend || testCard) {
        const r = await sendTestGroupText("【测试】订单下滑链路", `【测试】订单异常下滑系统链路验证：数据日期 ${dataDate} 无异常事件。`);
        console.log(formatResults([r]));
        if (r.ok) console.log("NOTIFY_TEST_SENT=1"); else process.exitCode = 1;
      }
      return;
    }

    // 按负责人分组
    const byOwner = new Map<string, { eventIds: number[]; items: OrderDropItemInfo[] }>();
    for (const r of rows) {
      const ex = (typeof r.extra_json === "object" && r.extra_json ? r.extra_json : {}) as Record<string, unknown>;
      const owner = String(r.owner ?? "").trim() || "未匹配负责人";
      if (!byOwner.has(owner)) byOwner.set(owner, { eventIds: [], items: [] });
      const g = byOwner.get(owner)!;
      g.eventIds.push(Number(r.event_id));
      g.items.push({
        itemId: String(ex.itemId ?? ""),
        storeName: String(ex.storeName ?? ""),
        msku: String(ex.msku ?? ""),
        productName: String(ex.productName ?? ""),
        baseline: Array.isArray(ex.baseline) ? (ex.baseline as number[]).map(toSafeQty) : [],
        current: toSafeQty(ex.current),
        avg: toSafeQty(ex.avg),
        dropPct: ex.dropPct === null || ex.dropPct === undefined ? null : Number(ex.dropPct),
        reason: ex.reason === "zero_streak" ? "zero_streak" : "drop",
        consecutiveDays: toSafeQty(ex.consecutiveDays) || 1,
      });
    }

    const markNotified = async (ids: number[]): Promise<void> => {
      if (!ids.length) return;
      await db.query(
        `UPDATE biz_event SET extra_json = JSON_SET(COALESCE(extra_json,'{}'), '$.notified', 1)
         WHERE event_id IN (${ids.map(() => "?").join(",")})`,
        ids,
      );
    };

    // ── 2026-07-18 --test-card：卡片版预览，只发测试群，不回写 notified ──
    if (testCard) {
      const cardItems: OrderDropCardItem[] = [];
      for (const [owner, g] of byOwner) {
        for (const p of g.items) {
          const baseTxt = p.baseline.join(" / ");
          const detail = p.reason === "zero_streak"
            ? `近3天订单 ${baseTxt}（日均${p.avg}）→ 连续${p.consecutiveDays >= 3 ? p.consecutiveDays : 3}天 0 单`
            : `近3天订单 ${baseTxt}（日均${p.avg}）→ 当日 ${p.current}　↓${p.dropPct !== null ? (p.dropPct * 100).toFixed(1) : "?"}%`;
          cardItems.push({
            owner: owner === "未匹配负责人" ? "" : owner,
            storeName: p.storeName, itemId: p.itemId, msku: p.msku, productName: p.productName,
            detail, streak: streakLabel(p.consecutiveDays),
          });
        }
      }
      const bundle = buildOrderDropCard(dataDate, cardItems, { testPrefix: true });
      const r = await sendCardWithFallbackToChat("订单下滑卡片预览", getTestChatId(), bundle.card, bundle.fallbackText);
      console.log(`[test-card] 结果: ok=${r.ok} cardOk=${r.cardOk} fallbackUsed=${r.fallbackUsed}${r.error ? ` error=${r.error}` : ""}`);
      if (r.ok) console.log("NOTIFY_TEST_SENT=1");
      else process.exitCode = 1;
      console.log("[test-card] 不回写 notified，事件保持待发送状态。");
      return;
    }

    // ── test-send：全部旁路测试群 ──
    if (testSend) {
      let allOk = true;
      for (const [owner, g] of byOwner) {
        const text = buildOwnerMessage(owner, dataDate, g.items);
        const r = await sendTestGroupText(`【测试】订单下滑-${owner}`, `【测试】${text}`);
        console.log(formatResults([r]));
        if (!r.ok) allOk = false;
      }
      if (allOk) console.log("NOTIFY_TEST_SENT=1"); else process.exitCode = 1;
      console.log("[test-send] 不回写 notified，事件保持待发送状态。");
      return;
    }

    // ── dry-run / --send ──
    const results: SendResult[] = [];
    let anyFail = false;
    let token = "";
    if (doSend) token = await getTenantToken();

    // 群汇总（可选通道）
    const chatId = (process.env.FEISHU_ORDER_DROP_CHAT_ID ?? "").trim();
    if (chatId) {
      const allItems = [...byOwner.entries()].map(([o, g]) => `— ${o}：${g.items.length}个异常`).join("\n");
      const summary = `【订单异常下滑汇总】数据日期：${dataDate}\n${allItems}`;
      const r = await sendTextToTarget(token, { type: "chat", label: "订单下滑群汇总", id: chatId }, summary, doSend);
      results.push(r);
      if (!r.ok) anyFail = true;
    }

    // 2026-07-20 需求方指令：私信不再分发各负责人，统一发送给指定接收人
    // （默认 林翔，env FEISHU_ORDER_DROP_RECEIVER 可覆盖）；消息仍按负责人分组，标题可见归属
    const receiverName = (process.env.FEISHU_ORDER_DROP_RECEIVER ?? "林翔").trim();
    if (!doSend) {
      for (const [owner, g] of byOwner) console.log(`\n[dry-run] 「${owner}」${g.items.length} 个异常 → 统一私信「${receiverName}」（未解析 open_id）`);
    } else {
      const { targets, warnings } = await resolveActiveMembers([receiverName]);
      for (const w of warnings) console.log(`  [花名册] ${w}`);
      const target = targets.find((t) => t.label === receiverName);
      if (!target) {
        console.log(`  [错误] 统一接收人「${receiverName}」花名册未命中，本次不发送不回写（事件保持待发送）`);
        anyFail = true;
      } else {
        for (const [owner, g] of byOwner) {
          const text = buildOwnerMessage(owner, dataDate, g.items);
          const r = await sendTextToTarget(token, target, text, true);
          results.push(r);
          if (r.ok) await markNotified(g.eventIds);
          else anyFail = true;
        }
      }
    }

    console.log("\n" + "=".repeat(60));
    console.log(formatResults(results));
    if (anyFail) process.exitCode = 1;
    if (!doSend) console.log("[dry-run] 零发送零回写。观察期请用 --test-send。");
  } finally {
    await db.end().catch(() => {});
  }
}

main().catch((e) => {
  console.error(`${SCRIPT_NAME} 失败:`, e instanceof Error ? e.message : String(e));
  process.exit(1);
});
