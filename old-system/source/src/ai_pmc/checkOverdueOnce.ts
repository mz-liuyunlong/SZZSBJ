/**
 * src/ai_pmc/checkOverdueOnce.ts
 * 补货建议逾期检查 —— 独立入口（不影响 cron）
 *   预览： npx ts-node src/ai_pmc/checkOverdueOnce.ts
 *   真发： npx ts-node src/ai_pmc/checkOverdueOnce.ts --send
 */
process.env.TZ = 'Asia/Shanghai';

import { checkReplenishOverdue } from './checkReplenishOverdue';
import { logger } from './logger';

checkReplenishOverdue(process.argv.includes('--send'))
  .then(() => logger.info('[checkOverdueOnce] 结束'))
  .catch((e) => { logger.error('[checkOverdueOnce] 致命错误', e); process.exitCode = 1; });
