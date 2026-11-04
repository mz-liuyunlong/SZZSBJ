# PMC 设置 · WFS 设置 API（S2 / S3）

日期：2026-11-03。PRP：`PRPs/pmc-wfs-settings.md`（#303 已批准）；决策：`docs/data-sources/decisions/pmc-wfs-settings-decision.md`。
前缀 `/api/pmc/wfs/settings`。数据只来自新系统 PostgreSQL，不调用领星、不写入 Walmart，没有 Celery 任务。

## 权限

| 能力 | permissionKey |
|---|---|
| 所有 GET | `page:pmc:wfs:view` + 来源账号数据范围（`require_source_account_scope`） |
| 所有写（POST / PUT） | `action:pmc:wfs-settings:manage`；本地 5173 预览账号没有此键，前端写按钮保持灰色（navigation `readOnly: true`） |

## 返回格式

统一 `SuccessEnvelope`：`{ data, meta, request_id }`。`meta` 固定含 `source = "new_system_postgresql"`、`source_tables`（`ref_wfs_rule_setting_versions`、`ref_wfs_rule_settings`、`ref_wfs_fc_regions`、`ref_wfs_creation_defaults`、`evt_wfs_settings_changes`）；分页接口另含 `page`、`page_size`、`total`。

## 分页、搜索、排序（docs/SEARCH_FILTER_SORT_RULES.md）

- 分页：`page`（≥1，默认 1）、`page_size`（默认 50，最大 1000；修改记录最大 200）。超出范围返回 422。
- 搜索：`keyword`（≤100 字）+ `search_field`（各接口白名单，默认 `all`）。
- 排序：`sort_by` 只接受白名单字段，`sort_order` 为 `asc` / `desc`；白名单外返回 422。同值时按稳定次键排序。
- 下拉选项（地区、州、物流商、运输方式）随列表一起返回，来自整个数据集而不是当前页。

## 端点

### 规则（异常与提醒规则）

- `GET /rules/rows` — 生效版本的规则行，服务端分页（页面列表用）
  - 查询：`at`（日期，取那天生效的版本，默认今天）、`page`、`page_size`、`keyword`、`search_field` = `all|node|remark|notify`、`region`、`decided`（true = 已确认，false = 示例 · 待定）、`category` = `shipping|transit|receiving|dispute|other`（创建与发货 / 物流在途 / 收货与上架 / 申诉 / 其他，按 rule_key 归类）、`sort_by` = `row_no|node|days|row_effective_date`（默认 `row_no`）、`sort_order`
  - 返回：`{ version, items: (RuleRow + category)[], total, total_rows, sample_rows, regions, category_counts }`；`total_rows`、`sample_rows`、`category_counts` 按整个版本统计（供统计卡和分类按钮），`total` 是当前筛选后的条数
- `GET /rules` — 生效版本的整张规则表（编辑抽屉用；保存仍是整版本）。查询：`at`
- `GET /rules/versions` — 规则版本历史
- `POST /rules/versions` — 保存新版本，201
  - 请求：`{ effective_date, reason(2–500 字), rows: RuleRow[1..100] }`；生效日不得早于今天

`RuleRow`：`rule_key, node, region, carrier, channel, days(0–365), remind_days(0–365), row_effective_date, notify, remark, decided`

### 仓库地区

- `GET /fc-regions` — 看板上出现过的 Walmart 仓库（FC）
  - 查询：`page`、`page_size`、`keyword`、`search_field` = `all|fc|zip|address`、`region`（美西 / 美中 / 美东 / 待定）、`state`、`sort_by` = `fc|zip|state|shipments`（默认 `fc`）、`sort_order`
  - 返回：`{ items, total, states }`；`items[]`：`fc, zip, city, state, address(地址全称), region, region_source(saved|state), shipments, updated_by, updated_at`。页面不显示仓库名称
- `PUT /fc-regions/{fc}` — 改地区。请求：`{ region, reason }`

### 创建货件默认值

- `GET /creation-defaults?source_account_ref=` — 本账号未保存时返回 8088 默认值（`saved = false`）
- `PUT /creation-defaults` — 请求：`{ source_account_ref?, transport, ship_date_offset(0–120), pallet_boxes(1–100), mixed_boxes(0–1000), carrier_opt, reason }`

### 物流渠道字典

- `GET /logistics-channels` — 只读，来自已导入的领星渠道文件
  - 查询：`page`、`page_size`、`keyword`、`search_field` = `all|channel_id|channel_name|provider`、`provider`、`method`、`enabled`、`sort_by` = `provider_name|channel_id|channel_name`（默认 `provider_name`）、`sort_order`
  - 返回：`{ items, loaded, total, providers, methods }`；`items[]`：`provider_id`（物流商编号，领星）、`provider_name`、`channel_id`（渠道编号，领星）、`channel_name`、`method_name`、`enabled`。没有导入文件时 `loaded = false`、`items = []`

### 修改记录

- `GET /changes` — 查询：`entity` = `rules|fc_region|creation_defaults`、`page`、`page_size(≤200)`。返回 `{ items, total }`

## 错误码

| HTTP | code | 场景 |
|---|---|---|
| 401 | — | 未登录 |
| 403 | `FORBIDDEN` / `DATA_SCOPE_DENIED` | 缺权限，或来源账号不在数据范围 |
| 404 | `NOT_FOUND` | 看板上没有这个 FC |
| 422 | 校验失败 / `WFS_SETTINGS_EFFECTIVE_DATE_PAST` / `WFS_SETTINGS_ACCOUNT_REQUIRED` | 参数越界、排序字段不在白名单、生效日早于今天、多账号时没指定账号 |
| 503 | `WFS_SETTINGS_NOT_READY` | 设置表还没迁移（迁移 0077） |

## 日志与留痕

每次写入都在 `evt_wfs_settings_changes` 记录操作人、原因、修改前后值；规则只新增版本，不覆盖旧版本。

## 变更记录

- 2026-11-04 fix4：`GET /rules/rows` 增加 `category` 筛选，返回 `total_rows`、`category_counts` 和每行 `category`；页面改为「业务配置中心」框架（WFS 异常与提醒：提醒规则 / 通知与口径说明 / 版本与修改记录）。
- 2026-11-03 fix3：`GET /rules/rows` 新增；`/fc-regions`、`/logistics-channels` 改为服务端分页、搜索、筛选、白名单排序，返回下拉选项；前端页面移到「PMC 设置」分组（`/pmc/settings/...`），旧路径重定向。
- 2026-11-03 fix2：仓库地区增加邮编、地址全称；物流渠道返回领星物流商编号、渠道编号。
- 2026-11-03 S2 / S3：首版。
