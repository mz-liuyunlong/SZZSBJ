/**
 * src/ai_pmc/notify.ts
 * Phase 5 — 提醒发送 + 通知日志写入
 *
 * 职责：
 *   - 把 checkStatus() 的 AlertItem[] 按「接收人 open_id」聚合成一条消息（不拆条，6.7）
 *   - 通过飞书自定义机器人 webhook 发送，消息内用 <at user_id="ou_xxx"> @ 对应负责人
 *   - 升级（ESCALATE_*）阶段单独成段，@ 江梓博
 *   - 每条提醒发送后写入 PMC通知日志(4BfsYD)，无论成功失败都写 send_status
 *   - 返回 sentStages，供 updateTasks 写回台账
 *
 * 安全：默认 dry-run（只打印不发送、不写日志）；加 --send 或 doSend=true 才真发。
 *
 * 环境变量：FEISHU_PMC_WEBHOOK_URL（PMC 提醒群机器人 webhook）
 */

process.env.TZ = 'Asia/Shanghai';

import 'dotenv/config';
import { FeishuSheetWriter } from '../feishuSheetWriter';
import { AlertItem } from './checkStatus';
import { Stage, STAGE_LABEL, isEscalateStage } from './stages';
import { PmcConfig, PMC_SPREADSHEET_TOKEN, SHEET, SHEET_NAME, loadPmcConfig } from './config';
import { nowBJString, todayBJString } from './dateUtil';
import { logger } from './logger';

const axios = require('axios/dist/node/axios.cjs') as typeof import('axios').default;

const FEISHU_MSG_MAX_LEN = 28000;

// 通知日志列顺序（A..I）
// A=log_id B=item_id C=order_sn D=task_stage E=notify_time
// F=notify_type G=receiver H=send_status I=error_msg

export interface NotifyResult {
  /** key = "itemId|||orderSn|||stage" → 是否发送成功 */
  sentStages: Map<string, boolean>;
  totalAlerts: number;
  sentGroups: number;
  failedGroups: number;
}

interface Group {
  openId: string;
  name: string;
  normal: AlertItem[];
  escalate: AlertItem[];
}

// ─────────────────────────────────────────────
// 聚合：按接收人 open_id 分组
// ─────────────────────────────────────────────

function groupByReceiver(alerts: AlertItem[]): Group[] {
  const map = new Map<string, Group>();
  for (const a of alerts) {
    const key = a.ownerOpenId || `__noopenid__${a.ownerName}`;
    let g = map.get(key);
    if (!g) {
      g = { openId: a.ownerOpenId, name: a.ownerName, normal: [], escalate: [] };
      map.set(key, g);
    }
    if (isEscalateStage(a.stage)) g.escalate.push(a);
    else g.normal.push(a);
  }
  return Array.from(map.values());
}

// ─────────────────────────────────────────────
// 消息文本构造
// ─────────────────────────────────────────────

function atTag(openId: string, name: string): string {
  return openId ? `<at user_id="${openId}">${name}</at>` : `@${name}`;
}

function renderTaskLine(idx: number, a: AlertItem): string {
  const label = STAGE_LABEL[a.stage] ?? a.stage;
  return (
    `${idx}. [${label}] ${a.itemId} ${a.productName}\n` +
    `   采购单：${a.orderSn} | ${a.suggestion}`
  );
}

function buildPersonalMessage(g: Group): string {
  const date = todayBJString();
  const lines: string[] = [];

  if (g.normal.length > 0) {
    lines.push(`【AI智能PMC提醒】${date}`);
    lines.push(`${atTag(g.openId, g.name)} 你有 ${g.normal.length} 个任务需要处理：`);
    g.normal.forEach((a, i) => lines.push(renderTaskLine(i + 1, a)));
  }

  if (g.escalate.length > 0) {
    if (lines.length > 0) lines.push('');
    lines.push(`【PMC升级通知 ⚠️】${date}`);
    lines.push(`${atTag(g.openId, g.name)} 以下任务严重逾期，需要您关注：`);
    g.escalate.forEach((a, i) => lines.push(renderTaskLine(i + 1, a)));
  }

  return lines.join('\n');
}

/** 群汇总（可选）：各阶段计数 */
function buildGroupSummary(alerts: AlertItem[], pmcName: string, pmcOpenId: string): string {
  const date = todayBJString();
  const count = (s: Stage) => alerts.filter(a => a.stage === s).length;
  const overdue = alerts.filter(a => a.needEscalate).length;
  return [
    `【PMC周报 ${date}】`,
    `本次共提醒 ${alerts.length} 个任务：`,
    `- 审批未下单：${count(Stage.APPROVE_PENDING)} 个`,
    `- 已下单未到货：${count(Stage.ARRIVAL_PENDING)} 个`,
    `- 到仓待发货：${count(Stage.ARRIVED_PENDING_SHIP)} 个`,
    `- 到仓逾期：${count(Stage.OVERDUE_SHIP)} 个`,
    `- 需升级：${overdue} 个 ⚠️ ${overdue > 0 ? atTag(pmcOpenId, pmcName) : ''}`,
  ].join('\n');
}

// ─────────────────────────────────────────────
// 飞书发送
// ─────────────────────────────────────────────

async function sendToFeishu(webhookUrl: string, message: string, doSend: boolean): Promise<{ ok: boolean; err: string }> {
  if (!doSend) {
    console.log('\n[dry-run] 消息预览：\n' + '─'.repeat(60) + '\n' + message + '\n' + '─'.repeat(60));
    return { ok: true, err: '' };
  }
  if (!webhookUrl) {
    return { ok: false, err: '缺少 FEISHU_PMC_WEBHOOK_URL 环境变量' };
  }
  // 超长分片
  const chunks: string[] = [];
  for (let i = 0; i < message.length; i += FEISHU_MSG_MAX_LEN) chunks.push(message.slice(i, i + FEISHU_MSG_MAX_LEN));

  for (const [i, chunk] of chunks.entries()) {
    try {
      const resp = await axios.post(
        webhookUrl,
        { msg_type: 'text', content: { text: chunk } },
        { headers: { 'Content-Type': 'application/json' }, timeout: 15000 },
      );
      const data = resp.data as Record<string, unknown>;
      const ok = data.StatusCode === 0 || data.code === 0;
      if (!ok) return { ok: false, err: `飞书返回非成功(${i + 1}/${chunks.length}): ${JSON.stringify(data)}` };
    } catch (e) {
      return { ok: false, err: `飞书请求失败(${i + 1}/${chunks.length}): ${e instanceof Error ? e.message : String(e)}` };
    }
  }
  return { ok: true, err: '' };
}

// ─────────────────────────────────────────────
// 通知日志写入（4BfsYD，追加）
// ─────────────────────────────────────────────

function appendNotifyLog(
  writer: FeishuSheetWriter,
  rows: string[][],
  doSend: boolean,
): void {
  if (rows.length === 0) return;
  if (!doSend) {
    logger.info(`[notify] dry-run：跳过通知日志写入（${rows.length} 条）`);
    return;
  }
  try {
    const startRow = writer.getRowCount({
      spreadsheetToken: PMC_SPREADSHEET_TOKEN,
      sheetId: SHEET.notifyLog,
      sheetName: SHEET_NAME.notifyLog,
    }) + 1;
    const endRow = startRow + rows.length - 1;
    writer.writeCells({
      spreadsheetToken: PMC_SPREADSHEET_TOKEN,
      sheetId: SHEET.notifyLog,
      sheetName: SHEET_NAME.notifyLog,
      range: `A${startRow}:I${endRow}`,
      rows,
      dryRun: false,
      confirmWrite: true,
      allowOverwrite: false,
    });
    logger.info(`[notify] 通知日志写入 ${rows.length} 条`);
  } catch (e) {
    logger.error('[notify] 通知日志写入失败（不影响主流程）', e);
  }
}

// ─────────────────────────────────────────────
// 主函数
// ─────────────────────────────────────────────

/**
 * 发送提醒。
 * @param alerts   checkStatus() 结果
 * @param config   loadPmcConfig() 结果
 * @param doSend   true=真发并写日志；false=dry-run 仅预览
 * @param withGroupSummary 是否额外发送群汇总（runSunday 周报用）
 */
export async function notify(
  alerts: AlertItem[],
  config: PmcConfig,
  doSend: boolean,
  withGroupSummary = false,
): Promise<NotifyResult> {
  const writer = new FeishuSheetWriter();
  const sentStages = new Map<string, boolean>();
  const logRows: string[][] = [];
  const notifyTime = nowBJString();

  if (alerts.length === 0) {
    logger.info('[notify] 无待提醒任务');
    return { sentStages, totalAlerts: 0, sentGroups: 0, failedGroups: 0 };
  }

  const groups = groupByReceiver(alerts);
  logger.info(`[notify] 待发送 ${alerts.length} 条提醒，聚合为 ${groups.length} 个接收人，模式=${doSend ? '真实发送' : 'dry-run'}`);

  let sentGroups = 0;
  let failedGroups = 0;

  for (const g of groups) {
    const message = buildPersonalMessage(g);
    const { ok, err } = await sendToFeishu(config.pmcWebhookUrl, message, doSend);
    if (ok) sentGroups++; else { failedGroups++; logger.warn(`[notify] 发送给 ${g.name} 失败：${err}`); }

    // 记录每条 alert 的发送结果 + 通知日志行
    for (const a of [...g.normal, ...g.escalate]) {
      const stageKey = `${a.itemId}|||${a.orderSn}|||${a.stage}`;
      sentStages.set(stageKey, ok);
      const notifyType = isEscalateStage(a.stage) ? '升级通知' : '个人提醒';
      logRows.push([
        '',                         // A log_id（飞书可用公式或留空，由表自增）
        a.itemId,                   // B item_id
        a.orderSn,                  // C order_sn
        a.stage,                    // D task_stage（枚举值，P1-4）
        notifyTime,                 // E notify_time
        notifyType,                 // F notify_type
        a.ownerName,                // G receiver
        ok ? '成功' : '失败',        // H send_status
        ok ? '' : err,              // I error_msg
      ]);
    }
  }

  // 群汇总（可选）
  if (withGroupSummary) {
    const summary = buildGroupSummary(alerts, config.owners.pmc.name, config.owners.pmc.openId);
    const { ok, err } = await sendToFeishu(config.pmcWebhookUrl, summary, doSend);
    if (!ok) logger.warn(`[notify] 群汇总发送失败：${err}`);
    logRows.push(['', '—', '—', 'GROUP_SUMMARY', notifyTime, '群汇总', config.owners.pmc.name, ok ? '成功' : '失败', ok ? '' : err]);
  }

  appendNotifyLog(writer, logRows, doSend);

  logger.info(`[notify] 完成：成功 ${sentGroups} 组，失败 ${failedGroups} 组`);
  return { sentStages, totalAlerts: alerts.length, sentGroups, failedGroups };
}

// ─────────────────────────────────────────────
// CLI 自测：ts-node src/ai_pmc/notify.ts [--send]
// ─────────────────────────────────────────────

if (require.main === module) {
  (async () => {
    const doSend = process.argv.includes('--send');
    const { fetchPurchaseOrders } = await import('./fetchLingxing');
    const { readOwners } = await import('./readOwners');
    const { checkStatus } = await import('./checkStatus');
    const writer = new FeishuSheetWriter();
    const config = loadPmcConfig(writer);
    const orders = await fetchPurchaseOrders(undefined, 50);
    const ownerMap = await readOwners();
    const alerts = checkStatus(orders, config, ownerMap);
    const result = await notify(alerts, config, doSend, true);
    console.log('notify 结果:', JSON.stringify({ totalAlerts: result.totalAlerts, sentGroups: result.sentGroups, failedGroups: result.failedGroups }, null, 2));
  })().catch(e => { logger.error('[notify] CLI 自测失败', e); process.exitCode = 1; });
}
