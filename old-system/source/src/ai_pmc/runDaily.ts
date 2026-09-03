/**
 * src/ai_pmc/runDaily.ts
 * Phase 6 — 每日 09:00 入口（到仓/发货按天提醒）P0-3
 * Phase 7B — 末尾追加 WFS 发货流程细分提醒
 *
 * 只处理「到仓待发货 / 到仓逾期 / 发货升级」+「WFS 发货流程超时」。不重复生成台账。
 *
 * 运行：
 *   dry-run 预览：  npx ts-node src/ai_pmc/runDaily.ts
 *   真实发送：      npx ts-node src/ai_pmc/runDaily.ts --send
 */

process.env.TZ = 'Asia/Shanghai';

import { FeishuSheetWriter } from '../feishuSheetWriter';
import { runPipeline, isSendMode } from './pipeline';
import { loadPmcConfig } from './config';
import { fetchWfsShipmentItems } from './fetchShipmentStatus';
import { checkShipmentFlow } from './checkShipmentFlow';
import { notifyShipment } from './notifyShipment';
import { Stage } from './stages';
import { logger } from './logger';

(async () => {
  // Phase 6：到仓发货主链路
  await runPipeline({
    label: 'runDaily',
    regenerate: false,
    stagesFilter: [Stage.ARRIVED_PENDING_SHIP, Stage.OVERDUE_SHIP, Stage.ESCALATE_SHIP],
    withGroupSummary: false,
  });

  // Phase 7B：WFS 发货流程细分提醒（单步异常不影响主流程）
  try {
    const doSend = isSendMode();
    const config = loadPmcConfig(new FeishuSheetWriter());
    const items = await fetchWfsShipmentItems();
    const alerts = checkShipmentFlow(items, config);
    const r = await notifyShipment(alerts, config, doSend);
    logger.info(`[runDaily] 7B发货流程提醒：共${r.total}条，成功${r.sentGroups}组，失败${r.failedGroups}组`);
  } catch (e) {
    logger.error('[runDaily] 7B 异常，已跳过（不影响主流程）', e);
  }
})().catch((e) => {
  logger.error('[runDaily] 致命错误', e);
  process.exitCode = 1;
});
