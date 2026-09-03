/**
 * src/ai_pmc/runWednesday.ts
 * Phase 6 — 周三 16:00 入口（复查）
 *
 * 刷新台账 + 复查审批→下单→到货→发货各阶段，对未处理/逾期继续提醒，
 * 逾期超阈值的升级 @ 江梓博（升级逻辑在 checkStatus 内）。
 * 防重复（近30天通知日志）保证「未处理」任务按间隔再提醒，不重复轰炸。
 *
 * 运行：
 *   dry-run 预览：  npx ts-node src/ai_pmc/runWednesday.ts
 *   真实发送：      npx ts-node src/ai_pmc/runWednesday.ts --send
 */

process.env.TZ = 'Asia/Shanghai';

import { runPipeline, isSendMode } from './pipeline';
import { buildLedger } from './buildLedger';
import { checkReplenishOverdue } from './checkReplenishOverdue';
import { logger } from './logger';

(async () => {
  // Phase 6：采购/到货/发货复查 + 升级
  await runPipeline({
    label: 'runWednesday',
    regenerate: true,
    withGroupSummary: false,
  });

  // Phase 9：先刷新全链路台账（采纳的会自动推进走，剩下的才是真未处理）
  try {
    await buildLedger(isSendMode());
  } catch (e) {
    logger.error('[runWednesday] 全链路台账刷新异常，已跳过（不影响主流程）', e);
  }

  // 补货建议超3天未处理 → 强升级提醒 + @江梓博
  try {
    await checkReplenishOverdue(isSendMode());
  } catch (e) {
    logger.error('[runWednesday] 补货建议逾期检查异常，已跳过（不影响主流程）', e);
  }
})().catch((e) => {
  logger.error('[runWednesday] 致命错误', e);
  process.exitCode = 1;
});
