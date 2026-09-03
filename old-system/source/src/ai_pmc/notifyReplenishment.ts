/**
 * src/ai_pmc/notifyReplenishment.ts
 * Phase 8 — 补货提醒发送（按运营负责人聚合）+ 通知日志
 *
 * 默认 dry-run；doSend=true 才真发真写。
 */

process.env.TZ = 'Asia/Shanghai';

import 'dotenv/config';
import { FeishuSheetWriter } from '../feishuSheetWriter';
import { ReplenishTask } from './calcReplenishment';
import { PmcConfig, PMC_SPREADSHEET_TOKEN, SHEET, SHEET_NAME } from './config';
import { nowBJString } from './dateUtil';
import { logger } from './logger';

const axios = require('axios/dist/node/axios.cjs') as typeof import('axios').default;

function atTag(openId: string, name: string): string {
  return openId ? `<at user_id="${openId}">${name}</at>` : `@${name}`;
}

async function sendToFeishu(url: string, message: string, doSend: boolean): Promise<{ ok: boolean; err: string }> {
  if (!doSend) {
    console.log('\n[dry-run][补货] 消息预览：\n' + '─'.repeat(60) + '\n' + message + '\n' + '─'.repeat(60));
    return { ok: true, err: '' };
  }
  if (!url) return { ok: false, err: '缺少 FEISHU_PMC_WEBHOOK_URL 环境变量' };
  // 超长分片（补货消息可能较长）
  const MAX = 28000;
  const chunks: string[] = [];
  for (let i = 0; i < message.length; i += MAX) chunks.push(message.slice(i, i + MAX));
  for (const chunk of chunks) {
    try {
      const resp = await axios.post(url, { msg_type: 'text', content: { text: chunk } },
        { headers: { 'Content-Type': 'application/json' }, timeout: 15000 });
      const data = resp.data as Record<string, unknown>;
      const ok = data.StatusCode === 0 || data.code === 0;
      if (!ok) return { ok: false, err: `飞书返回非成功: ${JSON.stringify(data)}` };
    } catch (e) {
      return { ok: false, err: `飞书请求失败: ${e instanceof Error ? e.message : String(e)}` };
    }
  }
  return { ok: true, err: '' };
}

function renderTask(idx: number, t: ReplenishTask): string {
  const ai = t.aiResult;
  if (ai && ai.aiSuccess) {
    return (
      `${idx}. ${t.sku} ${t.productName}（${t.itemId}）\n` +
      `   【优先级：${ai.priority}】系统建议${t.suggestQty}件 → AI调整${ai.adjustedSuggestQty}件\n` +
      `   调整原因：${ai.reason}\n` +
      `   分析：${ai.analysis}`
    );
  }
  return (
    `${idx}. ${t.sku} ${t.productName}（${t.itemId}）\n` +
    `   系统建议补货${t.suggestQty}件（日均${t.adjustedAvg} × 目标天数 − 当前库存${t.totalInventory}）\n` +
    `   AI评估暂不可用，请人工复核。`
  );
}

export interface NotifyReplenishResult { total: number; sentGroups: number; failedGroups: number; }

export async function notifyReplenishment(tasks: ReplenishTask[], config: PmcConfig, doSend: boolean): Promise<NotifyReplenishResult> {
  const evaluated = tasks.filter((t) => t.aiResult);
  if (evaluated.length === 0) {
    logger.info('[notifyReplenishment] 无补货任务');
    return { total: 0, sentGroups: 0, failedGroups: 0 };
  }
  const writer = new FeishuSheetWriter();
  const date = nowBJString().slice(0, 10);
  const notifyTime = nowBJString();
  const logRows: string[][] = [];
  let sentGroups = 0, failedGroups = 0;

  // 按运营负责人聚合
  const groups = new Map<string, { name: string; openId: string; list: ReplenishTask[] }>();
  for (const t of evaluated) {
    const k = t.ownerOpenId || t.ownerName;
    if (!groups.has(k)) groups.set(k, { name: t.ownerName, openId: t.ownerOpenId, list: [] });
    groups.get(k)!.list.push(t);
  }

  for (const g of groups.values()) {
    // 高优先级排前
    g.list.sort((a, b) => priorityRank(b.aiResult?.priority) - priorityRank(a.aiResult?.priority));
    const lines = [`【补货提醒】${date}`, `${atTag(g.openId, g.name)} 有 ${g.list.length} 个商品需要补货：`];
    g.list.forEach((t, i) => lines.push(renderTask(i + 1, t)));
    const { ok, err } = await sendToFeishu(config.pmcWebhookUrl, lines.join('\n'), doSend);
    if (ok) sentGroups++; else { failedGroups++; logger.warn(`[notifyReplenishment] 发给${g.name}失败：${err}`); }
    for (const t of g.list) {
      logRows.push(['', t.itemId, '补货', 'REPLENISH', notifyTime, '补货提醒', t.ownerName, ok ? '成功' : '失败', ok ? '' : err]);
    }
  }

  if (doSend && logRows.length > 0) {
    try {
      const start = writer.getRowCount({ spreadsheetToken: PMC_SPREADSHEET_TOKEN, sheetId: SHEET.notifyLog, sheetName: SHEET_NAME.notifyLog }) + 1;
      writer.writeCells({
        spreadsheetToken: PMC_SPREADSHEET_TOKEN, sheetId: SHEET.notifyLog, sheetName: SHEET_NAME.notifyLog,
        range: `A${start}:I${start + logRows.length - 1}`, rows: logRows,
        dryRun: false, confirmWrite: true, allowOverwrite: false,
      });
      logger.info(`[notifyReplenishment] 通知日志写入 ${logRows.length} 条`);
    } catch (e) {
      logger.error('[notifyReplenishment] 通知日志写入失败（不影响主流程）', e);
    }
  }

  logger.info(`[notifyReplenishment] 完成：成功${sentGroups}组，失败${failedGroups}组`);
  return { total: evaluated.length, sentGroups, failedGroups };
}

function priorityRank(p?: string): number {
  if (p === '高') return 3;
  if (p === '中') return 2;
  if (p === '低') return 1;
  return 0;
}
