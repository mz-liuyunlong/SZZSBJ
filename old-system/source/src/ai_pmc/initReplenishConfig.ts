/**
 * src/ai_pmc/initReplenishConfig.ts
 * Phase 8 — 一键把补货规则默认配置写入飞书 FyeDgo（补货规则配置）
 *
 * 表：补货规则配置 (spreadsheetToken="<REDACTED_FEISHU_SPREADSHEET_TOKEN>", sheetId=FyeDgo)
 * 布局：A=字段名, B=值, C=说明（带表头）。runReplenishment 会读 A/B 两列。
 *
 * 运行：
 *   预览（不写）：  npx ts-node src/ai_pmc/initReplenishConfig.ts --dry
 *   实际写入：      npx ts-node src/ai_pmc/initReplenishConfig.ts
 */

process.env.TZ = 'Asia/Shanghai';

import { FeishuSheetWriter } from '../feishuSheetWriter';
import { PMC_SPREADSHEET_TOKEN } from './config';
import { REPLENISH_SHEET_ID } from './replenishConfig';
import { logger, errMsg } from './logger';

const SHEET_NAME = '补货规则配置';

// 字段名, 值, 说明
const ROWS: string[][] = [
  ['字段名', '值', '说明'],
  ['sales_days_short', '15', '短期销量天数'],
  ['sales_days_long', '30', '长期销量天数'],
  ['sales_method', 'MAX', '取15/30天较大值'],
  ['safety_days', '50', '安全库存天数'],
  ['q4_months', '10,11,12', 'Q4旺季月份'],
  ['q4_multiplier', '2.0', 'Q4销量倍数'],
  ['yoy_days', '30', '同比天数'],
  ['include_domestic', 'TRUE', '算国内仓库存'],
  ['include_purchase_pending', 'TRUE', '算采购未到货'],
  ['include_in_transit', 'FALSE', 'FBA在途不做，置否'],
  ['include_overseas', 'TRUE', '算WFS海外在库'],
  ['min_suggest_qty', '50', '最小触发补货量（阈值）'],
  ['min_order_qty', '100', '单次补货量下限(pcs)'],
  ['ai_evaluate', '启用', '是否启用AI评估'],
  ['ai_batch_size', '20', '每批AI评估数量'],
  ['ai_timeout_ms', '30000', 'AI单次调用超时(ms)'],
  ['notify_day', '周日', '提醒日'],
  ['is_active', '启用', '总开关（停用则跳过整个补货模块）'],
];

function main(): void {
  const dryRun = process.argv.includes('--dry');
  const writer = new FeishuSheetWriter();
  const endRow = ROWS.length; // 含表头
  const range = `A1:C${endRow}`;

  logger.info(`[initReplenishConfig] 目标 FyeDgo(${REPLENISH_SHEET_ID}) ${range}，模式=${dryRun ? 'dry-run' : '实际写入'}`);
  console.log('将写入内容：');
  for (const r of ROWS) console.log('  ' + r.join(' | '));

  try {
    writer.writeCells({
      spreadsheetToken: PMC_SPREADSHEET_TOKEN,
      sheetId: REPLENISH_SHEET_ID,
      sheetName: SHEET_NAME,
      range,
      rows: ROWS,
      dryRun,
      confirmWrite: !dryRun,
      allowOverwrite: true,
    });
    logger.info(`[initReplenishConfig] ${dryRun ? 'dry-run 预览完成（未写入）' : '写入完成'}`);
  } catch (e) {
    logger.error('[initReplenishConfig] 写入失败', e);
    process.exitCode = 1;
  }
}

if (require.main === module) {
  try { main(); } catch (e) { logger.error('[initReplenishConfig] 致命错误', e); process.exitCode = 1; void errMsg; }
}
