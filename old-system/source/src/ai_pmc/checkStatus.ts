/**
 * src/ai_pmc/checkStatus.ts
 * Phase 4 — 阶段超时 / 升级 / 终态判断，生成待提醒列表
 *
 * 输入：标准化采购单 + PmcConfig + OwnerMap
 * 输出：AlertItem[]（每条对应一条需要发送的提醒）
 *
 * 内部额外读取：
 *   - PMC任务台账 (0HadpM)：获取 DONE 状态
 *   - PMC通知日志 (4BfsYD)：防重复（近 LOG_LOOKBACK_DAYS 天）
 */

process.env.TZ = 'Asia/Shanghai';

import { FeishuSheetWriter } from '../feishuSheetWriter';
import { PurchaseOrder } from './fetchLingxing';
import { OwnerMap, lookupOwner } from './readOwners';
import { Stage, STAGE_TASK_STATUS } from './stages';
import { PmcConfig, PMC_SPREADSHEET_TOKEN, SHEET } from './config';
import { daysSince, isEmptyTime, parseBJDateMs } from './dateUtil';
import { logger } from './logger';

// 避免未用告警的占位（STAGE_TASK_STATUS 供 updateTasks 复用同枚举）
void STAGE_TASK_STATUS;

// ─────────────────────────────────────────────
// 输出类型
// ─────────────────────────────────────────────

export interface AlertItem {
  itemId: string;
  orderSn: string;
  productName: string;
  stage: Stage;
  daysOverdue: number;       // 已逾期天数（相对各阶段基准时间）
  ownerName: string;
  ownerOpenId: string;
  suggestion: string;
  needEscalate: boolean;
  escalateStage: Stage | null;
}

// Phase 7a-A：到仓未发货提醒的"采购单太老即视为历史遗留"阈值（天），可用环境变量覆盖
const STALE_SHIP_DAYS = Number(process.env.PMC_STALE_SHIP_DAYS || '60') || 60;

// 通知日志列索引（4BfsYD）
// A=log_id B=item_id C=order_sn D=task_stage E=notify_time F=notify_type G=receiver H=send_status I=error_msg
const LOG_COL = {
  ITEM_ID:     1,  // B
  ORDER_SN:    2,  // C
  TASK_STAGE:  3,  // D
  NOTIFY_TIME: 4,  // E
  SEND_STATUS: 7,  // H（成功/失败）
};

// 台账列索引（0HadpM）
const LEDGER_COL = {
  ITEM_ID:  0, // A
  ORDER_SN: 1, // B
  STAGE:    5, // F
};

// ─────────────────────────────────────────────
// 工具
// ─────────────────────────────────────────────

/** 从采购单拿指定 SKU 的产品名（ISSUE-3：按 SKU 取，多 SKU 单不串） */
function getProductName(order: PurchaseOrder, sku: string): string {
  const hit = order.item_list?.find((i) => String(i.sku ?? '').trim() === sku);
  return hit?.product_name ?? order.item_list?.[0]?.product_name ?? order.order_sn;
}

/** 聚合数量（ISSUE-3：仅统计指定 SKU 的明细，避免多 SKU 采购单互相串数） */
function getQty(order: PurchaseOrder, sku: string): { qReal: number; qEntry: number } {
  let qReal = 0; let qEntry = 0;
  for (const item of order.item_list) {
    if (String(item.sku ?? '').trim() !== sku) continue;
    qReal  += item.quantity_real  ?? 0;
    qEntry += item.quantity_entry ?? 0;
  }
  return { qReal, qEntry };
}

// ─────────────────────────────────────────────
// 读通知日志：建立防重复 Map
// key = "itemId|||orderSn|||stage"  value = 最近 notify_time 字符串
// ─────────────────────────────────────────────

function loadNotifyLog(writer: FeishuSheetWriter, lookbackDays: number): Map<string, string> {
  const map = new Map<string, string>();
  try {
    const rows = writer.readValues({
      spreadsheetToken: PMC_SPREADSHEET_TOKEN,
      sheetId: SHEET.notifyLog,
      range: 'A1:I3000',
    });
    if (rows.length < 2) return map;

    const cutoffMs = Date.now() - lookbackDays * 24 * 60 * 60 * 1000;

    for (const row of rows.slice(1)) {
      const notifyTime = String(row[LOG_COL.NOTIFY_TIME] ?? '').trim();
      if (!notifyTime) continue;
      const tsMs = parseBJDateMs(notifyTime);
      if (tsMs === null || tsMs < cutoffMs) continue;

      // 只对"成功"的通知去重；失败的允许重发（避免发送失败却被永久压制）
      const sendStatus = String(row[LOG_COL.SEND_STATUS] ?? '').trim();
      if (sendStatus && sendStatus !== '成功') continue;

      const itemId    = String(row[LOG_COL.ITEM_ID]   ?? '').trim();
      const orderSn   = String(row[LOG_COL.ORDER_SN]  ?? '').trim();
      const taskStage = String(row[LOG_COL.TASK_STAGE] ?? '').trim();
      if (!itemId || !orderSn || !taskStage) continue;

      const key = `${itemId}|||${orderSn}|||${taskStage}`;
      const existing = map.get(key);
      // 保留最新的 notify_time（ISSUE-6：用毫秒数值比较，避免字典序误差）
      if (!existing) {
        map.set(key, notifyTime);
      } else {
        const a = parseBJDateMs(notifyTime);
        const b = parseBJDateMs(existing);
        if (a !== null && (b === null || a > b)) map.set(key, notifyTime);
      }
    }
    logger.info(`[checkStatus] 通知日志加载完成，近${lookbackDays}天共${map.size}条去重记录`);
  } catch (e) {
    logger.warn(`[checkStatus] 通知日志读取失败，防重复跳过: ${String(e)}`);
  }
  return map;
}

// ─────────────────────────────────────────────
// 读台账：建立 DONE 集合
// ─────────────────────────────────────────────

interface LedgerInfo {
  doneKeys: Set<string>; // key = "itemId|||orderSn"
}

function loadLedgerInfo(writer: FeishuSheetWriter): LedgerInfo {
  const doneKeys = new Set<string>();
  try {
    const rows = writer.readValues({
      spreadsheetToken: PMC_SPREADSHEET_TOKEN,
      sheetId: SHEET.taskLedger,
      range: 'A1:F3000',
    });
    for (const row of rows.slice(1)) {
      const itemId  = String(row[LEDGER_COL.ITEM_ID]  ?? '').trim();
      const orderSn = String(row[LEDGER_COL.ORDER_SN] ?? '').trim();
      const stage   = String(row[LEDGER_COL.STAGE]    ?? '').trim();
      if (!itemId || !orderSn) continue;
      if (stage === Stage.DONE) doneKeys.add(`${itemId}|||${orderSn}`);
    }
    logger.info(`[checkStatus] 台账加载完成，DONE行${doneKeys.size}条`);
  } catch (e) {
    logger.warn(`[checkStatus] 台账读取失败，DONE判断跳过: ${String(e)}`);
  }
  return { doneKeys };
}

// ─────────────────────────────────────────────
// D0 确定逻辑（P0-2）
// ─────────────────────────────────────────────

function resolveD0(order: PurchaseOrder, itemId: string, notifyLog: Map<string, string>): string | null {
  // 优先：领星 warehouse_time
  if (!isEmptyTime(order.arrival_time)) return order.arrival_time;
  // 兜底：通知日志中该(itemId+orderSn)首次进入 ARRIVED_PENDING_SHIP 的时间
  const logKey = `${itemId}|||${order.order_sn}|||${Stage.ARRIVED_PENDING_SHIP}`;
  const logTime = notifyLog.get(logKey);
  if (logTime) return logTime;
  return null;
}

// ─────────────────────────────────────────────
// 防重复检查
// ─────────────────────────────────────────────

function shouldSkip(
  itemId: string,
  orderSn: string,
  stage: Stage,
  intervalDays: number,
  notifyLog: Map<string, string>,
): boolean {
  const key = `${itemId}|||${orderSn}|||${stage}`;
  const lastTime = notifyLog.get(key);
  if (!lastTime) return false;
  const days = daysSince(lastTime);
  if (days === null) return false;
  return days < intervalDays;
}

// ─────────────────────────────────────────────
// 主函数
// ─────────────────────────────────────────────

/**
 * 检查所有采购单状态，返回需要提醒的列表。
 *
 * @param orders        fetchPurchaseOrders() 结果
 * @param config        loadPmcConfig() 结果
 * @param ownerMap      readOwners() 结果
 * @param stagesFilter  可选：只检查指定阶段（runDaily 用于过滤 R003/R004）
 * @param shippedSkus   Phase 7a：近N天有发货动作的SKU，命中则视为已安排发货
 * @param localStockSkus Phase 7a：本地仓有库存的SKU；为空/缺省=拉取失败，降级不过滤
 */
export function checkStatus(
  orders: PurchaseOrder[],
  config: PmcConfig,
  ownerMap: OwnerMap,
  stagesFilter?: Stage[],
  shippedSkus: Set<string> = new Set(),
  localStockSkus?: Set<string> | null,
): AlertItem[] {
  const writer = new FeishuSheetWriter();
  const notifyLog  = loadNotifyLog(writer, config.logLookbackDays);
  const ledgerInfo = loadLedgerInfo(writer);
  const filterSet  = stagesFilter ? new Set(stagesFilter) : null;

  const alerts: AlertItem[] = [];
  const { rules } = config;

  for (const order of orders) {
    if (!order.order_sn) continue;

    // 按 sku 分出 itemId
    const skuSet = new Set(order.item_list.map((i) => String(i.sku ?? '').trim()).filter(Boolean));
    if (skuSet.size === 0) skuSet.add('__unknown__');

    for (const itemId of skuSet) {
      const orderSn   = order.order_sn;
      const key       = `${itemId}|||${orderSn}`;
      const ownerInfo = lookupOwner(itemId, ownerMap);
      void ownerInfo; // 运营负责人用于台账H列；提醒收件人按固定角色

      // 终态跳过（P1-6）
      if (ledgerInfo.doneKeys.has(key)) continue;

      const { qReal, qEntry } = getQty(order, itemId); // ISSUE-3：按当前SKU聚合
      const productName = getProductName(order, itemId);

      // ── R001 审批未下单 ──────────────────────────────────────
      if (!isEmptyTime(order.auditor_time) && isEmptyTime(order.order_time)) {
        const days = daysSince(order.auditor_time) ?? 0;
        if (days >= rules.R001.timeoutDays) {
          if (!filterSet || filterSet.has(Stage.APPROVE_PENDING)) {
            if (!shouldSkip(itemId, orderSn, Stage.APPROVE_PENDING, rules.R001.intervalDays, notifyLog)) {
              const needEsc = rules.R001.escalateDays !== null && days >= rules.R001.escalateDays;
              alerts.push({
                itemId, orderSn, productName,
                stage: Stage.APPROVE_PENDING,
                daysOverdue: days,
                ownerName: config.owners.purchase.name,
                ownerOpenId: config.owners.purchase.openId,
                suggestion: `审批通过已${days}天，请尽快下单`,
                needEscalate: needEsc,
                escalateStage: needEsc ? Stage.ESCALATE_APPROVE : null,
              });
            }
          }
          if (rules.R001.escalateDays !== null && days >= rules.R001.escalateDays) {
            if (!filterSet || filterSet.has(Stage.ESCALATE_APPROVE)) {
              if (!shouldSkip(itemId, orderSn, Stage.ESCALATE_APPROVE, rules.R001.intervalDays, notifyLog)) {
                alerts.push({
                  itemId, orderSn, productName,
                  stage: Stage.ESCALATE_APPROVE,
                  daysOverdue: days,
                  ownerName: config.owners.pmc.name,
                  ownerOpenId: config.owners.pmc.openId,
                  suggestion: `⚠️ 审批后${days}天仍未下单，请升级处理`,
                  needEscalate: true,
                  escalateStage: Stage.ESCALATE_APPROVE,
                });
              }
            }
          }
        }
        continue; // 同一采购单同一SKU只走一个阶段
      }

      // ── R002 已下单未到货（含部分到货） ──────────────────────
      const isPartial = qEntry > 0 && qEntry < qReal;
      const notArrived = qReal === 0 || qEntry < qReal;
      if (!isEmptyTime(order.order_time) && notArrived) {
        const days = daysSince(order.order_time) ?? 0;
        if (days >= rules.R002.timeoutDays) {
          const suggestion = isPartial
            ? `已到货${qEntry}/${qReal}件，距下单${days}天，请跟进尾款到货`
            : `距下单${days}天未到货，请跟进`;
          if (!filterSet || filterSet.has(Stage.ARRIVAL_PENDING)) {
            if (!shouldSkip(itemId, orderSn, Stage.ARRIVAL_PENDING, rules.R002.intervalDays, notifyLog)) {
              const needEsc = rules.R002.escalateDays !== null && days >= rules.R002.escalateDays;
              alerts.push({
                itemId, orderSn, productName,
                stage: Stage.ARRIVAL_PENDING,
                daysOverdue: days,
                ownerName: config.owners.purchase.name,
                ownerOpenId: config.owners.purchase.openId,
                suggestion,
                needEscalate: needEsc,
                escalateStage: needEsc ? Stage.ESCALATE_ARRIVAL : null,
              });
            }
          }
          if (rules.R002.escalateDays !== null && days >= rules.R002.escalateDays) {
            if (!filterSet || filterSet.has(Stage.ESCALATE_ARRIVAL)) {
              if (!shouldSkip(itemId, orderSn, Stage.ESCALATE_ARRIVAL, rules.R002.intervalDays, notifyLog)) {
                alerts.push({
                  itemId, orderSn, productName,
                  stage: Stage.ESCALATE_ARRIVAL,
                  daysOverdue: days,
                  ownerName: config.owners.pmc.name,
                  ownerOpenId: config.owners.pmc.openId,
                  suggestion: `⚠️ 距下单${days}天仍未到货，请升级催货`,
                  needEscalate: true,
                  escalateStage: Stage.ESCALATE_ARRIVAL,
                });
              }
            }
          }
        }
        continue;
      }

      // ── R003/R004 已到仓 ─────────────────────────────────────
      const fullyArrived = qReal > 0 && qEntry >= qReal;
      // Phase 7a：已到货但该SKU近N天已有发货计划/货件 → 已安排发货，不再提醒仓库发货
      const alreadyShipped = shippedSkus.has(itemId);
      // Phase 7a-A：采购单太老（update_time 超 PMC_STALE_SHIP_DAYS 天）且无近期发货动作 → 历史遗留，不提醒
      const orderAgeDays = daysSince(order.update_time);
      const isStale = orderAgeDays !== null && orderAgeDays > STALE_SHIP_DAYS;
      // Phase 7a：本地仓库存 ≤ 0 → 已发走/被扣减 → 不提醒（localStockSkus 为 null 时降级不过滤）
      const hasLocalStock = localStockSkus ? localStockSkus.has(itemId) : true;
      const notShipped = order.status_shipped !== 2 && !alreadyShipped && !isStale && hasLocalStock;

      if (fullyArrived && notShipped) {
        const d0 = resolveD0(order, itemId, notifyLog);
        const daysFromD0 = d0 ? (daysSince(d0) ?? 0) : 0;

        if (daysFromD0 >= rules.R004.timeoutDays) {
          if (!filterSet || filterSet.has(Stage.OVERDUE_SHIP)) {
            if (!shouldSkip(itemId, orderSn, Stage.OVERDUE_SHIP, rules.R004.intervalDays, notifyLog)) {
              const needEsc = rules.R004.escalateDays !== null && daysFromD0 >= rules.R004.escalateDays;
              alerts.push({
                itemId, orderSn, productName,
                stage: Stage.OVERDUE_SHIP,
                daysOverdue: daysFromD0,
                ownerName: config.owners.warehouse.name,
                ownerOpenId: config.owners.warehouse.openId,
                suggestion: `货到仓已${daysFromD0}天未发货，请尽快处理`,
                needEscalate: needEsc,
                escalateStage: needEsc ? Stage.ESCALATE_SHIP : null,
              });
            }
          }
          if (rules.R004.escalateDays !== null && daysFromD0 >= rules.R004.escalateDays) {
            if (!filterSet || filterSet.has(Stage.ESCALATE_SHIP)) {
              if (!shouldSkip(itemId, orderSn, Stage.ESCALATE_SHIP, rules.R004.intervalDays, notifyLog)) {
                alerts.push({
                  itemId, orderSn, productName,
                  stage: Stage.ESCALATE_SHIP,
                  daysOverdue: daysFromD0,
                  ownerName: config.owners.pmc.name,
                  ownerOpenId: config.owners.pmc.openId,
                  suggestion: `⚠️ 货到仓${daysFromD0}天未发货，请升级处理`,
                  needEscalate: true,
                  escalateStage: Stage.ESCALATE_SHIP,
                });
              }
            }
          }
        } else {
          if (!filterSet || filterSet.has(Stage.ARRIVED_PENDING_SHIP)) {
            if (!shouldSkip(itemId, orderSn, Stage.ARRIVED_PENDING_SHIP, rules.R003.intervalDays, notifyLog)) {
              alerts.push({
                itemId, orderSn, productName,
                stage: Stage.ARRIVED_PENDING_SHIP,
                daysOverdue: daysFromD0,
                ownerName: config.owners.warehouse.name,
                ownerOpenId: config.owners.warehouse.openId,
                suggestion: d0 ? `货已到仓${daysFromD0}天，请安排发货` : '货已到仓，请安排发货',
                needEscalate: false,
                escalateStage: null,
              });
            }
          }
        }
      }
    }
  }

  logger.info(`[checkStatus] 检查完成，共${alerts.length}条待提醒（其中升级${alerts.filter((a) => a.needEscalate).length}条）`);
  return alerts;
}
