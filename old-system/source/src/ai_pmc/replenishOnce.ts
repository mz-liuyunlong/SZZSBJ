/**
 * src/ai_pmc/replenishOnce.ts
 * Phase 8 — 补货模块独立入口（手动单独触发）
 *
 * 运行：
 *   dry-run 预览：  npx ts-node src/ai_pmc/replenishOnce.ts
 *   真实发送：      npx ts-node src/ai_pmc/replenishOnce.ts --send
 */

process.env.TZ = 'Asia/Shanghai';

import { runReplenishment } from './runReplenishment';
import { isSendMode } from './pipeline';
import { logger } from './logger';

runReplenishment(isSendMode()).catch((e) => {
  logger.error('[replenishOnce] 致命错误', e);
  process.exitCode = 1;
});
