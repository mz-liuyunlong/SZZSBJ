# 旧系统领星 API 溯源基线表

## 1. 文档定位

本文件用于记录**旧系统**中领星 API、RAW 原始存储、DIM/FACT 清洗落库、前端/internal GET、页面展示、计算口径与迁移风险之间的证据链。

本文件是旧系统迁移证据基线，不是新系统实现批准文件。任何新系统表结构、同步任务、接口、前端页面接入，仍必须经过 Source Decision、PRP、Owner Review 和受控实现。

## 2. 使用边界

- 允许用于旧系统溯源、迁移分析、字段口径复核、RAW 优先级判断和验收对账。
- 不允许直接作为新系统建表、写入 DIM/FACT、前端接口开发或生产同步任务的批准依据。
- 表中写明“原始存储 RAW”的链路，应优先转化为新系统 RAW 接入候选。
- RAW 之后进入清洗层、DIM、FACT、MART / READ MODEL 的逻辑，必须另行确认字段含义、口径、幂等规则、权限、审计和数据质量。
- “当前状态”“迁移风险备注”必须在迁移 PRP 中逐项处理，不能默认忽略。

## 3. 迁移原则

```text
旧系统证据链
  -> 新系统 Source Decision
  -> 新系统 RAW Foundation
  -> L3 Standardized / Cleansed
  -> L4 Canonical / L5 Reference / L6 Identity
  -> L7 DIM / L8 FACT
  -> L9 MART / READ MODEL
  -> Backend API
  -> Frontend
```

关键原则：

1. 真实领星接口返回后，优先写入新系统 RAW。
2. RAW 保存完整请求、完整响应、响应码、成功状态、业务日期、拉取时间和 hash。
3. 后续结构化记录必须保留 `source_raw_id` 回指 RAW。
4. DIM / FACT 不得绕过 RAW 直接写入。
5. 前端不得直接读取 RAW 或领星 API，应读取后端整理后的 read model API。

## 4. 快速索引

| 编号 | 数据分类 | 领星接口 / 来源 | 原始存储 RAW | 清洗后存储 DIM/FACT | 当前状态 | 迁移风险备注 |
| --- | --- | --- | --- | --- | --- | --- |
| LX-LINEAGE-001 | 通用基础链路 | 全部下列写 RAW 的领星接口 | raw_lingxing_api：api_path、request_method、request_params_json、response_json、response_code、is_success、error_message、data_date、pulled_at、raw_hash、extra_json。 | 各接口再写入对应 DIM / FACT；source_raw_id 指回 RAW。 | 当前基础模型 | internal-readonly 会返回 request_params_json 与 response_json；新系统应做权限、字段白名单、分页和大 JSON 限制。 |
| LX-LINEAGE-002 | 商品与库存 | POST /basicOpen/multiplatform/walmart/list | raw_lingxing_api（完整分页响应）。 | dim_store；dim_product；fact_inventory_daily。 | 当前主同步实现 | 库存同步日期是拉取日，不是销售查询日；迁移时必须明确历史库存快照口径。 |
| LX-LINEAGE-003 | 商品价格 | POST /basicOpen/multiplatform/walmart/list，status=[0] | raw_lingxing_walmart_listing：capture_date、capture_date_la、store_id、item_id、msku、row_json。 | 更新 dim_product.buy_box_price、buy_box_price_updated_at。 | 当前实现 | Buy Box 缺失会退挂牌价，字段语义混用；价格不能直接被称为纯 Buy Box 价。 |
| LX-LINEAGE-004 | 销售 | POST /basicOpen/platformStatisticsV2/saleStat/pageList，result_type=1 和 3 | raw_lingxing_api（两种 result_type 的完整分页响应）。 | fact_sales_daily。 | 当前主同步实现 | 订单数口径错误风险：新系统不能复用 order_count 作为订单去重数。 |
| LX-LINEAGE-005 | 广告商品绩效 SP | POST /basicOpen/multiplatform/ads/reportAdItemSpList | raw_lingxing_api（手动和自动 SP 的完整分页响应）。 | fact_ads_product_daily。 | 当前主同步实现 | 广告花费还存在 CSV 搜索词、SEM、账单等平行来源；新系统需定义唯一权威汇总口径，防重复。 |
| LX-LINEAGE-006 | 广告关键词 SP | POST /basicOpen/multiplatform/ads/reportKeywordSpList；同时用 reportAdItemSpList 建商品映射 | raw_lingxing_api（关键词和商品映射接口响应）。 | fact_ads_keyword_daily。 | 当前实现 | 关键词花费不等于商品广告花费；不可将两个 FACT 无条件相加。 |
| LX-LINEAGE-007 | 广告商品绩效 SB/SV | POST /basicOpen/multiplatform/ads/reportAdItemSbList；POST /basicOpen/multiplatform/ads/reportAdItemSvList | raw_lingxing_api。 | fact_ads_product_daily，campaign_type 分别为 sba、video。 | 当前实现 | 旧文档若标记为探针已过时；但无 ItemID 广告费的商品归属仍是风险。 |
| LX-LINEAGE-008 | 广告配置快照 | queryCampaignSpList、queryGroupSpList、reportAdGroupSbList、queryAdGroupSvList、reportKeywordSpList、reportKeywordSbList、reportKeywordSvList | raw_lingxing_api（店铺 × 实体 × 广告类型 × 页）。 | fact_ads_campaign_snapshot_daily；fact_ads_group_snapshot_daily；fact_ads_keyword_snapshot_daily；fact_ads_snapshot_status。 | 当前实现 | queryAdGroupSvList 在源码注明参数错误，SV 广告组快照不能视为完整。 |
| LX-LINEAGE-009 | 店铺与广告主 | POST /pb/mp/shop/v2/getSellerList；POST /basicOpen/adReport/advertiser/list；辅以 reportAdItemSpList | 当前 syncWalmartStores.ts 未写 RAW。 | dim_store_config；dim_store。 | 当前实现 | 没有 RAW 审计留痕；迁移时应补齐店铺授权快照与历史变更。 |
| LX-LINEAGE-010 | 商品成本与商品名 | POST /erp/sc/routing/data/local_inventory/batchGetProductInfo | raw_lingxing_api（批量响应）。 | dim_product_cost_config；另一个脚本更新 dim_product.product_name，并可补空 SKU。 | 当前实现 | DIM 表还含人工配送费；迁移必须区分人工成本与领星成本的覆盖优先级。 |
| LX-LINEAGE-011 | 采购进度 | POST /erp/sc/routing/data/local_inventory/purchaseOrderList | raw_lingxing_api。 | fact_purchase_order；fact_purchase_order_item。 | 当前实现 | 采购数量字段需确认哪个代表开放采购量，不能只按表名推断。 |
| LX-LINEAGE-012 | 采购现金支出 | POST /erp/sc/routing/data/local_inventory/purchaseOrderList | raw_lingxing_api。 | fact_purchase_cash；fact_purchase_cash_item。 | 当前实现 | 复核关闭后不更新会造成历史订单与领星后续修订不一致。 |
| LX-LINEAGE-013 | 库存批次与库存成本 | POST /erp/sc/routing/data/local_inventory/getBatchDetailList | raw_lingxing_api。 | fact_lingxing_batch。 | 当前实现 | 批次守恒不通过仍可入库；新系统应将异常状态显式化。 |
| LX-LINEAGE-014 | 本地仓库存 | POST /erp/sc/data/local_inventory/warehouse；POST /erp/sc/routing/data/local_inventory/inventoryDetails | inventoryDetails 响应 → raw_lingxing_api；仓库列表仅作筛选，未见独立 RAW。 | fact_local_inventory_daily。 | 当前实现 | 仓库列表不留 RAW；SKU→商品一对多分摊会使前端库存不是领星原始仓库数。 |
| LX-LINEAGE-015 | 汇率 | POST /erp/sc/routing/finance/currency/currencyMonth | raw_lingxing_api。 | fact_lingxing_fx_rate。 | 当前实现 | 不同模块的汇率月份与兜底规则必须统一，否则利润会不一致。 |
| LX-LINEAGE-016 | 头程发货与分摊 | POST /cepf/warehouse/api/openApi/queryShippingListPage | raw_lingxing_api。 | fact_shipping_order；fact_shipping_first_let。 | 当前实现 | 匹配不唯一的数据仍存在；作废单不参加守恒告警，迁移时应保留审计状态。 |
| LX-LINEAGE-017 | WFS货件 | POST /cepf/warehouse/api/openApi/queryWFSCargoPage | raw_lingxing_api。 | fact_wfs_shipment；fact_wfs_shipment_item；event_arrival_notify。 | 当前实现 | 货件状态与通知是事件型数据；补历史数据时必须避免重复通知。 |
| LX-LINEAGE-018 | 月度结算利润 | POST /basicOpen/multiplatform/profit/report/msku | raw_lingxing_api。 | fact_settlement_msku_monthly。 | 当前实现 | extra_json 是重要保底字段；新系统需先字段实证后再拆 promotion/refund/commission。 |
| LX-LINEAGE-019 | 订单结算 WFS费率 | POST /basicOpen/multiplatform/profit/report/order | raw_lingxing_settlement_order：capture_batch、msku_query、unique_id、row_index、row_json。 | dim_product_wfs_fee_auto。 | 当前实现 | 众数费率是估计值且有最小样本门槛；应保留样本数和时间窗。 |
| LX-LINEAGE-020 | 售后退款 | POST /basicOpen/openapi/multiplatform/walmart/returnOrder/list | raw_walmart_return_order：头部与单个商品合成 row_json，并保存关键字段。 | fact_refund_daily。 | 当前实现 | 如果新系统只认完成退款，结果会与旧系统不同；须先确定退款状态口径。 |
| LX-LINEAGE-021 | 账期与对账单 | POST /basicOpen/multiplatformFinance/walmart/bill/payout/list；POST /basicOpen/multiplatformFinance/walmart/bill/statement/list | raw_lingxing_api。 | fact_reconciliation_period；fact_reconciliation_item；fact_ad_credit_detail；fact_commission_saving；event_finance_sentinel_alert。 | 当前实现 | 类别映射规则属于核心财务口径；迁移必须版本化并保留 unknown/other。 |
| LX-LINEAGE-022 | 渠道订单销量 | POST /pb/mp/order/v2/list | raw_lingxing_api。 | Walmart：fact_mp_sales_channel_daily；其它渠道：fact_channel_clearance_sales_daily。 | 当前实现 | 请求窗口用北京时间边界，Walmart 业务日通常为美西，可能有跨日偏差。 |
| LX-LINEAGE-023 | 促销折扣与快速销量 | POST /pb/mp/order/v2/list | raw_mp_order_item 保存全部商品行；raw_mp_order_discount 只保存折扣非0行；均保留 row_json。 | fact_promo_discount_daily；fact_sales_fast_daily。 | 当前实现 | 送样阈值规则硬编码，且快速销量并非权威利润数据；迁移时要明确标记兜底行。 |
| LX-LINEAGE-024 | TEMU清货刊登 | POST /basicOpen/multiplatform/temu/list | raw_lingxing_api。 | biz_clearance_other_channel。 | 当前实现 | INSERT IGNORE 会使已存在商品的店铺/状态/负责人可能陈旧。 |
| LX-LINEAGE-025 | AI PMC直连补货 | purchaseOrderList、saleStat/pageList、inventoryDetails、shipmentPlanLists、queryWFSCargoPage | 该链主要内存处理，未走上述 MySQL RAW/FACT。 | 飞书 PMC 任务、补货台账和通知；不是 MySQL 数据仓库链。 | 代码存在，运行状态待确认 | 缺 RAW 与 MySQL 追溯；新系统建议统一写入可审计任务与输入快照。 |
| LX-LINEAGE-026 | 利润派生链 | 非新增领星接口：组合 sales、ads、inventory、cost、WFS fee、退款、仓储、送样订单。 | fact_profit_daily；订单利润 V2 在查询时再次聚合。 | 日利润包含日期、店铺、ItemID、MSKU、SKU、负责人、销售、广告、库存、配送费、采购/头程、佣金、利润、毛利率等。 | 这是迁移最高风险链：输入来源、日界、成本快照、送样规则、汇率与缺失成本策略必须逐项验收。 |  |
| LX-LINEAGE-027 | 导入：WFS仓储 CSV | 非领星 API。Seller Center 仓储 CSV 导入。 | raw_walmart_storage_csv：row_no=0 为摘要，其余逐行 row_json。 | fact_wfs_storage_fee；异步展开 fact_storage_fee_daily。 | 当前前端导入 | 导入成功后异步 spawn 日摊脚本；若子进程失败，原始仓储费用已写入而利润日摊可能未刷新。 |
| LX-LINEAGE-028 | 导入：WFS入库运输 CSV | 非领星 API。Seller Center 入库运输 CSV 导入。 | raw_walmart_inbound_csv：摘要行和全部原始行 row_json。 | fact_inbound_freight_alloc。 | 当前前端导入 | 未匹配货件的金额会暂挂；迁移需保留重新分摊流程和余额核对。 |
| LX-LINEAGE-029 | 导入：清货目标 XLSX/CSV | 非领星 API。POST /api/clearance-center/parse-xlsx 和 /import-monthly-target。 | 不保存文件或原始行，仅在内存解析 grid。 | Walmart 目标写 biz_monthly_plan；其它渠道更新 biz_clearance_other_channel 的 monthly_target、target_month、monthly_cleared。 | 当前前端导入 | 没有原文件审计留存；新系统如需可追溯应额外存文件哈希、原表头和拒绝行。 |
| LX-LINEAGE-030 | 导入：其他渠道清货 XLSX/CSV | 非领星 API。POST /api/clearance-center/import-other-channel。 | 不保存文件或原始行。 | biz_clearance_other_channel。 | 当前前端导入 | 平台标识关联策略需要固定，否则后续订单销量无法稳定回填到清货项。 |
| LX-LINEAGE-031 | 导入：月度规划 XLSX/CSV | 非领星 API。POST /api/ai-business/monthly-plan/parse-xlsx 和 /monthly-plan。 | 不保存文件，仅在内存解析 grid。 | biz_monthly_plan。 | 当前前端导入 | 上月实际依赖 raw_feishu_table 的旧利润快照，迁移时需替换或回填该基座。 |
| LX-LINEAGE-032 | 导入：自动广告搜索词 CSV | 非领星 API。独立 Walmart Ads 导入服务，主导入器不在当前副本。 | raw_walmart_ads_csv：任务、店铺、操作人和每行 row_json。 | fact_ads_keyword_daily，source_type=walmart_auto_csv。 | 导入证据不完整 | 生产 csv_processor 和 API 主实现缺失；迁移前必须补齐代码及运行任务。 |
| LX-LINEAGE-033 | 导入：SEM每日报表 CSV | 非领星 API。POST /api/walmart-sem/upload，类型 sem_daily。 | raw_walmart_sem_csv：任务、类型、行号、日期、店铺、操作人和 row_json。 | fact_ads_product_daily，campaign_type=sem；可用 dim_sem_campaign_item 补商品归属。 | 交付件代码存在，部署待确认 | SEM 与领星广告 FACT 共表，汇总必须按 source/campaign_type 防重复；商品归属失败需持续治理。 |
| LX-LINEAGE-034 | 导入：SEM账单 CSV | 非领星 API。POST /api/walmart-sem/upload，类型 sem_billing。 | raw_walmart_sem_csv，csv_type=sem_billing。 | fact_sem_billing_daily。 | 交付件代码存在，部署待确认 | SEM账单与日绩效不是同一粒度，不能直接用于替代日广告花费。 |
| LX-LINEAGE-035 | 导入：Connect广告发票 PDF | 非领星 API。页面入口 /walmart-connect-invoice；当前副本未找到解析写库主实现。 | raw_walmart_connect_invoice：摘要和 PDF 原文行 row_json。 | fact_onsite_ads_invoice_head；fact_onsite_ads_invoice_line；dim_connect_account。 | 读取链和表结构存在，导入实现缺失 | 高风险缺口：必须取得 PDF 解析器、任务队列和异常处理代码后才能迁移。 |
| LX-LINEAGE-036 | 探针与旧脚本 | allMarketplace、reportProductSpList、reportPlatform、queryPageType、report/sku、候选运费/付款接口等。 | 多数只打印控制台或查询既有表，未形成稳定 RAW。 | 未发现稳定的生产 DIM/FACT 写入。 | 迁移时排除，除非业务方明确确认仍需保留。 |  |

# 5. 逐链路明细

## LX-LINEAGE-001｜通用基础链路

**领星接口 / 来源：** 全部下列写 RAW 的领星接口

### 获取数据

完整请求参数、完整响应、响应码、成功状态、业务日期与拉取时间。

### 原始存储 RAW

raw_lingxing_api：api_path、request_method、request_params_json、response_json、response_code、is_success、error_message、data_date、pulled_at、raw_hash、extra_json。

### 清洗后存储 DIM/FACT

各接口再写入对应 DIM / FACT；source_raw_id 指回 RAW。

### 保存字段与关联键

唯一键为 api_path + data_date + raw_hash；结构化记录一般保存 source_raw_id。

### 清洗规则

RAW 优先。部分脚本在 RAW 写入或回查失败时阻止下游 FACT；有少数脚本未保留 RAW。

### 不进入结构化表的情况

未被映射的接口字段通常仍在 response_json，不等于删除。

### 前端 / internal GET

GET /api/internal-readonly/raw/lingxing?api_path=... 读取 raw_lingxing_api；GET /api/internal-readonly/lingxing-sales/sync-tasks 读取 sync_task_log。

### 页面与渲染内容

RAW 无正常业务页面；internal-readonly 供内部审计或排查。

### 原值 / 计算口径

原始 JSON，不做业务计算。

### 证据文件

reports/database/LEGACY_DATABASE_SCHEMA_ONLY.sql:328；src/internalReadonlyApi.ts:987

### 当前状态

当前基础模型

### 迁移风险备注

internal-readonly 会返回 request_params_json 与 response_json；新系统应做权限、字段白名单、分页和大 JSON 限制。

---

## LX-LINEAGE-002｜商品与库存

**领星接口 / 来源：** POST /basicOpen/multiplatform/walmart/list

### 获取数据

item_id 或 itemId、status_name 或 status、msku、local_sku 或 sku、商品名、available_quantity、wfs_available_quantity、warehouse_stock、inbound_stock、reserved_stock、stock_days。

### 原始存储 RAW

raw_lingxing_api（完整分页响应）。

### 清洗后存储 DIM/FACT

dim_store；dim_product；fact_inventory_daily。

### 保存字段与关联键

dim_product：platform、store_id、item_id、msku、sku、item_name、walmart_publish_status。库存：snapshot_date、店铺、ItemID、MSKU、SKU、available_stock、non_wfs_available_stock、wfs_available_stock、warehouse_stock、inbound_stock、reserved_stock、stock_days、source_raw_id。

### 清洗规则

available_stock = available_quantity + wfs_available_quantity；空 SKU、名称、发布状态不覆盖旧值；同 ItemID 仅有一个非空 SKU 时回填空 SKU；库存日期取实际拉取日 CST。

### 不进入结构化表的情况

缺 ItemID 不进入 DIM/FACT；其余未映射商品字段仅留 RAW；多 SKU 冲突不猜测。

### 前端 / internal GET

GET /api/lingxing-sales/inventory；GET /api/internal-readonly/inventory/daily；GET /api/internal-readonly/products。

### 页面与渲染内容

每日销售明细的库存页显示库存字段；数据看板用于库存异常；PMC 库存一览继续叠加本地库存、采购和货件。

### 原值 / 计算口径

库存值为清洗后的接口原值；PMC 中本地 SKU 对多 ItemID 会按近 30 天销量分摊。

### 证据文件

src/syncLingxingDailyToDb.ts:535、348、616；src/lingxingSalesRoutes.ts:200；src/internalReadonlyApi.ts:558

### 当前状态

当前主同步实现

### 迁移风险备注

库存同步日期是拉取日，不是销售查询日；迁移时必须明确历史库存快照口径。

---

## LX-LINEAGE-003｜商品价格

**领星接口 / 来源：** POST /basicOpen/multiplatform/walmart/list，status=[0]

### 获取数据

在线商品的 item_id、msku、store_id、store_name、buy_box_price、price、listing_start_time。

### 原始存储 RAW

raw_lingxing_walmart_listing：capture_date、capture_date_la、store_id、item_id、msku、row_json。

### 清洗后存储 DIM/FACT

更新 dim_product.buy_box_price、buy_box_price_updated_at。

### 保存字段与关联键

按 store_id + item_id + msku 匹配；DIM 只更新价格两列。

### 清洗规则

优先大于 0 的 buy_box_price，缺失时取大于 0 的 price；不会覆盖人工商品字段。

### 不进入结构化表的情况

0 或空价格不更新；MSRP、促销价等仅留 row_json；匹配不到 DIM 商品不更新。

### 前端 / internal GET

无专用价格 GET；GET /api/ai-business/monthly-plan/todo 间接使用 dim_product.buy_box_price。

### 页面与渲染内容

目标管理的新品目标使用该价格作为无成交时的单价兜底。

### 原值 / 计算口径

新品销量 = ceil(上架日至月末天数 × 0.3)；销售目标 = 销量 × 价格；利润目标 = 销售目标 × 5%。

### 证据文件

src/syncWalmartListingPrice.ts:1、118、132；src/aiBusinessRoutes.ts:214

### 当前状态

当前实现

### 迁移风险备注

Buy Box 缺失会退挂牌价，字段语义混用；价格不能直接被称为纯 Buy Box 价。

---

## LX-LINEAGE-004｜销售

**领星接口 / 来源：** POST /basicOpen/platformStatisticsV2/saleStat/pageList，result_type=1 和 3

### 获取数据

platform_product_id 或 platformProductId、volumeTotal；1 代表销量，3 代表销售额。

### 原始存储 RAW

raw_lingxing_api（两种 result_type 的完整分页响应）。

### 清洗后存储 DIM/FACT

fact_sales_daily。

### 保存字段与关联键

stat_date、platform、store_id、store_name、item_id、msku、sku、sales_qty、order_count、sales_amount、source_raw_id。按 ItemID 将 volumeTotal 聚合后关联 dim_product。

### 清洗规则

从本轮 walmart/list 或 dim_product 回填 MSKU/SKU；找不到 MSKU 时整行跳过，避免空 MSKU 双计。

### 不进入结构化表的情况

无 MSKU 商品不进入 FACT；其他上游字段只留 RAW。

### 前端 / internal GET

GET /api/lingxing-sales/sales；GET /api/lingxing-sales/summary；GET /api/internal-readonly/lingxing-sales/daily-overview。

### 页面与渲染内容

每日销售明细销售页、销售汇总、数据看板、利润页、PMC 和清货模块。

### 原值 / 计算口径

销量和销售额是聚合后原值；代码将 order_count 直接写为 sales_qty，不是真实去重订单数。

### 证据文件

src/syncLingxingDailyToDb.ts:406、670；src/lingxingSalesRoutes.ts:65、103；src/internalReadonlyApi.ts:389

### 当前状态

当前主同步实现

### 迁移风险备注

订单数口径错误风险：新系统不能复用 order_count 作为订单去重数。

---

## LX-LINEAGE-005｜广告商品绩效 SP

**领星接口 / 来源：** POST /basicOpen/multiplatform/ads/reportAdItemSpList

### 获取数据

广告主、活动、广告组、ItemID、MSKU、曝光、点击、CTR、花费、归因订单、归因销售、ACOS、CPC、CVR、ROAS。

### 原始存储 RAW

raw_lingxing_api（手动和自动 SP 的完整分页响应）。

### 清洗后存储 DIM/FACT

fact_ads_product_daily。

### 保存字段与关联键

stat_date、店铺、advertiser_id、campaign/ad_group 的 ID 与名称、campaign_type、item_id、msku、impressions、clicks、ctr、ad_spend、orders、total_sales、acos、cpc、cvr、roas、source_raw_id。

### 清洗规则

字段别名归一与数值化；接口返回的比率未二次重算。

### 不进入结构化表的情况

无 ItemID 不进入 FACT；状态、预算、关键词等非商品绩效字段仅留 RAW。

### 前端 / internal GET

GET /api/lingxing-sales/ads；GET /api/internal-readonly/ads/product-daily；GET /api/internal-readonly/walmart-ads/list；GET /api/finance/ads-fee/list。

### 页面与渲染内容

每日销售明细广告页、广告费用报表、销售看板和利润页。

### 原值 / 计算口径

页面行级指标来自结构化原值；费用报表按日期、商品和广告类型 SUM(ad_spend)。

### 证据文件

src/syncLingxingDailyToDb.ts:466、724；src/lingxingSalesRoutes.ts:148；src/internalReadonlyApi.ts:462

### 当前状态

当前主同步实现

### 迁移风险备注

广告花费还存在 CSV 搜索词、SEM、账单等平行来源；新系统需定义唯一权威汇总口径，防重复。

---

## LX-LINEAGE-006｜广告关键词 SP

**领星接口 / 来源：** POST /basicOpen/multiplatform/ads/reportKeywordSpList；同时用 reportAdItemSpList 建商品映射

### 获取数据

活动、广告组、关键词、匹配类型、出价、曝光、点击、花费、归因订单、归因销售、CTR/CVR/ACOS/CPC/ROAS；商品接口提供 campaignId + adGroupId 到 ItemID 映射。

### 原始存储 RAW

raw_lingxing_api（关键词和商品映射接口响应）。

### 清洗后存储 DIM/FACT

fact_ads_keyword_daily。

### 保存字段与关联键

日期、店铺、广告主、活动/广告组、ItemID、MSKU、keyword、normalized_keyword、match_type、keyword_type、曝光点击花费订单销售、CTR/CVR/ACOS/CPC/ROAS、keyword_bid、source_type=manual_kw、extra_json.keywordId。

### 清洗规则

关键词 trim + lowercase；CTR/CVR/ACOS 百分数转小数；仅 store + item 唯一时回填 MSKU。

### 不进入结构化表的情况

空关键词不入 FACT；曝光、点击、花费、订单、销售五项全 0 不入 FACT；映射不到商品时 ItemID/MSKU 可空。

### 前端 / internal GET

GET /api/internal-readonly/ads/keyword-daily。

### 页面与渲染内容

广告系统手动广告/关键词明细。

### 原值 / 计算口径

行指标为清洗后原值；汇总 CTR、ACOS 等应从分子分母重算，不能平均行级比例。

### 证据文件

src/syncManualAdKeywordDaily.ts:250、305、359；src/internalReadonlyApi.ts:526

### 当前状态

当前实现

### 迁移风险备注

关键词花费不等于商品广告花费；不可将两个 FACT 无条件相加。

---

## LX-LINEAGE-007｜广告商品绩效 SB/SV

**领星接口 / 来源：** POST /basicOpen/multiplatform/ads/reportAdItemSbList；POST /basicOpen/multiplatform/ads/reportAdItemSvList

### 获取数据

SB/SV 的活动、广告组、ItemID、曝光、点击、花费、归因订单/销售和比率。

### 原始存储 RAW

raw_lingxing_api。

### 清洗后存储 DIM/FACT

fact_ads_product_daily，campaign_type 分别为 sba、video。

### 保存字段与关联键

字段与 SP 商品广告相同；同日按广告主、活动、广告组、ItemID UPSERT。

### 清洗规则

数值化；每页最多重试 3 次。

### 不进入结构化表的情况

无 itemId 或 adItemId 不入 FACT；其他字段仅留 RAW。

### 前端 / internal GET

与 SP 共用 GET /api/lingxing-sales/ads、/api/internal-readonly/ads/product-daily、/api/internal-readonly/walmart-ads/list、/api/finance/ads-fee/list。

### 页面与渲染内容

SB/SV 广告数据、广告费用报表、数据看板和利润页。

### 原值 / 计算口径

展示商品级指标；无 ItemID 的 SV 花费可在统一报表层按广告组分配。

### 证据文件

src/syncSbSvAdsDaily.ts:35、100、139；src/adsFeeReportRoutes.ts:51

### 当前状态

当前实现

### 迁移风险备注

旧文档若标记为探针已过时；但无 ItemID 广告费的商品归属仍是风险。

---

## LX-LINEAGE-008｜广告配置快照

**领星接口 / 来源：** queryCampaignSpList、queryGroupSpList、reportAdGroupSbList、queryAdGroupSvList、reportKeywordSpList、reportKeywordSbList、reportKeywordSvList

### 获取数据

活动、广告组、关键词的状态、预算、竞价策略、匹配类型、出价、创建时间、接口分页完整性。

### 原始存储 RAW

raw_lingxing_api（店铺 × 实体 × 广告类型 × 页）。

### 清洗后存储 DIM/FACT

fact_ads_campaign_snapshot_daily；fact_ads_group_snapshot_daily；fact_ads_keyword_snapshot_daily；fact_ads_snapshot_status。

### 保存字段与关联键

Campaign 保存状态、预算、策略、日期和 row_json；Group 保存活动/广告组状态和 row_json；Keyword 保存 keyword_id、名称、出价、状态、匹配类型和 row_json；状态表保存 API 总数、已抓取数、页数、是否完整和错误。

### 清洗规则

按快照日期保存；接口失败、分页触顶、记录数不足都显式记录完整性状态。

### 不进入结构化表的情况

无 keywordId 不进关键词快照；不可结构化字段保留 row_json 与 RAW。

### 前端 / internal GET

未发现稳定的前端专用 GET；主要供完整性哨兵与核查脚本读取。

### 页面与渲染内容

当前前端不直接展示，属于广告配置审计和缺失检测链路。

### 原值 / 计算口径

配置是某日快照，不是效果指标；状态表 is_complete 才能判定数据完整。

### 证据文件

src/syncAdsConfigSnapshotDaily.ts:72、258、281、297、318

### 当前状态

当前实现

### 迁移风险备注

queryAdGroupSvList 在源码注明参数错误，SV 广告组快照不能视为完整。

---

## LX-LINEAGE-009｜店铺与广告主

**领星接口 / 来源：** POST /pb/mp/shop/v2/getSellerList；POST /basicOpen/adReport/advertiser/list；辅以 reportAdItemSpList

### 获取数据

店铺 ID/名称、同步状态、授权状态、广告主 ID/名称及对应关系。

### 原始存储 RAW

当前 syncWalmartStores.ts 未写 RAW。

### 清洗后存储 DIM/FACT

dim_store_config；dim_store。

### 保存字段与关联键

dim_store_config 保存 platform、store_id、store_name、advertiser_id、advertiser_name、is_active、auth_status、first_seen_at、last_seen_at。

### 清洗规则

is_sync=1 且 status=1 才视为活动店铺；授权状态归一；失活可禁用但不覆盖人工启用。

### 不进入结构化表的情况

上游其它店铺/授权字段不保留 RAW。

### 前端 / internal GET

GET /api/lingxing-sales/stores；GET /api/finance/stores。

### 页面与渲染内容

全站店铺筛选、同步遍历店铺与广告主映射。

### 原值 / 计算口径

前端通常只渲染店铺 ID/名称；广告主 ID 用于后端同步。

### 证据文件

src/syncWalmartStores.ts:20、149；src/lingxingSalesRoutes.ts:49

### 当前状态

当前实现

### 迁移风险备注

没有 RAW 审计留痕；迁移时应补齐店铺授权快照与历史变更。

---

## LX-LINEAGE-010｜商品成本与商品名

**领星接口 / 来源：** POST /erp/sc/routing/data/local_inventory/batchGetProductInfo

### 获取数据

本地 SKU、cg_price、product_logistics_relation.US_cg_transport_costs、产品名称及其它商品资料。

### 原始存储 RAW

raw_lingxing_api（批量响应）。

### 清洗后存储 DIM/FACT

dim_product_cost_config；另一个脚本更新 dim_product.product_name，并可补空 SKU。

### 保存字段与关联键

成本表保存店铺、ItemID、MSKU、SKU、purchase_cost、first_mile_shipping_cost、effective_date、source_system、source_raw_id。

### 清洗规则

只更新领星采购和头程成本，不覆盖人工 delivery_fee；名称/SKU 更新要求唯一匹配且非歧义。

### 不进入结构化表的情况

SKU 为空、采购与头程同时为空时跳过；歧义商品不更新；其它字段留 RAW。

### 前端 / internal GET

GET /api/lingxing-sales/daily-metrics；GET /api/internal-readonly/lingxing-sales/daily-overview；GET /api/internal-readonly/products；利润、清货、财务接口间接读取。

### 页面与渲染内容

利润明细、看板、订单利润、单品现金利润、清货中心。

### 原值 / 计算口径

采购与头程常为 CNY，利润与现金利润会按不同汇率换 USD；不是直接显示接口金额。

### 证据文件

src/syncLingxingProductCost.ts:32、155、381；src/syncProductNameFromLingxing.ts:547

### 当前状态

当前实现

### 迁移风险备注

DIM 表还含人工配送费；迁移必须区分人工成本与领星成本的覆盖优先级。

---

## LX-LINEAGE-011｜采购进度

**领星接口 / 来源：** POST /erp/sc/routing/data/local_inventory/purchaseOrderList

### 获取数据

采购单号、状态、发货状态、仓库、下单/创建/审核/更新时间，商品 SKU/MSKU/名称、实采/入库/收货数量、预计到货日。

### 原始存储 RAW

raw_lingxing_api。

### 清洗后存储 DIM/FACT

fact_purchase_order；fact_purchase_order_item。

### 保存字段与关联键

头表：order_sn、状态、仓库和日期字段；明细：order_sn、sku、msku、product_name、quantity_real、quantity_entry、quantity_receive、expect_arrive_time、source_raw_id。

### 清洗规则

按订单和订单商品 UPSERT，状态与数量可覆盖更新。

### 不进入结构化表的情况

缺订单号不写头表；缺 SKU/MSKU 的明细不能形成有效采购明细；其它字段只留 RAW。

### 前端 / internal GET

GET /api/pmc/inventory/overview。

### 页面与渲染内容

库存一览表中的采购在途/未收货数量。

### 原值 / 计算口径

PMC 将采购按本地 SKU 对应商品分摊；不是逐采购单原样展示。

### 证据文件

src/syncPurchaseOrders.ts:19、94、115；src/pmcInventoryRoutes.ts:38

### 当前状态

当前实现

### 迁移风险备注

采购数量字段需确认哪个代表开放采购量，不能只按表名推断。

---

## LX-LINEAGE-012｜采购现金支出

**领星接口 / 来源：** POST /erp/sc/routing/data/local_inventory/purchaseOrderList

### 获取数据

采购单金额、商品金额、运费、其它费用、供应商、创建人、数量、付款状态、币种及商品行金额。

### 原始存储 RAW

raw_lingxing_api。

### 清洗后存储 DIM/FACT

fact_purchase_cash；fact_purchase_cash_item。

### 保存字段与关联键

头表：order_sn、order_time/create_time、amount_total、goods_amount、shipping_amount、other_amount、supplier_name、quantity_total、pay_status_text、currency_code；明细：sku、msku、sid、quantity、unit_price、amount。

### 清洗规则

记账日优先 order_time，否则 create_time；相同 SKU + MSKU 聚合；unit_price = amount / quantity；金额差异只告警。

### 不进入结构化表的情况

无有效日期跳过；过复核关闭点的历史订单不继续漂移更新；其它字段仅 RAW。

### 前端 / internal GET

GET /api/finance/item-cash-profit；GET /api/finance/item-cash-profit-v2。

### 页面与渲染内容

单品现金利润。

### 原值 / 计算口径

采购支出按商品归属、月份和汇率汇总；前端展示现金分类和利润，不展示原采购单行。

### 证据文件

src/syncPurchaseCash.ts:35、212、233；src/aiFinanceIcpV2Routes.ts:94

### 当前状态

当前实现

### 迁移风险备注

复核关闭后不更新会造成历史订单与领星后续修订不一致。

---

## LX-LINEAGE-013｜库存批次与库存成本

**领星接口 / 来源：** POST /erp/sc/routing/data/local_inventory/getBatchDetailList

### 获取数据

仓库、批次、关联单、类型、商品、SKU/MSKU、库存数量、在途/良品/次品、采购/其它/头程/库存单价和金额、库龄、供应商。

### 原始存储 RAW

raw_lingxing_api。

### 清洗后存储 DIM/FACT

fact_lingxing_batch。

### 保存字段与关联键

保存 wid、wh_name、batch_no、order_sn、type、商品、SKU/MSKU、各种数量、purchase_price、other_price、head_stock_price、stock_price、stock_cost、amount、fee、批次日期、inventory_age、source_batch_json、purchase_sns_json、supplier_names。

### 清洗规则

按 wid + batch_no UPSERT；批次 JSON 与采购单号 JSON 也保留。

### 不进入结构化表的情况

缺 batch_no 或 SKU 跳过；价格和金额守恒异常只告警，不拒绝；未映射字段仍在 JSON/RAW。

### 前端 / internal GET

无专用明细 GET；GET /api/finance/item-cash-profit 和 /item-cash-profit-v2 间接读取。

### 页面与渲染内容

单品现金利润中的期初/库存资产。

### 原值 / 计算口径

stock_cost 等是领星批次原值，页面再按商品、月份和币种汇总。

### 证据文件

src/syncLingxingBatch.ts:27、160；src/aiFinanceRoutes.ts:1307

### 当前状态

当前实现

### 迁移风险备注

批次守恒不通过仍可入库；新系统应将异常状态显式化。

---

## LX-LINEAGE-014｜本地仓库存

**领星接口 / 来源：** POST /erp/sc/data/local_inventory/warehouse；POST /erp/sc/routing/data/local_inventory/inventoryDetails

### 获取数据

仓库有效状态与各仓 SKU 实时库存数量。

### 原始存储 RAW

inventoryDetails 响应 → raw_lingxing_api；仓库列表仅作筛选，未见独立 RAW。

### 清洗后存储 DIM/FACT

fact_local_inventory_daily。

### 保存字段与关联键

snapshot_date、sku、qty、source_raw_id；按有效仓库汇总 SKU 库存。

### 清洗规则

排除无效/删除/异常仓库；候选数量字段归一；日期取拉取日。

### 不进入结构化表的情况

无 SKU、无效仓库、异常行不入 FACT；库位等不结构化。

### 前端 / internal GET

GET /api/pmc/inventory/overview。

### 页面与渲染内容

库存一览表的本地库存。

### 原值 / 计算口径

同本地 SKU 对多 ItemID：按近30天销量分摊，无销量均分，末行吸收舍入尾差。

### 证据文件

src/syncLocalInventory.ts:17、32、133；src/pmcInventoryRoutes.ts:130

### 当前状态

当前实现

### 迁移风险备注

仓库列表不留 RAW；SKU→商品一对多分摊会使前端库存不是领星原始仓库数。

---

## LX-LINEAGE-015｜汇率

**领星接口 / 来源：** POST /erp/sc/routing/finance/currency/currencyMonth

### 获取数据

月份、币种编码/名称/图标、官方汇率 rate_org、我的汇率 my_rate、领星更新时间。

### 原始存储 RAW

raw_lingxing_api。

### 清洗后存储 DIM/FACT

fact_lingxing_fx_rate。

### 保存字段与关联键

rate_month、currency_code、currency_name、icon、rate_org、my_rate、lx_update_time、source_raw_id。

### 清洗规则

按月 + 币种 UPSERT；使用时优先 my_rate，否则 rate_org。

### 不进入结构化表的情况

无效月份或币种跳过；其它元数据仅留 RAW。

### 前端 / internal GET

GET /api/finance/fx/lingxing。

### 页面与渲染内容

财务工具汇率页；发货、采购和现金利润也间接使用。

### 原值 / 计算口径

汇率页展示原值；头程和现金利润多按归属月的上一个月汇率折算。

### 证据文件

src/syncLingxingFxRate.ts:31、156；src/aiFinanceRoutes.ts:176

### 当前状态

当前实现

### 迁移风险备注

不同模块的汇率月份与兜底规则必须统一，否则利润会不一致。

---

## LX-LINEAGE-016｜头程发货与分摊

**领星接口 / 来源：** POST /cepf/warehouse/api/openApi/queryShippingListPage

### 获取数据

发货单状态、物流、实际运费/其它费用及币种、商品发货量、按品采购价、税费、头程、WFS 库存价。

### 原始存储 RAW

raw_lingxing_api。

### 清洗后存储 DIM/FACT

fact_shipping_order；fact_shipping_first_let。

### 保存字段与关联键

头表保存物流、日期、freight_cny/usd、other_cny/usd、alloc_sum、alloc_diff、implied_rate；明细保存货件、店铺、MSKU/SKU/GTIN/ItemID、delivery_num、各成本和 match_status。

### 清洗规则

只取实际费用；cash_date 优先 actual_delivery_time，缺失退 delivery_time；USD 用上月领星汇率折 CNY；用 MSKU + 数量匹配货件。

### 不进入结构化表的情况

expected_transportation_cost 与 expected_other_cost 不入结构化费用；匹配歧义/失败以状态保留；缺 shipping_code 跳过。

### 前端 / internal GET

GET /api/finance/item-cash-profit；GET /api/finance/item-cash-profit-v2 间接读取。

### 页面与渲染内容

单品现金利润中的头程成本与财务哨兵。

### 原值 / 计算口径

按品头程 = per_first_let_cost × delivery_num；alloc_diff = 分摊合计 − 整单费用 CNY 等值。

### 证据文件

src/syncShippingOrders.ts:1、195、310、342；src/aiFinanceRoutes.ts:1203

### 当前状态

当前实现

### 迁移风险备注

匹配不唯一的数据仍存在；作废单不参加守恒告警，迁移时应保留审计状态。

---

## LX-LINEAGE-017｜WFS货件

**领星接口 / 来源：** POST /cepf/warehouse/api/openApi/queryWFSCargoPage

### 获取数据

货件 ID/编号、店铺、状态及状态时间、物流编码、更新日；商品 MSKU/SKU/GTIN/名称、申报/发货/签收/损坏数量。

### 原始存储 RAW

raw_lingxing_api。

### 清洗后存储 DIM/FACT

fact_wfs_shipment；fact_wfs_shipment_item；event_arrival_notify。

### 保存字段与关联键

头表保存 shipment_id、cargo_code、状态和状态时间；明细保存 msku、sku、gtin、product_name、declare_num、shipments_num、received_num、damaged_qty。

### 清洗规则

状态必须为 0 至 4；数量安全转数；负责人只在店铺 + MSKU 唯一时映射；接收中/关闭跃迁生成事件。

### 不进入结构化表的情况

缺货件 ID/店铺、状态非法、商品无 MSKU 不入 FACT；未映射负责人留空。

### 前端 / internal GET

GET /api/pmc/inventory/overview。

### 页面与渲染内容

库存一览表的 WFS 在途与到货通知。

### 原值 / 计算口径

在途 = max(shipments_num − received_num, 0)，仅未关闭/未取消货件；前端显示聚合值。

### 证据文件

src/syncWfsShipments.ts:95、210、254、277；src/pmcInventoryRoutes.ts:96

### 当前状态

当前实现

### 迁移风险备注

货件状态与通知是事件型数据；补历史数据时必须避免重复通知。

---

## LX-LINEAGE-018｜月度结算利润

**领星接口 / 来源：** POST /basicOpen/multiplatform/profit/report/msku

### 获取数据

已实证：storeId、storeName、msku、localSku、currencyCode、salesNum、salesAmount、purchaseAmount、transportationAmount；其余字段可能存在。

### 原始存储 RAW

raw_lingxing_api。

### 清洗后存储 DIM/FACT

fact_settlement_msku_monthly。

### 保存字段与关联键

platform、store_id、store_name、msku、settlement_month、currency_code、sales_amount、sales_num、purchase_amount、transportation_amount、extra_json、amount_hash、source_raw_id。

### 清洗规则

store_id 使用请求侧值避免 JSON 大整数精度损坏；整行另存 extra_json。

### 不进入结构化表的情况

缺 MSKU 跳过；促销、退款、佣金等未实证字段不拆列，但在 extra_json/RAW 可追溯；totalSum 禁用。

### 前端 / internal GET

无专用结算明细 GET；GET /api/finance/item-cash-profit 和 /item-cash-profit-v2 间接读取。

### 页面与渲染内容

单品现金利润、历史销量和期初成本链。

### 原值 / 计算口径

按月聚合、ItemID 归属和币种换算后展示，不是结算行原样。

### 证据文件

src/syncSettlementMonthly.ts:1、77、167；src/aiFinanceIcpV2Routes.ts:459

### 当前状态

当前实现

### 迁移风险备注

extra_json 是重要保底字段；新系统需先字段实证后再拆 promotion/refund/commission。

---

## LX-LINEAGE-019｜订单结算 WFS费率

**领星接口 / 来源：** POST /basicOpen/multiplatform/profit/report/order

### 获取数据

订单级 uniqueId、MSKU、销量、平台物流金额、订单日期等。

### 原始存储 RAW

raw_lingxing_settlement_order：capture_batch、msku_query、unique_id、row_index、row_json。

### 清洗后存储 DIM/FACT

dim_product_wfs_fee_auto。

### 保存字段与关联键

平台、店铺、MSKU、fee、sample_units、fee_orders、skipped_no_qty、mode_count、window_start/end。

### 清洗规则

单件费率 = abs(平台物流金额之和) / 销量之和；按店铺 + MSKU 取众数，平票取较新订单；至少10件样本。

### 不进入结构化表的情况

无销量费用行不参与费率；样本不足费率为空；其它订单字段保留 row_json。

### 前端 / internal GET

GET /api/pmc/wfs-fee/list；利润链间接读取。

### 页面与渲染内容

WFS费用异常、旧利润和产品管理。

### 原值 / 计算口径

实际费率 × 销量形成 WFS 成本；不是直接采用人工配送费。

### 证据文件

src/syncWfsFeeFromSettlement.ts:34、205、250；src/pmcWfsFeeRoutes.ts:42

### 当前状态

当前实现

### 迁移风险备注

众数费率是估计值且有最小样本门槛；应保留样本数和时间窗。

---

## LX-LINEAGE-020｜售后退款

**领星接口 / 来源：** POST /basicOpen/openapi/multiplatform/walmart/returnOrder/list

### 获取数据

退货单、店铺、退货类型、申请日期、商品 MSKU、数量、退款金额、状态、原因和说明。

### 原始存储 RAW

raw_walmart_return_order：头部与单个商品合成 row_json，并保存关键字段。

### 清洗后存储 DIM/FACT

fact_refund_daily。

### 保存字段与关联键

RAW 保存订单、商品、店铺、类型、状态、日期、数量、line_total_amount、原因；FACT 保存店铺、ItemID、MSKU、refund_date、refund_orders、refund_qty、refund_amount。

### 清洗规则

退款日取 returnOrderDate；金额取含税 lineTotalAmount；店铺 ID 做精度修复；按店铺 + MSKU + 日重算。

### 不进入结构化表的情况

仅 returnType=REFUND 进 FACT；REPLACEMENT/PREORDER 只留 RAW；缺退货单号/MSKU 跳过。

### 前端 / internal GET

GET /api/profit-v2/order-profit；GET /api/sales-detail-v2/list。

### 页面与渲染内容

订单利润 V2、每日销售明细 V2。

### 原值 / 计算口径

订单利润扣 refund_amount；30天退款率 = 30天退款件数 / 30天销量；INITIATED 与 COMPLETED 都计入。

### 证据文件

src/syncWalmartReturnOrders.ts:26、103、146；src/orderProfitV2Routes.ts:166

### 当前状态

当前实现

### 迁移风险备注

如果新系统只认完成退款，结果会与旧系统不同；须先确定退款状态口径。

---

## LX-LINEAGE-021｜账期与对账单

**领星接口 / 来源：** POST /basicOpen/multiplatformFinance/walmart/bill/payout/list；POST /basicOpen/multiplatformFinance/walmart/bill/statement/list

### 获取数据

账期、应付金额、支付日；交易日期、商品、交易类型/说明、费用类别、金额、币种、广告活动、佣金激励。

### 原始存储 RAW

raw_lingxing_api。

### 清洗后存储 DIM/FACT

fact_reconciliation_period；fact_reconciliation_item；fact_ad_credit_detail；fact_commission_saving；event_finance_sentinel_alert。

### 保存字段与关联键

账期头保存期间与应付；明细保存期间、日期、MSKU/Item、归一费用类别、金额、交易数、币种；返还逐行保存；Sale 行佣金激励另行聚合。

### 清洗规则

费用类别归一为销售、退款、WFS、广告、入库运输、移除、仓储、SEM、其他等；未知类目归 other。

### 不进入结构化表的情况

PaymentSummary 不入交易 FACT；非返还不入返还表；非 Sale 激励不入佣金节省表；原文仍在 RAW。

### 前端 / internal GET

GET /api/finance/credits/list；GET /api/finance/commission-savings/list；GET /api/finance/item-cash-profit(-v2)。

### 页面与渲染内容

返还明细、单品现金利润。

### 原值 / 计算口径

现金利润按归一费用类别归入收入/支出；广告返还页面优先改用 Connect 发票，避免与 statement 重复。

### 证据文件

src/syncWalmartBillDaily.ts:37、159、294、321、352；src/aiFinanceRoutes.ts:50、97

### 当前状态

当前实现

### 迁移风险备注

类别映射规则属于核心财务口径；迁移必须版本化并保留 unknown/other。

---

## LX-LINEAGE-022｜渠道订单销量

**领星接口 / 来源：** POST /pb/mp/order/v2/list

### 获取数据

订单时间、状态、平台、店铺、商品、MSKU或平台商品号、数量、配送类型。

### 原始存储 RAW

raw_lingxing_api。

### 清洗后存储 DIM/FACT

Walmart：fact_mp_sales_channel_daily；其它渠道：fact_channel_clearance_sales_daily。

### 保存字段与关联键

Walmart 保存 WFS、自发货、混合销量和订单数；其它渠道保存 stat_date、platform、platform_ref、local_sku、sales_qty、order_cnt。

### 清洗规则

配送类型 3=WFS、2=自发货、1=混合；取消/删除订单排除；窗口内消失旧键归零。

### 不进入结构化表的情况

取消、删除订单不进 FACT；映射不到 Walmart 商品时无法可靠归属；订单其它字段仅 RAW。

### 前端 / internal GET

GET /api/clearance-center/list；GET /api/ai-business/monthly-plan/todo。

### 页面与渲染内容

清货中心、目标管理。

### 原值 / 计算口径

清货显示近7日和当月渠道销量；目标管理在上月覆盖至少25日时以 WFS 销量参与豁免判断。

### 证据文件

src/syncMpOrdersChannelDaily.ts:24、346、447；src/clearanceCenterRoutes.ts:134；src/aiBusinessRoutes.ts:924

### 当前状态

当前实现

### 迁移风险备注

请求窗口用北京时间边界，Walmart 业务日通常为美西，可能有跨日偏差。

---

## LX-LINEAGE-023｜促销折扣与快速销量

**领星接口 / 来源：** POST /pb/mp/order/v2/list

### 获取数据

订单商品行：订单号、明细号、购买日、店铺、MSKU、商品价、折扣额、数量和状态。

### 原始存储 RAW

raw_mp_order_item 保存全部商品行；raw_mp_order_discount 只保存折扣非0行；均保留 row_json。

### 清洗后存储 DIM/FACT

fact_promo_discount_daily；fact_sales_fast_daily。

### 保存字段与关联键

折扣表保存日期、店铺、ItemID、MSKU、订单数、数量、正值折扣金额；快速表保存 sales_qty、sales_amount、order_cnt。

### 清洗规则

去货币符号、取美西日期、排除取消单；ItemID 由 dim_product 映射；普通日更近2日，回补最多31日。

### 不进入结构化表的情况

折扣为0不进折扣 RAW/FACT但仍进全量商品 RAW；无法映射 ItemID 时快速表写空字符串。

### 前端 / internal GET

GET /api/profit-v2/order-profit；GET /api/sales-detail-v2/list。

### 页面与渲染内容

订单利润 V2、每日销售明细 V2。

### 原值 / 计算口径

绝对折扣 >= 商品价 - 0.01 判为送样，销售、销量及线性成本剔除；快速销量只在利润日整日缺失时兜底，利润字段留空。

### 证据文件

src/syncMpOrderDiscount.ts:1、167、194、233、276；src/salesDetailV2Routes.ts:117

### 当前状态

当前实现

### 迁移风险备注

送样阈值规则硬编码，且快速销量并非权威利润数据；迁移时要明确标记兜底行。

---

## LX-LINEAGE-024｜TEMU清货刊登

**领星接口 / 来源：** POST /basicOpen/multiplatform/temu/list

### 获取数据

TEMU 刊登的 MSKU、平台商品标识、状态、店铺、近30天销量等。

### 原始存储 RAW

raw_lingxing_api。

### 清洗后存储 DIM/FACT

biz_clearance_other_channel。

### 保存字段与关联键

保存 sku=msku、mskus、owner、channel='TEMU'、platform_ref、manual_stock=0、status、added_by、remark。

### 清洗规则

仅 status=102 且符合前缀规则的行；按 MSKU 去重；INSERT IGNORE。

### 不进入结构化表的情况

店铺名、近30天销量等不结构化；已存在记录不自动更新；不符合筛选仅 RAW。

### 前端 / internal GET

GET /api/clearance-center/list。

### 页面与渲染内容

清货中心的其他渠道行。

### 原值 / 计算口径

前端销量来自渠道订单聚合，不直接展示领星列表的近30天销量字段。

### 证据文件

src/syncTemuClearanceListing.ts:18、56、70、100；src/clearanceCenterRoutes.ts:134

### 当前状态

当前实现

### 迁移风险备注

INSERT IGNORE 会使已存在商品的店铺/状态/负责人可能陈旧。

---

## LX-LINEAGE-025｜AI PMC直连补货

**领星接口 / 来源：** purchaseOrderList、saleStat/pageList、inventoryDetails、shipmentPlanLists、queryWFSCargoPage

### 获取数据

采购、销量、本地库存、FBA/WFS货件中补货任务需要的日期、状态、SKU/MSKU、数量。

### 原始存储 RAW

该链主要内存处理，未走上述 MySQL RAW/FACT。

### 清洗后存储 DIM/FACT

飞书 PMC 任务、补货台账和通知；不是 MySQL 数据仓库链。

### 保存字段与关联键

采购单归一为订单号、状态、审核/下单/到仓时间和商品数量；库存/销量按 SKU 聚合；货件筛选近期未完成记录。

### 清洗规则

调用含重试；仅保留补货计算所需字段。

### 不进入结构化表的情况

未参与补货判断的接口字段不保存；进程失败时内存数据不留档。

### 前端 / internal GET

无浏览器 GET；业务人员通过飞书 PMC 表格和通知查看。

### 页面与渲染内容

PMC 看板、补货任务、逾期提醒。

### 原值 / 计算口径

补货结果为内存计算输出，与 MySQL PMC 库存一览是并行链，不能默认同口径。

### 证据文件

src/ai_pmc/fetchLingxing.ts:17、88、175；src/ai_pmc/fetchShipments.ts:23、77、106；src/ai_pmc/runReplenishment.ts:43

### 当前状态

代码存在，运行状态待确认

### 迁移风险备注

缺 RAW 与 MySQL 追溯；新系统建议统一写入可审计任务与输入快照。

---

## LX-LINEAGE-026｜利润派生链

**领星接口 / 来源：** 非新增领星接口：组合 sales、ads、inventory、cost、WFS fee、退款、仓储、送样订单。

### 获取数据

旧链把日利润快照写入 raw_feishu_table 的语义表 order_profit_daily；输入 RAW 见各上游链。

### 原始存储 RAW

fact_profit_daily；订单利润 V2 在查询时再次聚合。

### 清洗后存储 DIM/FACT

日利润包含日期、店铺、ItemID、MSKU、SKU、负责人、销售、广告、库存、配送费、采购/头程、佣金、利润、毛利率等。

### 保存字段与关联键

旧日利润：汇率6.6，特殊店铺佣金15%其余12%；V2 剔除 CS、送样，扣退款/仓储，并采用历史成本快照。

### 清洗规则

无销售基座不生成日利润；旧链缺成本时常按0参与，可能高估；fact_profit_daily 构建脚本不在当前副本。

### 不进入结构化表的情况

GET /api/lingxing-sales/daily-metrics；GET /api/profit-v2/order-profit；GET /api/sales-detail-v2/list；GET /api/lingxing-sales/dashboard*。

### 前端 / internal GET

利润明细、数据看板、订单利润 V2、每日销售明细 V2。

### 页面与渲染内容

V2：净销售 = 销售 - 送样销售；订单利润 = 净销售 - 广告 - WFS - 佣金 - 采购 - 头程 - 退款 - 仓储；ROI = 订单利润 × 6.6 / (采购CNY + 头程CNY)。

### 原值 / 计算口径

src/services/lingxingDailyMetricsService.ts:1、120；src/orderProfitV2Routes.ts:322；src/salesDetailV2Routes.ts:472

### 证据文件

派生链存在，构建器缺失

### 当前状态

这是迁移最高风险链：输入来源、日界、成本快照、送样规则、汇率与缺失成本策略必须逐项验收。

### 迁移风险备注

未记录

---

## LX-LINEAGE-027｜导入：WFS仓储 CSV

**领星接口 / 来源：** 非领星 API。Seller Center 仓储 CSV 导入。

### 获取数据

报告期、总费用、GTIN、SKU、ItemID、标准/长期/旺季平均库存、天数、最终费用、原金额、折扣、尺寸重量、日费率。

### 原始存储 RAW

raw_walmart_storage_csv：row_no=0 为摘要，其余逐行 row_json。

### 清洗后存储 DIM/FACT

fact_wfs_storage_fee；异步展开 fact_storage_fee_daily。

### 保存字段与关联键

保存店铺、SKU、GTIN、ItemID、报告期、平均库存、最终费用、原金额、折扣、尺寸、重量、各档日费率、source_task_id。

### 清洗规则

兼容新旧表头；旧版缺原金额/折扣时 original=final、discount=0；优先文件 ItemID，否则按店铺+SKU 唯一映射；账期守恒后写入。

### 不进入结构化表的情况

无效 GTIN、空 SKU、说明行跳过；费用差>0.5或非同起止重叠账期整批拒绝；空报告仅留 RAW 摘要。

### 前端 / internal GET

GET /api/finance/storage/list；GET /api/pmc/storage/list；利润 V2 读取 fact_storage_fee_daily。

### 页面与渲染内容

财务工具、仓储费、订单利润 V2。

### 原值 / 计算口径

日摊按周账单分段或账期均摊，最后一天吸收尾差；利润扣日摊，不扣整期原费用。

### 证据文件

src/aiFinanceRoutes.ts:241、274、406、444；src/expandStorageFeeDaily.ts:25；admin-frontend/src/AiFinanceTools.tsx:153

### 当前状态

当前前端导入

### 迁移风险备注

导入成功后异步 spawn 日摊脚本；若子进程失败，原始仓储费用已写入而利润日摊可能未刷新。

---

## LX-LINEAGE-028｜导入：WFS入库运输 CSV

**领星接口 / 来源：** 非领星 API。Seller Center 入库运输 CSV 导入。

### 获取数据

报告期、Shipment ID、Delivery Date、Service Type、Reason Code、Actual Charge 等运费行。

### 原始存储 RAW

raw_walmart_inbound_csv：摘要行和全部原始行 row_json。

### 清洗后存储 DIM/FACT

fact_inbound_freight_alloc。

### 保存字段与关联键

保存店铺、cargo_code、shipment_id、结算月、报告期、MSKU、ItemID、申报量、货件总运费、分摊额、alloc_basis、source_task_id。

### 清洗规则

先按货件汇总 Actual Charge；匹配 WFS 货件；按 shipments_num 分摊，缺失退 declare_num，末行吸收尾差。

### 不进入结构化表的情况

Service Type/Reason Code 不拆列但留 RAW；货件匹配不到时保存 msku 空、alloc_basis=none；重叠账期拒绝。

### 前端 / internal GET

GET /api/finance/inbound/list；GET /api/finance/inbound/unmatched；GET /api/pmc/inbound/list。

### 页面与渲染内容

财务工具、入库运输、单品现金利润。

### 原值 / 计算口径

匹配成功后按品成本；未匹配额保留待处理，不会静默消失。

### 证据文件

src/aiFinanceRoutes.ts:515、553、636、714、766；admin-frontend/src/AiFinanceTools.tsx:172

### 当前状态

当前前端导入

### 迁移风险备注

未匹配货件的金额会暂挂；迁移需保留重新分摊流程和余额核对。

---

## LX-LINEAGE-029｜导入：清货目标 XLSX/CSV

**领星接口 / 来源：** 非领星 API。POST /api/clearance-center/parse-xlsx 和 /import-monthly-target。

### 获取数据

渠道、ItemID、店铺、SKU、负责人、本月目标件数、本月已清。

### 原始存储 RAW

不保存文件或原始行，仅在内存解析 grid。

### 清洗后存储 DIM/FACT

Walmart 目标写 biz_monthly_plan；其它渠道更新 biz_clearance_other_channel 的 monthly_target、target_month、monthly_cleared。

### 保存字段与关联键

按渠道、店铺、ItemID、负责人关联；目标数量和月已清数量保存。

### 清洗规则

最多1000行；负责人必须等于选择负责人；校验商品、店铺、负责人和目标正整数。

### 不进入结构化表的情况

错误行逐行拒绝，原文件与未使用列不留存。

### 前端 / internal GET

GET /api/clearance-center/list。

### 页面与渲染内容

清货中心。

### 原值 / 计算口径

完成率与状态是导入目标 + 后续订单销量的组合结果，不是文件原字段。

### 证据文件

src/clearanceCenterRoutes.ts:828、899；admin-frontend/src/ClearanceCenter.tsx:331

### 当前状态

当前前端导入

### 迁移风险备注

没有原文件审计留存；新系统如需可追溯应额外存文件哈希、原表头和拒绝行。

---

## LX-LINEAGE-030｜导入：其他渠道清货 XLSX/CSV

**领星接口 / 来源：** 非领星 API。POST /api/clearance-center/import-other-channel。

### 获取数据

产品 SKU、负责人、渠道、平台商品标识、库存数量、备注。

### 原始存储 RAW

不保存文件或原始行。

### 清洗后存储 DIM/FACT

biz_clearance_other_channel。

### 保存字段与关联键

sku、mskus、owner、channel、platform_ref、manual_stock、status、added_by、remark。

### 清洗规则

允许 Walmart、Amazon、Shein、TEMU、TikTok；相同 SKU+渠道按规则更新或重新激活。

### 不进入结构化表的情况

负责人不一致、渠道非法、SKU或平台标识为空的行拒绝；文件原行不留存。

### 前端 / internal GET

GET /api/clearance-center/list。

### 页面与渲染内容

清货中心的其他渠道行。

### 原值 / 计算口径

销量来自 fact_channel_clearance_sales_daily，不是导入文件数量；手工库存为导入原值。

### 证据文件

src/clearanceCenterRoutes.ts:998、1048、134；admin-frontend/src/ClearanceCenter.tsx:351

### 当前状态

当前前端导入

### 迁移风险备注

平台标识关联策略需要固定，否则后续订单销量无法稳定回填到清货项。

---

## LX-LINEAGE-031｜导入：月度规划 XLSX/CSV

**领星接口 / 来源：** 非领星 API。POST /api/ai-business/monthly-plan/parse-xlsx 和 /monthly-plan。

### 获取数据

店铺、ItemID、MSKU、月报问题、新品标记、正常运营、两项指标与目标、销售/利润目标、说明。

### 原始存储 RAW

不保存文件，仅在内存解析 grid。

### 清洗后存储 DIM/FACT

biz_monthly_plan。

### 保存字段与关联键

plan_month、店铺、ItemID、MSKU、负责人、issue_text、normal_operation、indicator1/2 类型和目标、deadline、note、target_sales_amount、target_gross_profit、操作人。

### 清洗规则

负责人/月份/清单强校验；非新品必须销售和利润目标；两个指标不得重复；截止日自动取当月最后一天。

### 不进入结构化表的情况

空填写行跳过；他人、豁免、清单外产品拒绝；新品忽略人工目标，走公司公式；文件不留存。

### 前端 / internal GET

GET /api/ai-business/monthly-plan/todo；GET /api/ai-business/monthly-plan/months。

### 页面与渲染内容

目标管理。

### 原值 / 计算口径

新品目标为系统计算；上月销售/利润/广告来自旧利润快照聚合；豁免由 WFS 库存、WFS销量和在途共同判断。

### 证据文件

src/aiBusinessRoutes.ts:924、1114、1178、1215；admin-frontend/src/MonthlyPlanPanel.tsx:220

### 当前状态

当前前端导入

### 迁移风险备注

上月实际依赖 raw_feishu_table 的旧利润快照，迁移时需替换或回填该基座。

---

## LX-LINEAGE-032｜导入：自动广告搜索词 CSV

**领星接口 / 来源：** 非领星 API。独立 Walmart Ads 导入服务，主导入器不在当前副本。

### 获取数据

日期、ItemID/名称、搜索词、Campaign/Ad Group、竞价关键词、匹配类型、曝光、点击、花费、订单、归因销售、售出件数、加购、详情页浏览。

### 原始存储 RAW

raw_walmart_ads_csv：任务、店铺、操作人和每行 row_json。

### 清洗后存储 DIM/FACT

fact_ads_keyword_daily，source_type=walmart_auto_csv。

### 保存字段与关联键

日期、店铺、Campaign/Ad Group、ItemID、商品名、搜索词、匹配类型、曝光、点击、CTR、花费、订单、CVR、归因销售、ACOS/CPC/ROAS、加购、任务。

### 清洗规则

按日期 + Campaign + AdGroup + 商品 + 搜索词聚合，重新计算指标；跨 Campaign 不得合并。

### 不进入结构化表的情况

竞价策略、目标 ROAS、竞价关键词、售出件数、详情页浏览等没有独立列但保留 RAW。

### 前端 / internal GET

GET /api/internal-readonly/ads/keyword-daily；独立广告系统读接口主实现不在副本。

### 页面与渲染内容

自动广告、全部广告、导入任务。

### 原值 / 计算口径

CSV 提供搜索词和14天归因细节；总广告费仍应以商品广告 FACT 为权威，不能与其重复累计。

### 证据文件

scripts/rebuild_auto_ads_fact.py:1、76、94；src/internalReadonlyApi.ts:526；admin-frontend/src/AppShell.tsx:43

### 当前状态

导入证据不完整

### 迁移风险备注

生产 csv_processor 和 API 主实现缺失；迁移前必须补齐代码及运行任务。

---

## LX-LINEAGE-033｜导入：SEM每日报表 CSV

**领星接口 / 来源：** 非领星 API。POST /api/walmart-sem/upload，类型 sem_daily。

### 获取数据

日期、Campaign ID/名称、曝光、点击、广告花费、归因销售等。

### 原始存储 RAW

raw_walmart_sem_csv：任务、类型、行号、日期、店铺、操作人和 row_json。

### 清洗后存储 DIM/FACT

fact_ads_product_daily，campaign_type=sem；可用 dim_sem_campaign_item 补商品归属。

### 保存字段与关联键

日期、店铺、Campaign、ItemID、MSKU、曝光、点击、CTR、花费、orders=0、销售、ACOS、CPC、CVR=NULL、ROAS、任务。

### 清洗规则

按日期 + Campaign 聚合；ItemID 先从活动名解析有效数字，再用 dim_sem_campaign_item；同店同日旧 SEM 行先清除以防改名重复。

### 不进入结构化表的情况

归属失败时仍保留 FACT，但 ItemID/MSKU 为空；其它 CSV 列留 RAW。

### 前端 / internal GET

GET /api/walmart-sem/data/list；GET /api/walmart-sem/data/stores。

### 页面与渲染内容

SEM广告数据的每日明细。

### 原值 / 计算口径

合计 CTR=总点击/总曝光，CPC=总花费/总点击，ACOS=总花费/总销售，ROAS=总销售/总花费。

### 证据文件

交付件/walmart_sem_delivery/backend/walmart_sem/service.py:133、162、206；router.py:216；frontend/walmart-sem-data/page.tsx:12

### 当前状态

交付件代码存在，部署待确认

### 迁移风险备注

SEM 与领星广告 FACT 共表，汇总必须按 source/campaign_type 防重复；商品归属失败需持续治理。

---

## LX-LINEAGE-034｜导入：SEM账单 CSV

**领星接口 / 来源：** 非领星 API。POST /api/walmart-sem/upload，类型 sem_billing。

### 获取数据

发票号/日期、计费起止日、扣费或返还、发票总额、Campaign、行金额、币种、支付状态/方式、附加说明。

### 原始存储 RAW

raw_walmart_sem_csv，csv_type=sem_billing。

### 清洗后存储 DIM/FACT

fact_sem_billing_daily。

### 保存字段与关联键

店铺、invoice_id、invoice_date、billing_from/to、charge_type、invoice_total、Campaign、line_amount、currency、支付状态/方式、附加说明、ItemID、任务。

### 清洗规则

按发票 + Campaign + 费用类型聚合；商品归属规则与 SEM 每日报表相同。

### 不进入结构化表的情况

归属失败 ItemID 为空但账单保留；其它 CSV 字段仅 RAW。

### 前端 / internal GET

GET /api/walmart-sem/billing/list。

### 页面与渲染内容

SEM广告数据账单 Tab。

### 原值 / 计算口径

数据库 AD_CREDIT 保存正值；前端显示为负值；净额 = 扣费 − 返还。

### 证据文件

交付件/walmart_sem_delivery/backend/walmart_sem/service.py:225、258；router.py:273；frontend/walmart-sem-data/page.tsx:50

### 当前状态

交付件代码存在，部署待确认

### 迁移风险备注

SEM账单与日绩效不是同一粒度，不能直接用于替代日广告花费。

---

## LX-LINEAGE-035｜导入：Connect广告发票 PDF

**领星接口 / 来源：** 非领星 API。页面入口 /walmart-connect-invoice；当前副本未找到解析写库主实现。

### 获取数据

设计上读取账号、发票号、账期、开票/扣款日、广告花费、抵扣、实扣额、付款方式和 Campaign 明细。

### 原始存储 RAW

raw_walmart_connect_invoice：摘要和 PDF 原文行 row_json。

### 清洗后存储 DIM/FACT

fact_onsite_ads_invoice_head；fact_onsite_ads_invoice_line；dim_connect_account。

### 保存字段与关联键

头表定义：账号、发票、日期、账期、subtotal、total_ad_spend、total_credits_applied、total_charged、payment_method；明细定义：section、campaign_ref_id/name、金额、匹配 Campaign、ItemID。

### 清洗规则

表结构注明可按账号绑定店铺和重导幂等；具体 PDF 字段解析/拒绝规则在当前副本无法验证。

### 不进入结构化表的情况

无法确认哪些 PDF 行会被拒绝、如何解析和如何保留原文；需补生产导入器代码。

### 前端 / internal GET

GET /api/finance/ads-fee/list?granularity=bill；GET /api/finance/credits/list。

### 页面与渲染内容

广告发票导入、广告账单扣费、返还明细。

### 原值 / 计算口径

账单页显示发票级原金额；返还取 total_credits_applied 的绝对值，并作为当前广告返还权威源。

### 证据文件

reports/database/LEGACY_DATABASE_SCHEMA_ONLY.sql:126、146、174、198；src/adsFeeReportRoutes.ts:51；src/aiFinanceRoutes.ts:45；admin-frontend/src/AppShell.tsx:48

### 当前状态

读取链和表结构存在，导入实现缺失

### 迁移风险备注

高风险缺口：必须取得 PDF 解析器、任务队列和异常处理代码后才能迁移。

---

## LX-LINEAGE-036｜探针与旧脚本

**领星接口 / 来源：** allMarketplace、reportProductSpList、reportPlatform、queryPageType、report/sku、候选运费/付款接口等。

### 获取数据

用于验证接口连通性、字段、枚举和费用来源。

### 原始存储 RAW

多数只打印控制台或查询既有表，未形成稳定 RAW。

### 清洗后存储 DIM/FACT

未发现稳定的生产 DIM/FACT 写入。

### 保存字段与关联键

仅临时样本与探针结论。

### 清洗规则

不构成正式数据产品链路。

### 不进入结构化表的情况

无稳定业务 GET。

### 前端 / internal GET

无正式业务页面。

### 页面与渲染内容

不应作为生产数据源或直接迁移功能。

### 原值 / 计算口径

src/testConnection.ts:10；src/testLingxingToFeishu.ts:13；src/probeCashCostSourcesV2.ts:42

### 证据文件

疑似探针/旧脚本

### 当前状态

迁移时排除，除非业务方明确确认仍需保留。

### 迁移风险备注

未记录

---

