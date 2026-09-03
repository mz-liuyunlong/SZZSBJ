# 硬编码资源 ID 报告

仅记录文件路径、字段名和占位符类型；禁止输出或恢复真实值。

| 文件路径 | 字段名 | 风险等级 | 是否已脱敏 | 次数 |
|---|---|---|---|---:|
| `AI经营分析报告/generate_weekly_report_manual.py` | `SPREADSHEET_TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 1 |
| `AI经营分析报告/generate_weekly_report_manual.py` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 2 |
| `AI经营分析报告/正式系统/aiBusinessRoutes.ts` | `SPREADSHEET_TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 1 |
| `AI经营分析报告/正式系统/交付件/FeishuRawSalesData.tsx` | `sheetId` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 5 |
| `AI经营分析报告/正式系统/交付件/aiBusinessRoutes.ts` | `SPREADSHEET_TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 1 |
| `AI经营分析报告/正式系统/交付件/generate_weekly_report.py` | `SPREADSHEET_TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 1 |
| `AI经营分析报告/正式系统/交付件/generate_weekly_report.py` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 2 |
| `admin-frontend/src/FeishuRawSalesData.tsx` | `sheetId` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 7 |
| `config/currentReportFieldMapping.json` | `sheetId` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 3 |
| `config/currentReportFieldMapping.json` | `spreadsheetToken` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 2 |
| `context/DATABASE_MAP.md` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 6 |
| `context/PIPELINE_MAP.md` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 9 |
| `context/PROJECT_CONTEXT.md` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 1 |
| `context/SYSTEM_MAP.md` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 1 |
| `context/TASK_CHANGE_LOG.md` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 3 |
| `docs/feishu_item_owner_sync.md` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 1 |
| `docs/internal_api_readonly.md` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 2 |
| `scripts/check-sheet-headers.js` | `SPREADSHEET_TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 1 |
| `scripts/generate_monthly_report.py` | `SPREADSHEET_TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 1 |
| `scripts/generate_monthly_report.py` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 1 |
| `scripts/refresh-owner-openids.sh` | `SHEET_ID` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 2 |
| `scripts/refresh-owner-openids.sh` | `SHEET_TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 2 |
| `scripts/verify_report_and_noorder_migration.sh` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 1 |
| `src/aiBusinessRoutes.ts` | `SPREADSHEET_TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 1 |
| `src/ai_pmc/initLedgerHeader.ts` | `SHEET_ID` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 1 |
| `src/ai_pmc/initLedgerHeader.ts` | `TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 1 |
| `src/feishuRawSalesRoutes.ts` | `SPREADSHEET_TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 1 |
| `src/feishuRawSalesRoutes.ts` | `sheetId` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 7 |
| `src/lowProfitNotify.ts` | `SPREADSHEET_TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 1 |
| `src/lowProfitNotify.ts` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 1 |
| `src/performanceSummaryReport.ts` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 3 |
| `src/sentinelCore.ts` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 2 |
| `src/syncLingxingToRawFeishu.ts` | `SPREADSHEET_TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 1 |
| `src/syncLingxingToRawFeishu.ts` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 2 |
| `src/syncOrderProfitDaily.ts` | `SHEET_ID` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 1 |
| `src/syncOrderProfitDaily.ts` | `SPREADSHEET_TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 1 |
| `src/syncOrderProfitDaily.ts` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 2 |
| `src/testLingxingToFeishu.ts` | `SPREADSHEET_TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 1 |
| `产品管理TabV1_实施计划.md` | `sheetId` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 2 |
| `月报系统/交付件/generate_monthly_report.py` | `SPREADSHEET_TOKEN` / `<REDACTED_FEISHU_SPREADSHEET_TOKEN>` | 高 | 是 | 1 |
| `月报系统/交付件/generate_monthly_report.py` | `sheet_id` / `<REDACTED_FEISHU_SHEET_ID>` | 高 | 是 | 1 |

命中文件数：29；脱敏出现次数：86。
