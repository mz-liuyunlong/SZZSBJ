/**
 * checkDataSentinel.ts — P7 数据完整性哨兵 CLI（2026-08-10 设计v4定稿）
 *
 * cron（部署时挂）：
 *   15 20 * * *   --check  --send    # 主检：5项零容差检查，异常发修复确认卡
 *   0  9-23 * * * --remind --send    # 整点提醒：未闭环事件先复查(通过即静默+闭环卡)，仍异常再催
 *   0  9  * * 1   --weekly --send    # 周一周汇总
 *
 * 用法：
 *   npx ts-node src/checkDataSentinel.ts --check              # dry-run（打印，零发送零写事件）
 *   npx ts-node src/checkDataSentinel.ts --check --send       # 真实：写事件+发卡(仅陈佳聪)
 *   npx ts-node src/checkDataSentinel.ts --check --test-send --send  # 全发测试群(卡带test:1按钮只应答)
 *   --remind / --weekly 同理。
 *
 * 铁律：本脚本只读业务数据 + 写 event_sentinel_alert(哨兵自身事件表)；修复动作仅由卡片确认触发(回调侧)。
 */

import "dotenv/config";
import {
  NotifyTarget, getNotifyTenantToken, getTestChatId, resolveActiveMembers, sendCardToTarget, sendTextToTarget,
} from "./feishuNotify";
import {
  CHECKS, SENTINEL_NOTIFY, SentinelEvent, buildFixCard, buildManualCard, buildResolvedCard,
  checkDef, getDb, listUnresolved, loadEvent, markManual, markResolved, bumpRemind,
  upsertOpenEvent, verifyCheck, MAX_AUTO_ATTEMPTS,
} from "./sentinelCore";

async function getTarget(testSend: boolean): Promise<NotifyTarget | null> {
  if (testSend) return { type: "chat", label: `测试群(原目标:${SENTINEL_NOTIFY})`, id: getTestChatId() };
  const { targets } = await resolveActiveMembers([SENTINEL_NOTIFY]);
  return targets[0] ?? null;
}

async function sendCard(target: NotifyTarget | null, card: Record<string, unknown>, fb: string, send: boolean): Promise<boolean> {
  if (!send) { console.log(`[dry-run] 卡片 →\n${fb}\n`); return true; }
  if (!target) { console.log(`[WARN] 找不到通知目标 ${SENTINEL_NOTIFY}`); return false; }
  const r = await sendCardToTarget(target, card, fb, true);
  return r.ok;
}

async function doCheck(send: boolean, testSend: boolean): Promise<void> {
  const db = await getDb();
  let anomalies = 0, resolvedNow = 0, ok = 0, sentOk = 0, sentFail = 0;
  try {
    const target = send ? await getTarget(testSend) : null;
    for (const def of CHECKS) {
      for (const date of def.targetDates()) {
        const v = await verifyCheck(db, def.key, date);
        if (v.ok) {
          ok++;
          // 此前未闭环的同键事件 → 自动闭环
          const open = (await listUnresolved(db)).find((e) => e.check_key === def.key && e.target_date === date);
          if (open) {
            if (send && !testSend) await markResolved(db, open.id, "sentinel_auto");
            resolvedNow++;
            const { card, fb } = buildResolvedCard(open, v.detail);
            if (await sendCard(target, card, fb, send)) sentOk++; else sentFail++;
          }
          continue;
        }
        anomalies++;
        let ev: SentinelEvent;
        if (send && !testSend) {
          const id = await upsertOpenEvent(db, def.key, date, v.detail);
          ev = (await loadEvent(db, id)) as SentinelEvent;
          if (!def.repairable && ev.status !== "manual") { await markManual(db, ev.id); ev.status = "manual"; }
        } else {
          ev = { id: 0, check_key: def.key, target_date: date, status: def.repairable ? "open" : "manual",
            attempt_count: 0, remind_count: 0, detail: v.detail };
        }
        const useManual = !def.repairable || ev.attempt_count >= MAX_AUTO_ATTEMPTS;
        const { card, fb } = useManual ? buildManualCard(ev, testSend) : buildFixCard(ev, testSend);
        if (await sendCard(target, card, fb, send)) sentOk++; else sentFail++;
      }
    }
  } finally { await db.end().catch(() => undefined); }
  console.log("SUMMARY_JSON=" + JSON.stringify({
    mode: send ? (testSend ? "test" : "send") : "dry-run", action: "check",
    checks_ok: ok, anomalies, auto_resolved: resolvedNow, sent_ok: sentOk, sent_fail: sentFail, status: "success",
  }));
}

async function doRemind(send: boolean, testSend: boolean): Promise<void> {
  const db = await getDb();
  let reminded = 0, resolvedNow = 0, sentOk = 0, sentFail = 0;
  try {
    const list = await listUnresolved(db);
    if (list.length === 0) {
      console.log("SENTINEL_REMIND_SKIP 无未闭环事件");
      console.log("SUMMARY_JSON=" + JSON.stringify({ action: "remind", open: 0, status: "success" }));
      return;
    }
    const target = send ? await getTarget(testSend) : null;
    for (const ev of list) {
      const v = await verifyCheck(db, ev.check_key, ev.target_date);
      if (v.ok) {
        if (send && !testSend) await markResolved(db, ev.id, "recheck_pass");
        resolvedNow++;
        const { card, fb } = buildResolvedCard(ev, v.detail);
        if (await sendCard(target, card, fb, send)) sentOk++; else sentFail++;
        continue;
      }
      ev.detail = v.detail;
      const def = checkDef(ev.check_key);
      const useManual = !def?.repairable || ev.status === "manual" || ev.attempt_count >= MAX_AUTO_ATTEMPTS;
      const { card, fb } = useManual ? buildManualCard(ev, testSend) : buildFixCard(ev, testSend);
      if (await sendCard(target, card, fb, send)) sentOk++; else sentFail++;
      if (send && !testSend) await bumpRemind(db, ev.id);
      reminded++;
    }
  } finally { await db.end().catch(() => undefined); }
  console.log("SUMMARY_JSON=" + JSON.stringify({
    mode: send ? (testSend ? "test" : "send") : "dry-run", action: "remind",
    reminded, auto_resolved: resolvedNow, sent_ok: sentOk, sent_fail: sentFail, status: "success",
  }));
}

async function doWeekly(send: boolean, testSend: boolean): Promise<void> {
  const db = await getDb();
  try {
    const [rows] = await db.execute(
      `SELECT COUNT(*) total,
              SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END) resolved,
              SUM(CASE WHEN status='manual' THEN 1 ELSE 0 END) manual_open,
              SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) still_open
       FROM event_sentinel_alert WHERE first_alert_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)`);
    const r = (rows as Array<Record<string, unknown>>)[0] ?? {};
    const total = Number(r.total ?? 0);
    const text = total === 0
      ? `【数据哨兵·周报】过去7天全部检查通过，无任何异常 ✅（saleStat族恒等/明细行数/库存快照/经营状态快照/msku脏行/渠道有无）`
      : `【数据哨兵·周报】过去7天异常 ${total} 起：已解决 ${Number(r.resolved ?? 0)}｜转人工未闭环 ${Number(r.manual_open ?? 0)}｜待处理 ${Number(r.still_open ?? 0)}。未闭环项每小时提醒中。`;
    if (!send) { console.log(`[dry-run] 周报 →\n${text}`); }
    else {
      const target = await getTarget(testSend);
      if (target) {
        const token = await getNotifyTenantToken();
        await sendTextToTarget(token, target, testSend ? `[原目标:私聊 ${SENTINEL_NOTIFY}]\n${text}` : text, true);
      }
    }
    console.log("SUMMARY_JSON=" + JSON.stringify({ action: "weekly", total7d: total, mode: send ? (testSend ? "test" : "send") : "dry-run", status: "success" }));
  } finally { await db.end().catch(() => undefined); }
}

async function main(): Promise<void> {
  const a = process.argv.slice(2);
  const send = a.includes("--send");
  const testSend = a.includes("--test-send") || (process.env.BUSINESS_REPORT_FORCE_TEST ?? "").trim() === "1";
  if (a.includes("--weekly")) return doWeekly(send, testSend);
  if (a.includes("--remind")) return doRemind(send, testSend);
  return doCheck(send, testSend);
}

main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
