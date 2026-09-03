# 最终脱敏报告

- 本轮仅修改 `old_final/source/` 和最终报告；输入目录保持只读。
- 本轮新增脱敏：10 个文件，20 处。
- 公开的飞书 OpenAPI 地址不是内部资源标识，予以保留。
- 报告仅记录路径、类型和数量；不记录任何原始值。

| 文件路径 | 新增脱敏类型 | 处数 |
|---|---|---:|
| `source/context/DATABASE_MAP.md` | Sheet ID | 4 |
| `source/context/SYSTEM_MAP.md` | Sheet ID | 5 |
| `source/context/TASK_CHANGE_LOG.md` | Sheet ID | 2 |
| `source/docs/feishu_item_owner_sync.md` | Sheet ID | 2 |
| `source/docs/internal_api_readonly.md` | Sheet ID | 2 |
| `source/legacy_feishu_20260723/syncNoMovingProducts.ts` | Sheet ID | 1 |
| `source/src/ai_pmc/replenishConfig.ts` | Sheet ID | 1 |
| `source/src/notifyRules/autoAdImportCheck.test.ts` | openId / ou_ 标识 | 1 |
| `source/src/performanceSummaryReport.ts` | Sheet ID | 1 |
| `source/src/testLingxingToFeishu.ts` | Sheet ID | 1 |

> 禁止输出或恢复任何真实资源标识值。
