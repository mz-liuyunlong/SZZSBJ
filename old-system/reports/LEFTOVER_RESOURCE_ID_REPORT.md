# 遗留资源 ID 检查报告

- 检查范围：`old_final/source/` 全部可读文本文件。
- 本轮命中文件：10 个；全部已脱敏。
- 脱敏后仍命中的硬编码资源标识：0 处。
- 本报告不记录真实值。

| 命中文件路径 | 字段名或类型 | 是否已脱敏 |
|---|---|---|
| `source/context/DATABASE_MAP.md` | Sheet ID | 是 |
| `source/context/SYSTEM_MAP.md` | Sheet ID | 是 |
| `source/context/TASK_CHANGE_LOG.md` | Sheet ID | 是 |
| `source/docs/feishu_item_owner_sync.md` | Sheet ID | 是 |
| `source/docs/internal_api_readonly.md` | Sheet ID | 是 |
| `source/legacy_feishu_20260723/syncNoMovingProducts.ts` | Sheet ID | 是 |
| `source/src/ai_pmc/replenishConfig.ts` | Sheet ID | 是 |
| `source/src/notifyRules/autoAdImportCheck.test.ts` | openId / ou_ 标识 | 是 |
| `source/src/performanceSummaryReport.ts` | Sheet ID | 是 |
| `source/src/testLingxingToFeishu.ts` | Sheet ID | 是 |

## 指定文件复核

| 文件 | 结果 |
|---|---|
| `source/context/SYSTEM_MAP.md` | 已复核；命中内容已脱敏 |
| `source/context/DATABASE_MAP.md` | 已复核；命中内容已脱敏 |
| `source/docs/internal_api_readonly.md` | 已复核；命中内容已脱敏 |
| `source/docs/feishu_item_owner_sync.md` | 已复核；命中内容已脱敏 |
| `source/legacy_feishu_20260723/syncNoMovingProducts.ts` | 已复核；命中内容已脱敏 |
| `source/src/ai_pmc/replenishConfig.ts` | 已复核；命中内容已脱敏 |
| `source/src/ai_pmc/initReplenishConfig.ts` | 已复核 |
| `source/src/testLingxingToFeishu.ts` | 已复核；命中内容已脱敏 |

> 禁止输出或恢复任何真实资源标识值。
