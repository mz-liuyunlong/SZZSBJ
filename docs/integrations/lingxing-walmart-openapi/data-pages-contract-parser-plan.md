# DATA-PAGES-1B：领星接口 Contract 注册与 Parser 设计

状态：`DRAFT_IMPLEMENTATION_PLAN`

日期：2026-09-16

本文件承接：

```text
PRPs/data-pages-daily-sales-listing-order-profit.md
docs/data-sources/decisions/data-pages-daily-sales-listing-order-profit-decision.md
```

本阶段目标是把 DATA-PAGES-1 的 7 个领星 / Walmart 来源接口，转换为可以进入代码实现的 contract 与 parser 设计。当前文件不调用真实接口、不写数据库、不创建 migration、不改生产配置。

## 1. 范围

### In scope

- 明确 7 个接口的运行时 contract。
- 明确 outbound 保护策略。
- 明确 parser 输入、输出、主键候选、跳过规则和数据质量门禁。
- 明确哪些 parser 只能进入设计，哪些可以进入第一批实现。
- 明确 `advertiser/list -> reportAdItemSpList` 依赖关系。

### Out of scope

- 不创建 DIM / FACT / MART 表。
- 不写 Alembic migration。
- 不实现后端页面查询 API。
- 不替换前端 mock。
- 不调用真实领星 API。
- 不连接生产数据库。

## 2. Contract 注册总览

| interface_key | API path | handler_key | request_kind | outbound_enabled 建议 | 说明 |
|---|---|---|---|---:|---|
| `sellerListMultiPlatform` | `/pb/mp/shop/v2/getSellerList` | `lingxing.seller_list_multiplaform.v1` | `offset_page` | true | 店铺维度，容量 10 |
| `walmartListingList` | `/basicOpen/multiplatform/walmart/list` | `lingxing.walmart_listing_list.v1` | `offset_page` | true | Listing 主数据，容量 1，不强制店铺参数 |
| `saleStatPageList` | `/basicOpen/platformStatisticsV2/saleStat/pageList` | `lingxing.sale_stat_page_list.v1` | `offset_page` | true | 销量/订单量/销售额，容量 1 |
| `orderV2List` | `/pb/mp/order/v2/list` | `lingxing.order_v2_list.v1` | `offset_page` | true | 订单明细，容量 10 |
| `walmartReturnOrderList` | `/basicOpen/openapi/multiplatform/walmart/returnOrder/list` | `lingxing.walmart_return_order_list.v1` | `offset_page` | true | 售后退款，容量 1，只保留 REFUND |
| `walmartAdvertiserList` | `/basicOpen/adReport/advertiser/list` | `lingxing.walmart_advertiser_list.v1` | `offset_page` | true | 广告主前置依赖，容量 1 |
| `walmartAdItemSpList` | `/basicOpen/multiplatform/ads/reportAdItemSpList` | `lingxing.walmart_ad_item_sp_list.v1` | `offset_page` | true | SP 广告商品报表，容量 1，依赖 advertiserId |

说明：当前 `gov_integration_interfaces.request_kind` 只支持 `offset_page` 和 `id_batch_page`。因此 page/pageSize 与 pageNum/pageSize 接口先统一注册为 `offset_page`，具体分页字段由 contract body 字段描述。

## 3. Client contract 设计

### 3.1 `/pb/mp/shop/v2/getSellerList`

允许 body 字段：

```text
offset
length
platform_code
status
is_sync
```

推荐固定：

```json
{
  "offset": 0,
  "length": 200,
  "platform_code": [10008]
}
```

分页字段：

```text
offset_field = offset
page_size_field = length
max_page_size = 200
```

### 3.2 `/basicOpen/multiplatform/walmart/list`

用户确认当前不需要带店铺参数。文档中存在 `store_ids`，但 DATA-PAGES-1 不依赖该参数。

允许 body 字段：

```text
offset
length
listing_time_field
listing_start_time
listing_end_time
status
fulfillment_types
search_field
search_single_value
principalUids
store_ids
```

推荐第一批：

```json
{
  "offset": 0,
  "length": 200
}
```

分页字段：

```text
offset_field = offset
page_size_field = length
max_page_size = 200
```

### 3.3 `/basicOpen/platformStatisticsV2/saleStat/pageList`

用户确认页面/API 层不写参数。同步层按文档保存 contract。

允许 body 字段：

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

推荐内部同步：

```text
data_type = 1
result_type in [1, 2, 3]
date_unit = 4
```

分页字段：

```text
page_field = page
page_size_field = length
max_query_range = 90 days
```

### 3.4 `/pb/mp/order/v2/list`

允许 body 字段：

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

固定口径：

```text
date_type = global_purchase_time
platform_code = [10008]
```

分页字段：

```text
offset_field = offset
page_size_field = length
max_page_size = 500
max_query_range = 31 days
```

### 3.5 `/basicOpen/openapi/multiplatform/walmart/returnOrder/list`

允许 body 字段：

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

固定口径：

```text
dateType = 1
returnTypeList = ["REFUND"]
sortField = returnOrderDate
```

分页字段：

```text
page_field = pageNum
page_size_field = pageSize
max_query_range = 1 year
```

### 3.6 `/basicOpen/adReport/advertiser/list`

允许 body 字段：

```text
paging
page
limit
searchText
```

推荐：

```json
{
  "paging": "true",
  "page": 1,
  "limit": 200
}
```

分页字段：

```text
page_field = page
page_size_field = limit
```

### 3.7 `/basicOpen/multiplatform/ads/reportAdItemSpList`

允许 body 字段：

```text
advertiserIds
campaignType
startDate
endDate
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
searchType
```

固定口径：

```text
campaignType = ["sponsoredProducts-manual", "sponsoredProducts-auto"]
advertiserIds 来自 /basicOpen/adReport/advertiser/list
startDate/endDate 间隔不超过 31 天
```

分页字段：

```text
page_field = pageNum
page_size_field = pageSize
max_page_size = 200
```

## 4. Parser 设计

### 4.1 通用 parser 输出

所有 parser 输出必须具备：

```text
source_raw_request_ref_id
source_line_hash 或 source_group_key
source_line_ordinal
parsed_count
skipped_count
invalid_count
parse_warnings_json
```

不得输出真实 raw payload 或真实 SKU 明细到日志。

### 4.2 店铺 parser

输入：`/pb/mp/shop/v2/getSellerList`

记录路径：

```text
data[].list[]
```

核心字段：

```text
platform_name
platform_code
store_id
store_name
sid
currency
status
is_sync
```

唯一键：

```text
source_account_ref + platform_code_raw + store_id
```

跳过规则：

```text
store_id 为空：invalid
platform_code 非 Walmart 时：可入维表，但 DATA-PAGES-1 MART 不使用
```

### 4.3 Walmart Listing parser

输入：`/basicOpen/multiplatform/walmart/list`

记录路径：

```text
data.list[]
```

核心字段：

```text
item_id
picture_url
msku
local_sku
local_name
store_id
store_name
title
price
currency_icon
listing_start_time
available_quantity
wfs_available_quantity
average_rating
review_count
gtin
upc
brand
status_name
fulfillment_type
fulfillment_type_name
item_url
variant_unique_id
```

唯一键：

```text
source_account_ref + store_id + item_id
```

跳过规则：

```text
item_id 为空：invalid
store_id 为空：invalid
price 无币种：保留 amount，但 currency_status=missing
```

### 4.4 saleStat parser

输入：`/basicOpen/platformStatisticsV2/saleStat/pageList`

记录路径：

```text
data[]
```

核心字段：

```text
date_collect
currency_code
platform_code
platform_name
platform_product_id
platform_product_title
sid
store_name
msku
sku
product_name
volumeTotal
```

parser 规则：

```text
1. result_type 由请求体/请求引用传入，不从 response 猜。
2. date_collect 是日期明细对象，volumeTotal 是小计。
3. date_collect 展开为 business_date + metric_value。
4. platform_product_id 数组长度为 1 时，可直接映射 item_id。
5. platform_product_id 数组长度 > 1 时，不得复制 volumeTotal；必须存 source_group_key 并标记 allocation_status=needs_owner_decision。
```

事实粒度：

```text
business_date_la + source_account_ref + store_id + item_id + result_type
```

### 4.5 订单 parser

输入：`/pb/mp/order/v2/list`

记录路径：

```text
data.list[].item_info[]
```

父级字段：

```text
data.list[].global_order_no
data.list[].global_purchase_time
data.list[].status
data.list[].status_sub
data.list[].flow_node
data.list[].store_id
data.list[].amount_currency
data.list[].transaction_info[].order_total_amount
```

行字段：

```text
item_info[].global_item_no
item_info[].order_item_no
item_info[].id
item_info[].quantity
item_info[].msku
item_info[].local_sku
item_info[].product_no
item_info[].platform_order_no
item_info[].sales_revenue_amount
item_info[].discount_amount
```

唯一键候选优先级：

```text
1. source_account_ref + global_order_no + global_item_no
2. source_account_ref + global_order_no + order_item_no
3. source_account_ref + global_order_no + item_info.id
4. source_account_ref + global_order_no + source_line_hash
```

时间规则：

```text
global_purchase_time 按用户口径视为中国时间
转 UTC
再转 America/Los_Angeles business_date
```

送样识别：

```text
sales_revenue_amount == 0
或 order_total_amount == 0
或 discount_amount 抵消商品金额
```

### 4.6 退款 parser

输入：`/basicOpen/openapi/multiplatform/walmart/returnOrder/list`

父记录路径：

```text
data.list[]
```

行记录路径：

```text
data.list[].items[]
```

过滤：

```text
returnType == "REFUND"
```

父级字段：

```text
returnOrderId
returnType
returnTypeName
returnOrderDate
returnByDate
customerOrderId
storeId
storeName
siteCode
```

行字段：

```text
items[].purchaseOrderId
items[].msku
items[].localSku
items[].quantityDisplay
items[].lineTotalAmount
items[].lineTotalCurrency
items[].status
items[].currentRefundStatus
items[].statusTime
items[].trackingNo
```

文档没有明确 return_line_id，第一期唯一键候选：

```text
source_account_ref + returnOrderId + purchaseOrderId + msku/localSku + trackingNo + statusTime
```

必须额外保存：

```text
source_line_hash
source_line_ordinal
```

### 4.7 广告主 parser

输入：`/basicOpen/adReport/advertiser/list`

记录路径：

```text
data.list[]
```

字段：

```text
advertiserId
advertiserName
status
```

唯一键：

```text
source_account_ref + advertiserId
```

### 4.8 SP 广告商品 parser

输入：`/basicOpen/multiplatform/ads/reportAdItemSpList`

记录路径：

```text
data.list[]
```

核心字段：

```text
advertiserId
adSpend
itemId
campaignId
adGroupId
adItemId
adName
campaignName
adGroupName
mpAdvertiserName
mpSellerName
attributedSales
attributedOrders
attributedUnits
advertisedSkuSales
advertisedSkuUnits
numAdsClicks
numAdsShown
acos
roas
cpc
ctr
cvr
key
```

事实粒度：

```text
business_date_la + source_account_ref + advertiserId + campaignId + adGroupId + adItemId + itemId
```

若 `adItemId` 为空：

```text
fallback: key 或 source_line_hash
```

## 5. Contract wiring 注意事项

### 5.1 当前模型限制

`gov_integration_interface_dependencies.dependency_type` 当前只允许：

```text
requires_sku_ids
```

因此 `advertiser/list -> reportAdItemSpList` 的依赖不能直接写成 `requires_advertiser_ids`，除非 DATA-PAGES-1C migration 扩展 check constraint。

1B 只能记录依赖设计；真正写入依赖表应放在 1C 或专门 migration 中。

### 5.2 request_kind 限制

当前 `request_kind` 只支持：

```text
offset_page
id_batch_page
```

因此 page/pageSize 和 pageNum/pageSize 接口先注册为 `offset_page`，实际分页字段由 handler contract 控制。

## 6. 进入代码实现的最小切片

第一批代码可以只做：

```text
1. LingxingEndpoint Literal 增加 4 个缺失接口。
2. _ENDPOINT_CONTRACTS 增加/修正 7 个 DATA-PAGES-1 接口 contract。
3. 增加 parser field-map / spec 模块，不写 DB。
4. 增加单元测试验证 contract 不泄露敏感数据、字段白名单、安全失败。
5. 不创建 DIM/FACT/MART 表。
6. 不写入 gov_integration_interface_dependencies 的 advertiser 依赖，等 1C migration。
```

## 7. 验收

- [ ] 新接口 path 只能是白名单 Literal。
- [ ] 未批准字段会被拒绝。
- [ ] token 不进入请求 body、响应 envelope、repr、str。
- [ ] capacity=1 接口在调度设计中默认串行。
- [ ] parser spec 不包含真实 SKU、payload、token。
- [ ] 不新增 migration。
- [ ] 不调用真实外部 API。
