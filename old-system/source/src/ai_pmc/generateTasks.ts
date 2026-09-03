/**
 * src/ai_pmc/generateTasks.ts
 * Phase 3 — 台账生成与更新
 *
 * 台账列（0HadpM）：
 *   A=ItemID  B=采购单号  C=店铺  D=MSKU  E=任务类型
 *   F=当前阶段  G=任务状态  H=运营负责人  I=系统建议
 *   J=人工备注(不覆盖)  K=任务进展明细(追加)  L=最近更新
 */

process.env.TZ = 'Asia/Shanghai';

import { FeishuSheetWriter } from '../feishuSheetWriter';
import { PurchaseOrder, PurchaseOrderItem } from './fetchLingxing';
import { OwnerMap, lookupOwner } from './readOwners';
import { Stage } from './stages';
import { logger } from './logger';
import { acquireLock } from './lock';

// ─────────────────────────────────────────────
// 常量
// ─────────────────────────────────────────────

const LEDGER_TOKEN     = '<REDACTED_FEISHU_SPREADSHEET_TOKEN>';
const LEDGER_SHEET_ID  = '<REDACTED_FEISHU_SHEET_ID>';
const LEDGER_SHEET_NAME = 'PMC任务台账';

// 列索引（0-based）
const C = {
  ITEM_ID:      0,  // A
  ORDER_SN:     1,  // B
  SHOP:         2,  // C
  MSKU:         3,  // D
  TASK_TYPE:    4,  // E
  STAGE:        5,  // F
  STATUS:       6,  // G
  OWNER:        7,  // H
  SUGGESTION:   8,  // I
  MANUAL_NOTE:  9,  // J ← 不覆盖
  PROGRESS_LOG: 10, // K ← 追加
  UPDATED_AT:   11, // L
};

const TOTAL_COLS = 12;

// ─────────────────────────────────────────────
// 工具函数
// ─────────────────────────────────────────────

function makeKey(itemId: string, orderSn: string): string {
  return `${itemId}|||${orderSn}`;
}

function nowBJ(): string {
  return new Date().toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).replace(/\//g, '-');
}

function isEmpty(v: unknown): boolean {
  return v === null || v === undefined || v === '' || v === '0000-00-00 00:00:00';
}

function aggregateItems(items: PurchaseOrderItem[]): {
  msku: string; quantityReal: number; quantityEntry: number;
} {
  const mskuSet = new Set<string>();
  let quantityReal = 0;
  let quantityEntry = 0;
  for (const item of items) {
    (item.msku ?? []).forEach(m => mskuSet.add(m));
    quantityReal  += item.quantity_real  ?? 0;
    quantityEntry += item.quantity_entry ?? 0;
  }
  return { msku: Array.from(mskuSet).join(', '), quantityReal, quantityEntry };
}

function resolveStage(order: PurchaseOrder, qReal: number, qEntry: number): {
  stage: string; status: string; taskType: string; suggestion: string;
} {
  if (order.status_shipped === 2)
    return { stage: Stage.DONE, status: '已完成', taskType: '到仓发货', suggestion: '已完成，无需操作' };
  if (qReal > 0 && qEntry >= qReal)
    return { stage: Stage.ARRIVED_PENDING_SHIP, status: '已到仓待发货', taskType: '到仓发货', suggestion: '请安排发货' };
  if (qEntry > 0 && qEntry < qReal)
    return { stage: Stage.ARRIVAL_PENDING, status: '部分到货跟进中', taskType: '采购到货', suggestion: `已到${qEntry}/${qReal}，继续跟进` };
  if (!isEmpty(order.order_time))
    return { stage: Stage.ARRIVAL_PENDING, status: '已下单待到货', taskType: '采购到货', suggestion: '跟进到货情况' };
  if (!isEmpty(order.auditor_time))
    return { stage: Stage.APPROVE_PENDING, status: '待下单', taskType: '采购下单', suggestion: '请及时下单' };
  return { stage: Stage.APPROVE_PENDING, status: '待下单', taskType: '补货执行', suggestion: '请推进审批并下单' };
}

// ─────────────────────────────────────────────
// 主函数
// ─────────────────────────────────────────────

export function generateTasks(orders: PurchaseOrder[], ownerMap: OwnerMap): void {
  const writer = new FeishuSheetWriter();

  // Step 1：读台账
  logger.info('[generateTasks] 读取台账...');
  let existingRows: (string | number | boolean | null)[][] = [];
  try {
    existingRows = writer.readValues({
      spreadsheetToken: LEDGER_TOKEN,
      sheetId: LEDGER_SHEET_ID,
      range: 'A1:L3000',
    });
  } catch (e) {
    logger.error('[generateTasks] 读取台账失败，中止', e);
    return;
  }

  // 建立 (ItemID+采购单号) → 1-based行号 Map（每次运行重新建，不缓存）
  const keyToRow = new Map<string, number>();
  for (let i = 1; i < existingRows.length; i++) {
    const row = existingRows[i];
    const itemId  = String(row[C.ITEM_ID]  ?? '').trim();
    const orderSn = String(row[C.ORDER_SN] ?? '').trim();
    if (itemId && orderSn) keyToRow.set(makeKey(itemId, orderSn), i + 1);
  }
  logger.info(`[generateTasks] 台账现有${keyToRow.size}条，共${existingRows.length}行`);

  // Step 2：构建写入列表
  const toUpdate: Array<{ rowNum: number; sysRow: string[]; logCell: string }> = [];
  const toAppend: string[][] = [];

  for (const order of orders) {
    if (!order.order_sn) continue;

    // 按 sku 分组
    const skuGroups = new Map<string, PurchaseOrderItem[]>();
    for (const item of order.item_list) {
      const sku = (item.sku ?? '').trim();
      if (!sku) continue;
      if (!skuGroups.has(sku)) skuGroups.set(sku, []);
      skuGroups.get(sku)!.push(item);
    }
    if (skuGroups.size === 0) skuGroups.set('__no_sku__', []);

    for (const [, items] of skuGroups) {
      const itemId  = items[0]?.sku?.trim() || '__unknown__';
      const orderSn = order.order_sn.trim();
      const key     = makeKey(itemId, orderSn);

      const { msku, quantityReal, quantityEntry } = aggregateItems(items);
      const { stage, status, taskType, suggestion } = resolveStage(order, quantityReal, quantityEntry);
      const shop      = order.shop_name?.trim() || '未知';
      const ownerInfo = lookupOwner(itemId, ownerMap);
      const logLine   = `[${nowBJ()}] 系统：阶段=${stage}，状态=${status}`;

      if (keyToRow.has(key)) {
        const rowNum  = keyToRow.get(key)!;
        const existRow = existingRows[rowNum - 1];

        // 校验键一致（P1-2）
        const eItemId  = String(existRow?.[C.ITEM_ID]  ?? '').trim();
        const eOrderSn = String(existRow?.[C.ORDER_SN] ?? '').trim();
        if (eItemId !== itemId || eOrderSn !== orderSn) {
          logger.warn(`[generateTasks] 行${rowNum}键不一致，跳过`);
          continue;
        }

        // 终态跳过（P1-6）
        if (String(existRow?.[C.STAGE] ?? '').trim() === Stage.DONE) {
          logger.info(`[generateTasks] ${itemId} 已DONE，跳过`);
          continue;
        }

        // K列追加
        const existLog = String(existRow?.[C.PROGRESS_LOG] ?? '').trim();
        const newLog   = existLog ? `${existLog}\n${logLine}` : logLine;

        // 系统列 A-I（9列，跳过 J）
        const sysRow = [itemId, orderSn, shop, msku, taskType, stage, status, ownerInfo.name, suggestion];
        toUpdate.push({ rowNum, sysRow, logCell: newLog });

      } else {
        const newRow = new Array<string>(TOTAL_COLS).fill('');
        newRow[C.ITEM_ID]      = itemId;
        newRow[C.ORDER_SN]     = orderSn;
        newRow[C.SHOP]         = shop;
        newRow[C.MSKU]         = msku;
        newRow[C.TASK_TYPE]    = taskType;
        newRow[C.STAGE]        = stage;
        newRow[C.STATUS]       = status;
        newRow[C.OWNER]        = ownerInfo.name;
        newRow[C.SUGGESTION]   = suggestion;
        newRow[C.MANUAL_NOTE]  = '';
        newRow[C.PROGRESS_LOG] = logLine;
        newRow[C.UPDATED_AT]   = nowBJ();
        toAppend.push(newRow);
      }
    }
  }

  logger.info(`[generateTasks] 待更新${toUpdate.length}行，待新增${toAppend.length}行`);

  // Step 3：获取运行锁
  const lock = acquireLock('generateTasks');
  if (!lock) {
    logger.warn('[generateTasks] 未获取到运行锁，跳过写入');
    return;
  }

  try {
    // 更新已有行：分两段写，跳过 J 列
    for (const { rowNum, sysRow, logCell } of toUpdate) {
      try {
        // 写 A-I（9列）
        writer.writeCells({
          spreadsheetToken: LEDGER_TOKEN,
          sheetId: LEDGER_SHEET_ID,
          sheetName: LEDGER_SHEET_NAME,
          range: `A${rowNum}:I${rowNum}`,
          rows: [sysRow],
          dryRun: false,
          confirmWrite: true,
          allowOverwrite: true,
        });
        // 写 K-L（跳过J）
        writer.writeCells({
          spreadsheetToken: LEDGER_TOKEN,
          sheetId: LEDGER_SHEET_ID,
          sheetName: LEDGER_SHEET_NAME,
          range: `K${rowNum}:L${rowNum}`,
          rows: [[logCell, nowBJ()]],
          dryRun: false,
          confirmWrite: true,
          allowOverwrite: true,
        });
      } catch (e) {
        logger.error(`[generateTasks] 更新行${rowNum}失败`, e);
      }
    }

    // 追加新行
    if (toAppend.length > 0) {
      const startRow = existingRows.length + 1; // 现有行数+1（含表头）
      const endRow   = startRow + toAppend.length - 1;
      try {
        writer.writeCells({
          spreadsheetToken: LEDGER_TOKEN,
          sheetId: LEDGER_SHEET_ID,
          sheetName: LEDGER_SHEET_NAME,
          range: `A${startRow}:L${endRow}`,
          rows: toAppend,
          dryRun: false,
          confirmWrite: true,
          allowOverwrite: false,
        });
      } catch (e) {
        logger.error('[generateTasks] 追加新行失败', e);
      }
    }

    logger.info('[generateTasks] 写入完成');
  } finally {
    lock.release();
  }
}
