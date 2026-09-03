/**
 * productRuleSignalNotify.ts - B线第5期：产品规则信号飞书通报（测试版）
 *
 * 数据流：biz_product_rule_signal_daily (20:55生成, should_notify=1)
 *        → 去重判定(EVENT层 event_product_rule_signal_notify)
 *        → 飞书群消息（测试阶段只发群，负责人个人消息为转正后二期）
 *
 * 批次判定（该表无 batch_id/completed_at，按扫描定稿的近似口径）：
 *   取 MAX(signal_date) 为最近批次；校验该批 created_at 首尾跨度 <= 10 分钟
 *   （20:55 单事务写入，实测首尾同秒）且行数>0，否则视为批次异常中止。
 *
 * 去重策略（定稿）：
 *   指纹 = platform|store_id|item_id|msku|rule_code（不含 owner：改派不算新信号，owner 仅展示）
 *   1. 新触发（无开放周期）→ 发送，插入周期行 notify_count=1
 *   2. 持续存在 → 距 last_notified_at 满 notify_frequency_days（信号自带，缺省3天）再提醒一次
 *   3. 恢复（当批不再出现）→ 周期行置 closed；再次触发视为新信号（新周期行）
 *   4. 同批次重跑不重复：同指纹同 signal_date 已通知 → 跳过（幂等）
 *   5. 发送失败不写去重状态（send_status 不落 sent、不更新 last_notified_at）→ 下次运行重发
 *
 * 体积控制：每负责人最多展开 10 条 + "另有N条"计数；超 28000 字符自动分片。
 *
 * 参数：默认 dry-run（不发送、不写事件表）；--send 发送并落事件表；
 *       --date=YYYY-MM-DD 指定批次日期；--force-preview 忽略去重预览全量（强制 dry-run）。
 * 接收群：env RULE_SIGNAL_CHAT_IDS（测试阶段=测试群，转正改生产群，代码零改动）。
 * 建议 cron（本轮不写入）：
 *   5 9 * * * cd /opt/lingxing-auto && npx ts-node src/productRuleSignalNotify.ts --send >> /opt/lingxing-auto/logs/product-rule-signal-notify.log 2>&1
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { parseListEnv, fanoutText, formatResults, getTestChatId, sendCardWithFallbackToChat, NotifyTarget, SendResult } from "./feishuNotify";
import { buildRuleSignalCard } from "./notifyRules/reminderCards";

const SIGNAL_TABLE = "biz_product_rule_signal_daily";
const EVENT_TABLE = "event_product_rule_signal_notify";
const DEFAULT_FREQ_DAYS = 3;
const PER_OWNER_LIMIT = 10;
const BATCH_SPAN_MINUTES = 10;
const PAGE_URL = "http://42.193.254.170/admin/#/feishu-raw-sales-data";

interface SignalRow extends mysql.RowDataPacket {
  signal_date: string;
  platform: string;
  store_id: string | null;
  store_name: string | null;
  item_id: string;
  msku: string | null;
  owner: string | null;
  rule_code: string;
  rule_name: string | null;
  rule_level: string | null;
  trigger_reason: string | null;
  suggested_action: string | null;
  notify_frequency_days: number | null;
}

interface EventRow extends mysql.RowDataPacket {
  id: number;
  signal_fingerprint: string;
  signal_date: string;
  last_notified_at: string | null;
  notify_count: number;
  send_status: string;
}

type PlanKind = "new" | "repeat" | "skip";

function dbConfig() {
  return {
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true as const,
  };
}

function shTime(): string {
  return new Date().toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
}

function fingerprintOf(r: SignalRow): string {
  return [r.platform ?? "", r.store_id ?? "", r.item_id ?? "", r.msku ?? "", r.rule_code ?? ""].join("|");
}

function argValue(prefix: string): string {
  const a = process.argv.find((x) => x.startsWith(prefix));
  return a ? a.slice(prefix.length) : "";
}

async function resolveBatch(db: mysql.Connection, dateOverride: string): Promise<{ signalDate: string; ok: boolean; note: string }> {
  const dateCond = dateOverride ? "= ?" : `= (SELECT MAX(signal_date) FROM ${SIGNAL_TABLE})`;
  const params = dateOverride ? [dateOverride] : [];
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT DATE_FORMAT(MAX(signal_date), '%Y-%m-%d') AS d, COUNT(*) AS c,
            TIMESTAMPDIFF(MINUTE, MIN(created_at), MAX(created_at)) AS span_min
     FROM ${SIGNAL_TABLE} WHERE signal_date ${dateCond}`,
    params,
  );
  const d = String(rows[0]?.d ?? "");
  const c = Number(rows[0]?.c ?? 0);
  const span = Number(rows[0]?.span_min ?? 0);
  if (!d || c === 0) return { signalDate: d, ok: false, note: "目标批次无数据" };
  if (span > BATCH_SPAN_MINUTES) return { signalDate: d, ok: false, note: `批次 created_at 跨度 ${span} 分钟 > ${BATCH_SPAN_MINUTES}，疑似半批次` };
  return { signalDate: d, ok: true, note: `rows=${c}, created_at 跨度 ${span} 分钟` };
}

async function loadSignals(db: mysql.Connection, signalDate: string): Promise<SignalRow[]> {
  const [rows] = await db.query<SignalRow[]>(
    `SELECT DATE_FORMAT(s.signal_date, '%Y-%m-%d') AS signal_date,
            s.platform, s.store_id, s.store_name, s.item_id, s.msku, s.owner,
            s.rule_code, s.rule_name, s.rule_level, s.trigger_reason, s.suggested_action,
            s.notify_frequency_days
     FROM ${SIGNAL_TABLE} s
     LEFT JOIN dim_product p
       ON p.platform = s.platform AND COALESCE(p.store_id,'') = COALESCE(s.store_id,'')
      AND p.item_id = s.item_id AND COALESCE(p.msku,'') = COALESCE(s.msku,'')
     WHERE s.signal_date = ?
       AND s.should_notify = 1
       AND s.platform = 'walmart'
       AND COALESCE(p.product_management_status, 'active') <> 'archived'
     ORDER BY s.owner, s.rule_level, s.rule_code, s.item_id`,
    [signalDate],
  );
  return rows;
}

/** 打开中的周期行（同指纹最新一条非 closed） */
async function loadOpenCycles(db: mysql.Connection, fingerprints: string[]): Promise<Map<string, EventRow>> {
  const map = new Map<string, EventRow>();
  if (!fingerprints.length) return map;
  const [rows] = await db.query<EventRow[]>(
    `SELECT e.id, e.signal_fingerprint, DATE_FORMAT(e.signal_date, '%Y-%m-%d') AS signal_date,
            DATE_FORMAT(e.last_notified_at, '%Y-%m-%d %H:%i:%s') AS last_notified_at,
            e.notify_count, e.send_status
     FROM ${EVENT_TABLE} e
     JOIN (SELECT signal_fingerprint, MAX(id) AS max_id FROM ${EVENT_TABLE}
           WHERE signal_fingerprint IN (?) GROUP BY signal_fingerprint) latest
       ON latest.max_id = e.id
     WHERE e.send_status <> 'closed'`,
    [fingerprints],
  );
  for (const r of rows) map.set(r.signal_fingerprint, r);
  return map;
}

function daysBetween(fromDateTime: string, now: Date): number {
  const from = new Date(fromDateTime.replace(" ", "T") + "+08:00");
  return (now.getTime() - from.getTime()) / 86400000;
}

function buildMessage(signalDate: string, toNotify: SignalRow[], planKinds: Map<string, PlanKind>): string {
  const byOwner = new Map<string, SignalRow[]>();
  for (const s of toNotify) {
    const key = (s.owner ?? "").trim() || "(未分配负责人)";
    const list = byOwner.get(key) ?? [];
    list.push(s);
    byOwner.set(key, list);
  }
  const products = new Set(toNotify.map((s) => `${s.item_id}|${s.msku ?? ""}`));
  const lines: string[] = [
    `【产品规则信号提醒】${shTime()}`,
    `信号批次: ${signalDate}（20:55 规则引擎生成）`,
    `本次提醒信号数: ${toNotify.length} ｜ 涉及负责人: ${byOwner.size} ｜ 涉及产品: ${products.size}`,
    "（同一信号按规则自带提醒频率去重，持续存在每 N 天提醒一次；[新] 为本批新触发）",
  ];
  for (const [owner, list] of byOwner) {
    lines.push("", `负责人：${owner}（${list.length} 条）`);
    list.slice(0, PER_OWNER_LIMIT).forEach((s, i) => {
      const tag = planKinds.get(fingerprintOf(s)) === "new" ? "[新] " : "";
      lines.push(
        `${i + 1}. ${tag}${s.store_name ?? s.store_id ?? "-"} ｜ ItemID ${s.item_id} ｜ MSKU ${s.msku ?? "-"}`,
        `   [${s.rule_level ?? "-"}] ${s.rule_name ?? s.rule_code}：${s.trigger_reason ?? "-"}`,
        `   建议：${s.suggested_action ?? "暂无系统规则建议"}`,
      );
    });
    if (list.length > PER_OWNER_LIMIT) lines.push(`   …另有 ${list.length - PER_OWNER_LIMIT} 条未展开`);
  }
  lines.push("", `页面：${PAGE_URL}`);
  return lines.join("\n");
}

async function main(): Promise<void> {
  const doSend = process.argv.includes("--send");
  const forcePreview = process.argv.includes("--force-preview");
  // 2026-07-18 需求方指令：卡片版预览（🚦 产品规则信号日报）。只发测试群、不写事件表、不动生产文本路径。
  const testCard = process.argv.includes("--test-card");
  if (testCard && doSend) {
    console.log("[错误] --test-card 与 --send 禁止同时使用");
    process.exit(1);
  }
  const dateOverride = argValue("--date=");
  const effectiveSend = doSend && !forcePreview;
  const taskRunId = `RSN-${new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14)}-${Math.random().toString(36).slice(2, 6)}`;

  console.log("=".repeat(60));
  console.log("产品规则信号通报（B线第5期·正式版 2026-07-15 转正）");
  console.log(`执行时间（上海）: ${shTime()} ｜ task_run_id: ${taskRunId}`);
  console.log(`模式: ${effectiveSend ? "真实发送" : forcePreview ? "force-preview（忽略去重预览，不发送不写库）" : "dry-run（加 --send 发送）"}`);
  console.log("=".repeat(60));

  const summary = {
    taskRunId, signalDate: "", signalCount: 0, productCount: 0, ownerCount: 0,
    newTriggerCount: 0, repeatReminderCount: 0, skippedByDedupCount: 0,
    closedCycleCount: 0, sent: effectiveSend, sendSuccess: 0, sendFailed: 0, status: "success",
  };
  const db = await mysql.createConnection(dbConfig());
  try {
    const batch = await resolveBatch(db, dateOverride);
    if (!batch.ok) {
      console.log(`[中止] 批次校验未通过: ${batch.note}（signal_date=${batch.signalDate || "无"}）`);
      summary.status = "aborted";
      process.exitCode = 2;
      return;
    }
    summary.signalDate = batch.signalDate;
    console.log(`最近成功批次: signal_date=${batch.signalDate}（${batch.note}）`);

    const signals = await loadSignals(db, batch.signalDate);
    summary.signalCount = signals.length;
    summary.productCount = new Set(signals.map((s) => `${s.item_id}|${s.msku ?? ""}`)).size;
    summary.ownerCount = new Set(signals.map((s) => (s.owner ?? "").trim() || "-")).size;
    console.log(`should_notify 信号: ${signals.length} ｜ 产品: ${summary.productCount} ｜ 负责人: ${summary.ownerCount}`);
    if (!signals.length) {
      console.log("本批无需通知的信号。");
      return;
    }

    // ── 去重判定 ──
    const fingerprints = [...new Set(signals.map(fingerprintOf))];
    const openCycles = await loadOpenCycles(db, fingerprints);
    const now = new Date();
    const planKinds = new Map<string, PlanKind>();
    const toNotify: SignalRow[] = [];
    for (const s of signals) {
      const fp = fingerprintOf(s);
      if (planKinds.has(fp)) continue; // 同指纹取首条
      const open = openCycles.get(fp);
      if (forcePreview) {
        planKinds.set(fp, "new");
        toNotify.push(s);
        continue;
      }
      if (!open) {
        planKinds.set(fp, "new");
        toNotify.push(s);
      } else if (open.signal_date === batch.signalDate && open.last_notified_at) {
        planKinds.set(fp, "skip"); // 同批次已通知（重跑幂等）
      } else {
        const freq = Number(s.notify_frequency_days ?? 0) > 0 ? Number(s.notify_frequency_days) : DEFAULT_FREQ_DAYS;
        if (open.last_notified_at && daysBetween(open.last_notified_at, now) >= freq) {
          planKinds.set(fp, "repeat");
          toNotify.push(s);
        } else {
          planKinds.set(fp, "skip");
        }
      }
    }
    summary.newTriggerCount = [...planKinds.values()].filter((k) => k === "new").length;
    summary.repeatReminderCount = [...planKinds.values()].filter((k) => k === "repeat").length;
    summary.skippedByDedupCount = [...planKinds.values()].filter((k) => k === "skip").length;
    console.log(`去重判定: 新触发 ${summary.newTriggerCount} ｜ 满频率再提醒 ${summary.repeatReminderCount} ｜ 去重跳过 ${summary.skippedByDedupCount}`);

    // ── 恢复关闭：开放周期中当批未出现的指纹 ──
    const todaySet = new Set(fingerprints);
    const toClose = [...openCycles.keys()].filter((fp) => !todaySet.has(fp));
    summary.closedCycleCount = toClose.length;

    // ── 2026-07-18 --test-card：卡片版预览，只发测试群，不写事件表 ──
    // （置于空判断之前：去重后为空也要用全量信号预览版式）
    if (!testCard && !toNotify.length) {
      console.log("去重后本次无需发送。");
      if (effectiveSend && toClose.length) {
        await db.query(
          `UPDATE ${EVENT_TABLE} SET send_status = 'closed' WHERE signal_fingerprint IN (?) AND send_status <> 'closed'`,
          [toClose],
        );
        console.log(`已关闭恢复周期: ${toClose.length} 个`);
      }
      return;
    }

    if (testCard) {
      const previewList = toNotify.length ? toNotify : signals;
      const cardItems = previewList.map((s) => ({
        owner: (s.owner ?? "").trim(),
        storeName: s.store_name ?? s.store_id ?? "-",
        itemId: s.item_id,
        msku: s.msku ?? "-",
        ruleLevel: s.rule_level ?? "",
        ruleName: s.rule_name ?? s.rule_code,
        triggerReason: s.trigger_reason ?? "-",
        suggestedAction: s.suggested_action ?? "",
        isNew: planKinds.get(fingerprintOf(s)) === "new",
      }));
      const bundle = buildRuleSignalCard(batch.signalDate, cardItems, { perOwnerLimit: PER_OWNER_LIMIT, pageUrl: PAGE_URL, testPrefix: true });
      console.log(`[test-card] 卡片预览${toNotify.length ? "（去重后待发列表）" : "（本批去重后为空，用全量信号预览版式）"}：${cardItems.length} 条 → 测试群`);
      const r = await sendCardWithFallbackToChat("规则信号卡片预览", getTestChatId(), bundle.card, bundle.fallbackText);
      console.log(`[test-card] 结果: ok=${r.ok} cardOk=${r.cardOk} fallbackUsed=${r.fallbackUsed}${r.error ? ` error=${r.error}` : ""}`);
      if (r.ok) console.log("NOTIFY_TEST_SENT=1");
      else process.exitCode = 1;
      console.log("[test-card] 不写事件表，去重状态不变。");
      return;
    }

    // ── 2026-07-19 生产切卡片（📉 低利润产品提醒，需求方确认）；失败自动降级纯文本；dry-run 走文本预览 ──
    const cardItems = toNotify.map((s) => ({
      owner: (s.owner ?? "").trim(),
      storeName: s.store_name ?? s.store_id ?? "-",
      itemId: s.item_id,
      msku: s.msku ?? "-",
      ruleLevel: s.rule_level ?? "",
      ruleName: s.rule_name ?? s.rule_code,
      triggerReason: s.trigger_reason ?? "-",
      suggestedAction: s.suggested_action ?? "",
      isNew: planKinds.get(fingerprintOf(s)) === "new",
    }));
    const bundle = buildRuleSignalCard(batch.signalDate, cardItems, { perOwnerLimit: PER_OWNER_LIMIT, pageUrl: PAGE_URL });

    const chatIds = parseListEnv("RULE_SIGNAL_CHAT_IDS");
    if (effectiveSend && !chatIds.length) {
      throw new Error("缺少 RULE_SIGNAL_CHAT_IDS 环境变量（测试阶段=测试群chat_id）");
    }
    const targets: NotifyTarget[] = chatIds.map((id, i) => ({ type: "chat", label: `规则信号群${i + 1}`, id }));
    let results: SendResult[];
    if (!effectiveSend) {
      results = await fanoutText("", targets.length ? targets : [{ type: "chat", label: "（未配置群，仅预览）", id: "" }], bundle.fallbackText, false);
    } else {
      results = [];
      for (const t of targets) {
        const r = await sendCardWithFallbackToChat(t.label, t.id, bundle.card, bundle.fallbackText);
        results.push({ label: t.label, type: "chat", ok: r.ok, retryCount: r.retryCount, ambiguousDelivery: r.ambiguousDelivery, error: r.error });
      }
    }
    console.log(`发送结果: ${formatResults(results)}`);
    summary.sendSuccess = results.filter((r) => r.ok).length;
    summary.sendFailed = results.filter((r) => !r.ok).length;

    if (!effectiveSend) {
      console.log("dry-run/force-preview：不写事件表。");
      return;
    }
    if (summary.sendFailed > 0) {
      // 发送失败：不写去重状态（不标记已发送），下次运行自动重发
      summary.status = "send_failed";
      console.log("[告警] 发送失败：本次不落任何去重/已发送状态，下次运行将重发");
      process.exitCode = 1;
      return;
    }

    // ── 发送成功后单事务落事件层 ──
    await db.beginTransaction();
    try {
      const nowSql = "NOW()";
      for (const s of toNotify) {
        const fp = fingerprintOf(s);
        const kind = planKinds.get(fp);
        if (kind === "new") {
          await db.query(
            `INSERT INTO ${EVENT_TABLE}
               (event_time, source, task_run_id, signal_date, platform, store_id, item_id, msku,
                owner, signal_code, signal_fingerprint, first_triggered_at, last_triggered_at,
                last_notified_at, notify_count, notify_target_type, notify_target, send_status)
             VALUES (${nowSql}, 'rule_signal_notify', ?, ?, ?, ?, ?, ?, ?, ?, ?, ${nowSql}, ${nowSql}, ${nowSql}, 1, 'chat', 'rule_signal_group', 'sent')`,
            [taskRunId, s.signal_date, s.platform, s.store_id ?? "", s.item_id, s.msku ?? "",
             s.owner ?? "", s.rule_code, fp],
          );
        } else if (kind === "repeat") {
          const open = openCycles.get(fp)!;
          await db.query(
            `UPDATE ${EVENT_TABLE}
                SET signal_date = ?, last_triggered_at = ${nowSql}, last_notified_at = ${nowSql},
                    notify_count = notify_count + 1, task_run_id = ?, send_status = 'sent'
              WHERE id = ?`,
            [s.signal_date, taskRunId, open.id],
          );
        }
      }
      // skip 的开放周期仅刷新 last_triggered_at 与 signal_date（信号仍存在）
      const skipFps = [...planKinds.entries()].filter(([, k]) => k === "skip").map(([fp]) => fp);
      if (skipFps.length) {
        await db.query(
          `UPDATE ${EVENT_TABLE} e
             JOIN (SELECT signal_fingerprint, MAX(id) AS max_id FROM ${EVENT_TABLE}
                   WHERE signal_fingerprint IN (?) GROUP BY signal_fingerprint) latest
               ON latest.max_id = e.id
              SET e.last_triggered_at = ${nowSql}, e.signal_date = ?
            WHERE e.send_status <> 'closed'`,
          [skipFps, batch.signalDate],
        );
      }
      if (toClose.length) {
        await db.query(
          `UPDATE ${EVENT_TABLE} SET send_status = 'closed' WHERE signal_fingerprint IN (?) AND send_status <> 'closed'`,
          [toClose],
        );
        console.log(`已关闭恢复周期: ${toClose.length} 个`);
      }
      await db.commit();
      console.log("事件层去重状态已提交。");
    } catch (e) {
      await db.rollback();
      summary.status = "event_write_failed";
      console.log(`[错误] 事件层写入失败已回滚（消息已发出，下次运行同批次可能重发一次，属可接受边界）: ${e instanceof Error ? e.message : String(e)}`);
      process.exitCode = 1;
    }
  } catch (e) {
    summary.status = "failed";
    console.log(`[错误] ${e instanceof Error ? e.message : String(e)}`);
    process.exitCode = 1;
  } finally {
    console.log("\n运行摘要：");
    console.log(JSON.stringify(summary, null, 2));
    await db.end();
  }
}

main().catch((e) => {
  console.log(`[致命错误] ${e instanceof Error ? e.message : String(e)}`);
  process.exitCode = 1;
});
