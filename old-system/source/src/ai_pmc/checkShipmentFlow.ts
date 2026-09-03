/**
 * src/ai_pmc/checkShipmentFlow.ts
 * Phase 7B — WFS 发货流程超时判断，生成待提醒列表
 *
 * 两类提醒（其余状态不提醒）：
 *   A. 已申报停留过久（货件已建未发货）→ 提醒仓库(刘晶晶)确认发出
 *      超时 PMC_SHIP_CONFIRM_DAYS(默认2天)，升级 ..._ESC(默认5天)，发江梓博
 *   B. 已发货后超物流缓冲未海外到货 → 提醒采购(巫新健)跟进物流
 *      超时 PMC_SHIP_OVERSEAS_DAYS(默认45天)，升级 ..._ESC(默认52天)，发江梓博
 *
 * 防重复：读 PMC通知日志近30天，仅对 send_status=成功 的记录去重，间隔内不重复发。
 */

process.env.TZ = 'Asia/Shanghai';

import { FeishuSheetWriter } from '../feishuSheetWriter';
import { WfsShipmentItem } from './fetchShipmentStatus';
import { PmcConfig, PMC_SPREADSHEET_TOKEN, SHEET } from './config';
import { daysSince, parseBJDateMs } from './dateUtil';
import { logger } from './logger';

// 阶段常量（用于通知日志 task_stage 与防重复）
export const SHIP_STAGE = {
  CONFIRM_PENDING: 'SHIP_CONFIRM_PENDING',     // 已申报未发货超时
  OVERSEAS_PENDING: 'SHIP_OVERSEAS_PENDING',   // 已发货未海外到货超时
  ESCALATE_CONFIRM: 'ESCALATE_SHIP_CONFIRM',
  ESCALATE_OVERSEAS: 'ESCALATE_SHIP_OVERSEAS',
} as const;

// 规则（环境变量可覆盖；可后续移入规则配置表）
const CONFIRM_DAYS  = Number(process.env.PMC_SHIP_CONFIRM_DAYS  || '2')  || 2;
const CONFIRM_ESC   = Number(process.env.PMC_SHIP_CONFIRM_ESC   || '5')  || 5;
const CONFIRM_INTERVAL = Number(process.env.PMC_SHIP_CONFIRM_INTERVAL || '1') || 1;
const OVERSEAS_DAYS = Number(process.env.PMC_SHIP_OVERSEAS_DAYS || '45') || 45;
const OVERSEAS_ESC  = Number(process.env.PMC_SHIP_OVERSEAS_ESC  || '52') || 52;
const OVERSEAS_INTERVAL = Number(process.env.PMC_SHIP_OVERSEAS_INTERVAL || '3') || 3;

export interface ShipmentAlert {
  itemId: string;
  cargoCode: string;
  productName: string;
  stage: string;
  daysOverdue: number;
  ownerName: string;
  ownerOpenId: string;
  suggestion: string;
  needEscalate: boolean;
  escalateStage: string | null;
}

const LOG_COL = { ITEM_ID: 1, ORDER_SN: 2, TASK_STAGE: 3, NOTIFY_TIME: 4, SEND_STATUS: 7 };

/** 读通知日志近30天，仅成功记录；key = itemId|||cargoCode|||stage → 最近 notify_time */
function loadNotifyLog(writer: FeishuSheetWriter, lookbackDays: number): Map<string, string> {
  const map = new Map<string, string>();
  try {
    const rows = writer.readValues({ spreadsheetToken: PMC_SPREADSHEET_TOKEN, sheetId: SHEET.notifyLog, range: 'A1:I3000' });
    if (rows.length < 2) return map;
    const cutoff = Date.now() - lookbackDays * 86400000;
    for (const row of rows.slice(1)) {
      const status = String(row[LOG_COL.SEND_STATUS] ?? '').trim();
      if (status && status !== '成功') continue;
      const t = String(row[LOG_COL.NOTIFY_TIME] ?? '').trim();
      const ms = parseBJDateMs(t);
      if (ms === null || ms < cutoff) continue;
      const itemId = String(row[LOG_COL.ITEM_ID] ?? '').trim();
      const ref    = String(row[LOG_COL.ORDER_SN] ?? '').trim(); // 7B 用 cargoCode 存这列
      const stage  = String(row[LOG_COL.TASK_STAGE] ?? '').trim();
      if (!itemId || !stage) continue;
      const key = `${itemId}|||${ref}|||${stage}`;
      const prev = map.get(key);
      if (!prev || (parseBJDateMs(t) ?? 0) > (parseBJDateMs(prev) ?? 0)) map.set(key, t);
    }
  } catch (e) {
    logger.warn(`[checkShipmentFlow] 通知日志读取失败，防重复跳过: ${String(e)}`);
  }
  return map;
}

function shouldSkip(notifyLog: Map<string, string>, itemId: string, ref: string, stage: string, intervalDays: number): boolean {
  const last = notifyLog.get(`${itemId}|||${ref}|||${stage}`);
  if (!last) return false;
  const d = daysSince(last);
  return d !== null && d < intervalDays;
}

export function checkShipmentFlow(items: WfsShipmentItem[], config: PmcConfig): ShipmentAlert[] {
  const writer = new FeishuSheetWriter();
  const notifyLog = loadNotifyLog(writer, config.logLookbackDays);
  const alerts: ShipmentAlert[] = [];
  const warehouse = config.owners.warehouse;
  const purchase  = config.owners.purchase;

  for (const it of items) {
    // A. 已申报未发货
    if (it.syncStatus === '已申报') {
      const days = daysSince(it.createDate);
      if (days !== null && days >= CONFIRM_DAYS && !shouldSkip(notifyLog, it.itemId, it.cargoCode, SHIP_STAGE.CONFIRM_PENDING, CONFIRM_INTERVAL)) {
        const esc = days >= CONFIRM_ESC;
        alerts.push({
          itemId: it.itemId, cargoCode: it.cargoCode, productName: it.productName,
          stage: SHIP_STAGE.CONFIRM_PENDING, daysOverdue: days,
          ownerName: warehouse.name, ownerOpenId: warehouse.openId,
          suggestion: `WFS货件 ${it.cargoCode} 已申报${days}天仍未发货，请尽快确认发出`,
          needEscalate: esc, escalateStage: esc ? SHIP_STAGE.ESCALATE_CONFIRM : null,
        });
      }
      continue;
    }
    // B. 已发货未海外到货
    if (it.syncStatus === '已发货') {
      // 已发货基准：to_await_time(epoch ms) 优先，否则 createDate
      const base = it.awaitTime && it.awaitTime !== '0' ? it.awaitTime : it.createDate;
      const days = daysSince(base);
      if (days !== null && days >= OVERSEAS_DAYS && !shouldSkip(notifyLog, it.itemId, it.cargoCode, SHIP_STAGE.OVERSEAS_PENDING, OVERSEAS_INTERVAL)) {
        const esc = days >= OVERSEAS_ESC;
        alerts.push({
          itemId: it.itemId, cargoCode: it.cargoCode, productName: it.productName,
          stage: SHIP_STAGE.OVERSEAS_PENDING, daysOverdue: days,
          ownerName: purchase.name, ownerOpenId: purchase.openId,
          suggestion: `WFS货件 ${it.cargoCode} 已发货${days}天仍未海外到货，请跟进物流`,
          needEscalate: esc, escalateStage: esc ? SHIP_STAGE.ESCALATE_OVERSEAS : null,
        });
      }
      continue;
    }
    // 入库中 / 已完成 等：不提醒
  }

  logger.info(`[checkShipmentFlow] WFS发货流程检查完成，待提醒${alerts.length}条（升级${alerts.filter(a => a.needEscalate).length}条）`);
  return alerts;
}
