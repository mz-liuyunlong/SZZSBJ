# 内部只读数据 API 文档

## 1. 使用说明

本 API 面向公司内部同事开放数据中台查询能力。调用方只能通过 HTTP GET 查询已开放数据，不能写入、同步、导入、上传、修改、删除数据，也不能执行任意 SQL。

后端角色为 `readonly_admin`，数据只来自 `DIM / FACT / EVENT / AI / RAW` 已开放查看接口。

## 2. 鉴权方式

后端从环境变量读取只读 Token：

```bash
INTERNAL_READONLY_API_TOKEN=<由管理员单独发放，不写入文档>
```

调用时在 Header 携带：

```http
Authorization: Bearer xxxxxx
```

Token 错误或缺失返回 `401 Unauthorized`。已认证但访问写入、同步、导入、上传、修改、删除类接口返回 `403 Forbidden`。

错误码说明：

- `200 OK`：请求成功。
- `400 Bad Request`：缺少必填参数或参数格式错误。
- `401 Unauthorized`：缺少 Token 或 Token 错误。
- `403 Forbidden`：已认证，但访问了非 GET、同步、导入、上传、更新或删除类接口。
- `404 Not Found`：接口路径不在只读 API 白名单内。
- `500 Internal Server Error`：服务端查询失败，请联系管理员排查日志。

## 3. API Base URL

同事使用的正式 Base URL：

```text
https://gpt-api.giginana.com/api/internal-readonly
```

内部部署说明：请求经 giginana.com 的海外中转反向代理转发到新业务服务器 42.193.254.170:3001；同事不直接使用裸 IP。

统一路径前缀：

```text
https://gpt-api.giginana.com/api/internal-readonly
```

## 4. 通用分页与过滤

所有查询接口均分页：

- `page`：页码，默认 `1`
- `page_size`：每页数量，默认 `50`，最大 `500`

常用过滤参数：

- `date`：日期，格式 `YYYY-MM-DD`
- `store` / `store_name`：店铺名称
- `store_id`：店铺 ID
- `item_id`：商品 ID
- `msku`：MSKU

通用返回结构：

```json
{
  "role": "readonly_admin",
  "total": 100,
  "page": 1,
  "page_size": 50,
  "rows": []
}
```

## 5. 权限限制

允许访问：

- `GET /lingxing-sales/daily-overview`
- `GET /lingxing-sales/sync-tasks`
- `GET /ads/product-daily`
- `GET /walmart-ads/list`
- `GET /ads/keyword-daily`
- `GET /inventory/daily`
- `GET /products`
- `GET /owners`
- `GET /keywords`
- `GET /events`
- `GET /ai-analysis`
- `GET /sales-detail/list`
- `GET /raw/feishu`
- `GET /feishu-raw-sales/data`
- `GET /raw/lingxing`

禁止访问：

- `POST /lingxing-sales/sync-daily`
- `POST /sync/*`
- `POST /import/*`
- `POST /upload/*`
- `PUT /*`
- `PATCH /*`
- `DELETE /*`
- 任何执行 SQL、同步、导入、上传、更新、删除语义接口

## 6. 接口列表

### 接口名称：
领星销售日数据查询

### 请求方式：
GET

### 请求路径：
`/lingxing-sales/daily-overview`

### 权限：
`readonly_admin`

### 参数：
- `date`：日期，必填
- `store_name` / `store`：店铺，可选
- `store_id`：店铺 ID，可选
- `item_id`：商品 ID，可选
- `msku`：MSKU，可选
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 数据来源表：
- `fact_sales_daily`
- `fact_ads_product_daily`
- `fact_inventory_daily`
- `dim_product_owner`
- `dim_product_cost_config`

### 返回字段：
- `stat_date`：日期
- `store_name`：店铺
- `item_id`：商品 ID
- `msku`：MSKU
- `sales_qty`：销量
- `sales_amount`：销售额
- `ad_spend`：广告花费
- `wfs_available_stock`：WFS 可售库存
- `owner_name`：负责人
- `purchase_cost`：采购成本
- `logistics_cost`：物流成本

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/lingxing-sales/daily-overview?date=2026-06-25&page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "stat_date": "2026-06-25",
      "store_name": "Walmart Store",
      "item_id": "123456",
      "msku": "MSKU-001",
      "sales_qty": 10,
      "sales_amount": "199.90",
      "ad_spend": "12.30",
      "wfs_available_stock": 88,
      "owner_name": "张三",
      "purchase_cost": "5.0000",
      "logistics_cost": "1.2000"
    }
  ]
}
```

### 接口名称：
同步日志查询

### 请求方式：
GET

### 请求路径：
`/lingxing-sales/sync-tasks`

### 权限：
`readonly_admin`

### 参数：
- `status`：同步状态，可选
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 数据来源表：
- `sync_task_log`

### 返回字段：
- `task_id`：任务 ID
- `task_name`：任务名称
- `source_system`：来源系统
- `target_table`：目标表
- `started_at`：开始时间
- `finished_at`：结束时间
- `status`：状态
- `pulled_count`：拉取数量
- `inserted_count`：插入数量
- `updated_count`：更新数量
- `failed_count`：失败数量
- `error_message`：错误信息

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/lingxing-sales/sync-tasks?page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "task_id": 1001,
      "task_name": "领星每日销售入库",
      "source_system": "lingxing",
      "target_table": "fact_sales_daily",
      "status": "success",
      "pulled_count": 100,
      "inserted_count": 10,
      "updated_count": 90,
      "failed_count": 0
    }
  ]
}
```

### 接口名称：
商品广告日数据查询

### 请求方式：
GET

### 请求路径：
`/ads/product-daily`

### 权限：
`readonly_admin`

### 参数：
- `date`：单日日期，可选；与 `date_start` / `date_end` 同时传入时，以 `date` 为准
- `date_start`：开始日期，可选，格式 `YYYY-MM-DD`
- `date_end`：结束日期，可选，格式 `YYYY-MM-DD`
- `store_name` / `store`：店铺，可选
- `store_id`：店铺 ID，可选
- `item_id`：商品 ID，可选
- `msku`：MSKU，可选
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 数据来源表：
- `fact_ads_product_daily`

### 返回字段：
- `stat_date`：日期
- `store_name`：店铺
- `advertiser_id`：广告主 ID
- `campaign_id`：广告活动 ID
- `campaign_name`：广告活动名称
- `campaign_type`：广告类型
- `ad_group_id`：广告组 ID
- `ad_group_name`：广告组名称
- `item_id`：商品 ID
- `msku`：MSKU
- `impressions`：曝光
- `clicks`：点击
- `ctr`：点击率
- `ad_spend`：广告花费
- `orders`：广告订单
- `total_sales`：广告销售额
- `acos`：ACoS
- `cpc`：CPC
- `cvr`：CVR
- `roas`：RoAS

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/ads/product-daily?date=2026-06-25&item_id=123456&page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "stat_date": "2026-06-25",
      "store_name": "Walmart Store",
      "campaign_name": "SP Campaign",
      "item_id": "123456",
      "msku": "MSKU-001",
      "impressions": 1000,
      "clicks": 40,
      "ad_spend": "12.3000",
      "orders": 3,
      "total_sales": "59.9700",
      "acos": "0.2051"
    }
  ]
}
```

### 接口名称：
Walmart 商品广告列表查询

### 请求方式：
GET

### 请求路径：
`/walmart-ads/list`

### 权限：
`readonly_admin`

### 参数：
- `date`：单日日期，可选；与 `date_start` / `date_end` 同时传入时，以 `date` 为准
- `date_start`：开始日期，可选，格式 `YYYY-MM-DD`
- `date_end`：结束日期，可选，格式 `YYYY-MM-DD`
- `store_name` / `store`：店铺，可选
- `store_id`：店铺 ID，可选
- `item_id`：商品 ID，可选
- `msku`：MSKU，可选；当前 `fact_ads_product_daily` 主要按 ItemID 粒度解释，生产数据中 MSKU 可能为空，不建议前端把 MSKU 作为广告主筛选条件
- `advertiser_id`：广告主 ID，可选
- `campaign_id`：广告活动 ID，可选
- `campaign_name`：广告活动名称，模糊匹配，可选
- `ad_group_id`：广告组 ID，可选
- `ad_group_name`：广告组名称，模糊匹配，可选
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 不支持的参数：
- `keyword`：不支持；关键词广告请使用 `/ads/keyword-daily`
- `owner`：不支持
- `ad_type`：不支持
- `sort_by` / `sort_dir`：不支持；当前固定按 `stat_date DESC, id DESC` 排序
- `limit` / `offset`：不支持；请使用 `page` / `page_size`
- `date_start` / `date_end`：不支持日期范围查询
- `acos_min` / `acos_max`：不支持
- `roas_min` / `roas_max`：不支持
- `ad_spend_min` / `ad_spend_max`：不支持
- `total_sales_min` / `total_sales_max`：不支持
- `orders_min` / `orders_max`：不支持
- `clicks_min` / `clicks_max`：不支持
- `impressions_min` / `impressions_max`：不支持

### 未支持参数的实际行为：
当前实现只读取上方“参数”列表中的字段。未列出的查询参数会被静默忽略，不影响查询结果，也不会报错。需要日期范围、数值范围或排序能力时，应先新增后端显式支持后再开放给前端。

### 数据来源表：
- `fact_ads_product_daily`

### 返回字段：
- `id`：记录 ID
- `stat_date`：日期
- `store_id`：店铺 ID
- `store_name`：店铺
- `advertiser_id`：广告主 ID
- `campaign_id`：广告活动 ID
- `campaign_name`：广告活动名称
- `campaign_type`：广告类型
- `ad_group_id`：广告组 ID
- `ad_group_name`：广告组名称
- `item_id`：商品 ID
- `msku`：MSKU
- `impressions`：曝光
- `clicks`：点击
- `ctr`：点击率
- `ad_spend`：广告花费
- `orders`：广告订单
- `total_sales`：广告销售额
- `acos`：ACoS
- `cpc`：CPC
- `cvr`：CVR
- `roas`：RoAS
- `source_system`：来源系统
- `created_at`：创建时间
- `updated_at`：更新时间

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/walmart-ads/list?date=2026-06-25&page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "id": 1,
      "stat_date": "2026-06-25",
      "store_name": "Walmart Store",
      "campaign_name": "SP Campaign",
      "ad_group_name": "Ad Group",
      "item_id": "123456",
      "msku": "MSKU-001",
      "impressions": 1000,
      "clicks": 40,
      "ad_spend": "12.3000",
      "orders": 3,
      "total_sales": "59.9700",
      "acos": "0.205100"
    }
  ]
}
```

### 接口名称：
关键词广告日数据查询

### 请求方式：
GET

### 请求路径：
`/ads/keyword-daily`

### 权限：
`readonly_admin`

### 参数：
- `date`：单日日期，可选；与 `date_start` / `date_end` 同时传入时，以 `date` 为准
- `date_start`：开始日期，可选，格式 `YYYY-MM-DD`
- `date_end`：结束日期，可选，格式 `YYYY-MM-DD`
- `store_name` / `store`：店铺，可选
- `store_id`：店铺 ID，可选
- `item_id`：商品 ID，可选
- `msku`：MSKU，可选
- `keyword`：关键词，模糊匹配，可选
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 数据来源表：
- `fact_ads_keyword_daily`

### 返回字段：
- `stat_date`：日期
- `store_name`：店铺
- `campaign_id`：广告活动 ID
- `campaign_name`：广告活动名称
- `ad_group_id`：广告组 ID
- `ad_group_name`：广告组名称
- `item_id`：商品 ID
- `item_name`：商品名称
- `msku`：MSKU
- `keyword`：关键词原文
- `normalized_keyword`：标准化关键词
- `match_type`：匹配类型
- `keyword_type`：关键词类型
- `impressions`：曝光
- `clicks`：点击
- `ctr`：点击率
- `ad_spend`：广告花费
- `orders`：广告订单
- `conversion_rate`：转化率
- `total_sales`：广告销售额
- `acos`：ACoS
- `cpc`：CPC
- `cvr`：CVR
- `roas`：RoAS
- `keyword_bid`：当天关键词 BID；若该来源当天无 BID 数据则返回 `null`，当前自动广告来源 `walmart_auto_csv` 为 `null`
- `source_type`：数据来源类型

### 日期行为说明：
- 传 `date`：按单日查询
- 只传 `date_start`：查询 `>= date_start`
- 只传 `date_end`：查询 `<= date_end`
- 同时传 `date_start` 与 `date_end`：按闭区间查询
- 未传 `date` / `date_start` / `date_end`：保持当前旧行为，不额外加默认时间窗口

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/ads/keyword-daily?date_start=2026-06-25&date_end=2026-06-30&keyword=chair&page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "stat_date": "2026-06-25",
      "store_name": "Walmart Store",
      "item_id": "123456",
      "msku": "MSKU-001",
      "keyword": "chair",
      "match_type": "broad",
      "ad_spend": "10.0000",
      "orders": 2,
      "total_sales": "39.9800",
      "keyword_bid": "0.5000",
      "source_type": "lingxing_keyword"
    }
  ]
}
```

### 接口名称：
库存日数据查询

### 请求方式：
GET

### 请求路径：
`/inventory/daily`

### 权限：
`readonly_admin`

### 参数：
- `date`：日期，可选
- `store_name` / `store`：店铺，可选
- `store_id`：店铺 ID，可选
- `item_id`：商品 ID，可选
- `msku`：MSKU，可选
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 数据来源表：
- `fact_inventory_daily`

### 返回字段：
- `snapshot_date`：库存快照日期
- `store_name`：店铺
- `item_id`：商品 ID
- `msku`：MSKU
- `sku`：SKU
- `available_stock`：可用库存
- `non_wfs_available_stock`：非 WFS 可售库存
- `wfs_available_stock`：WFS 可售库存
- `warehouse_stock`：仓库库存
- `inbound_stock`：在途库存
- `reserved_stock`：预留库存
- `stock_days`：库存天数

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/inventory/daily?date=2026-06-25&msku=MSKU-001&page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "snapshot_date": "2026-06-25",
      "store_name": "Walmart Store",
      "item_id": "123456",
      "msku": "MSKU-001",
      "available_stock": 120,
      "wfs_available_stock": 88,
      "non_wfs_available_stock": 32
    }
  ]
}
```

### 接口名称：
商品维度查询

### 请求方式：
GET

### 请求路径：
`/products`

### 权限：
`readonly_admin`

### 参数：
- `store_name` / `store`：店铺，可选
- `store_id`：店铺 ID，可选
- `item_id`：商品 ID，可选
- `msku`：MSKU，可选
- `owner`：负责人，可选
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 数据来源表：
- `dim_product`

### 返回字段：
- `store_id`：店铺 ID
- `store_name`：店铺
- `item_id`：商品 ID
- `msku`：MSKU
- `sku`：SKU
- `asin`：ASIN
- `product_name`：商品名称
- `item_name`：平台侧商品名称
- `category`：分类
- `brand`：品牌
- `owner`：负责人
- `status`：状态
- `fulfillment_type`：配送方式
- `source_system`：来源系统
- `updated_at`：更新时间

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/products?owner=张三&page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "store_name": "Walmart Store",
      "item_id": "123456",
      "msku": "MSKU-001",
      "product_name": "Product Name",
      "owner": "张三",
      "status": "active"
    }
  ]
}
```

### 接口名称：
负责人查询

### 请求方式：
GET

### 请求路径：
`/owners`

### 权限：
`readonly_admin`

### 参数：
- `owner` / `owner_name`：负责人姓名，可选
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 数据来源表：
- `dim_owner`

### 返回字段：
- `owner_id`：负责人 ID
- `owner_name`：负责人姓名
- `department`：部门
- `role_name`：角色
- `feishu_user_id`：飞书用户 ID
- `status`：状态
- `updated_at`：更新时间

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/owners?page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "owner_id": 1,
      "owner_name": "张三",
      "department": "运营",
      "role_name": "运营负责人",
      "status": "active"
    }
  ]
}
```

### 接口名称：
关键词维度查询

### 请求方式：
GET

### 请求路径：
`/keywords`

### 权限：
`readonly_admin`

### 参数：
- `keyword`：关键词，模糊匹配，可选
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 数据来源表：
- `dim_keyword`

### 返回字段：
- `keyword_id`：关键词 ID
- `keyword_text`：关键词原文
- `normalized_keyword`：标准化关键词
- `keyword_type`：关键词类型
- `platform`：平台
- `first_seen_at`：首次出现时间
- `last_seen_at`：最近出现时间
- `updated_at`：更新时间

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/keywords?keyword=chair&page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "keyword_id": 1,
      "keyword_text": "chair",
      "normalized_keyword": "chair",
      "keyword_type": "manual_keyword",
      "platform": "walmart"
    }
  ]
}
```

### 接口名称：
业务事件查询

### 请求方式：
GET

### 请求路径：
`/events`

### 权限：
`readonly_admin`

### 参数：
- `date`：事件日期，可选
- `store_name` / `store`：店铺，可选
- `store_id`：店铺 ID，可选
- `item_id`：商品 ID，可选
- `msku`：MSKU，可选
- `event_type`：事件类型，可选
- `status`：事件状态，可选
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 数据来源表：
- `biz_event`

### 返回字段：
- `event_id`：事件 ID
- `event_date`：事件日期
- `event_type`：事件类型
- `severity`：严重程度
- `store_id`：店铺 ID
- `store_name`：店铺
- `item_id`：商品 ID
- `msku`：MSKU
- `keyword`：关键词
- `campaign_id`：广告活动 ID
- `ad_group_id`：广告组 ID
- `owner`：负责人
- `title`：事件标题
- `reason`：触发原因
- `suggestion`：处理建议
- `status`：状态
- `source_table`：来源表
- `source_key`：来源记录标识
- `detected_by`：检测方式
- `created_at`：创建时间
- `updated_at`：更新时间
- `resolved_at`：解决时间

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/events?date=2026-06-25&status=open&page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "event_id": 1,
      "event_date": "2026-06-25",
      "event_type": "low_stock",
      "severity": "warning",
      "item_id": "123456",
      "msku": "MSKU-001",
      "title": "库存预警",
      "status": "open"
    }
  ]
}
```

### 接口名称：
AI 分析结果查询

### 请求方式：
GET

### 请求路径：
`/ai-analysis`

### 权限：
`readonly_admin`

### 参数：
- `date`：分析日期，可选
- `store_id`：店铺 ID，可选
- `item_id`：商品 ID，可选
- `msku`：MSKU，可选
- `analysis_type`：分析类型，可选
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 数据来源表：
- `ai_analysis_result`

### 返回字段：
- `analysis_id`：分析 ID
- `analysis_date`：分析日期
- `analysis_type`：分析类型
- `platform`：平台
- `store_id`：店铺 ID
- `item_id`：商品 ID
- `msku`：MSKU
- `keyword`：关键词
- `model_name`：模型名称
- `prompt_version`：提示词版本
- `conclusion`：结论
- `recommendation`：建议
- `risk_score`：风险评分
- `confidence`：置信度
- `source_event_id`：关联事件 ID
- `created_at`：创建时间

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/ai-analysis?date=2026-06-25&analysis_type=sales_analysis&page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "analysis_id": 1,
      "analysis_date": "2026-06-25",
      "analysis_type": "sales_analysis",
      "item_id": "123456",
      "msku": "MSKU-001",
      "conclusion": "销量稳定",
      "recommendation": "继续观察"
    }
  ]
}
```

### 接口名称：
飞书 RAW 原始数据查看

### 请求方式：
GET

### 请求路径：
`/raw/feishu`

### 权限：
`readonly_admin`

### 参数：
- `date`：数据日期，可选
- `sheet_id`：<REDACTED_FEISHU_SHEET_ID> ID，可选
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 不支持的参数：
RAW 接口无 store/item/msku 独立列（业务值在 row_json/response_json 中），以下参数不支持，传入将返回 `400`：`{"error":"Unsupported query parameter for RAW endpoint","unsupported_params":[...]}`。如需按店铺/商品/负责人等业务维度筛选，请改用 `/sales-detail/list`。 传入 `store`/`store_name`/`store_id`/`item_id`/`msku` 均返回 400。

### 数据来源表：
- `raw_feishu_table`

### 返回字段：
- `id`：RAW 记录 ID
- `source_system`：来源系统
- `sheet_id`：<REDACTED_FEISHU_SHEET_ID> ID
- `sheet_name`：Sheet 名称
- `row_index`：行号
- `row_json`：原始行 JSON
- `data_date`：数据日期
- `pulled_at`：拉取时间
- `created_at`：创建时间
- `updated_at`：更新时间

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/raw/feishu?sheet_id=<REDACTED_FEISHU_SHEET_ID>&page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "id": 1,
      "source_system": "feishu",
      "sheet_id": "<REDACTED_FEISHU_SHEET_ID>",
      "sheet_name": "当日数据",
      "row_index": 2,
      "row_json": {
        "店铺": "Walmart Store",
        "商品ID": "123456"
      },
      "data_date": "2026-06-25"
    }
  ]
}
```

### 接口名称：
业务销售明细查询

### 请求方式：
GET

### 请求路径：
`/sales-detail/list`

### 权限：
`readonly_admin`

### 接口定位：
业务明细只读接口，用于销售明细和经营分析筛选。该接口只读取 DIM / FACT 层，不读取 RAW 表，不执行任意 SQL。

### 参数：
- `date`：单日日期，可选，格式 `YYYY-MM-DD`；与 `date_start` / `date_end` 同时传入时，以 `date` 为准
- `date_start`：开始日期，可选，格式 `YYYY-MM-DD`
- `date_end`：结束日期，可选，格式 `YYYY-MM-DD`
- `store_name` / `store`：店铺名称，可选
- `store_id`：店铺 ID，可选
- `item_id`：商品 ID，可选
- `sku`：SKU，可选
- `msku`：MSKU，可选
- `owner`：负责人，可选
- `lifecycle_stage`：生命周期，可选
- `profit_level`：利润等级，可选
- `gross_margin_min` / `gross_margin_max`：毛利率范围，可选；比率口径，`0.17` 表示 17%
- `ad_ratio_min` / `ad_ratio_max`：广告占比范围，可选；比率口径，`0.17` 表示 17%
- `sales_amount_min` / `sales_amount_max`：销售额范围，可选
- `orders_min` / `orders_max`：订单量范围，可选
- `sort_by`：排序字段，可选，默认 `stat_date`
- `sort_dir`：排序方向，可选，默认 `desc`
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 日期规则：
- 未传 `date` / `date_start` / `date_end` 时，默认查询最近 7 天，避免全表扫描
- 只传 `date_start`：查询 `>= date_start`
- 只传 `date_end`：查询 `<= date_end`
- 日期格式错误返回 `400`

### 排序白名单：
- `stat_date`
- `sales_amount`
- `sales_qty`
- `ad_spend`
- `ad_ratio`
- `gross_margin`
- `gross_profit`
- `available_stock`

非法 `sort_by` 或 `sort_dir` 返回 `400`，不会把前端传入的排序字段直接拼接进 SQL。

### 数据口径：
- 多条件之间为 `AND`
- 分页 `total` 为完整过滤后的结果数量
- 广告指标按 `stat_date + platform + store_id + item_id` 聚合后展示，`ad_metric_scope` 固定为 `item_level`
- 广告指标是 ItemID 商品级，不是 MSKU 精确广告指标；如果一个 ItemID 下有多个 MSKU，广告指标不做销售额占比分摊
- `ad_ratio = ad_spend / sales_amount`；当 `ad_spend` 为空、`sales_amount` 为空或 `sales_amount = 0` 时返回 `NULL`
- `gross_margin` 来自 `fact_profit_daily.profit_rate`，比率口径，`0.17` 表示 17%
- 按 `ad_ratio_min` / `ad_ratio_max` 筛选时，`ad_ratio` 为 `NULL` 的行会被排除，包括无广告、销售额为 0 或销售额为空的明细
- 按 `gross_margin_min` / `gross_margin_max` 筛选时，`gross_margin` 为 `NULL` 的行会被排除
- 当前不开放 `platform` 筛选参数；实现默认限定 `s.platform = 'walmart'`

### 数据来源表：
- `fact_sales_daily`
- `fact_profit_daily`
- `fact_inventory_daily`
- `fact_ads_product_daily`
- `dim_product`
- `dim_product_business_state`

### 返回字段：
- `stat_date`：日期
- `store_id`：店铺 ID
- `store_name`：店铺
- `item_id`：商品 ID
- `sku`：SKU
- `msku`：MSKU
- `product_name`：商品名称
- `owner`：负责人
- `sales_qty`：销量
- `sales_amount`：销售额
- `ad_spend`：广告花费
- `ad_sales`：广告销售额
- `ad_orders`：广告订单
- `ad_ratio`：广告占比
- `ad_metric_scope`：广告指标粒度，固定 `item_level`
- `gross_profit`：毛利润
- `gross_margin`：毛利率
- `available_stock`：可用库存
- `wfs_available_stock`：WFS 可售库存
- `inventory_status`：库存状态
- `lifecycle_stage`：生命周期
- `profit_level`：利润等级
- `problem_tags`：问题标签

### 空结果格式：

```json
{
  "role": "readonly_admin",
  "total": 0,
  "page": 1,
  "page_size": 50,
  "rows": []
}
```

### 错误响应：
- `400`：参数格式错误、日期格式错误、非法 `sort_by` 或非法 `sort_dir`
- `401`：缺少 Token 或 Token 错误
- `403`：非 GET 或写入类请求
- `500`：查询异常，返回 `{"error":"Query failed"}`；不会返回 SQL、Token、密码、服务器路径或 stack trace

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/sales-detail/list?date_start=2026-07-01&date_end=2026-07-05&page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "stat_date": "2026-07-05",
      "store_name": "Walmart Store",
      "item_id": "123456",
      "sku": "SKU-001",
      "msku": "MSKU-001",
      "owner": "张三",
      "sales_qty": 10,
      "sales_amount": "199.9000",
      "ad_spend": "12.3000",
      "ad_sales": "59.9700",
      "ad_orders": "3",
      "ad_ratio": "0.061531",
      "ad_metric_scope": "item_level",
      "gross_profit": "36.5000",
      "gross_margin": "0.182591",
      "available_stock": 120,
      "wfs_available_stock": 88
    }
  ]
}
```

### 接口名称：
飞书 RAW 原始数据查询

### 请求方式：
GET

### 请求路径：
`/feishu-raw-sales/data`

### 权限：
`readonly_admin`

### 接口定位：
这是 RAW 查询接口，仅用于原始数据查看、排查和审计，不是每日销售明细业务接口。该接口直接读取 `raw_feishu_table`，业务字段存放在 `row_json` 中，当前不承载店铺、商品、负责人、毛利率、广告占比等业务筛选。

### 参数：
- `date`：数据日期，可选
- `sheet_id`：<REDACTED_FEISHU_SHEET_ID> ID，可选
- `sheet_name`：Sheet 名称，模糊匹配，可选
- `row_index`：行号，可选
- `keyword`：原始 JSON 内容关键词，模糊匹配，可选
- `source_system`：来源系统，可选
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 不支持的参数：
RAW 接口无 store/item/msku 独立列（业务值在 row_json/response_json 中），以下参数不支持，传入将返回 `400`：`{"error":"Unsupported query parameter for RAW endpoint","unsupported_params":[...]}`。如需按店铺/商品/负责人等业务维度筛选，请改用 `/sales-detail/list`。
- `store` / `store_name`
- `store_id`
- `item_id`
- `msku`
- `sku`：不支持
- `owner`：不支持
- `date_start` / `date_end`：不支持日期范围查询
- `gross_margin_min` / `gross_margin_max`：不支持
- `ad_ratio_min` / `ad_ratio_max`：不支持
- `sort_field` / `sort_order`：不支持；当前固定按 `id DESC` 排序
- `limit` / `offset`：不支持；请使用 `page` / `page_size`

### 重要限制：
`store` / `store_name` / `store_id` / `item_id` / `msku` 当前会触发 `500`，根因是 `raw_feishu_table` 没有这些独立列，线上错误为 `ERROR 1054 Unknown column`。前端禁止向本 RAW 接口传这些参数。

如需店铺、SKU、MSKU、商品 ID、负责人、日期范围、毛利率、广告占比等业务筛选，应新增并使用业务明细只读接口，例如 `GET /api/internal-readonly/sales-detail/list`。不要把 RAW 接口改造成复杂业务查询接口。

### 未支持参数的实际行为：
除上方会触发 `500` 的业务字段外，其它未读取参数通常会被静默忽略，不影响查询结果。为避免误判，前端只应开放本文“参数”列表中的字段。

### 数据来源表：
- `raw_feishu_table`

### 返回字段：
- `id`：RAW 记录 ID
- `source_system`：来源系统
- `sheet_id`：<REDACTED_FEISHU_SHEET_ID> ID
- `sheet_name`：Sheet 名称
- `row_index`：行号
- `row_json`：原始行 JSON
- `data_date`：数据日期
- `pulled_at`：拉取时间
- `created_at`：创建时间
- `updated_at`：更新时间

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/feishu-raw-sales/data?sheet_id=<REDACTED_FEISHU_SHEET_ID>&page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "id": 1,
      "source_system": "feishu",
      "sheet_id": "<REDACTED_FEISHU_SHEET_ID>",
      "sheet_name": "当日数据",
      "row_index": 2,
      "row_json": {
        "店铺": "Walmart Store",
        "商品ID": "123456",
        "MSKU": "MSKU-001"
      },
      "data_date": "2026-06-25"
    }
  ]
}
```

### 接口名称：
领星 RAW 原始响应查看

### 请求方式：
GET

### 请求路径：
`/raw/lingxing`

### 权限：
`readonly_admin`

### 参数：
- `date`：数据日期，可选
- `api_path`：领星 API 路径，可选
- `page`：页码，默认 1
- `page_size`：每页数量，默认 50，最大 500

### 不支持的参数：
RAW 接口无 store/item/msku 独立列（业务值在 row_json/response_json 中），以下参数不支持，传入将返回 `400`：`{"error":"Unsupported query parameter for RAW endpoint","unsupported_params":[...]}`。如需按店铺/商品/负责人等业务维度筛选，请改用 `/sales-detail/list`。 传入 `store`/`store_name`/`store_id`/`item_id`/`msku` 均返回 400。

### 数据来源表：
- `raw_lingxing_api`

### 返回字段：
- `id`：RAW 记录 ID
- `source_system`：来源系统
- `api_path`：接口路径
- `request_method`：请求方法
- `request_params_json`：请求参数 JSON
- `response_json`：原始响应 JSON
- `response_code`：响应码
- `is_success`：是否成功
- `error_message`：错误信息
- `data_date`：数据日期
- `pulled_at`：拉取时间
- `created_at`：创建时间
- `updated_at`：更新时间

### 示例请求：

```bash
curl -H "Authorization: Bearer xxxxxx" \
"https://gpt-api.giginana.com/api/internal-readonly/raw/lingxing?date=2026-06-25&page=1&page_size=50"
```

### 示例返回：

```json
{
  "role": "readonly_admin",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "rows": [
    {
      "id": 1,
      "source_system": "lingxing",
      "api_path": "/walmart/list",
      "request_method": "POST",
      "response_code": "0",
      "is_success": 1,
      "data_date": "2026-06-25"
    }
  ]
}
```

## 7. 数据库层保护建议

建议为只读 API 使用单独 MySQL 用户，并在后端通过以下环境变量配置：

```bash
READONLY_DB_HOST=127.0.0.1
READONLY_DB_PORT=3306
READONLY_DB_USER=walmart_readonly
READONLY_DB_PASSWORD=<仅服务器 .env 保存，不对外提供>
READONLY_DB_NAME=walmart_ai_data
```

MySQL 授权示例：

```sql
CREATE USER 'walmart_readonly'@'%' IDENTIFIED BY '<由管理员在服务器上生成的强随机密码>';
GRANT SELECT ON walmart_ai_data.* TO 'walmart_readonly'@'%';
FLUSH PRIVILEGES;
```

验权命令：

```sql
SHOW GRANTS FOR 'walmart_readonly'@'%';
```

验收标准：只出现 `SELECT` 权限，不应出现 `INSERT`、`UPDATE`、`DELETE`、`ALTER`、`DROP` 等写入或结构变更权限。

## 8. 注意事项

- 不要把 `INTERNAL_READONLY_API_TOKEN` 写入代码、文档示例或前端。
- 不要把 MySQL 密码、服务器路径、token、`.env` 内容返回给调用方。
- 不允许调用方传入 SQL。
- RAW 查看接口仅用于内部排查，调用时仍受 Token、GET、分页限制。
- 所有 API 调用会在后端日志记录时间、路径、方法、查询参数、IP、User-Agent 和角色。
- 对普通同事只发 Token 和接口文档，不发数据库账号密码。
