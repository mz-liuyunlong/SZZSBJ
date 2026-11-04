# PMC 总看板 API（只读）

前缀 `/api/pmc/overview`。全部为 GET，统一信封（`success / data / error / meta / request_id`），权限 `pmc:overview:read`，并要求可信来源账号范围（为空时 403 `DATA_SCOPE_DENIED`）。5173 过渡数据源为一份 8088 数据日快照（环境变量 `PMC_OVERVIEW_SNAPSHOT_FILE`，仅 local / dev / test）；快照缺失或损坏时 503 `PMC_OVERVIEW_NOT_READY`，不返回示例数据。`meta` 含 `source`、`source_objects`、`data_date`、`rule_version`、`draft_mode`，列表另含 `page`、`page_size`、`total`。

| 方法与路径 | operation_id | 说明 |
|---|---|---|
| `GET /summary` | `getPmcOverviewSummary` | 汇总卡片（全部 ItemID，不随筛选变化）、参数、未归属、海外仓合计 |
| `GET /items` | `listPmcOverviewItems` | ItemID 主表，服务端筛选 / 排序 / 分页 |
| `GET /items/{item_id}` | `getPmcOverviewItem` | ItemID 详情；不存在 404 |
| `GET /filter-options` | `getPmcOverviewFilterOptions` | 店铺、负责人、问题类型 |
| `GET /warehouses` | `getPmcOverviewWarehouses` | 仓库分布 |
| `GET /rules` | `getPmcOverviewRules` | 判断参数（只读） |
| `GET /export` | `getPmcOverviewExport` | Excel 数据（筛选参数同 `/items`，无分页） |

## `GET /items` 查询参数

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `store_id` | string ≤ 64 | — | 店铺 ID |
| `owner` | string ≤ 64 | — | 负责人 |
| `cats` | 可重复，问题类型枚举 | — | 多个时须全部满足 |
| `keyword` | string ≤ 100 | — | ItemID / SKU / MSKU / 品名 / 草稿号，包含匹配 |
| `only_issue` | bool | `true` | 只看有问题的 |
| `page` | int ≥ 1 | 1 | |
| `page_size` | int | 50 | 只允许 50 / 100 / 200 / 500 / 1000，其他值 422 |
| `sort_by` | 白名单 | — | `daily`、`wm_available`、`supply`、`cover`、`oos_days`、`n30`、`gap_days`；不传 = 按问题优先级；其他值 422 |
| `sort_order` | `asc` / `desc` | `desc` | 空值始终排在最后 |

返回 `data.items`（主表行）与 `data.category_counts`（每个问题类型的 ItemID 数，按除 `cats` 外的全部条件统计，供分类按钮显示）。

## 变更记录

- 2026-11-04：修复 `page_size` 校验（原为整数字面量，查询串 `"50"` 一律 422，导致页面主表无数据）；`page_size` 增加 1000；新增 `sort_by` / `sort_order` 白名单排序与 `category_counts`；页面按高密度报表样板（PageShell + ReportTableShell，同采购看板）重做。
