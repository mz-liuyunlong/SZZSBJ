# DATA-PAGES-1 数据源决策：每日销售 / 订单利润 / Listing 管理

状态：`READY_FOR_PRP`

日期：2026-09-16

适用范围：

- 每日销售页面
- 订单利润页面
- Listing 管理页面
- 领星 Walmart 相关接口同步、清洗、聚合、查询 API 与前端真实渲染

## 1. 决策摘要

DATA-PAGES-1 使用 `REBUILD_SYNC` 策略：领星 / Walmart 作为外部权威来源，新系统通过现有 `integration_sync` 治理框架同步，原始响应进入现有 ODS/RAW 治理层，再清洗到 DIM / FACT / MART。前端业务 API 只读取 MART / READ MODEL，不直接读取 RAW。

本决策不新增接口专属 RAW 表。原始层复用现有：

```text
ods_api_raw_blobs
ods_api_raw_request_refs
gov_parse_jobs
gov_data_lineage
```

当前业务层需要新增：

```text
DIM:
- dim_lingxing_stores
- dim_walmart_listings
- dim_walmart_advertisers

FACT:
- fact_walmart_sales_item_daily
- fact_walmart_order_items
- fact_walmart_refund_items
- fact_walmart_ad_item_sp_daily

MART / READ MODEL:
- mart_daily_sales_item_day
- mart_order_profit_sku_day
- mart_listing_management_current

RULE VERSION:
- ref_store_commission_rule_versions
```

订单利润不单独拉一套数据链路，依赖 `mart_daily_sales_item_day` 聚合。

## 2. 文档来源

本决策基于仓库内领星接口整理资料：

```text
docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv
docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv
docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv
```

这些资料是项目内的精简只读参考。真实实现仍需保留运行时 ODS 证据、请求引用、解析任务和数据血缘。

## 3. 当前仓库数据状态

已存在：

```text
基础 SKU / 产品数据
产品管理部分成本/价格数据
integration_sync 同步治理层
ODS RAW blob/request ref 层
```

缺失：

```text
正式店铺维表
Walmart Listing 当前维表
销售日事实表
订单明细事实表
退款事实表
广告主体维表
广告商品日报事实表
每日销售 MART
订单利润 MART
Listing 管理 MART
```

## 4. 接口总览

| 数据集 | 接口 ID | API path | token_bucket_capacity | 分页 | 最大页长 | 增量字段 / 时间范围 | 目标表 |
|---|---|---|---:|---|---:|---|---|
| 店铺 | `LX-F8354824E040` | `/pb/mp/shop/v2/getSellerList` | 10 | `offset/length` | 200 | 无增量，分页全量 | `dim_lingxing_stores` |
| Walmart Listing | `LX-9212623D77EA` | `/basicOpen/multiplatform/walmart/list` | 1 | `offset/length` | 200 | `listing_time_field/listing_start_time/listing_end_time`，不超过 31 天 | `dim_walmart_listings` |
| 销量统计 V2 | `LX-A4FD6B748623` | `/basicOpen/platformStatisticsV2/saleStat/pageList` | 1 | `page/length` | 待接口实际 | `start_date/end_date/date_unit`，不超过 90 天 | `fact_walmart_sales_item_daily` |
| 订单管理订单列表 | `LX-5C93F09C1D1B` | `/pb/mp/order/v2/list` | 10 | `offset/length` | 500 | `date_type/start_time/end_time`，不超过 31 天 | `fact_walmart_order_items` |
| Walmart 售后订单 | `LX-571E669C2E50` | `/basicOpen/openapi/multiplatform/walmart/returnOrder/list` | 1 | `pageNum/pageSize` | 待接口实际 | `startDate/endDate/dateType/sortField`，不超过一年 | `fact_walmart_refund_items` |
| Walmart 广告主列表 | `LX-1DC15769BD57` | `/basicOpen/adReport/advertiser/list` | 1 | `page/limit` | 待接口实际 | 无增量，分页全量 | `dim_walmart_advertisers` |
| Walmart SP 广告商品报表 | `LX-0CB86D55776C` | `/basicOpen/multiplatform/ads/reportAdItemSpList` | 1 | `pageNum/pageSize` | 200 | `startDate/endDate/orderField`，间隔不超过 31 天 | `fact_walmart_ad_item_sp_daily` |

令牌桶容量是项目接口索引中的 `token_bucket_capacity`，不是完整限流策略。实现时仍需保守串行/低并发调度，特别是容量为 1 的接口。

## 5. 接口级决策

### 5.1 `/pb/mp/shop/v2/getSellerList`

用途：店铺主数据。当前页面只需要 `platform_name`、`platform_code`、`store_id`，但落库应保留 `sid`、`store_name`、`currency`、授权状态和同步状态，方便后续佣金规则、店铺筛选和平台扩展。

请求参数候选：

```text
offset
length
platform_code: [10008]
status
is_sync
```

返回字段：

```text
data[].list.platform_name
data[].list.platform_code
data[].list.store_id
data[].list.store_name
data[].list.sid
data[].list.currency
data[].list.status
data[].list.is_sync
```

落库：`dim_lingxing_stores`

主键/唯一键：

```text
source_account_ref + platform_code_raw + store_id
```

### 5.2 `/basicOpen/multiplatform/walmart/list`

用途：Walmart 在线 Listing 当前数据。

用户确认：DATA-PAGES-1 当前调用不需要带店铺参数。文档中存在 `store_ids`，但本阶段不作为业务依赖。

分页/增量：

```text
offset/length，length 上限 200
listing_time_field/listing_start_time/listing_end_time 可用于增量，窗口不超过 31 天
```

核心返回字段：

```text
data.list[].item_id
data.list[].picture_url
data.list[].msku
data.list[].local_sku
data.list[].local_name
data.list[].store_id
data.list[].store_name
data.list[].title
data.list[].price
data.list[].currency_icon
data.list[].listing_start_time
data.list[].listing_end_time
data.list[].offer_start_date
data.list[].offer_end_date
data.list[].available_quantity
data.list[].wfs_available_quantity
data.list[].average_rating
data.list[].review_count
data.list[].gtin
data.list[].upc
data.list[].brand
data.list[].status_name
data.list[].fulfillment_type
data.list[].fulfillment_type_name
data.list[].item_url
data.list[].variant_unique_id
```

落库：`dim_walmart_listings`

唯一键：

```text
source_account_ref + store_id + item_id
```

### 5.3 `/basicOpen/platformStatisticsV2/saleStat/pageList`

用途：销量、订单量、销售额统计。

用户确认：页面/API 设计中不暴露该接口请求参数。内部同步可依据接口文档使用必要参数。

内部同步参数候选：

```text
data_type
date_unit
start_date
end_date
page
length
result_type
sids
```

业务口径：

```text
result_type=1 -> 销量
result_type=2 -> 订单量
result_type=3 -> 销售额
```

返回字段：

```text
data[].date_collect
data[].currency_code
data[].platform_code
data[].platform_name
data[].platform_product_id
data[].platform_product_title
data[].sid
data[].store_name
data[].msku
data[].sku
data[].product_name
data[].volumeTotal
```

解析注意：`date_collect` 是日期到值的明细对象，`volumeTotal` 是小计。parser 不得把 `volumeTotal` 与 `date_collect` 双重计入。若返回数组维度存在多个 `platform_product_id`，必须保留 `source_group_key` 和原始维度 JSON，避免重复分摊。

落库：`fact_walmart_sales_item_daily`

推荐事实粒度：

```text
business_date_la + source_account_ref + store_id + item_id + result_type
```

最终 MART 汇总为：

```text
business_date_la + source_account_ref + store_id + item_id
```

### 5.4 `/pb/mp/order/v2/list`

用途：订单明细、送样识别、订单金额校验。

用户确认：

```text
date_type 固定 global_purchase_time
接口时间按中国时间理解
利润统计统一到 Walmart 业务日 America/Los_Angeles
```

文档参数：

```text
date_type
start_time
end_time
offset
length
platform_code
store_id
order_status
include_delete
global_order_nos
platform_order_nos
platform_order_names
```

`start_time/end_time` 为秒级时间戳，查询跨度不超过 31 天。

返回字段候选：

```text
data.list[].global_order_no
data.list[].global_purchase_time
data.list[].status
data.list[].status_sub
data.list[].flow_node
data.list[].store_id
data.list[].amount_currency
data.list[].item_info[].global_item_no
data.list[].item_info[].order_item_no
data.list[].item_info[].id
data.list[].item_info[].quantity
data.list[].item_info[].msku
data.list[].item_info[].local_sku
data.list[].item_info[].product_no
data.list[].item_info[].platform_order_no
data.list[].item_info[].sales_revenue_amount
data.list[].item_info[].discount_amount
data.list[].transaction_info[].order_total_amount
data.list[].transaction_info[].discount_amount
data.list[].platform_info[].platform_order_no
data.list[].platform_info[].purchase_time
```

订单行唯一键候选：

```text
source_account_ref + global_order_no + global_item_no
```

备选：

```text
source_account_ref + global_order_no + order_item_no
source_account_ref + global_order_no + item_info.id
source_account_ref + global_order_no + stable_line_hash
```

最终 parser 必须用真实 JSON 样例验证 `global_item_no/order_item_no/id` 的稳定性。

落库：`fact_walmart_order_items`

### 5.5 `/basicOpen/openapi/multiplatform/walmart/returnOrder/list`

用途：退款额、退货量、30 天退货率、订单利润扣减。

用户确认：

```text
dateType 固定 1
只保留 REFUND
```

文档参数：

```text
dateType
startDate
endDate
pageNum
pageSize
returnTypeList
returnStatusList
storeIdList
searchType
searchSingleValue
searchMultiValue
sortField
sortType
```

`dateType=1` 表示售后时间 `returnOrderDate`。`returnTypeList` 可传 `REFUND`。

返回字段：

```text
data.list[].returnOrderId
data.list[].returnType
data.list[].returnTypeName
data.list[].returnOrderDate
data.list[].returnByDate
data.list[].customerOrderId
data.list[].storeId
data.list[].storeName
data.list[].siteCode
data.list[].items[].purchaseOrderId
data.list[].items[].msku
data.list[].items[].localSku
data.list[].items[].quantityDisplay
data.list[].items[].lineTotalAmount
data.list[].items[].lineTotalCurrency
data.list[].items[].status
data.list[].items[].currentRefundStatus
data.list[].items[].statusTime
data.list[].items[].trackingNo
```

过滤：

```text
returnType == "REFUND"
```

事实粒度候选：文档没有明确 `return_line_id`。第一期推荐使用可追溯复合键并保留 line hash：

```text
source_account_ref + returnOrderId + purchaseOrderId + msku/localSku + trackingNo + statusTime
```

同时存：

```text
source_line_hash
source_line_ordinal
```

落库：`fact_walmart_refund_items`

### 5.6 `/basicOpen/adReport/advertiser/list`

用途：查询 Walmart 广告主，提供 `advertiserId` 给 SP 广告商品报表。

请求参数：

```text
paging
page
limit
searchText
```

返回字段：

```text
data.list[].advertiserId
data.list[].advertiserName
data.list[].status
data.total
```

落库：`dim_walmart_advertisers`

唯一键：

```text
source_account_ref + advertiser_id
```

### 5.7 `/basicOpen/multiplatform/ads/reportAdItemSpList`

用途：SP 广告商品报表，提供广告费 `adSpend` 和 item 级广告指标。

依赖：必须先从 `/basicOpen/adReport/advertiser/list` 获取 `advertiserId`。

请求参数：

```text
advertiserIds: required
campaignType: required, 查询 SP 时必须且只能携带 sponsoredProducts-manual / sponsoredProducts-auto
startDate: required
endDate: required
pageNum
pageSize
paging
day
orderField
orderType
adGroupIds
campaignIds
status
searchText
```

限制：`startDate/endDate` 间隔不能超过 31 天。

返回字段：

```text
data.list[].advertiserId
data.list[].adSpend
data.list[].itemId
data.list[].campaignId
data.list[].adGroupId
data.list[].adItemId
data.list[].adName
data.list[].campaignName
data.list[].adGroupName
data.list[].mpAdvertiserName
data.list[].mpSellerName
data.list[].attributedSales
data.list[].attributedOrders
data.list[].attributedUnits
data.list[].advertisedSkuSales
data.list[].advertisedSkuUnits
data.list[].numAdsClicks
data.list[].numAdsShown
data.list[].acos
data.list[].roas
data.list[].cpc
data.list[].ctr
data.list[].cvr
data.list[].key
```

推荐事实粒度：

```text
business_date_la + source_account_ref + advertiser_id + campaign_id + ad_group_id + ad_item_id + item_id
```

MART 使用时再按：

```text
business_date_la + item_id
```

聚合 `ad_spend_amount`。

## 6. 数据库设计原则

### 6.1 外部 ID

所有外部 ID 按 string 保存：

```text
store_id
sid
item_id
variant_unique_id
global_order_no
global_item_no
order_item_no
returnOrderId
purchaseOrderId
advertiserId
campaignId
adGroupId
adItemId
```

不得将 SKU / MSKU / item_id / product_id / listing_id 互相推导。

### 6.2 金额字段

金额字段必须拆成：

```text
*_amount
*_currency_code
```

源数据中只有币种符号时，先存 `*_currency_symbol_raw`，不得猜测币种。

### 6.3 时间字段

统一保留：

```text
source_*_raw
source_timezone
*_at_utc
business_date_la
business_timezone = America/Los_Angeles
```

订单接口 `global_purchase_time` 需要按用户口径从中国时间转换到 UTC，再转换为 Walmart 业务日。

退货接口 `dateType=1` 对应售后时间 `returnOrderDate`；第一期退款事实业务日期使用 `returnOrderDate`，同时保留 `items[].statusTime` 用于状态追溯。

### 6.4 成本、汇率、佣金规则

第一期默认：

```text
exchange_rate = 6.6
commission_rate = 0.15
```

但不能硬编码到计算结果外部。店铺佣金必须版本化：`ref_store_commission_rule_versions`。

MART 计算结果必须快照保存：

```text
exchange_rate
commission_rate
commission_rule_version_id
cost_status
calc_version
calculated_at
```

## 7. 页面字段数据源

### 7.1 每日销售

主要来源：

```text
fact_walmart_sales_item_daily
fact_walmart_order_items
fact_walmart_refund_items
fact_walmart_ad_item_sp_daily
dim_walmart_listings
dim_lingxing_stores
dws_product_management_pricing_current
ref_store_commission_rule_versions
```

输出 MART：`mart_daily_sales_item_day`

### 7.2 订单利润

来源：`mart_daily_sales_item_day`

输出 MART：`mart_order_profit_sku_day`

粒度：

```text
business_date_la + source_account_ref + local_sku
```

若页面需要商品维度下钻，再回查 `mart_daily_sales_item_day`。

### 7.3 Listing 管理

主要来源：

```text
dim_walmart_listings
dim_lingxing_stores
mart_daily_sales_item_day rolling 7/14/30 days
fact_walmart_ad_item_sp_daily rolling 30 days
products / product_platform_listings / product management pricing
```

输出 MART：`mart_listing_management_current`

第一期暂不强行接入的字段：

```text
划线价
购物车状态
沃尔玛卖家
是否被跟卖
停用原因
GPT 分析
系统运营日志
运营日志
在途库存
```

若源字段已在 Walmart Listing 接口中存在，第一期可接入：

```text
brand
status_name
fulfillment_type
fulfillment_type_name
item_url
upc
variant_unique_id
```

## 8. 同步顺序

```text
1. /pb/mp/shop/v2/getSellerList -> dim_lingxing_stores
2. /basicOpen/multiplatform/walmart/list -> dim_walmart_listings
3. /basicOpen/platformStatisticsV2/saleStat/pageList -> fact_walmart_sales_item_daily
4. /pb/mp/order/v2/list -> fact_walmart_order_items
5. /basicOpen/openapi/multiplatform/walmart/returnOrder/list -> fact_walmart_refund_items
6. /basicOpen/adReport/advertiser/list -> dim_walmart_advertisers
7. /basicOpen/multiplatform/ads/reportAdItemSpList -> fact_walmart_ad_item_sp_daily
8. refresh mart_daily_sales_item_day
9. refresh mart_order_profit_sku_day
10. refresh mart_listing_management_current
```

## 9. Token bucket / 调度决策

接口容量为 1 的接口必须默认串行：

```text
/basicOpen/multiplatform/walmart/list
/basicOpen/platformStatisticsV2/saleStat/pageList
/basicOpen/openapi/multiplatform/walmart/returnOrder/list
/basicOpen/adReport/advertiser/list
/basicOpen/multiplatform/ads/reportAdItemSpList
```

容量为 10 的接口可有限并发，但第一期仍建议保守：

```text
/pb/mp/shop/v2/getSellerList
/pb/mp/order/v2/list
```

完整补充速率、429 冷却、账号维度限流未在整理文档中明确，第一期必须使用保守限流、指数退避、可重试 work item 和分页 checkpoint。

## 10. 数据质量门禁

每个 parser 必须记录：

```text
source_raw_request_ref_id
source_line_hash / source_group_key
parsed_count
skipped_count
invalid_count
parse_warnings_json
```

关键门禁：

- `store_id` 为空：不得写主事实，只记录 parse warning。
- `item_id` 为空：不得参与 Listing / sales / ads join。
- 金额无币种：金额可入库但必须标记 `currency_status=missing`。
- saleStat 多 item 数组：不得无证据平均/复制金额。
- returnOrder 非 REFUND：跳过，不写退款事实表。
- 订单时间转换失败：不得写业务日期，保留 raw 并记录 invalid。

## 11. PRP 进入条件

本决策状态为 `READY_FOR_PRP`。允许进入 PRP 编写与实施设计。

实现时仍需：

- 按仓库规则走 Alembic migration。
- 后端保持 Route -> Schema -> Service -> Repository -> Model。
- 前端业务 API 不查 RAW。
- 不连接生产数据库。
- 不调用真实外部 API。
- 不修改 `old-system/**`。
- 不输出密钥、token、Authorization、raw payload 或真实 SKU 明细。
