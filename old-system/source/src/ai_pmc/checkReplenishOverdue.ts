/**
 * src/ai_pmc/checkReplenishOverdue.ts
 * 周三升级检查 —— 补货建议超 3 天未处理，强提醒运营 + @江梓博
 *
 * 判定：台账中 全链路阶段='补货建议'（非"不采纳"）且 H列人工备注为空，
 *      且该建议首次出现已 ≥ 3 天（取 I列进展明细首行日期）。
 * 处理两条出路：采纳→去领星下采购单（系统下次自动认领推进）；不采纳→台账H列标注。
 * 当日防重复（读 PMC通知日志，同 itemId+类型+当天已成功 不再发）。
 *
 * 默认 dry-run；doSend=true 才真发真写日志。供 runWednesday 调用。
 */

process.env.TZ = 'Asia/Shanghai';

import 'dotenv/config';
import { FeishuSheetWriter } from '../feishuSheetWriter';
import { loadPmcConfig, PMC_SPREADSHEET_TOKEN, SHEET, SHEET_NAME } from './config';
import { readOwners, lookupOwner, FALLBACK_OPEN_ID, FALLBACK_NAME } from './readOwners';
import { daysSince, nowBJString } from './dateUtil';
import { logger } from './logger';

const axios = require('axios/dist/node/axios.cjs') as typeof import('axios').default;

const LEDGER_TOKEN = '<REDACTED_FEISHU_SPREADSHEET_TOKEN>';
const LEDGER_SHEET_ID = '<REDACTED_FEISHU_SHEET_ID>';
const LEDGER_RANGE = 'A1:J5000';
const C = { ITEM_ID: 0, SKU: 1, SHOP: 2, NAME: 3, STAGE: 4, OWNER: 5, SUGGEST: 6, NOTE: 7, LOG: 8, UPDATED: 9 };

const STAGE_REPLENISH = '补货建议';
const OVERDUE_DAYS = 3;
const NOTIFY_TYPE = '补货建议逾期';
const ESCALATE_NAME = '江梓博';

function str(v: unknown): string { return v === null || v === undefined ? '' : String(v).trim(); }

/** 取进展明细首行的日期 "YYYY-MM-DD" */
function firstSeenDate(log: string): string | null {
  const m = log.match(/\[(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : null;
}

async function sendToFeishu(url: string, message: string, doSend: boolean): Promise<{ ok: boolean; err: string }> {
  if (!doSend) {
    console.log('\n[dry-run][补货建议逾期] 消息预览：\n' + '─'.repeat(60) + '\n' + message + '\n' + '─'.repeat(60));
    return { ok: true, err: '' };
  }
  if (!url) return { ok: false, err: '缺少 FEISHU_PMC_WEBHOOK_URL' };
  try {
    const resp = await axios.post(url, { msg_type: 'text', content: { text: message } },
      { headers: { 'Content-Type': 'application/json' }, timeout: 15000 });
    const data = resp.data as Record<string, unknown>;
    const ok = data.StatusCode === 0 || data.code === 0;
    return ok ? { ok: true, err: '' } : { ok: false, err: `飞书返回非成功: ${JSON.stringify(data)}` };
  } catch (e) {
    return { ok: false, err: `飞书请求失败: ${e instanceof Error ? e.message : String(e)}` };
  }
}

interface OverdueRow { itemId: string; sku: string; name: string; ownerName: string; ownerOpenId: string; days: number; suggest: string; }

export async function checkReplenishOverdue(doSend: boolean): Promise<void> {
  const writer = new FeishuSheetWriter();
  const config = loadPmcConfig(writer);
  const ownerMap = await readOwners();
  const today = nowBJString().slice(0, 10);

  // 1. 读台账，挑出逾期补货建议
  let rows: (string | number | boolean | null)[][] = [];
  try {
    rows = writer.readValues({ spreadsheetToken: LEDGER_TOKEN, sheetId: LEDGER_SHEET_ID, range: LEDGER_RANGE });
  } catch (e) { logger.error('[checkReplenishOverdue] 读台账失败，跳过', e); return; }

  const overdue: OverdueRow[] = [];
  for (let i = 1; i < rows.length; i++) {
    const r = rows[i];
    if (str(r[C.STAGE]) !== STAGE_REPLENISH) continue;   // 仅"补货建议"（"不采纳"已是别的阶段值）
    if (str(r[C.NOTE]) !== '') continue;                 // 人工已处理（备注非空）→ 跳过
    const itemId = str(r[C.ITEM_ID]); if (!itemId) continue;
    const seen = firstSeenDate(str(r[C.LOG]));
    const days = seen ? (daysSince(seen) ?? 0) : 0;
    if (days < OVERDUE_DAYS) continue;
    const owner = lookupOwner(itemId, ownerMap);
    overdue.push({
      itemId, sku: str(r[C.SKU]), name: str(r[C.NAME]),
      ownerName: str(r[C.OWNER]) || owner.name || FALLBACK_NAME,
      ownerOpenId: owner.openId || FALLBACK_OPEN_ID,
      days, suggest: str(r[C.SUGGEST]),
    });
  }

  if (overdue.length === 0) { logger.info('[checkReplenishOverdue] 无逾期补货建议'); return; }
  logger.info(`[checkReplenishOverdue] 逾期补货建议 ${overdue.length} 条`);

  // 2. 当日防重复：读通知日志，同 itemId + 本类型 + 当天已成功 → 跳过
  const sentToday = new Set<string>();
  try {
    const logs = writer.readValues({ spreadsheetToken: PMC_SPREADSHEET_TOKEN, sheetId: SHEET.notifyLog, range: 'A1:I5000' });
    for (const lr of logs) {
      if (str(lr[5]) === NOTIFY_TYPE && str(lr[4]).startsWith(today) && str(lr[7]) === '成功') sentToday.add(str(lr[1]));
    }
  } catch { /* 日志读失败不阻断 */ }

  const pending = overdue.filter((o) => !sentToday.has(o.itemId));
  if (pending.length === 0) { logger.info('[checkReplenishOverdue] 逾期项今日已全部提醒过，跳过'); return; }

  // 3. 按运营负责人聚合发送
  const groups = new Map<string, { name: string; openId: string; list: OverdueRow[] }>();
  for (const o of pending) {
    const k = o.ownerOpenId || o.ownerName;
    if (!groups.has(k)) groups.set(k, { name: o.ownerName, openId: o.ownerOpenId, list: [] });
    groups.get(k)!.list.push(o);
  }

  const atEsc = `<at user_id="${FALLBACK_OPEN_ID}">${ESCALATE_NAME}</at>`;
  const notifyTime = nowBJString();
  const logRows: string[][] = [];
  let sent = 0, failed = 0;

  for (const g of groups.values()) {
    const at = g.openId ? `<at user_id="${g.openId}">${g.name}</at>` : `@${g.name}`;
    const lines = [
      `【补货建议逾期·执行力】${today}`,
      `${at} 以下 ${g.list.length} 个补货建议已超 ${OVERDUE_DAYS} 天未处理，今日必须处理：`,
      `采纳→去领星下采购单（系统下次自动认领推进）；不采纳→台账「人工处理备注」列标注"不采纳"。`,
      `⚠️ 逾期未处理，记执行力问题 1 次。${atEsc} 监督。`,
    ];
    g.list.forEach((o, i) => lines.push(`${i + 1}. ${o.sku} ${o.name}（${o.itemId}）已挂 ${o.days} 天 | ${o.suggest}`));
    const { ok, err } = await sendToFeishu(config.pmcWebhookUrl, lines.join('\n'), doSend);
    if (ok) sent++; else { failed++; logger.warn(`[checkReplenishOverdue] 发给${g.name}失败：${err}`); }
    for (const o of g.list) {
      logRows.push(['', o.itemId, '补货建议', 'REPLENISH_OVERDUE', notifyTime, NOTIFY_TYPE, o.ownerName, ok ? '成功' : '失败', ok ? '' : err]);
    }
  }

  if (doSend && logRows.length > 0) {
    try {
      const start = writer.getRowCount({ spreadsheetToken: PMC_SPREADSHEET_TOKEN, sheetId: SHEET.notifyLog, sheetName: SHEET_NAME.notifyLog }) + 1;
      writer.writeCells({ spreadsheetToken: PMC_SPREADSHEET_TOKEN, sheetId: SHEET.notifyLog, sheetName: SHEET_NAME.notifyLog,
        range: `A${start}:I${start + logRows.length - 1}`, rows: logRows, dryRun: false, confirmWrite: true, allowOverwrite: false });
      logger.info(`[checkReplenishOverdue] 通知日志写入 ${logRows.length} 条`);
    } catch (e) { logger.error('[checkReplenishOverdue] 通知日志写入失败（不影响）', e); }
  }

  logger.info(`[checkReplenishOverdue] 完成：成功${sent}组，失败${failed}组`);
}
