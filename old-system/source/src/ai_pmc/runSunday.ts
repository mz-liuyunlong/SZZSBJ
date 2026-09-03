/**
 * src/ai_pmc/runSunday.ts
 * Phase 6 — 周日 18:00 入口（全链路）
 * Phase 8 — 末尾追加补货模块（含 AI 评估）
 *
 * 生成/更新任务台账 + 检查所有阶段 + 发个人提醒 + 群周报；之后跑补货模块。
 *
 * 运行：
 *   dry-run 预览：  npx ts-node src/ai_pmc/runSunday.ts
 *   真实发送：      npx ts-node src/ai_pmc/runSunday.ts --send
 */

process.env.TZ = 'Asia/Shanghai';

import { runPipeline, isSendMode } from './pipeline';
import { runReplenishment } from './runReplenishment';
import { buildLedger } from './buildLedger';
import { logger } from './logger';

(async () => {
  // Phase 6：采购到货前 + 到仓发货主链路 + 群周报
  await runPipeline({
    label: 'runSunday',
    regenerate: true,
    withGroupSummary: true,
  });

  // Phase 8：补货模块（单步异常不影响主流程）
  try {
    await runReplenishment(isSendMode());
  } catch (e) {
    logger.error('[runSunday] 补货模块异常，已跳过（不影响主流程）', e);
  }

  // Phase 9：全链路台账构建（一个 SKU 一行，单步异常不影响主流程）
  try {
    await buildLedger(isSendMode());
  } catch (e) {
    logger.error('[runSunday] 全链路台账构建异常，已跳过（不影响主流程）', e);
  }
})().catch((e) => {
  logger.error('[runSunday] 致命错误', e);
  process.exitCode = 1;
});
