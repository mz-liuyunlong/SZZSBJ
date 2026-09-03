# 领星每日销售数据入库说明

## 概述

`syncLingxingDailyToDb.ts` 是独立的入库脚本，将领星 API 三个接口的数据写入 MySQL 数据仓库。

**不修改任何已有脚本，不建新表，仅写入已有表。**

---

## 调用方式

```bash
# 同步昨日数据（默认）
npx ts-node src/syncLingxingDailyToDb.ts

# 指定日期
npx ts-node src/syncLingxingDailyToDb.ts --date 2026-06-25

# 使用 npm script
npm run sync:lingxing-daily -- --date 2026-06-25
```

---

## 数据流

```
领星 API
  ├── walmart/list (分页，每页20条)
  │     → raw_lingxing_api     (每页一条，INSERT IGNORE)
  │     → dim_store            (ON DUPLICATE KEY UPDATE)
  │     → dim_product          (ON DUPLICATE KEY UPDATE)
  │     → fact_inventory_daily (ON DUPLICATE KEY UPDATE)
  │
  ├── saleStat result_type=1 (销量，每页200条)
  ├── saleStat result_type=3 (销售额，每页200条)
  │     → raw_lingxing_api     (每页一条)
  │     → fact_sales_daily     (ON DUPLICATE KEY UPDATE)
  │
  └── reportAdItemSpList (广告明细，每页200条)
        → raw_lingxing_api        (每页一条)
        → fact_ads_product_daily  (ON DUPLICATE KEY UPDATE)

全程 → sync_task_log (任务开始/结束/状态/计数)
```

---

## 字段映射

### walmart/list → fact_inventory_daily

| API 字段 | DB 字段 | 说明 |
|---|---|---|
| item_id | item_id | 商品ID |
| msku | msku | MSKU |
| local_sku | sku | SKU |
| local_name | item_name（dim_product） | 商品名 |
| wfs_available_quantity | available_stock / wfs_available_stock | WFS 可售库存 |
| warehouse_stock | warehouse_stock | 仓库库存（若有） |
| inbound_stock | inbound_stock | 在途库存（若有） |

### saleStat → fact_sales_daily

| API 字段 | DB 字段 | 说明 |
|---|---|---|
| platform_product_id | item_id | 商品ID（数组，取第一个） |
| volumeTotal (result_type=1) | sales_qty / order_count | 销量 |
| volumeTotal (result_type=3) | sales_amount | 销售额（$） |

msku / sku 通过 item_id 从 walmart/list 结果中反查。

### reportAdItemSpList → fact_ads_product_daily

| API 字段（camelCase） | DB 字段 |
|---|---|
| campaignId | campaign_id |
| campaignName | campaign_name |
| campaignType | campaign_type |
| adGroupId | ad_group_id |
| adGroupName | ad_group_name |
| itemId | item_id |
| impressions | impressions |
| clicks | clicks |
| ctr / clickRate | ctr |
| adSpend | ad_spend |
| orders / orderNum | orders |
| totalSales / adSales | total_sales |
| acos / acosRate | acos |
| cpc | cpc |
| cvr / conversionRate | cvr |
| roas | roas |

---

## 唯一键说明

| 表 | 唯一键 |
|---|---|
| raw_lingxing_api | (api_path, data_date, raw_hash) |
| dim_store | (platform, store_id) |
| dim_product | (platform, store_id, item_id, msku) |
| fact_inventory_daily | (snapshot_date, platform, store_id, item_id, msku) |
| fact_sales_daily | (stat_date, platform, store_id, item_id, msku) |
| fact_ads_product_daily | (stat_date, platform, advertiser_id, campaign_id, ad_group_id, item_id) |

---

## 环境变量

与其他脚本相同，读取 `.env` 文件：

```
LINGXING_BASE_URL=https://openapi.lingxing.com
LINGXING_APP_ID=...
LINGXING_APP_SECRET=...
DB_HOST=...
DB_PORT=3306
DB_USER=...
DB_PASSWORD=...
DB_NAME=walmart_ai_data
```

---

## IP 白名单

Lingxing API 有 IP 白名单限制：

- **服务器 8.145.43.239**：已永久加白，直接可用
- **本地 Mac**：需在领星后台手动加白当前公网 IP
- **Cowork 沙箱**：无法直连，需在服务器上运行

---

## 执行索引 SQL

首次部署时需执行补充索引（可选，002 已覆盖主要索引）：

```bash
mysql walmart_ai_data < sql/006_lingxing_daily_required_indexes.sql
```

---

## 输出示例

```
══════════════════════════════════════════════════
  领星销售数据入库
  任务ID:   LXDB-20260625120000
  数据日期: 2026-06-25
  店铺数:   6
══════════════════════════════════════════════════

  ► 店铺: CN2601-瑞盈龙盛(刘云龙） (110687423514268160)
    商品数: 312
    库存写入: 312
    销售写入: 87 (qty来源 87 / amount来源 87)
    广告写入: 142

  ► 店铺: CN2501-掌上便捷(陈佳聪） (110687427724845056)
    ...

══ 完成 ═══════════════════════════════════════════
  CN2601-瑞盈龙盛: 商品 312 | 库存 312 | 销售 87 | 广告 142 | RAW 18
  CN2501-掌上便捷: 商品 198 | 库存 198 | 销售 53 | 广告 89 | RAW 14
  ...
══════════════════════════════════════════════════
```
