/**
 * arrivalNotify.ts - 到货提醒发送（读 event_arrival_notify pending → feishuNotify 统一发送）
 *
 * 通道（2026-07-14 需求方确认；2026-07-18 需求方指令变更：群通道停用）：
 *   - 群（FEISHU_ARRIVAL_CHAT_ID）：【已停用】只发个人私信+测试群镜像，不发业务群；
 *     恢复方式 FEISHU_ARRIVAL_GROUP_ENABLED=1（逻辑保留未删）。停用时事件回写挂个人私信通道，
 *     无负责人/花名册未命中的事件走测试群兜底并回写（防止 pending 堆积每日重复）。
 *   - 负责人私信：按 owner 聚合其名下事件（花名册 active 解析）
 *   - 升级同步接收人：FEISHU_ARRIVAL_ESCALATION_USERS（姓名列表，默认配"黄少如"，经花名册解析）
 *
 * 模式（批B规范）：
 *   默认 dry-run（零发送、零回写）；--send 生产发送并回写 notify_status；
 *   --test-send 全部消息只发测试群（FEISHU_NOTIFY_TEST_CHAT_ID），标题带【测试】，
 *   成功输出 NOTIFY_TEST_SENT=1，不回写事件状态、不解析真实接收人 open_id。
 *   --send 与 --test-send 禁止同用。
 *
 * 运行：
 *   npx ts-node src/arrivalNotify.ts               # dry-run
 *   npx ts-node src/arrivalNotify.ts --send        # 生产发送
 *   npx ts-node src/arrivalNotify.ts --test-send   # 测试群旁路
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import {
  getTenantToken,
  resolveActiveMembers,
  sendTextToTarget,
  sendTestGroupText,
  sendWebhookText,
  parseListEnv,
  formatResults,
  NotifyTarget,
  SendResult,
} from "./feishuNotify";
import {
  buildReceivingText,
  buildClosedText,
  buildStockOnlineText,
  buildNoAdsOwnerText,
  buildEscalationText,
  ShipmentEventPayload,
} from "./notifyRules/wfsArrivalRule";
import { buildAdGroupSilentText, buildAdGroupNoSpendText } from "./notifyRules/adGroupSilenceRule";

const SCRIPT_NAME = "arrivalNotify";
const MAX_EVENTS_PER_RUN = 200;

const doSend = process.argv.includes("--send");
const testSend = process.argv.includes("--test-send");
if (doSend && testSend) {
  console.log("[错误] --send 与 --test-send 禁止同时使用");
  process.exit(1);
}

interface EventRow {
  id: number;
  event_type: string;
  biz_key: string;
  event_date: string;
  owner: string;
  payload_json: Record<string, unknown> | null;
}

function buildEventText(e: EventRow): string {
  const p = (e.payload_json ?? {}) as Record<string, unknown>;
  switch (e.event_type) {
    case "wfs_shipment_receiving":
      return buildReceivingText(p as unknown as ShipmentEventPayload);
    case "wfs_shipment_closed":
      return buildClosedText(p as unknown as ShipmentEventPayload);
    case "wfs_stock_first_available":
      return buildStockOnlineText({
        storeName: String(p.storeName ?? ""), msku: String(p.msku ?? ""),
        productName: String(p.productName ?? ""), owner: String(p.owner ?? e.owner ?? ""),
        sellableDate: String(p.sellableDate ?? e.event_date), wfsQty: Number(p.wfsQty ?? 0),
      });
    case "wfs_no_ads_daily":
      return buildNoAdsOwnerText({
        storeName: String(p.storeName ?? ""), msku: String(p.msku ?? ""),
        productName: String(p.productName ?? ""), owner: String(p.owner ?? e.owner ?? ""),
        sellableDate: String(p.sellableDate ?? ""), noAdsDays: Number(p.noAdsDays ?? 0),
        dataThrough: String(p.dataThrough ?? ""),
      });
    case "wfs_no_ads_escalation":
      return buildEscalationText({
        storeName: String(p.storeName ?? ""), msku: String(p.msku ?? ""),
        productName: String(p.productName ?? ""), owner: String(p.owner ?? e.owner ?? ""),
        sellableDate: String(p.sellableDate ?? ""), noAdsDays: Number(p.noAdsDays ?? 0),
        dataThrough: String(p.dataThrough ?? ""),
      });
    case "ad_group_silent":
      return buildAdGroupSilentText({
        storeName: String(p.storeName ?? ""), campaignName: String(p.campaignName ?? ""),
        adGroupName: String(p.adGroupName ?? ""), msku: String(p.msku ?? ""),
        productName: String(p.productName ?? ""), owner: String(p.owner ?? e.owner ?? ""),
        dataThrough: String(p.dataThrough ?? ""), silentDays: Number(p.silentDays ?? 0),
      });
    case "ad_group_no_spend":
      return buildAdGroupNoSpendText({
        storeName: String(p.storeName ?? ""), campaignName: String(p.campaignName ?? ""),
        adGroupName: String(p.adGroupName ?? ""), msku: String(p.msku ?? ""),
        productName: String(p.productName ?? ""), owner: String(p.owner ?? e.owner ?? ""),
        dataThrough: String(p.dataThrough ?? ""), noSpendDays: Number(p.noSpendDays ?? 0),
      });
    default:
      return `【到货提醒】未知事件类型 ${e.event_type}（biz_key=${e.biz_key}）`;
  }
}

async function updateEventStatus(db: mysql.Connection, ids: number[], ok: boolean, error: string): Promise<void> {
  if (!ids.length) return;
  await db.query(
    `UPDATE event_arrival_notify
     SET notify_status = ?, notified_at = ${ok ? "NOW()" : "NULL"}, notify_error = ?
     WHERE id IN (${ids.map(() => "?").join(",")})`,
    [ok ? "notified" : "failed", ok ? "" : error.slice(0, 500), ...ids],
  );
}

async function main(): Promise<void> {
  const mode = testSend ? "test-send（仅测试群）" : doSend ? "真实发送" : "dry-run（零发送零回写）";
  console.log("=".repeat(60));
  console.log(`到货提醒发送 模式: ${mode}`);
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
    // 到货专线（2026-07-15 需求方决定）：本脚本只发 wfs_* 到货链路事件。
    // 广告组静默（ad_group_silent / ad_group_no_spend）与到货是两件事，
    // 不共用发送通道——其事件继续由 20:45 任务生成留痕，但不进本队列，
    // 待专属发送方案确定后由独立脚本发送（届时需先将历史积压标记 skipped）。
    const ARRIVAL_EVENT_TYPES = [
      "wfs_shipment_receiving",
      "wfs_shipment_closed",
      "wfs_stock_first_available",
      "wfs_no_ads_daily",
      "wfs_no_ads_escalation",
    ];
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id, event_type, biz_key, event_date, COALESCE(owner,'') AS owner, payload_json
       FROM event_arrival_notify
       WHERE notify_status = 'pending'
         AND event_type IN (${ARRIVAL_EVENT_TYPES.map(() => "?").join(",")})
       ORDER BY FIELD(event_type,'wfs_no_ads_escalation') DESC, id ASC
       LIMIT ?`,
      [...ARRIVAL_EVENT_TYPES, MAX_EVENTS_PER_RUN],
    );
    const events = rows as unknown as EventRow[];
    console.log(`待发送事件: ${events.length}`);
    if (!events.length) {
      if (testSend) {
        // 测试模式无事件也要验证链路可达
        const r = await sendTestGroupText("【测试】到货提醒链路", "【测试】到货提醒系统链路验证：当前无待发送事件。");
        console.log(formatResults([r]));
        if (r.ok) console.log("NOTIFY_TEST_SENT=1");
        else process.exitCode = 1;
      }
      return;
    }

    const escalations = events.filter((e) => e.event_type === "wfs_no_ads_escalation");
    const normals = events.filter((e) => e.event_type !== "wfs_no_ads_escalation");

    // 组装：群消息（升级逐条 + 汇总一条）
    const groupMessages: Array<{ label: string; text: string; eventIds: number[] }> = [];
    for (const e of escalations) {
      groupMessages.push({ label: `升级通报 ${e.biz_key}`, text: buildEventText(e), eventIds: [e.id] });
    }
    if (normals.length) {
      const summary = [`【到货提醒汇总】共 ${normals.length} 条`, ""];
      for (const e of normals) summary.push(buildEventText(e), "─".repeat(30));
      groupMessages.push({ label: "到货提醒汇总", text: summary.join("\n"), eventIds: normals.map((e) => e.id) });
    }

    // 组装：负责人私信（owner → 其名下事件全文）
    const byOwner = new Map<string, EventRow[]>();
    for (const e of events) {
      const owner = e.owner.trim();
      if (!owner) continue; // 未匹配负责人：仅进群汇总
      if (!byOwner.has(owner)) byOwner.set(owner, []);
      byOwner.get(owner)!.push(e);
    }

    // ── test-send：全部旁路测试群 ──────────────────────────────────
    if (testSend) {
      let allOk = true;
      for (const m of groupMessages) {
        const r = await sendTestGroupText(`【测试】${m.label}`, `【测试】${m.text}`);
        console.log(formatResults([r]));
        if (!r.ok) allOk = false;
      }
      for (const [owner, list] of byOwner) {
        const text = `【测试】以下为将私信「${owner}」的内容：\n\n${list.map(buildEventText).join("\n" + "─".repeat(30) + "\n")}`;
        const r = await sendTestGroupText(`【测试】负责人私信预览-${owner}`, text);
        console.log(formatResults([r]));
        if (!r.ok) allOk = false;
      }
      if (allOk) console.log("NOTIFY_TEST_SENT=1");
      else process.exitCode = 1;
      console.log("[test-send] 不回写事件状态，事件保持 pending。");
      return;
    }

    // ── dry-run / --send ──────────────────────────────────────────
    const results: SendResult[] = [];
    let anyFail = false;

    // 1) 群通道：2026-07-18 需求方指令停用（只发个人私信+测试群镜像，不发任何业务群）。
    //    恢复方式：FEISHU_ARRIVAL_GROUP_ENABLED=1（原逻辑保留未删）。
    const groupEnabled = (process.env.FEISHU_ARRIVAL_GROUP_ENABLED ?? "0").trim() === "1";
    const chatId = (process.env.FEISHU_ARRIVAL_CHAT_ID ?? "").trim();
    const groupWebhook = (process.env.FEISHU_ARRIVAL_WEBHOOK_URL ?? "").trim();
    let token = "";
    if (doSend) token = await getTenantToken();
    if (!groupEnabled) {
      console.log("[群通道] 已停用（2026-07-18 需求方指令），事件回写挂个人私信通道，无负责人事件走测试群兜底");
    } else {
      if (!chatId && !groupWebhook) {
        console.log("[警告] FEISHU_ARRIVAL_CHAT_ID 与 FEISHU_ARRIVAL_WEBHOOK_URL 均未配置，群通道跳过");
      }
      for (const m of groupMessages) {
        let r: SendResult | null = null;
        if (chatId) {
          r = await sendTextToTarget(token, { type: "chat", label: `到货群:${m.label}`, id: chatId }, m.text, doSend);
        } else if (groupWebhook) {
          r = await sendWebhookText(groupWebhook, `到货群webhook:${m.label}`, m.text, doSend);
        }
        if (r) {
          results.push(r);
          if (doSend) await updateEventStatus(db, m.eventIds, r.ok, r.error ?? "");
          if (!r.ok) anyFail = true;
        }
      }
    }

    // 2) 负责人私信（dry-run 禁止真实ID解析，只打印预览）
    //    2026-07-18：群通道停用时，事件状态回写在此通道完成；已尝试私信的事件记入 personallyCovered
    const personallyCovered = new Set<number>();
    if (byOwner.size) {
      if (!doSend) {
        for (const [owner, list] of byOwner) {
          console.log(`\n[dry-run] 将私信「${owner}」${list.length} 条事件（未解析 open_id）`);
        }
      } else {
        const { targets, warnings } = await resolveActiveMembers([...byOwner.keys()]);
        for (const w of warnings) console.log(`  [花名册] ${w}`);
        const targetMap = new Map(targets.map((t) => [t.label, t]));
        for (const [owner, list] of byOwner) {
          const target = targetMap.get(owner);
          if (!target) { console.log(`  [跳过] 负责人「${owner}」花名册未命中，其事件${groupEnabled ? "仅走群汇总" : "走测试群兜底"}`); continue; }
          const text = list.map(buildEventText).join("\n" + "─".repeat(30) + "\n");
          const r = await sendTextToTarget(token, target, text, true);
          results.push(r);
          list.forEach((e) => personallyCovered.add(e.id));
          if (!groupEnabled) await updateEventStatus(db, list.map((e) => e.id), r.ok, r.error ?? "");
          if (!r.ok) anyFail = true;
        }
      }
    }

    // 2b) 群通道停用时的兜底：无负责人/花名册未命中的事件 → 测试群 + 回写（防 pending 堆积每日重复）
    if (!groupEnabled) {
      if (!doSend) {
        const ownerlessCnt = events.filter((e) => !e.owner.trim()).length;
        if (ownerlessCnt) console.log(`[dry-run] 群通道停用：${ownerlessCnt} 条无负责人事件将走测试群兜底`);
      } else {
        const uncovered = events.filter((e) => !personallyCovered.has(e.id));
        if (uncovered.length) {
          const text = `【兜底】群通道已停用，以下 ${uncovered.length} 条事件无私信目标（无负责人或花名册未命中）：\n\n` +
            uncovered.map(buildEventText).join("\n" + "─".repeat(30) + "\n");
          const r = await sendTestGroupText("到货提醒-无负责人兜底", text);
          results.push(r);
          await updateEventStatus(db, uncovered.map((e) => e.id), r.ok, r.error ?? "");
          if (!r.ok) anyFail = true;
        }
      }
    }

    // 3) 升级同步接收人（默认配置 黄少如；仅升级事件触发）
    if (escalations.length) {
      const escalationNames = parseListEnv("FEISHU_ARRIVAL_ESCALATION_USERS");
      if (!escalationNames.length) {
        console.log("[警告] 存在升级事件但未配置 FEISHU_ARRIVAL_ESCALATION_USERS，升级同步通道跳过");
      } else if (!doSend) {
        console.log(`[dry-run] 将同步升级通报给: ${escalationNames.join("、")}（${escalations.length} 条，未解析 open_id）`);
      } else {
        const { targets, warnings } = await resolveActiveMembers(escalationNames);
        for (const w of warnings) console.log(`  [花名册] ${w}`);
        const text = escalations.map(buildEventText).join("\n" + "─".repeat(30) + "\n");
        for (const t of targets) {
          const r = await sendTextToTarget(token, t, text, true);
          results.push(r);
          if (!r.ok) anyFail = true;
        }
      }
    }

    console.log("\n" + "=".repeat(60));
    console.log(formatResults(results));
    if (anyFail) process.exitCode = 1;
    if (!doSend) console.log("[dry-run] 零发送零回写，加 --send 生产发送。");
  } finally {
    await db.end().catch(() => {});
  }
}

main().catch((e) => {
  console.error(`${SCRIPT_NAME} 失败:`, e instanceof Error ? e.message : String(e));
  process.exit(1);
});
