/**
 * src/ai_pmc/pipeline.ts
 * Phase 6 — 共享编排逻辑（被 runSunday / runWednesday / runDaily 复用）
 *
 * 步骤：
 *   1. loadPmcConfig
 *   2. fetchPurchaseOrders（≤500）
 *   3. readOwners
 *   4. （可选）generateTasks 生成/更新台账
 *   5a. fetchShipmentSkus + fetchLocalStockSkus（Phase 7a：到仓未发货判断）
 *   5b. checkStatus 生成待提醒（可按阶段过滤）
 *   6. notify 发送（dry-run 默认，--send 真发）
 *   7. （仅 --send）updateTasksAfterNotify 写回台账
 *
 * 每步独立 try/catch，单步异常写日志但不中断整体（P2 异常处理规范）。
 * doSend 由命令行 --send 控制，默认 dry-run。
 */

process.env.TZ = 'Asia/Shanghai';

import { FeishuSheetWriter } from '../feishuSheetWriter';
import { fetchPurchaseOrders } from './fetchLingxing';
import { readOwners } from './readOwners';
import { generateTasks } from './generateTasks';
import { checkStatus, AlertItem } from './checkStatus';
import { fetchShipmentSkus } from './fetchShipments';
import { fetchLocalStockSkus } from './fetchLocalInventory';
import { notify } from './notify';
import { updateTasksAfterNotify } from './updateTasks';
import { loadPmcConfig } from './config';
import { Stage } from './stages';
import { logger } from './logger';
import { nowBJString } from './dateUtil';

export interface PipelineOptions {
  label: string;               // 'runSunday' | 'runWednesday' | 'runDaily'
  regenerate: boolean;         // 是否生成/更新台账
  stagesFilter?: Stage[];      // 只检查指定阶段（runDaily 用）
  withGroupSummary: boolean;   // 是否发群汇总
  maxOrders?: number;
}

/** 是否真实发送（cron 传 --send；手动跑默认 dry-run 预览） */
export function isSendMode(): boolean {
  return process.argv.includes('--send');
}

export async function runPipeline(opts: PipelineOptions): Promise<void> {
  const startedAt = Date.now();
  const doSend = isSendMode();
  const writer = new FeishuSheetWriter();

  logger.info('='.repeat(60));
  logger.info(`[${opts.label}] 启动 @ ${nowBJString()}，模式=${doSend ? '真实发送' : 'dry-run'}`);
  logger.info('='.repeat(60));

  // 1. 配置
  const config = loadPmcConfig(writer);

  // 2. 采购单
  let orders = [] as Awaited<ReturnType<typeof fetchPurchaseOrders>>;
  try {
    orders = await fetchPurchaseOrders(undefined, opts.maxOrders ?? 500);
  } catch (e) {
    logger.error(`[${opts.label}] 拉取采购单失败，终止本次运行`, e);
    return;
  }
  if (orders.length === 0) {
    logger.warn(`[${opts.label}] 未拉取到采购单，结束`);
    return;
  }

  // 3. 负责人映射
  const ownerMap = await readOwners();

  // 4. 生成/更新台账（仅 Sunday/Wednesday）
  if (opts.regenerate) {
    try {
      if (doSend) {
        generateTasks(orders, ownerMap);
      } else {
        logger.info(`[${opts.label}] dry-run：跳过 generateTasks 写台账`);
      }
    } catch (e) {
      logger.error(`[${opts.label}] generateTasks 异常（不中断）`, e);
    }
  }

  // 5a. 拉取近N天有发货动作的SKU（Phase 7a：用于"到仓未发货"判断，失败则降级为空集合）
  let shippedSkus = new Set<string>();
  try {
    const sh = await fetchShipmentSkus();
    shippedSkus = sh.skus;
  } catch (e) {
    logger.error(`[${opts.label}] fetchShipmentSkus 异常，到仓未发货判断降级（不中断）`, e);
  }

  // 5a2. 拉取本地仓有库存的SKU（Phase 7a：库存≤0视为已发走；拉取失败返回null降级不过滤）
  let localStockSkus: Set<string> | null = null;
  try {
    const inv = await fetchLocalStockSkus();
    localStockSkus = inv.inStockSkus;
  } catch (e) {
    logger.error(`[${opts.label}] fetchLocalStockSkus 异常，库存过滤降级（不中断）`, e);
  }

  // 5b. 检查状态
  let alerts: AlertItem[] = [];
  try {
    alerts = checkStatus(orders, config, ownerMap, opts.stagesFilter, shippedSkus, localStockSkus);
  } catch (e) {
    logger.error(`[${opts.label}] checkStatus 异常，终止`, e);
    return;
  }

  // 6. 发送提醒
  let sentStages = new Map<string, boolean>();
  try {
    const result = await notify(alerts, config, doSend, opts.withGroupSummary);
    sentStages = result.sentStages;
    logger.info(`[${opts.label}] 提醒发送：共${result.totalAlerts}条，成功${result.sentGroups}组，失败${result.failedGroups}组`);
  } catch (e) {
    logger.error(`[${opts.label}] notify 异常（不中断）`, e);
  }

  // 7. 写回台账（仅真实发送）
  if (doSend && alerts.length > 0) {
    try {
      updateTasksAfterNotify(alerts, sentStages);
    } catch (e) {
      logger.error(`[${opts.label}] updateTasks 异常（不中断）`, e);
    }
  } else if (!doSend) {
    logger.info(`[${opts.label}] dry-run：跳过 updateTasks 写台账`);
  }

  const elapsed = ((Date.now() - startedAt) / 1000).toFixed(1);
  logger.info(`[${opts.label}] 完成，耗时 ${elapsed}s`);
}
