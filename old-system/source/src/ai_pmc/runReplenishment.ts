/**
 * src/ai_pmc/runReplenishment.ts
 * Phase 8 — 补货模块编排（供 runSunday 末尾调用）
 *
 * 流程：读配置 → 拉销量+库存 → 计算需补货 → 分批AI评估 → 按运营负责人发提醒。
 * 任何单步/单条失败只记日志、不中断（异常处理规范）。
 */

process.env.TZ = 'Asia/Shanghai';

import { FeishuSheetWriter } from '../feishuSheetWriter';
import { loadPmcConfig } from './config';
import { loadReplenishConfig } from './replenishConfig';
import { fetchSales } from './fetchSales';
import { fetchInventory } from './fetchInventory';
import { calcReplenishment, chunk, ReplenishTask, AiEvalResult } from './calcReplenishment';
import { aiEvaluate } from './aiEvaluate';
import { notifyReplenishment } from './notifyReplenishment';
import { logger } from './logger';

function disabledFallback(t: ReplenishTask): AiEvalResult {
  return {
    priority: '中',
    adjustedSuggestQty: t.suggestQty,
    reason: '未启用AI评估',
    analysis: `系统计算：日均${t.adjustedAvg}件，当前库存${t.totalInventory}件，建议补货${t.suggestQty}件`,
    aiSuccess: false,
  };
}

export async function runReplenishment(doSend: boolean): Promise<void> {
  const startedAt = Date.now();
  const writer = new FeishuSheetWriter();
  const config = loadPmcConfig(writer);
  const rcfg = loadReplenishConfig(writer);

  if (rcfg.isActive !== '启用') {
    logger.info('[runReplenishment] 补货模块已停用（is_active≠启用），跳过');
    return;
  }

  // 拉销量（直接调领星 saleStat）+ 库存
  const sales = await fetchSales(rcfg.salesDaysShort, rcfg.salesDaysLong, rcfg.yoyDays);
  const inventory = await fetchInventory(writer);

  // 计算需补货
  const tasks = calcReplenishment(sales, inventory, rcfg);
  logger.info(`[runReplenishment] 需补货 ${tasks.length} 个 SKU，开始分批AI评估（每批${rcfg.aiBatchSize}）`);

  if (tasks.length === 0) {
    logger.info('[runReplenishment] 无需补货，结束');
    return;
  }

  // 分批 AI 评估：每批内并发（aiEvaluate 自带失败兜底，并发安全），避免串行过慢
  const batches = chunk(tasks, rcfg.aiBatchSize);
  for (let b = 0; b < batches.length; b++) {
    const batch = batches[b];
    logger.info(`[runReplenishment] AI评估第${b + 1}/${batches.length}批，共${batch.length}条（并发）`);
    if (rcfg.aiEvaluate === '启用') {
      await Promise.all(batch.map(async (t) => { t.aiResult = await aiEvaluate(t, rcfg.aiTimeoutMs); }));
    } else {
      for (const t of batch) t.aiResult = disabledFallback(t);
    }
  }

  // 单次补货量下限：AI 调整量也不低于 min_order_qty
  for (const t of tasks) {
    if (t.aiResult && t.aiResult.adjustedSuggestQty < rcfg.minOrderQty) {
      t.aiResult.adjustedSuggestQty = rcfg.minOrderQty;
    }
  }

  const aiOk = tasks.filter((t) => t.aiResult?.aiSuccess).length;
  logger.info(`[runReplenishment] AI评估完成，成功${aiOk}/${tasks.length}（其余用系统计算兜底）`);

  // 逐条明细（便于核对：数量应≥min_order_qty，负责人正确）
  for (const t of tasks) {
    const aiQ = t.aiResult ? t.aiResult.adjustedSuggestQty : t.suggestQty;
    logger.info(`[补货明细] SKU:${t.sku} ${t.itemId} ${t.productName} | 日均${t.adjustedAvg} 库存${t.totalInventory}(国内${t.domestic}/采购${t.purchasePending}/WFS${t.overseas}) | 系统建议${t.suggestQty} AI${aiQ} | ${t.ownerName}`);
  }

  // 发通知
  const r = await notifyReplenishment(tasks, config, doSend);
  const elapsed = ((Date.now() - startedAt) / 1000).toFixed(1);
  logger.info(`[runReplenishment] 完成：补货${r.total}条，成功${r.sentGroups}组，失败${r.failedGroups}组，耗时${elapsed}s`);
}
