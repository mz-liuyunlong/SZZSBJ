/**
 * src/ai_pmc/initLedgerHeader.ts
 * 一次性脚本：把 PMC任务台账(0HadpM) 改成新 9 列结构（唯一键=本地SKU）
 *
 *   预览：       npx ts-node src/ai_pmc/initLedgerHeader.ts
 *   真实写入：   npx ts-node src/ai_pmc/initLedgerHeader.ts --send
 *   连旧数据一起清：npx ts-node src/ai_pmc/initLedgerHeader.ts --send --clear
 *
 * 新列：A=SKU(唯一键) B=店铺 C=品名 D=全链路阶段 E=主负责人
 *      F=AI系统建议 G=人工处理备注(系统不覆盖) H=任务进展明细(系统追加) I=最近更新
 *
 * 注意：
 *  - 第 1 行是合并标题横幅，写入"部分合并区"会被飞书拒绝 → 标题单独按整行 A1:L1 写、失败也不影响。
 *  - 表头只写第 2 行 A2:I2；旧第 10/11 列(J/K)表头与数据用 clearRange 清掉。
 *  - clearRange 无 5000 单元格限制；写入超行时 writer 会自动加行。
 */

process.env.TZ = 'Asia/Shanghai';

import { FeishuSheetWriter } from '../feishuSheetWriter';
import { logger } from './logger';

const TOKEN = '<REDACTED_FEISHU_SPREADSHEET_TOKEN>';
const SHEET_ID = '<REDACTED_FEISHU_SHEET_ID>';
const SHEET_NAME = 'PMC任务台账';

const TITLE = 'PMC任务台账（全链路）｜唯一键=ItemID（保留本地SKU列）｜阶段：补货建议→采购计划→采购下单→采购到货→到仓发货→海外到仓｜H列人工备注系统不覆盖（标"不采纳"可关闭补货建议）';
const HEADER = ['ItemID', 'SKU', '店铺', '品名', '全链路阶段', '主负责人', 'AI系统建议', '人工处理备注（系统不覆盖）', '任务进展明细（系统追加）', '最近更新'];

const CLEAR_TO_ROW = 2000;
const doSend = process.argv.includes('--send');
const doClear = process.argv.includes('--clear');

(async () => {
  const writer = new FeishuSheetWriter();
  logger.info(`[initLedgerHeader] 模式=${doSend ? '真实写入' : 'dry-run'}${doClear ? ' +清空旧数据' : ''}`);

  if (!doSend) {
    logger.info('[initLedgerHeader] dry-run，新表头预览：\n' + HEADER.join(' | '));
    if (doClear) logger.info(`[initLedgerHeader] 将清空 A3:L${CLEAR_TO_ROW}（含旧 J/K/L 列）`);
    return;
  }

  // 1. 表头写第 1 行（A1:J1，10列；横幅已删，表头即第1行）
  writer.writeCells({
    spreadsheetToken: TOKEN, sheetId: SHEET_ID, sheetName: SHEET_NAME,
    range: 'A1:J1', rows: [HEADER],
    dryRun: false, confirmWrite: true, allowOverwrite: true,
  });
  logger.info('[initLedgerHeader] 第1行表头已写入（A=ItemID, B=SKU, G=AI系统建议）');
  logger.info('[initLedgerHeader] 表头着色请用 scripts/fix-ledger-format.sh');

  // 2. 可选：清空旧数据（A3 起；clearRange 无 5000 格限制）
  if (doClear) {
    try {
      writer.clearRange({ spreadsheetToken: TOKEN, sheetId: SHEET_ID, sheetName: SHEET_NAME,
        range: `A3:J${CLEAR_TO_ROW}`, dryRun: false, confirmWrite: true });
      logger.info(`[initLedgerHeader] 已清空旧数据 A3:J${CLEAR_TO_ROW}`);
    } catch (e) { logger.error('[initLedgerHeader] 清空旧数据失败', e); }
  }
  logger.info('[initLedgerHeader] 完成');
})().catch((e) => { logger.error('[initLedgerHeader] 致命错误', e); process.exitCode = 1; });
