# PRP：DATA-PAGES-1 每日销售 / 订单利润 / Listing 管理真实数据闭环

状态：`READY_FOR_IMPLEMENTATION_DESIGN`

关联数据源决策：`docs/data-sources/decisions/data-pages-daily-sales-listing-order-profit-decision.md`

## 1. Goal

建设每日销售、订单利润、Listing 管理三个页面的真实数据闭环，替换当前 No-API / mock 数据状态。

最终完成状态：

```text
1. 7 个领星 Walmart 相关只读接口纳入 integration_sync 治理。
2. 原始响应进入现有 ODS/RAW 治理层。
3. 新增 DIM / FACT / MART 业务表。
4. 每日销售、订单利润、Listing 管理后端查询 API 可分页查询真实 MART。
5. 前端页面接入真实 API，保留既有页面交互与筛选体验。
6. 订单利润从每日销售 MART 聚合，不单独拉一套同步链路。
```

## 2. Why

当前三个页面仍是 mock / No-API 状态，不能支撑真实运营分析。DATA-PAGES-1 将完成 Walmart Listing、店铺、销售、订单、退款、广告费和成本的可追溯数据链路，为后续利润分析、Listing 管理、广告优化和运营复盘提供数据底座。

## 3. Scope

### In scope

- [ ] 新增 / 注册以下只读接口契约：
  - `/pb/mp/shop/v2/getSellerList`
  - `/basicOpen/multiplatform/walmart/list`
  - `/basicOpen/platformStatisticsV2/saleStat/pageList`
  - `/pb/mp/order/v2/list`
  - `/basicOpen/openapi/multiplatform/walmart/returnOrder/list`
  - `/basicOpen/adReport/advertiser/list`
  - `/basicOpen/multiplatform/ads/reportAdItemSpList`
- [ ] 复用现有 ODS：`ods_api_raw_blobs`、`ods_api_raw_request_refs`、`gov_parse_jobs`、`gov_data_lineage`。
- [ ] 新增业务层 DIM / FACT / MART / rule version 表。
- [ ] 实现 parser / repository / service / refresh 设计。
- [ ] 实现每日销售、订单利润、Listing 管理查询 API。
- [ ] 前端替换 mock 数据为真实 API client / hooks。
- [ ] 保留金额、币种、时区、来源、血缘、计算版本。
- [ ] 对 `REFUND`、送样订单、广告费分摊、成本缺失状态做明确处理。

### Out of scope

- [ ] 不做 AUTH-1 正式登录鉴权 / 权限体系。
- [ ] 不做 SYNC-1 同步任务真实执行闭环验收。
- [ ] 不做 WORKER-1 后台任务生产化。
- [ ] 不接入生产数据库。
- [ ] 不调用真实领星接口。
- [ ] 不修改 `old-system/**`。
- [ ] 不实现监控系统字段：购物车状态、是否被跟卖、沃尔玛卖家等。
- [ ] 不实现旧库字段：停用原因、GPT 分析、系统运营日志、运营日志。
- [ ] 不创建或修改平台 / ERP 状态。

## 4. Navigation / Page

```text
一级导航：销售
二级导航：每日销售、订单利润
页面路径：/sales/daily-sales、/sales/order-profit
页面状态：planned -> building

一级导航：产品
二级导航：Listing 管理
页面路径：/products/listing-management
页面状态：planned -> building
```

## 5. Permissions

AUTH-1 已排到最后，本 PRP 不实现正式权限体系。但后端 API 和前端字段必须预留权限 key。

```text
page permissionKey:
- sales.daily_sales.read
- sales.order_profit.read
- listing_management.read

action permissionKeys:
- sales.daily_sales.export
- sales.order_profit.export
- listing_management.export

data scope resource:
- source_account_ref
- store_id
- platform_code
- owner_ref

field permissions:
- sales.daily_sales.cost.read
- sales.daily_sales.profit.read
- sales.daily_sales.ad_spend.read
- sales.order_profit.cost.read
- sales.order_profit.profit.read
- listing_management.cost.read

high-risk actions:
- 无平台写入动作
- 无 ERP 写入动作
- 无生产数据库修改
```

## 6. Data Source

```text
data source decision file:
- docs/data-sources/decisions/data-pages-daily-sales-listing-order-profit-decision.md

decision status:
- READY_FOR_PRP

dataset classifications:
- 店铺：REBUILD_SYNC
- Walmart Listing：REBUILD_SYNC
- 销量统计：REBUILD_SYNC
- 订单明细：REBUILD_SYNC
- Walmart 退款/售后：REBUILD_SYNC
- Walmart 广告主：REBUILD_SYNC
- Walmart SP 广告商品报表：REBUILD_SYNC
- 产品成本：EXISTING_NEW_SYSTEM_DATA
- 店铺佣金：NEW_SYSTEM_OWNED_VERSIONED_RULE
- 汇率：NEW_SYSTEM_OWNED_VERSIONED_RULE

contains NEED_OWNER_DECISION:
- no

owner approval status:
- 用户已要求开始执行 DATA-PAGES-1

short-term strategy:
- 复用现有 ODS，新增 DIM/FACT/MART，前端查 MART

long-term strategy:
- 所有页面字段具备 source lineage、业务日期、币种和计算版本

legacy exit criteria:
- 每日销售 / 订单利润 / Listing 管理核心字段不再依赖 mock

old-system reference:
- no for first implementation slice

legacy MySQL readonly tables:
- none in first implementation slice

new PostgreSQL tables:
- dim_lingxing_stores
- dim_walmart_listings
- dim_walmart_advertisers
- fact_walmart_sales_item_daily
- fact_walmart_order_items
- fact_walmart_refund_items
- fact_walmart_ad_item_sp_daily
- mart_daily_sales_item_day
- mart_order_profit_sku_day
- mart_listing_management_current
- ref_store_commission_rule_versions

cache / mart tables:
- mart_daily_sales_item_day
- mart_order_profit_sku_day
- mart_listing_management_current

sensitive or critical domains:
- 财务 / 利润 / 库存 / 广告 / 退款 / 成本
```

## 7. API Contract

### 7.1 每日销售列表

```text
method: GET
path: /api/sales/daily-sales
request schema:
  - business_date_from
  - business_date_to
  - store_ids[]
  - platform_codes[]
  - owner_refs[]
  - search_field
  - keyword
  - page
  - page_size
  - sort_field
  - sort_order
response schema:
  - success
  - data.items[]
  - data.summary
  - data.page
  - data.page_size
  - data.total
error codes:
  - 400 invalid query
  - 401 unauthenticated placeholder
  - 403 permission denied placeholder
  - 422 validation error
  - 500 internal error
meta.source:
  - mart_daily_sales_item_day
meta.source_tables:
  - mart_daily_sales_item_day
  - fact_walmart_sales_item_daily
  - fact_walmart_order_items
  - fact_walmart_refund_items
  - fact_walmart_ad_item_sp_daily
  - dim_walmart_listings
  - dim_lingxing_stores
request_id: required
```

### 7.2 每日销售筛选项

```text
method: GET
path: /api/sales/daily-sales/options
response:
  - stores
  - owners
  - platforms
  - search_fields
  - date_presets
```

### 7.3 订单利润列表

```text
method: GET
path: /api/sales/order-profit
request schema:
  - business_date_from
  - business_date_to
  - store_ids[]
  - platform_codes[]
  - owner_refs[]
  - local_skus[]
  - item_ids[]
  - page
  - page_size
  - sort_field
  - sort_order
meta.source_tables:
  - mart_order_profit_sku_day
  - mart_daily_sales_item_day
```

### 7.4 Listing 管理列表

```text
method: GET
path: /api/listing-management/listings
request schema:
  - store_ids[]
  - owner_refs[]
  - product_status
  - listing_status
  - search_field
  - keyword
  - batch_values[]
  - page
  - page_size
  - sort_field
  - sort_order
meta.source_tables:
  - mart_listing_management_current
  - dim_walmart_listings
  - dim_lingxing_stores
```

### 7.5 Listing 管理筛选项

```text
method: GET
path: /api/listing-management/options
response:
  - stores
  - owners
  - product_statuses
  - listing_statuses
  - search_fields
```

## 8. UI Requirements

### 8.1 每日销售

```text
layout:
- 沿用当前页面 UI，不新增顶部栏字段
- 替换 mock 为 API 数据

table columns:
- 图片
- 分析
- 日期
- 店铺
- 负责人
- 前7天销量趋势
- 商品ID
- MSKU
- SKU
- 品名
- 平台
- 销量
- 订单量
- 销售额
- 剔除送样额
- 退货量
- 退款额
- 30天退货率
- 广告费
- 广告占比
- WFS配送费
- 店铺佣金
- 采购成本
- 头程成本
- 仓储费
- WFS可售
- 订单利润
- 利润率
- ROI
- 成本状态

filters:
- 日期范围
- 店铺
- 负责人
- 搜索字段 + 关键词

actions:
- 查询
- 重置
- 导出预留

states:
- loading
- empty
- error
- permission placeholder
```

### 8.2 订单利润

```text
layout:
- 沿用当前页面 UI
- 数据来自 mart_order_profit_sku_day

table columns:
- 日期
- SKU
- 商品ID集合
- 店铺数
- 销量
- 订单量
- 销售额
- 退款额
- 广告费
- 佣金
- WFS费用
- 采购成本
- 头程成本
- 仓储费
- 毛利润
- 毛利率
- ROI
- 成本状态
```

### 8.3 Listing 管理

```text
layout:
- 沿用当前页面 UI，不改变现有交互

table columns:
- 图片
- 商品ID
- MSKU
- 店铺
- 负责人
- SKU
- 商品名称
- 标题
- 产品等级
- 标签
- 在售价
- Listing 状态
- 生命周期
- 上架时间
- 类目
- WFS 可售
- 非 WFS 可售库存
- 7/14/30 销量
- 近30天广告费用
- 评分
- 评论数
- 品牌
- WFS费用
- GTIN
- UPC
- 店铺ID（不展示）

first-slice deferred real values:
- 划线价
- 购物车状态
- 沃尔玛卖家
- 是否被跟卖
- 停用原因
- GPT 分析
- 在途库存
```

## 9. SOP / API Docs

- [ ] Markdown API doc required
- [ ] OpenAPI metadata required
- [ ] SOP help page required
- [ ] PageShell help entry required

API 文档必须写清：

```text
- 查询参数
- 分页
- 排序
- meta.source_tables
- 字段权限占位
- 业务日期 America/Los_Angeles
- 计算口径
- 数据新鲜度
```

## 10. Implementation Plan

### Task 1：接口契约与治理注册

```text
1. 扩展 LingxingEndpoint 白名单。
2. 为 7 个接口补齐 contract。
3. 补齐 token_bucket_capacity。
4. 登记接口依赖：advertiser/list -> reportAdItemSpList。
5. 不启用生产 outbound。
```

### Task 2：数据库模型与 migration

```text
1. 新增 DIM / FACT / MART / rule version 表。
2. 所有外部 ID 使用 string。
3. 所有金额字段拆 amount + currency_code。
4. 所有时间字段保留 source/raw/UTC/business date。
5. 增加唯一约束、索引、source lineage 字段。
```

### Task 3：parser 与 refresh service

```text
1. getSellerList -> dim_lingxing_stores。
2. walmart/list -> dim_walmart_listings。
3. saleStat/pageList -> fact_walmart_sales_item_daily。
4. order/v2/list -> fact_walmart_order_items。
5. returnOrder/list -> fact_walmart_refund_items，只保留 REFUND。
6. advertiser/list -> dim_walmart_advertisers。
7. reportAdItemSpList -> fact_walmart_ad_item_sp_daily。
8. 刷新 3 张 MART。
```

### Task 4：后端查询 API

```text
1. 新增 sales 模块或在现有销售模块下实现 daily-sales/order-profit API。
2. 新增 listing-management API。
3. API 只查 MART / DIM，不查 RAW。
4. 支持分页、排序、筛选、summary。
5. 返回 meta.source_tables / freshness_at。
```

### Task 5：前端真实接入

```text
1. 新增 API client。
2. 新增 React Query hooks。
3. 替换 dailySalesMockData。
4. 替换 orderProfitSourceRecords + aggregateOrderProfitRows。
5. 替换 listingManagementMockData。
6. 保留现有页面样式、筛选、列配置、交互状态。
```

### Task 6：验收与防回归

```text
1. 后端单元测试 parser / repository / service。
2. API contract 测试。
3. 前端组件状态测试。
4. 不触碰生产。
5. 不输出 raw payload / token / SKU 明细。
```

## 11. Validation Gates

```bash
# frontend
npm run lint
npm run typecheck
npm run test
npm run build
npm run test:e2e

# backend
uv run ruff check .
uv run pytest
uv run alembic check
```

本 PRP 文件本身为文档变更，不执行本地命令。进入代码实现 PR 后必须执行对应 gate。

## 12. Forbidden Actions

```text
不修改 old-system
不连接生产数据库
不修改 .env
不调用真实外部 API
不部署
不重启服务
不输出密钥、token、Authorization、payload、RAW、真实 SKU 明细
不创建、编辑、删除、启停、调价、改库存、改广告投放
不把业务 API 直接接到 RAW
不把 store_id / sid / SKU / MSKU / item_id 互相推导
```

## 13. Rollback Plan

### 文档 PR 回滚

```text
revert PR 即可。
```

### 代码实现 PR 回滚

```text
1. 回滚前端 API 接入，恢复 mock fallback 或 feature flag disabled。
2. 回滚后端 route 注册。
3. 禁用接口 sync config。
4. 保留 ODS 原始证据，不清空。
5. 对新建业务表只做 migration downgrade 或新 migration 标记废弃，不手动改生产库。
```

### 数据回滚

```text
1. 生产数据回滚必须单独授权。
2. 不允许手动 UPDATE/DELETE 生产表。
3. 所有数据修正通过受控 migration / backfill / repair job。
```

## 14. Acceptance Checklist

- [ ] 数据源决策文件已完成并引用。
- [ ] 7 个接口的接口 ID、路径、令牌桶容量已记录。
- [ ] 店铺、Listing、销售、订单、退款、广告主体、广告商品报表的数据血缘已记录。
- [ ] DIM / FACT / MART 表范围已明确。
- [ ] 订单时间中国时间 -> UTC -> America/Los_Angeles 业务日口径已明确。
- [ ] returnOrder 只保留 REFUND 的口径已明确。
- [ ] advertiser/list 作为 reportAdItemSpList 的前置依赖已明确。
- [ ] API 契约 V1 已定义。
- [ ] 前端 mock 替换范围已定义。
- [ ] 第一批暂不实现字段已明确。
- [ ] 不涉及生产操作。
- [ ] CODEX_HANDOFF 更新（进入代码实现 PR 后执行）。
