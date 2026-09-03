/**
 * src/ai_pmc/generateTasks.ts
 * Phase 3 — 台账生成与更新
 *
 * 职责：
 *   - 读取 PMC任务台账(0HadpM) 现有数据，建立 (ItemID+采购单号)→行号 Map
 *   - 遍历领星 item_list，按 sku→ItemID 组成唯一键
 *   - 键已存在：实时定位行号 + 校验键一致 → 更新系统列(A-I,L)，跳过 J，K列追加
 *   - 键不存在：台账末尾追加新行
 *   - 批量写入 FeishuSheetWriter，写前持有运行锁
 *
 * 台账列映射（0HadpM）：
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
import { acquireLock, releaseLock } from './lock';

// ─────────────────────────────────────────────
// 常量
// ─────────────────────────────────────────────

const LEDGER_TOKEN    = '<REDACTED_FEISHU_SPREADSHEET_TOKEN>';
const LEDGER_SHEET_ID = '<REDACTED_FEISHU_SHEET_ID>';

const COL = {
  ITEM_ID:      0,  // A
  ORDER_SN:     1,  // B
  SHOP:         2,  // C
  MSKU:         3,  // D
  TASK_TYPE:    4,  // E
  STAGE:        5,  // F
  STATUS:       6,  // G
  OWNER:        7,  // H
  SUGGESTION:   8,  // I
  MANUAL_NOTE:  9,  // J  ← 系统不覆盖
  PROGRESS_LOG: 10, // K  ← 追加
  UPDATED_AT:   11, // L
} as const;

const TOTAL_COLS = 12; // A-L

// ─────────────────────────────────────────────
// 类型
// ─────────────────────────────────────────────

/** 唯一键字符串 */
function makeKey(itemId: string, orderSn: string): string {
  return `${itemId}|||${orderSn}`;
}

export interface TaskRow {
  itemId: string;
  orderSn: string;
  shop: string;
  msku: string;
  taskType: string;
  stage: Stage | string;
  status: string;
  ownerName: string;
  suggestion: string;
  progressLog: string; // 追加内容（本次新增的一行）
}

// ─────────────────────────────────────────────
// 工具
// ─────────────────────────────────────────────

function nowBJ(): string {
  return new Date().toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
    hour12: false,
  }).replace(/\//g, '-');
}

/** 空值口径（P1-9） */
function isEmpty(v: unknown): boolean {
  return v === null || v === undefined || v === '' || v === '0000-00-00 00:00:00';
}

/** 从 item_list 聚合同 (itemId, orderSn) 的数量 */
function aggregateItems(items: PurchaseOrderItem[]): {
  msku: string;
  productName: string;
  quantityReal: number;
  quantityEntry: number;
  expectArriveTime: string | null;
} {
  const mskuSet = new Set<string>();
  let productName = '';
  let quantityReal = 0;
  let quantityEntry = 0;
  let expectArriveTime: string | null = null;

  for (const item of items) {
    (item.msku ?? []).forEach(m => mskuSet.add(m));
    if (!productName && item.product_name) productName = item.product_name;
    quantityReal  += item.quantity_real  ?? 0;
    quantityEntry += item.quantity_entry ?? 0;
    if (!expectArriveTime && !isEmpty(item.expect_arrive_time)) {
      expectArriveTime = item.expect_arrive_time;
    }
  }

  return {
    msku: Array.from(mskuSet).join(', '),
    productName,
    quantityReal,
    quantityEntry,
    expectArriveTime,
  };
}

/** 判断采购单初始阶段 */
function resolveInitialStage(order: PurchaseOrder, qReal: number, qEntry: number): {
  stage: string;
  status: string;
  taskType: string;
  suggestion: string;
} {
  // 终态：发货完成
  if (order.status_shipped === 2) {
    return { stage: Stage.DONE, status: '已完成', taskType: '到仓发货', suggestion: '已完成，无需操作' };
  }
  // 已全部入库
  if (qReal > 0 && qEntry >= qReal) {
    return { stage: Stage.ARRIVED_PENDING_SHIP, status: '已到仓待发货', taskType: '到仓发货', suggestion: '请安排发货' };
  }
  // 部分到货
  if (qEntry > 0 && qEntry < qReal) {
    return { stage: Stage.ARRIVAL_PENDING, status: '部分到货跟进中', taskType: '采购到货', suggestion: `已到 ${qEntry}/${qReal}，继续跟进到货` };
  }
  // 已下单未到货
  if (!isEmpty(order.order_time)) {
    return { stage: Stage.ARRIVAL_PENDING, status: '已下单待到货', taskType: '采购到货', suggestion: '跟进到货情况' };
  }
  // 审批通过未下单
  if (!isEmpty(order.auditor_time)) {
    return { stage: Stage.APPROVE_PENDING, status: '待下单', taskType: '采购下单', suggestion: '请及时下单' };
  }
  // 其他（待审批）
  return { stage: Stage.APPROVE_PENDING, status: '待下单', taskType: '补货执行', suggestion: '请推进审批并下单' };
}

// ─────────────────────────────────────────────
// 主函数
// ─────────────────────────────────────────────

/**
 * 读取台账 → 对比领星数据 → 新增/更新行
 *
 * @param orders   fetchPurchaseOrders() 返回结果
 * @param ownerMap readOwners() 返回结果
 */
export async function generateTasks(
  orders: PurchaseOrder[],
  ownerMap: OwnerMap,
): Promise<void> {
  const writer = new FeishuSheetWriter(LEDGER_TOKEN, LEDGER_SHEET_ID);

  // ── Step 1：读取台账现有数据 ──
  logger.info('[generateTasks] 读取台账现有数据...');
  let existingRows: string[][] = [];
  try {
    existingRows = await writer.readAll();
  } catch (e) {
    logger.error('[generateTasks] 读取台账失败，中止本次生成', e);
    return;
  }

  // 建立 (ItemID+采购单号) → 行号 Map（行号从1开始，第1行为表头）
  // 每次运行重新建立，禁止跨运行缓存（P1-2）
  const keyToRow = new Map<string, number>(); // key → 1-based 行号
  for (let i = 1; i < existingRows.length; i++) {
    const row = existingRows[i];
    const itemId  = (row[COL.ITEM_ID]  ?? '').trim();
    const orderSn = (row[COL.ORDER_SN] ?? '').trim();
    if (itemId && orderSn) {
      keyToRow.set(makeKey(itemId, orderSn), i + 1); // i+1：1-based，含表头偏移
    }
  }
  logger.info(`[generateTasks] 台账现有 ${keyToRow.size} 条记录`);

  // ── Step 2：遍历领星采购单，构建写入操作列表 ──
  const toUpdate: Array<{ rowNum: number; data: Partial<Record<keyof typeof COL, string>> }> = [];
  const toAppend: string[][] = [];

  for (const order of orders) {
    if (!order.order_sn) continue;

    // 遍历 item_list，按 sku 分组（多 SKU 各自成行）
    // 先按 sku 分桶
    const skuGroups = new Map<string, PurchaseOrderItem[]>();
    for (const item of order.item_list) {
      const sku = (item.sku ?? '').trim();
      if (!sku) continue;
      if (!skuGroups.has(sku)) skuGroups.set(sku, []);
      skuGroups.get(sku)!.push(item);
    }

    if (skuGroups.size === 0) {
      // 无明细时用 order_sn 自身作唯一 sku 键（防止丢失）
      skuGroups.set('__no_sku__', order.item_list);
    }

    for (const [, items] of skuGroups) {
      // ItemID 与 sku 一致（领星 sku 即为系统 ItemID）
      const itemId = items[0]?.sku?.trim() || '__unknown__';
      const orderSn = order.order_sn.trim();
      const key = makeKey(itemId, orderSn);

      const { msku, quantityReal, quantityEntry } = aggregateItems(items);
      const { stage, status, taskType, suggestion } = resolveInitialStage(order, quantityReal, quantityEntry);

      // 店铺来源（P1-8）
      const shop = order.shop_name?.trim()
        || ownerMap.get(itemId)?.name  // 取负责人表带出（此处兜底用name，实际应有店铺字段）
        || '未知';

      // 运营负责人
      const ownerInfo = lookupOwner(itemId, ownerMap);

      // 进展日志行
      const logLine = `[${nowBJ()}] 系统：阶段=${stage}，状态=${status}`;

      if (keyToRow.has(key)) {
        // ── 已存在：实时重新定位行号，校验键一致后更新 ──
        const rowNum = keyToRow.get(key)!;
        const existRow = existingRows[rowNum - 1]; // 0-based index

        // 校验目标行键值一致（P1-2）
        const existItemId  = (existRow?.[COL.ITEM_ID]  ?? '').trim();
        const existOrderSn = (existRow?.[COL.ORDER_SN] ?? '').trim();
        if (existItemId !== itemId || existOrderSn !== orderSn) {
          logger.warn(`[generateTasks] 行${rowNum}键不一致（台账:${existItemId}/${existOrderSn} vs 领星:${itemId}/${orderSn}），跳过`);
          continue;
        }

        // 终态行跳过（P1-6）
        const existStage = (existRow?.[COL.STAGE] ?? '').trim();
        if (existStage === Stage.DONE) {
          logger.info(`[generateTasks] ItemID=${itemId} 已是终态 DONE，跳过`);
          continue;
        }

        // K列：追加到现有内容后
        const existLog = (existRow?.[COL.PROGRESS_LOG] ?? '').trim();
        const newLog = existLog ? `${existLog}\n${logLine}` : logLine;

        toUpdate.push({
          rowNum,
          data: {
            SHOP: shop,
            MSKU: msku,
            TASK_TYPE: taskType,
            STAGE: stage,
            STATUS: status,
            OWNER: ownerInfo.name,
            SUGGESTION: suggestion,
            // J 列（MANUAL_NOTE）：不写入
            PROGRESS_LOG: newLog,
            UPDATED_AT: nowBJ(),
          },
        });

      } else {
        // ── 不存在：追加新行 ──
        const newRow = new Array<string>(TOTAL_COLS).fill('');
        newRow[COL.ITEM_ID]      = itemId;
        newRow[COL.ORDER_SN]     = orderSn;
        newRow[COL.SHOP]         = shop;
        newRow[COL.MSKU]         = msku;
        newRow[COL.TASK_TYPE]    = taskType;
        newRow[COL.STAGE]        = stage;
        newRow[COL.STATUS]       = status;
        newRow[COL.OWNER]        = ownerInfo.name;
        newRow[COL.SUGGESTION]   = suggestion;
        newRow[COL.MANUAL_NOTE]  = '';  // J 列留空，人工填写
        newRow[COL.PROGRESS_LOG] = logLine;
        newRow[COL.UPDATED_AT]   = nowBJ();
        toAppend.push(newRow);
      }
    }
  }

  logger.info(`[generateTasks] 待更新 ${toUpdate.length} 行，待新增 ${toAppend.length} 行`);

  // ── Step 3：获取运行锁后批量写入（P2-4） ──
  const locked = await acquireLock();
  if (!locked) {
    logger.warn('[generateTasks] 未能获取运行锁，跳过写入');
    return;
  }

  try {
    // 更新已存在行（系统列 A-I、K、L；跳过 J）
    for (const { rowNum, data } of toUpdate) {
      try {
        // 写入各系统列（逐列写以跳过 J 列）
        const cellUpdates: Array<{ row: number; col: number; value: string }> = [];
        if (data.SHOP        != null) cellUpdates.push({ row: rowNum, col: COL.SHOP        + 1, value: data.SHOP });
        if (data.MSKU        != null) cellUpdates.push({ row: rowNum, col: COL.MSKU        + 1, value: data.MSKU });
        if (data.TASK_TYPE   != null) cellUpdates.push({ row: rowNum, col: COL.TASK_TYPE   + 1, value: data.TASK_TYPE });
        if (data.STAGE       != null) cellUpdates.push({ row: rowNum, col: COL.STAGE       + 1, value: data.STAGE });
        if (data.STATUS      != null) cellUpdates.push({ row: rowNum, col: COL.STATUS      + 1, value: data.STATUS });
        if (data.OWNER       != null) cellUpdates.push({ row: rowNum, col: COL.OWNER       + 1, value: data.OWNER });
        if (data.SUGGESTION  != null) cellUpdates.push({ row: rowNum, col: COL.SUGGESTION  + 1, value: data.SUGGESTION });
        if (data.PROGRESS_LOG!= null) cellUpdates.push({ row: rowNum, col: COL.PROGRESS_LOG+ 1, value: data.PROGRESS_LOG! });
        if (data.UPDATED_AT  != null) cellUpdates.push({ row: rowNum, col: COL.UPDATED_AT  + 1, value: data.UPDATED_AT });

        await writer.writeCells(cellUpdates, { confirmWrite: true });
      } catch (e) {
        logger.error(`[generateTasks] 更新行${rowNum}失败，跳过`, e);
      }
    }

    // 追加新行
    if (toAppend.length > 0) {
      try {
        await writer.appendRows(toAppend, { confirmWrite: true });
      } catch (e) {
        logger.error('[generateTasks] 追加新行失败', e);
      }
    }

    logger.info('[generateTasks] 写入完成');
  } finally {
    await releaseLock();
  }
}
