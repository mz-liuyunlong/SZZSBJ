/**
 * src/ai_pmc/notifyShipment.ts
 * Phase 7B — WFS 发货流程提醒发送 + 通知日志写入
 *
 * 按接收人聚合，一人一条；升级项额外 @ 江梓博。
 * 发送后写 PMC通知日志(4BfsYD)，order_sn 列存 cargoCode，task_stage 存阶段。
 * 默认 dry-run，doSend=true 才真发真写。
 */

process.env.TZ = 'Asia/Shanghai';

import 'dotenv/config';
import { FeishuSheetWriter } from '../feishuSheetWriter';
import { ShipmentAlert } from './checkShipmentFlow';
import { PmcConfig, PMC_SPREADSHEET_TOKEN, SHEET, SHEET_NAME } from './config';
import { nowBJString } from './dateUtil';
import { logger } from './logger';

const axios = require('axios/dist/node/axios.cjs') as typeof import('axios').default;

function atTag(openId: string, name: string): string {
  return openId ? `<at user_id="${openId}">${name}</at>` : `@${name}`;
}

async function sendToFeishu(url: string, message: string, doSend: boolean): Promise<{ ok: boolean; err: string }> {
  if (!doSend) {
    console.log('\n[dry-run][7B] 消息预览：\n' + '─'.repeat(60) + '\n' + message + '\n' + '─'.repeat(60));
    return { ok: true, err: '' };
  }
  if (!url) return { ok: false, err: '缺少 FEISHU_PMC_WEBHOOK_URL 环境变量' };
  try {
    const resp = await axios.post(url, { msg_type: 'text', content: { text: message } },
      { headers: { 'Content-Type': 'application/json' }, timeout: 15000 });
    const data = resp.data as Record<string, unknown>;
    const ok = data.StatusCode === 0 || data.code === 0;
    return { ok, err: ok ? '' : `飞书返回非成功: ${JSON.stringify(data)}` };
  } catch (e) {
    return { ok: false, err: `飞书请求失败: ${e instanceof Error ? e.message : String(e)}` };
  }
}

export interface NotifyShipmentResult { total: number; sentGroups: number; failedGroups: number; }

export async function notifyShipment(alerts: ShipmentAlert[], config: PmcConfig, doSend: boolean): Promise<NotifyShipmentResult> {
  if (alerts.length === 0) {
    logger.info('[notifyShipment] 无待提醒（7B）');
    return { total: 0, sentGroups: 0, failedGroups: 0 };
  }
  const writer = new FeishuSheetWriter();
  const url = config.pmcWebhookUrl;
  const date = nowBJString().slice(0, 10);
  const notifyTime = nowBJString();
  const logRows: string[][] = [];
  let sentGroups = 0, failedGroups = 0;

  // 按接收人聚合（普通提醒）
  const groups = new Map<string, { name: string; openId: string; list: ShipmentAlert[] }>();
  for (const a of alerts) {
    const k = a.ownerOpenId || a.ownerName;
    if (!groups.has(k)) groups.set(k, { name: a.ownerName, openId: a.ownerOpenId, list: [] });
    groups.get(k)!.list.push(a);
  }

  for (const g of groups.values()) {
    const lines = [`【发货流程提醒】${date}`, `${atTag(g.openId, g.name)} 有 ${g.list.length} 个货件需要跟进：`];
    g.list.forEach((a, i) => lines.push(`${i + 1}. ${a.itemId} ${a.productName}\n   ${a.suggestion}`));
    const { ok, err } = await sendToFeishu(url, lines.join('\n'), doSend);
    if (ok) sentGroups++; else { failedGroups++; logger.warn(`[notifyShipment] 发给${g.name}失败：${err}`); }
    for (const a of g.list) {
      logRows.push(['', a.itemId, a.cargoCode, a.stage, notifyTime, '发货流程提醒', a.ownerName, ok ? '成功' : '失败', ok ? '' : err]);
    }
  }

  // 升级：汇总 @ 江梓博
  const escalations = alerts.filter((a) => a.needEscalate);
  if (escalations.length > 0) {
    const pmc = config.owners.pmc;
    const lines = [`【发货升级 ⚠️】${date}`, `${atTag(pmc.openId, pmc.name)} 以下货件严重超时，请关注：`];
    escalations.forEach((a, i) => lines.push(`${i + 1}. ${a.itemId} ${a.productName} — ${a.suggestion}（已${a.daysOverdue}天）`));
    const { ok, err } = await sendToFeishu(url, lines.join('\n'), doSend);
    if (!ok) logger.warn(`[notifyShipment] 升级通知失败：${err}`);
    for (const a of escalations) {
      logRows.push(['', a.itemId, a.cargoCode, a.escalateStage ?? 'ESCALATE_SHIP', notifyTime, '升级通知', pmc.name, ok ? '成功' : '失败', ok ? '' : err]);
    }
  }

  // 写通知日志
  if (doSend && logRows.length > 0) {
    try {
      const start = writer.getRowCount({ spreadsheetToken: PMC_SPREADSHEET_TOKEN, sheetId: SHEET.notifyLog, sheetName: SHEET_NAME.notifyLog }) + 1;
      writer.writeCells({
        spreadsheetToken: PMC_SPREADSHEET_TOKEN, sheetId: SHEET.notifyLog, sheetName: SHEET_NAME.notifyLog,
        range: `A${start}:I${start + logRows.length - 1}`, rows: logRows,
        dryRun: false, confirmWrite: true, allowOverwrite: false,
      });
      logger.info(`[notifyShipment] 通知日志写入 ${logRows.length} 条`);
    } catch (e) {
      logger.error('[notifyShipment] 通知日志写入失败（不影响主流程）', e);
    }
  }

  logger.info(`[notifyShipment] 完成：成功${sentGroups}组，失败${failedGroups}组`);
  return { total: alerts.length, sentGroups, failedGroups };
}
