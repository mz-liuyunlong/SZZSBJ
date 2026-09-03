/**
 * src/ai_pmc/updateTasks.ts
 * Phase 4 — 台账更新（K列追加日志 + F/G/L列更新）
 *
 * 由 notify.ts 在发送提醒后调用，将本次提醒结果写入台账：
 *   - K列：追加 "[时间] 系统：已发送提醒 → 阶段=xxx，逾期N天" 一行
 *   - F列：更新当前阶段
 *   - G列：更新任务状态
 *   - L列：更新最近更新时间
 *   - J列（人工备注）：永不覆盖
 *
 * 写入前必须持有运行锁（由调用方保证，或内部自行获取）。
 */

process.env.TZ = 'Asia/Shanghai';

import { FeishuSheetWriter } from '../feishuSheetWriter';
import { AlertItem } from './checkStatus';
import { STAGE_TASK_STATUS } from './stages';
import { PMC_SPREADSHEET_TOKEN, SHEET, SHEET_NAME } from './config';
import { nowBJString } from './dateUtil';
import { logger } from './logger';
import { acquireLock } from './lock';

// 台账列索引（0-based）
const C = {
  ITEM_ID:      0,  // A
  ORDER_SN:     1,  // B
  STAGE:        5,  // F
  STATUS:       6,  // G
  MANUAL_NOTE:  9,  // J ← 不覆盖
  PROGRESS_LOG: 10, // K ← 追加
  UPDATED_AT:   11, // L
};

// ─────────────────────────────────────────────
// 主函数
// ─────────────────────────────────────────────

/**
 * 将提醒结果写入台账 K/F/G/L 列。
 *
 * @param alerts     checkStatus() 返回的待提醒列表（已过滤出成功发送的）
 * @param sentStages Map<"itemId|||orderSn|||stage", boolean> 发送结果
 */
export function updateTasksAfterNotify(
  alerts: AlertItem[],
  sentStages: Map<string, boolean>,
): void {
  if (alerts.length === 0) return;

  const writer = new FeishuSheetWriter();

  // 读台账定位行号
  let existingRows: (string | number | boolean | null)[][] = [];
  try {
    existingRows = writer.readValues({
      spreadsheetToken: PMC_SPREADSHEET_TOKEN,
      sheetId: SHEET.taskLedger,
      range: 'A1:L3000',
    });
  } catch (e) {
    logger.error('[updateTasks] 读台账失败，跳过更新', e);
    return;
  }

  // 建 key → 行号 Map（1-based，实时定位，不跨运行缓存）
  const keyToRow = new Map<string, number>();
  for (let i = 1; i < existingRows.length; i++) {
    const row     = existingRows[i];
    const itemId  = String(row[C.ITEM_ID]  ?? '').trim();
    const orderSn = String(row[C.ORDER_SN] ?? '').trim();
    if (itemId && orderSn) keyToRow.set(`${itemId}|||${orderSn}`, i + 1);
  }

  // 获取运行锁
  const lock = acquireLock('updateTasks');
  if (!lock) {
    logger.warn('[updateTasks] 未获取到运行锁，跳过台账更新');
    return;
  }

  try {
    const now = nowBJString();

    for (const alert of alerts) {
      const sentKey = `${alert.itemId}|||${alert.orderSn}|||${alert.stage}`;
      const sent    = sentStages.get(sentKey) ?? false;
      const rowKey  = `${alert.itemId}|||${alert.orderSn}`;
      const rowNum  = keyToRow.get(rowKey);

      if (!rowNum) {
        logger.warn(`[updateTasks] 找不到台账行：${rowKey}，跳过`);
        continue;
      }

      // 校验键一致（P1-2）
      const existRow  = existingRows[rowNum - 1];
      const eItemId   = String(existRow?.[C.ITEM_ID]  ?? '').trim();
      const eOrderSn  = String(existRow?.[C.ORDER_SN] ?? '').trim();
      if (eItemId !== alert.itemId || eOrderSn !== alert.orderSn) {
        logger.warn(`[updateTasks] 行${rowNum}键不一致，跳过`);
        continue;
      }

      // 构造 K 列追加内容
      const sendResult = sent ? '已发送' : '发送失败';
      const logLine    = `[${now}] 系统：${sendResult} → 阶段=${alert.stage}，逾期${alert.daysOverdue}天`;
      const existLog   = String(existRow?.[C.PROGRESS_LOG] ?? '').trim();
      const newLog     = existLog ? `${existLog}\n${logLine}` : logLine;

      try {
        // 写 F/G（阶段+状态）
        writer.writeCells({
          spreadsheetToken: PMC_SPREADSHEET_TOKEN,
          sheetId: SHEET.taskLedger,
          sheetName: SHEET_NAME.taskLedger,
          range: `F${rowNum}:G${rowNum}`,
          rows: [[alert.stage, STAGE_TASK_STATUS[alert.stage] ?? alert.stage]],
          dryRun: false,
          confirmWrite: true,
          allowOverwrite: true,
        });
        // 写 K/L（日志+更新时间）
        writer.writeCells({
          spreadsheetToken: PMC_SPREADSHEET_TOKEN,
          sheetId: SHEET.taskLedger,
          sheetName: SHEET_NAME.taskLedger,
          range: `K${rowNum}:L${rowNum}`,
          rows: [[newLog, now]],
          dryRun: false,
          confirmWrite: true,
          allowOverwrite: true,
        });
      } catch (e) {
        logger.error(`[updateTasks] 写入行${rowNum}失败`, e);
      }
    }

    logger.info(`[updateTasks] 台账更新完成，共处理${alerts.length}条`);
  } finally {
    lock.release();
  }
}
