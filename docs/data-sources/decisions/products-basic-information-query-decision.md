# Products Basic Information Query Source Decision

## 1. Status

```text
Investigation Date: 2026-09-07
Investigator: Backend Engineer Codex
Target method/path: 待定——本任务不定义后端接口契约
Source Discovery Status: Completed
Overall Decision State: BLOCKED_BY_OWNER_DECISION
Contains NEED_OWNER_DECISION: Yes
Owner Approval Status: Pending
Database Access Used: No
Server Access Used: No
External API Used: No
Decision File: docs/data-sources/decisions/products-basic-information-query-decision.md
Subsequent Interface PRP: Not created
```

本状态只表示已完成仓库内静态证据调查。源码与仓库文档不能证明当前生产数据库的实时表结构、数据量、新鲜度、账号权限或外部 API 可用性。

## 2. Scope

本次只覆盖产品基础身份信息候选范围：

- 平台、店铺标识与店铺展示名称。
- 商品标识（ItemID）、MSKU、SKU。
- 产品名称与旧接口中的名称 fallback。
- 品牌、分类。
- 与只读身份查询相关的基础状态候选。

产品负责人/员工归属、生命周期、手工运营状态、编辑、归档、批量操作、成本、库存、销售、利润、广告、结算、退款、Listing 写入及所有实现工作均不在范围内。

## 3. Executive Summary

已确认旧系统存在“产品管理”Tab，前端直接请求 `GET /api/feishu-raw-sales/product-management`；后端没有在该入口使用独立 service，而是在 route 内直接查询和组装数据。基础查询以 `dim_product` 为主，并用 `dim_store`、`dim_store_config` 补店铺名称。旧接口同时混入成本、状态、销售、库存、广告和人工配置数据，这些均不纳入本次决策。

仓库静态证据显示，`dim_product` 的 ItemID/MSKU/SKU/item_name/Walmart 发布状态由领星 `walmart/list` 链路刷新；`product_name` 由 `batchGetProductInfo` 的一次性、无 cron 任务回填，读取时再 fallback 到 `item_name`。旧飞书向 `dim_product_identity` 的结构化写入已经停用，但仓库仍有成本任务读取该表；因此它不是本次产品基础信息查询的权威来源，也不能在本决策中定为纯归档数据。

离线资料列出 Walmart 在线商品、本地产品列表/详情、品牌和分类等只读候选接口，但全部仍为“未验证/待评估”，不能视为已批准权威来源。由于产品名称、店铺名称、SKU 完整性、品牌/分类范围和基础状态语义仍需负责人决定，且使用旧库临时读取本身需要批准及单独 DB 盘点，总体状态必须保持 `BLOCKED_BY_OWNER_DECISION`。

## 4. Evidence Reviewed

以下均为仓库内只读证据：

| Evidence | Purpose |
|---|---|
| `old-system/source/admin-frontend/src/FeishuRawSalesData.tsx:125` | 产品管理 Tab、展示列和 GET 请求入口。 |
| `old-system/source/src/feishuRawSalesRoutes.ts:771` | 产品管理 GET route、直接 SQL、字段映射及响应。 |
| `old-system/source/src/syncLingxingDailyToDb.ts:298` | Walmart 商品数据到 `dim_product` 的解析与 upsert。 |
| `old-system/source/src/backfillDailyChain.ts:73` | 日链第一阶段调用 `syncLingxingDailyToDb.ts`。 |
| `old-system/source/src/syncProductNameFromLingxing.ts:20` | 本地产品详情到 `product_name` 的 RAW-first 回填链路。 |
| `old-system/source/src/syncWalmartStores.ts:2` | 店铺发现与 `dim_store_config` 写入线索。 |
| `old-system/source/src/storeRegistry.ts:4` | 店铺配置读取及写死配置 fallback。 |
| `old-system/source/context/SYSTEM_MAP.md:79` | 旧页面、接口、名称 fallback 和发布状态概览。 |
| `old-system/source/context/DATABASE_MAP.md:43` | 旧表、字段、唯一键和历史数据质量记录。 |
| `old-system/source/context/PIPELINE_MAP.md:17` | 仓库记录的调度、新鲜度与一次性任务状态。 |
| `old-system/source/docs/data_warehouse_schema.md:67` | 旧 DIM 粒度说明。 |
| `old-system/source/docs/feishu_item_owner_sync.md:5` | 旧飞书结构化商品身份链路已停用。 |
| `old-system/source/docs/lingxing/walmartList.md:62` | Walmart 在线商品候选字段。 |
| `old-system/source/docs/lingxing/ProductLists.md:50` | 本地产品列表候选字段。 |
| `old-system/source/docs/lingxing/ProductDetails.md:44` | 本地产品详情候选字段。 |
| `old-system/source/docs/lingxing/batchGetProductInfo.md:36` | 批量本地产品详情候选字段。 |
| `docs/integrations/lingxing-walmart-openapi/README.md:1` | 离线资料状态和使用限制。 |
| `docs/integrations/lingxing-walmart-openapi/api-verification-status.csv:8` | 候选接口均未验证。 |
| `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv:8`、`:10`、`:11`、`:19`、`:20`、`:143` | 候选接口的只读属性、分页和增量线索。 |
| `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv:2439` | 品牌、分类、名称、SKU、状态等候选响应字段。 |
| `docs/integrations/lingxing-walmart-openapi/do-not-use.md:1` | 禁止写入/副作用/非 Walmart 接口边界。 |
| `docs/data-sources/lingxing-walmart-api-to-system-data-map-draft.md:27` | 未批准的短期旧库、长期重建同步候选策略。 |
| `docs/database/INITIAL_SCHEMA_PLAN.md:31` | 新 PostgreSQL 主数据表仅为规划，不能证明数据所有权或已实现。 |

## 5. Candidate Legacy Entry Points

### 5.1 Page and API

- 旧页面：`FeishuRawSalesData.tsx` 中 `product_management` Tab，标签为“产品管理”（`old-system/source/admin-frontend/src/FeishuRawSalesData.tsx:125`、`:138`）。
- 展示列：旧页混合基础身份与负责人、状态、生命周期、销售、库存、广告、成本等字段（同文件 `:208`）。
- 读取接口：前端将该 Tab 映射为 `product-management` 并请求 `/api/feishu-raw-sales/${endpoint}`（同文件 `:927`、`:936`）。
- 后端入口：`GET /product-management`（`old-system/source/src/feishuRawSalesRoutes.ts:771`），完整挂载路径由仓库地图记录为 `GET /api/feishu-raw-sales/product-management`（`old-system/source/context/PIPELINE_MAP.md:203`）。
- service：在该入口未发现独立 service；route 在 `old-system/source/src/feishuRawSalesRoutes.ts:1085` 直接取得 DB 连接并执行内嵌 SQL。

### 5.2 Mandatory Pre-investigation Matrix

| Investigation item | Repository evidence and conclusion |
|---|---|
| 旧页面 | 已确认存在产品管理 Tab；证据：`old-system/source/admin-frontend/src/FeishuRawSalesData.tsx:125`、`:138`。 |
| 旧 API | 已确认存在 GET 读取接口；证据：`old-system/source/src/feishuRawSalesRoutes.ts:771`。 |
| 旧接口文件位置 | `old-system/source/src/feishuRawSalesRoutes.ts`。SQL 和响应映射均内嵌在 route。 |
| 读取表 | 基础候选为 `dim_product`、`dim_store`、`dim_store_config`（`old-system/source/src/feishuRawSalesRoutes.ts:866`）；同一旧接口还读状态、成本、销售、库存、广告、GPT 链接和清货审批表（同文件 `:918`-`:1030`），这些关联内容不在本次范围。 |
| 表写入方 | `old-system/source/src/syncLingxingDailyToDb.ts:298`-`:315` 从 `walmart/list` upsert `dim_product`；`old-system/source/src/syncProductNameFromLingxing.ts:549` 回填 `product_name`；`old-system/source/src/syncWalmartStores.ts:149` upsert `dim_store_config`。仅为仓库静态事实，未验证当前生产运行。 |
| cron / 脚本 / 外部 API | 仓库地图记录 16:45 `backfillDailyChain` 调用 `syncLingxingDailyToDb.ts`（`old-system/source/context/PIPELINE_MAP.md:43`；`old-system/source/src/backfillDailyChain.ts:73`）；产品名称任务无 cron（`old-system/source/context/PIPELINE_MAP.md:17`）。 |
| 人工写库入口 | 基础身份字段未发现当前页面写入口；页面写入的负责人、生命周期、WFS 费用、GPT 链接和产品管理状态均明确排除。旧飞书结构化写入已停用（`feishu_item_owner_sync.md:5`）。 |
| 外部平台重新获取可能性 | 存在线索：Walmart 在线商品、本地产品列表/详情、品牌和分类候选接口；但 `api-verification-status.csv:8`、`:10`、`:11`、`:19`、`:20`、`:143` 全部为未验证。 |
| 少量配置数据可行性 | 新系统规划包含产品/店铺/SKU 映射表名，但尚无证据批准由新系统维护哪些值；`NEED_OWNER_DECISION`。 |
| 短期策略 | 若负责人批准，基础标识可候选只读 `dim_product` 过渡；店铺展示名、名称和状态须先解决下文决定项，并另做精确 DB 盘点。 |
| 长期策略 | 经真实验证与单独 PRP 后，候选为新系统后台同步 Walmart listing 身份与领星本地产品资料；禁止 API route 实时批量拉取。 |

### 5.3 Read-path Tables

| Candidate table | Role in current GET | Evidence |
|---|---|---|
| `dim_product` | 基础行、平台、店铺 ID、ItemID、MSKU、SKU、两个名称字段及状态候选。 | `old-system/source/src/feishuRawSalesRoutes.ts:866`、`:1008`-`:1023` |
| `dim_store` | 店铺名称第一层 fallback。 | `old-system/source/src/feishuRawSalesRoutes.ts:867` |
| `dim_store_config` | 店铺名称第二层 fallback。 | `old-system/source/src/feishuRawSalesRoutes.ts:868` |
| `raw_lingxing_api` | 不被 GET 直接读取；仅为外部同步 RAW 留痕。 | `old-system/source/context/DATABASE_MAP.md:26` |
| `dim_product_identity` | 本次 GET 不读取；旧飞书结构化 writer 已停用，但成本任务仍读取，本查询明确排除。 | `old-system/source/docs/feishu_item_owner_sync.md:95`; `old-system/source/src/syncLingxingProductCost.ts:187`-`:194`; `old-system/source/src/syncProductCostToMysql.ts:156`-`:161`; `old-system/source/context/PIPELINE_MAP.md:47` |

## 6. Field / Dataset Decision Table

事实标签：`Confirmed static` 表示由仓库源码直接确认；`Documented static` 表示由仓库历史文档记录；`Inference` 是基于静态证据的建议；`Unknown` 必须由负责人或后续授权调查解决。任何标签都不代表当前生产事实。

| field_or_dataset | business_meaning | candidate_source_table_or_api | classification | evidence_path | current_writer | current_reader | external_origin | freshness_or_update_chain | confidence_level | short_term_strategy | long_term_strategy | risk_level | owner_decision_needed | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `platform`, `store_id`, `item_id`, `msku` | Walmart listing 的稳定识别组合候选 | Legacy `dim_product`; `/basicOpen/multiplatform/walmart/list` | `READ_LEGACY_TEMPORARILY` | `old-system/source/src/feishuRawSalesRoutes.ts:1008`; `old-system/source/src/syncLingxingDailyToDb.ts:308`; `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv:6323` | `syncLingxingDailyToDb.ts` | GET product-management | Lingxing 包装的 Walmart 在线商品资料 | 仓库记录为 16:45 日链；未验证当前生产 | High static / production unknown | 经负责人批准并完成 DB 盘点后，限定只读 `dim_product` | 验证后以后台同步重建，保留外部源标识与新鲜度 | High | Yes | Confirmed static：`platform` 在旧代码写死为 walmart；Unknown：当前数据完整性与旧库退出里程碑。 |
| `sku` | 本地产品 SKU 候选 | Legacy `dim_product.sku`; Walmart `local_sku`; local product `sku` | `READ_LEGACY_TEMPORARILY` | `old-system/source/src/syncLingxingDailyToDb.ts:305`; `old-system/source/src/syncLingxingDailyToDb.ts:553`; `old-system/source/context/DATABASE_MAP.md:175`; `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv:2465` | 日链写非空值，并存在同 Item 唯一 SKU 补空逻辑；一次性名称任务也有受限补空路径 | GET product-management | Walmart listing + Lingxing local product | 日链；仓库历史文档记录存在空值，未做本轮 DB 验证 | Medium | 只读旧值，空值保持 Unknown，禁止从 MSKU 猜 SKU | 外部源验证后重建同步并保留歧义/缺失状态 | High | Yes | Documented static：存在缺失与歧义风险；负责人需批准缺失展示和匹配规则。 |
| `product_name`, `item_name` | 产品展示名称/平台本地名称 | Legacy `dim_product`; `batchGetProductInfo`; Walmart `local_name` | `NEED_OWNER_DECISION` | `old-system/source/src/feishuRawSalesRoutes.ts:1015`; `old-system/source/src/feishuRawSalesRoutes.ts:1132`; `old-system/source/src/syncProductNameFromLingxing.ts:20`; `old-system/source/context/PIPELINE_MAP.md:17` | `item_name` 由日链写；`product_name` 由一次性、无 cron 任务回填 | GET 以 `product_name || item_name` 输出 | 两个不同外部接口与语义 | 一个日更、一个无 cron；名称新鲜度不一致 | High static / semantic unknown | 不得在负责人确认前把 fallback 结果定义为正式产品名称 | 决定名称语义后验证相应外部接口并重建同步 | High | Yes | Confirmed static：存在 fallback；Unknown：两个名称的业务定义、优先级和空值政策。 |
| `store_name` | 店铺展示名称及店铺映射 | `dim_product.store_name`, `dim_store`, `dim_store_config`; seller list | `NEED_OWNER_DECISION` | `old-system/source/src/feishuRawSalesRoutes.ts:866`; `old-system/source/src/syncWalmartStores.ts:20`; `old-system/source/src/storeRegistry.ts:34` | `syncWalmartStores.ts` 写 config；日链写 `dim_store`; registry 失败时回退写死配置 | GET 使用三层 `COALESCE` | Lingxing seller list / store config | 仓库记录 03:00 店铺发现；未验证当前生产 | Medium | 负责人先指定唯一权威表和 fallback 规则 | 新系统同步店铺主数据；是否维护人工别名另行决定 | High | Yes | Confirmed static：当前有多来源 fallback；Unknown：权威优先级和写死 fallback 是否仍有效。 |
| `brand`, `category` | 产品品牌与分类候选 | Local product list/detail; brand/category list APIs | `NEED_OWNER_DECISION` | `old-system/source/docs/lingxing/ProductLists.md:50`; `old-system/source/docs/lingxing/ProductDetails.md:67`; `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv:2439`; `docs/integrations/lingxing-walmart-openapi/api-verification-status.csv:10` | 当前旧 GET/`dim_product` 写链未发现对应字段写入 | 无当前 product-management reader | Lingxing ERP local product catalog | 候选接口支持增量/分页线索，但全部未验证 | Medium-low | 第一版不得凭离线文档补字段 | 若负责人纳入范围，验证接口后使用后台同步 | Medium | Yes | Confirmed static：旧 GET 未读取品牌/分类；Unknown：范围、映射关系、账号权限与实际返回。 |
| `walmart_publish_status` / local product `status` | 外部发布状态或 ERP 产品状态候选 | Legacy `dim_product.walmart_publish_status`; Walmart list `status_name`; local product `status` | `NEED_OWNER_DECISION` | `old-system/source/src/syncLingxingDailyToDb.ts:551`; `old-system/source/src/feishuRawSalesRoutes.ts:1023`; `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv:6340`; `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv:2468` | Walmart 发布状态由日链写；ERP local status 未发现当前写链 | GET 带 `_walmart_publish_status`，页面“产品状态”实际是被排除的人工管理状态 | 两套不同状态体系 | Walmart 状态随日链；ERP status 未接入 | High static / semantic unknown | 不得把人工 `product_management_status` 当基础外部状态 | 负责人选择状态语义后验证并同步唯一来源 | High | Yes | Confirmed static：状态体系不同；Unknown：正式只读查询需要哪一种。 |
| derived `product_type` | 旧页按 MSKU `CS` 前缀区分常规/测品 | SQL/response derivation from `msku` | `NEED_OWNER_DECISION` | `old-system/source/src/feishuRawSalesRoutes.ts:1017`; `old-system/source/admin-frontend/src/FeishuRawSalesData.tsx:210` | 无独立 writer | GET product-management | 无，旧代码派生 | 随 MSKU 读取即时派生 | High | 不默认纳入基础身份契约 | 负责人确认语义后再决定是否作为新系统自有派生字段 | Medium | Yes | Confirmed static：是规则派生而非源字段；可能属于运营分类。 |

没有任何基础身份字段可仅凭本轮证据直接批准为 `NEW_SYSTEM_OWNED`。新系统可否维护店铺别名、SKU 映射或人工纠错，需要负责人另行决定；初始 schema 规划中的表名不等于数据所有权批准。

### 6.1 Required Data Lineage Matrix

本矩阵只记录仓库静态证据、静态推断和待确认项，不代表生产环境事实；尚未定义正式接口契约，因此 `standard_field` 均为候选或待确认。

| field_or_dataset | current_authoritative_source | raw_field | standard_field | transformation_or_formula | timezone | currency | evidence_path | risk_check | owner_decision_needed | notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 商品身份（`platform`、`store_id`、`item_id`、`msku`） | 待确认；旧 GET 的仓库静态读源为 Legacy `dim_product` | `dp.platform`, `dp.store_id`, `dp.item_id`, `dp.msku` | 同名候选字段 | 旧写链将 `platform` 固定为 `walmart`；其余直接映射。静态代码推断，不等同生产事实 | 不适用 | 不适用 | `old-system/source/src/feishuRawSalesRoutes.ts:1008`; `old-system/source/src/syncLingxingDailyToDb.ts:308` | 未验证生产完整性、新鲜度、唯一键和旧库退出条件 | Yes：OD-1、OD-9 | 当前只可作为负责人批准后的临时只读候选。 |
| SKU / MSKU 映射 | 待确认；旧读源候选为 Legacy `dim_product` | `dp.sku`, `dp.msku`; 外部候选 `local_sku`, `msku` | `sku`, `msku` 候选字段 | 旧链仅写非空 SKU，并存在同 Item 唯一 SKU 补空逻辑；不得从 MSKU 猜 SKU。静态代码推断，不等同生产事实 | 不适用 | 不适用 | `old-system/source/src/syncLingxingDailyToDb.ts:305`; `old-system/source/src/syncLingxingDailyToDb.ts:553`; `old-system/source/context/DATABASE_MAP.md:175` | 空值、重复和歧义未做生产验证 | Yes：OD-4、OD-9 | 正式映射规则未确定。 |
| 产品名称（`product_name`, `item_name`） | 待确认；当前存在两个不同来源和不同刷新链 | `dp.product_name`, `dp.item_name`; 外部候选 `product_name`, `local_name` | 正式产品名称字段待确认 | 旧 GET 使用 `product_name || item_name`；该 fallback 不能自动成为新系统口径。静态代码推断，不等同生产事实 | 不适用 | 不适用 | `old-system/source/src/feishuRawSalesRoutes.ts:1015`; `old-system/source/src/feishuRawSalesRoutes.ts:1132`; `old-system/source/src/syncProductNameFromLingxing.ts:20`; `old-system/source/context/PIPELINE_MAP.md:17` | 名称语义、优先级、空值政策和新鲜度冲突 | Yes：OD-2、OD-10 | `item_name` 日链写入；`product_name` 仓库记录为一次性、无 cron 回填。 |
| Walmart 发布状态 / ERP 本地产品状态 | 待确认；两套状态体系不得合并为同一权威来源 | `dim_product.walmart_publish_status`; Walmart `status_name`; ERP local `status` | 正式基础状态字段待确认 | 旧 GET 暴露 Walmart 发布状态候选；ERP 状态未接入。不存在已批准的统一转换公式 | 不适用 | 不适用 | `old-system/source/src/syncLingxingDailyToDb.ts:551`; `old-system/source/src/feishuRawSalesRoutes.ts:1023`; `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv:6340`; `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv:2468` | 状态语义和来源冲突；外部字段未验证 | Yes：OD-6、OD-10 | 人工 `product_management_status` 明确不在本次范围。 |
| 店铺映射与展示名 | 待确认；旧 GET 同时读取 `dim_product`、`dim_store`、`dim_store_config` | `dp.store_id`, `dp.store_name`, `ds.store_name`, `dsc.store_name` | `store_id`, `store_name` 候选字段 | 旧 GET 使用三层 `COALESCE`；该 fallback 未获准成为正式规则。静态代码推断，不等同生产事实 | 不适用 | 不适用 | `old-system/source/src/feishuRawSalesRoutes.ts:866`; `old-system/source/src/syncWalmartStores.ts:20`; `old-system/source/src/storeRegistry.ts:34` | 多来源优先级、写死 fallback 和别名所有权未确认 | Yes：OD-3、OD-8、OD-9 | 必须先指定唯一权威来源。 |
| `dim_product_identity` | 不适用：本查询明确排除；不能据此断言该表全局归档 | `msku`, `local_sku` 等成本任务读取字段 | 不适用 | 不用于产品基础信息查询；无本查询转换公式 | 不适用 | 不适用 | `old-system/source/docs/feishu_item_owner_sync.md:95`; `old-system/source/src/syncLingxingProductCost.ts:187`-`:194`; `old-system/source/src/syncProductCostToMysql.ts:156`-`:161`; `old-system/source/context/PIPELINE_MAP.md:47` | 结构化 writer 已停用，但仍有成本读取依赖；不能定为 `ARCHIVE_ONLY` | No（本查询）；未来成本/采购价/供货价模块需另行数据源决策 | 仅说明本查询不用，不评价其他模块是否应继续使用或清退。 |
| Walmart listing 外部候选 | 未验证；不得视为当前权威来源 | `store_id`, `item_id`, `msku`, `local_sku`, `local_name`, `status_name` 候选 | 对应标准字段均待确认 | 仅有离线字段映射线索；实际响应、权限、分页、限流和增量行为待验证 | 待确认（本次候选字段未发现时间口径；若后续返回时间字段需另定） | 不适用 | `docs/integrations/lingxing-walmart-openapi/api-verification-status.csv:8`; `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv:6323` | 未调用真实 API，不能确认可用性和字段质量 | Yes：OD-10 | 真实 API 验证需单独授权。 |
| Lingxing 本地产品、品牌、分类外部候选 | 未验证；不得视为当前权威来源 | `product_name`, `sku`, `brand_name`, `category_name`, `status` 候选 | 名称、SKU、品牌、分类、ERP 状态字段均待确认 | 仅有离线字段映射线索；尚无批准的标准化转换 | 待确认（本次候选字段未发现时间口径；若后续返回时间字段需另定） | 不适用 | `old-system/source/docs/lingxing/ProductLists.md:50`; `old-system/source/docs/lingxing/ProductDetails.md:67`; `docs/integrations/lingxing-walmart-openapi/api-verification-status.csv:10`; `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv:2439` | 范围、映射关系、权限和实际返回均未验证 | Yes：OD-2、OD-4、OD-5、OD-6、OD-10 | 第一版不得凭离线资料补字段。 |

### 6.2 Risk Checklist

| Check | Result | Owner decision / reason |
|---|---|---|
| 连接真实数据库 | No | 本轮仅仓库静态调查。 |
| 连接服务器或 SSH | No | 未访问服务器。 |
| 调用真实外部 API | No | 未调用 Lingxing、Walmart 或其他外部 API。 |
| 读取 secrets 或 `.env` | No | 未读取或输出敏感配置。 |
| 修改 `old-system/**` | No | 旧系统只读。 |
| 将源码静态推断写成生产事实 | No | 全文明确区分静态事实、推断和生产未知。 |
| writer / 调度链是否存在未确认项 | Yes | OD-9：需单独只读 DB 盘点验证当前生产写入、新鲜度和运行状态。 |
| 外部 API 是否未经验证 | Yes | OD-10：候选接口均未验证，真实调用需单独授权。 |
| 权威来源是否未确认 | Yes | OD-2、OD-3、OD-5、OD-6、OD-10。 |
| raw → standard 是否存在缺口 | Yes | OD-2、OD-3、OD-4、OD-5、OD-6、OD-8。 |
| 时区 | 不适用 / 待确认 | 本次身份候选字段不含已确认时间字段；若后续纳入时间字段，需单独确认口径。 |
| 币种 | 不适用 | 本次排除所有金额、成本、费用和汇率字段。 |
| 是否存在 `NEED_OWNER_DECISION` | Yes | OD-1 至 OD-10 均保持未解决。 |
| Overall Decision State | `BLOCKED_BY_OWNER_DECISION` | 未满足进入接口 PRP 的门禁。 |

## 7. Explicitly Excluded Findings

以下内容在旧页面/接口中存在，但统一记录为“关联但不在本次范围”：

| Excluded domain | Evidence |
|---|---|
| 产品负责人/员工归属 | `old-system/source/admin-frontend/src/FeishuRawSalesData.tsx:209`; `old-system/source/src/feishuRawSalesRoutes.ts:1239` |
| 生命周期、上架时间、CS/常规生命周期规则 | `old-system/source/src/feishuRawSalesRoutes.ts:1017`; `old-system/source/src/feishuRawSalesRoutes.ts:1397` |
| 手工产品管理状态、编辑、归档、批量操作 | `old-system/source/src/feishuRawSalesRoutes.ts:1724` |
| WFS 配送费、采购成本、头程成本 | `old-system/source/src/feishuRawSalesRoutes.ts:934`-`:969`; `old-system/source/src/feishuRawSalesRoutes.ts:1560` |
| 销售 | `old-system/source/src/feishuRawSalesRoutes.ts:971`-`:976` |
| 库存 | `old-system/source/src/feishuRawSalesRoutes.ts:978`-`:991` |
| 广告、利润等级、GPT 链接 | `old-system/source/src/feishuRawSalesRoutes.ts:992`-`:1006` |
| 清货审批 | `old-system/source/src/feishuRawSalesRoutes.ts:1030` |
| Listing 写入、外部 API 写操作 | `docs/integrations/lingxing-walmart-openapi/do-not-use.md:9` |
| `dim_product_identity`（本次产品基础信息查询） | 旧飞书结构化写入已停用或未作为本次基础信息权威来源，但 `syncLingxingProductCost.ts` 与 `syncProductCostToMysql.ts` 成本相关任务仍读取；本次产品基础信息查询不使用。未来成本、采购价、供货价模块如需继续使用、迁移或清退，必须另行完成数据源决策。证据：`old-system/source/docs/feishu_item_owner_sync.md:95`; `old-system/source/src/syncLingxingProductCost.ts:187`-`:194`; `old-system/source/src/syncProductCostToMysql.ts:156`-`:161`; `old-system/source/context/PIPELINE_MAP.md:47`。 |

`launch_date` 虽在旧页显示，但其仓库文档表明由人工历史回填与库存/广告推导共同产生，并直接服务生命周期规则；本次不将其纳入基础身份决策。

## 8. Unknowns and Owner Decisions

| ID | Required owner decision | Why blocked |
|---|---|---|
| OD-1 | 是否批准第一期临时只读旧库；若批准，明确只读表、账号、查询/分页上限、性能边界和退出里程碑。 | `READ_LEGACY_TEMPORARILY` 必须负责人确认，本轮未连接 DB。 |
| OD-2 | 正式“产品名称”应采用 ERP `product_name`、Walmart `local_name/item_name`，还是明确的 fallback 语义。 | 当前一个日更、一个仅一次性回填。 |
| OD-3 | 店铺名称的唯一权威来源和别名/映射规则。 | 旧 GET 在三表间 fallback，store registry 还存在写死配置 fallback。 |
| OD-4 | SKU 为空或同 Item 多 SKU 时的显示、匹配和阻塞政策。 | 仓库历史证据记录 SKU 缺失，不能从 MSKU 猜测。 |
| OD-5 | 品牌、分类是否进入第一期基础信息，以及采用 ID、名称还是两者。 | 旧 GET 不提供；外部候选未验证。 |
| OD-6 | “基础状态”具体指 Walmart 发布状态、ERP local product status，或不纳入第一期。 | 两套外部状态不同；人工管理状态明确排除。 |
| OD-7 | 旧页派生 `product_type` 是否属于基础身份，还是运营/生命周期模块。 | 当前仅由 MSKU `CS` 前缀推导。 |
| OD-8 | 是否由新系统维护店铺别名、SKU 映射或人工纠错数据。 | schema 规划不能替代业务所有权决定。 |
| OD-9 | 是否另起只读 DB 盘点，验证 `dim_product`/店铺表真实结构、行数、空值、重复、更新时间和索引。 | 仓库源码不能证明当前生产状态。 |
| OD-10 | 长期外部来源选择和真实 API 验证优先级。 | 所有候选接口均为未验证/待评估，且真实调用需单独授权。 |

存在未解决的 `NEED_OWNER_DECISION`，因此当前不得进入后端接口 PRP。

## 9. Recommended Short-Term Strategy

1. 仅在负责人批准 OD-1 且另行完成精确只读 DB 盘点后，考虑用旧库 `dim_product` 提供平台、店铺 ID、ItemID、MSKU、SKU 和名称候选的临时读取。
2. 店铺展示名必须等 OD-3 确定唯一权威来源；不得复制旧接口的三表 fallback 作为默认新契约。
3. 产品名称、品牌、分类和基础状态在对应 owner decision 完成前保持不可承诺；不得用静态文档补值。
4. 旧接口混入的 FACT/BIZ/费用/人工状态数据不进入本次基础查询。
5. 临时旧库方案必须只读、受限分页、带新鲜度/缺失警告，并以长期同步切换验收为退出条件；具体 SLA、阈值和目标日期待负责人确定。

## 10. Recommended Long-Term Strategy

1. 候选 listing 身份来源为 `/basicOpen/multiplatform/walmart/list`：ItemID、MSKU、local SKU/name、店铺和 Walmart 发布状态。
2. 候选 ERP 产品资料来源为 `productList` / `productInfo` / `batchGetProductInfo`：产品名称、SKU、品牌、分类和 ERP 状态。
3. 所有接口必须先核对官方文档、账号权限、字段、分页、限流、错误码、增量范围和实际样本，再另行 PRP；当前离线资料不能作为批准。
4. 若获批重建，采用后台 integration + Celery 同步、RAW 留痕、标准化存储和数据质量检查；正式查询只读已同步数据，禁止 route 实时批量拉外部平台。
5. 外部身份字段保持单一权威来源；人工运营状态、生命周期、负责人、成本等继续属于各自独立模块，不得被产品资料同步覆盖。

## 11. Stop Conditions Triggered

- 安全边界停止条件：未触发。未连接数据库、服务器、SSH tunnel 或外部 API；未执行旧系统脚本；未读取或输出真实密钥。
- 决策门禁停止条件：已触发。OD-1 至 OD-10 尚未解决，且缺少真实 DB 盘点与外部 API 验证，因此总体状态为 `BLOCKED_BY_OWNER_DECISION`。
- 本轮在此停止，不创建后端接口 PRP，不定义 method/path、request/response schema、数据库模型、migration 或同步实现。

## 12. Next Step

1. 负责人逐项处理 OD-1 至 OD-10，并记录批准的字段范围、短期分类、长期来源和退出条件。
2. 如需要验证旧库，另起只读 DB 盘点任务，并明确批准精确数据库、表、账号和命令范围。本轮没有也不需要这些信息。
3. 如需要验证领星/Walmart 候选接口，另起真实 API 验证任务并明确授权；不得从本决策直接开始调用。
4. 只有所有阻塞项解决、决策文档经架构师复审并将总体状态明确更新为 `READY_FOR_PRP` 后，才能准备后端接口 PRP；仍不得直接写接口。

## 13. Appendix: Commands Run

本轮只使用 `git branch`、`git status`、`find`、`rg`、`sed`、`git diff --check`、`bash scripts/check-rule-pack.sh` 和文件补丁写入；未执行旧系统脚本。

关键只读命令：

```bash
git branch --show-current
git status --short --untracked-files=all
find AGENTS.md AI_DAILY_RULES.md CODEX_START_HERE.md PRPs/phase-2a-product-basic-information-source-discovery.md docs/delivery/agent-role-skill-routing.md docs/delivery/backend-data-source-decision-gate.md docs/DATA_SOURCE_AND_LINEAGE_RULES.md docs/OLD_SYSTEM_READONLY_RULES.md docs/data-sources/README.md -maxdepth 0 -type f -print
rg --files old-system | rg -i '(^|/|[-_.])(product|products|sku|msku|item|listing|walmart|store|dim_product|product_id|sku_id|商品|产品|店铺)([-_./]|$)'
rg --files docs/integrations | rg -i '(lingxing|领星|walmart|product|sku|msku|item|listing|商品|产品|店铺)'
rg -n -i '产品管理|产品基础信息|商品管理|商品基础信息' old-system/source
rg -n -i 'PRODUCT_MANAGEMENT|product-management|产品管理' old-system/source/admin-frontend/src/FeishuRawSalesData.tsx old-system/source/src/feishuRawSalesRoutes.ts old-system/source/context/SYSTEM_MAP.md old-system/source/context/DATABASE_MAP.md old-system/source/context/PIPELINE_MAP.md
rg -n -i 'INSERT\s+INTO\s+dim_product|UPDATE\s+dim_product' old-system/source/src old-system/source/legacy_feishu_20260723
rg -n 'LX-(9212623D77EA|3F1F087FF8A1|DCB0C142100B|BB8D0DF598AF|82FF3AF996D2|75F4963569A6)' docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv docs/integrations/lingxing-walmart-openapi/normalized/module_mapping.csv docs/integrations/lingxing-walmart-openapi/api-verification-status.csv docs/integrations/lingxing-walmart-openapi/normalized/deleted_interfaces.csv
sed -n '120,245p' old-system/source/admin-frontend/src/FeishuRawSalesData.tsx
sed -n '760,1235p' old-system/source/src/feishuRawSalesRoutes.ts
sed -n '270,355p' old-system/source/src/syncLingxingDailyToDb.ts
sed -n '530,665p' old-system/source/src/syncLingxingDailyToDb.ts
sed -n '1,220p' old-system/source/src/storeRegistry.ts
sed -n '1,240p' old-system/source/src/syncWalmartStores.ts
sed -n '1,85p' old-system/source/docs/lingxing/ProductLists.md
sed -n '1,75p' old-system/source/docs/lingxing/ProductDetails.md
sed -n '1,70p' old-system/source/docs/lingxing/batchGetProductInfo.md
sed -n '1,95p' old-system/source/docs/lingxing/walmartList.md
git status --short --untracked-files=all
git diff --check
bash scripts/check-rule-pack.sh
sed -n '1,320p' docs/data-sources/decisions/products-basic-information-query-decision.md
rg -n "dim_product_identity|syncLingxingProductCost|syncProductCostToMysql|PIPELINE_MAP" .
sed -n '1,380p' docs/data-sources/decisions/products-basic-information-query-decision.md
```
