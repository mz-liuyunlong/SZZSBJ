# Products Basic Information Query Source Decision

## 1. Status

```text
Investigation Date: 2026-09-07
Decision Update Date: 2026-09-07
Investigator: Backend Engineer Codex
Decision Update Author: Architect Codex
Target method/path: 待定——本任务不定义后端接口契约
Source Discovery Status: Completed
OD-9 Readonly DB Inventory: Completed
Overall Decision State: READY_FOR_PRP
Contains NEED_OWNER_DECISION In Approved Phase 2A Scope: No
Deferred Out-of-scope Decisions: Yes
Owner Approval Status: Approved for the narrowed Phase 2A scope
Owner Decision Approved By: Project Owner
Owner Decision Approval Date: 2026-09-07
Database Access Used In This Update: No
Server Access Used In This Update: No
External API Used In This Update: No
Decision File: docs/data-sources/decisions/products-basic-information-query-decision.md
Subsequent Interface PRP: Allowed to create; not created
```

`READY_FOR_PRP` 只适用于下文明确列出的 Phase 2A 产品基础信息只读查询缩小范围，只允许下一步创建和审批接口 PRP，不授权接口实现、数据库变更、外部 API 调用、同步任务或部署。

本决策依据仓库静态调查和已合并的 OD-9 脱敏只读数据库盘点报告。OD-9 证明了批准范围内的表结构和聚合数据质量事实，但不能证明外部来源新鲜度、外部 API 可用性或长期权威来源已经完成验证。

## 2. Scope

本次 `READY_FOR_PRP` 只覆盖以下第一阶段来源字段：

- `item_id`
- `sku`
- `msku`
- `item_name`
- `store_id`

字段边界：

- `sku` 允许为空，不得作为全局唯一身份，不得从 MSKU 或 ItemID 推导，也不得因缺失而丢弃产品。
- `item_id` 是外部商品标识，不等于新系统内部 `product_id`。
- `msku` 可用于运营识别，但不自动等同新系统内部 `product_id`。
- 产品名称第一阶段优先使用 `item_name`；不得默认 fallback 到 `product_name`。
- `store_id` 可作为第一阶段店铺身份字段；`store_name` 不进入第一阶段 API response 或前端展示。

本决策不批准 `platform` 作为第一阶段 response 字段。它仍可作为旧表组合键和来源血缘的结构上下文，但若未来需要对外返回，必须在后续 Source Decision 或负责人确认中明确。

产品负责人/员工归属、生命周期、手工运营状态、编辑、归档、批量操作、成本、WFS 费用、库存、销售、利润、广告、结算、退款、Listing 写入、store alias、SKU mapping 写能力及所有实现工作均不在范围内。

## 3. Executive Summary

已确认旧系统存在“产品管理”Tab，前端直接请求 `GET /api/feishu-raw-sales/product-management`；后端没有在该入口使用独立 service，而是在 route 内直接查询和组装数据。基础查询以 `dim_product` 为主，并用 `dim_store`、`dim_store_config` 补店铺名称。旧接口同时混入成本、状态、销售、库存、广告和人工配置数据，这些均不纳入本次决策。

仓库静态证据显示，`dim_product` 的 ItemID/MSKU/SKU/item_name/Walmart 发布状态由领星 `walmart/list` 链路刷新；`product_name` 由 `batchGetProductInfo` 的一次性、无 cron 任务回填，读取时再 fallback 到 `item_name`。旧飞书向 `dim_product_identity` 的结构化写入已经停用，但仓库仍有成本任务读取该表；因此它不是本次产品基础信息查询的权威来源，也不能在本决策中定为纯归档数据。

OD-9 已确认 `dim_product`、`dim_store`、`dim_store_config` 存在，行数分别为 2,446、9、10；`item_id`、`msku`、`store_id` 缺失率为 0%，SKU 缺失 662 行、缺失率为 27.06%，并存在重复及交叉映射风险。店铺匹配统计的实际连接粒度无法确认，`store_name` 仍缺少唯一权威来源证据；更新时间字段也只能作为结构性风险证据，不能证明来源新鲜度。

负责人已批准 OD-1：第一阶段按 `READ_LEGACY_TEMPORARILY` 临时只读旧库，并受本决策缩小字段范围约束。负责人已解决 OD-3 在本阶段的阻塞方式：排除 `store_name`，只保留 `store_id`。因此缩小后的产品基础信息查询达到 `READY_FOR_PRP`；未验证的外部接口、被排除字段和长期标准层均不在此次批准范围内。

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
| `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md:1` | OD-9 已批准三表只读盘点的结构、索引和脱敏聚合证据。 |

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
| 少量配置数据可行性 | 本阶段不适用。store alias、SKU mapping 和人工纠错写能力已由 OD-8 后置，不进入本期接口范围。 |
| 短期策略 | 负责人已批准按 `READ_LEGACY_TEMPORARILY` 从 `dim_product` 读取本决策明确允许的五个字段；不读取或返回 `store_name`，不复制旧三表名称 fallback。 |
| 长期策略 | 按 OD-10 先验证 Walmart Listing 来源，再按需评估 Lingxing local product；完成独立 Source Decision、PRP、标准层和同步任务后退出旧库。禁止 API route 实时批量拉取。 |

### 5.3 Read-path Tables

| Candidate table | Role in current GET | Evidence |
|---|---|---|
| `dim_product` | 第一阶段临时只读来源；后续 API PRP 只可讨论 `item_id`、`sku`、`msku`、`item_name`、`store_id`。 | `old-system/source/src/feishuRawSalesRoutes.ts:866`、`:1008`-`:1023`; `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md:46` |
| `dim_store` | 仅作为 OD-9 店铺证据来源；因 `store_name` 排除，不自动授权第一阶段运行时查询或连接。 | `old-system/source/src/feishuRawSalesRoutes.ts:867`; `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md:64` |
| `dim_store_config` | 仅作为 OD-9 店铺证据来源；因 `store_name` 排除，不自动授权第一阶段运行时查询或连接。 | `old-system/source/src/feishuRawSalesRoutes.ts:868`; `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md:76` |
| `raw_lingxing_api` | 不被 GET 直接读取；仅为外部同步 RAW 留痕。 | `old-system/source/context/DATABASE_MAP.md:26` |
| `dim_product_identity` | 本次 GET 不读取；旧飞书结构化 writer 已停用，但成本任务仍读取，本查询明确排除。 | `old-system/source/docs/feishu_item_owner_sync.md:95`; `old-system/source/src/syncLingxingProductCost.ts:187`-`:194`; `old-system/source/src/syncProductCostToMysql.ts:156`-`:161`; `old-system/source/context/PIPELINE_MAP.md:47` |

## 6. Field / Dataset Decision Table

本表只列入缩小后的第一阶段字段。每个字段组只有一种当前分类；被排除项目不以 `NEED_OWNER_DECISION` 留在本期接口范围内。

| field_or_dataset | business_meaning | candidate_source_table_or_api | classification | evidence_path | current_writer | current_reader | external_origin | freshness_or_update_chain | confidence_level | short_term_strategy | long_term_strategy | risk_level | owner_decision_needed | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `item_id`, `msku`, `store_id` | 第一阶段外部商品、运营 SKU 与店铺身份字段 | Legacy `dim_product` | `READ_LEGACY_TEMPORARILY` | `old-system/source/src/feishuRawSalesRoutes.ts:1008`; `old-system/source/src/syncLingxingDailyToDb.ts:308`; `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md:107`; `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md:109`; `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md:126` | 仓库静态证据指向 `syncLingxingDailyToDb.ts`；当前运行状态未由 OD-9 证明 | Legacy GET product-management | Lingxing 包装的 Walmart Listing 数据 | 旧表仅有行变更时间候选，不能证明来源新鲜度 | High for structure / freshness unknown | 通过只读账号、受限分页和 Legacy Readonly Repository 读取，不写旧库 | 先验证 Walmart Listing，再通过独立 PRP 同步到新系统标准层 | High | No for narrowed scope | `item_id`、`msku` 不等于内部 `product_id`；`store_id` 不得自动转换为 `store_name`。 |
| `sku` | 第一阶段可空的本地 SKU 标识 | Legacy `dim_product.sku` | `READ_LEGACY_TEMPORARILY` | `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md:108`; `old-system/source/src/syncLingxingDailyToDb.ts:305` | 仓库静态证据指向旧日链 | Legacy GET product-management | Walmart Listing / Lingxing local product 历史链路 | 来源新鲜度未证明 | High for observed quality risk | 原值只读返回；允许为空，不推导、不丢弃产品、不作为全局唯一身份 | 按 OD-10 验证来源后重建同步，保留空值和歧义状态 | High | No for narrowed scope | OD-9：662 行缺失，缺失率 27.06%，且存在重复和交叉映射风险。 |
| `item_name` | 第一阶段产品名称 | Legacy `dim_product.item_name` | `READ_LEGACY_TEMPORARILY` | `old-system/source/src/feishuRawSalesRoutes.ts:1015`; `old-system/source/src/syncLingxingDailyToDb.ts:308`; `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md:58` | 仓库静态证据指向旧日链 | Legacy GET product-management | Walmart Listing 名称链路候选 | 来源新鲜度和空值率未由 OD-9 证明 | Medium | 优先返回 `item_name`；为空时保留空值或待确认，不 fallback `product_name` | 先验证 Walmart Listing 名称字段，再按需评估 Lingxing local product | High | No for narrowed scope | `product_name` 明确排除，不得恢复旧接口 fallback。 |

### 6.1 Required Data Lineage Matrix

本矩阵只批准来源范围，不定义最终 API 类型或数据库字段；后续接口 PRP 必须完成版本化数据契约和字段字典审批后才能实现。

| field_or_dataset | current_authoritative_source | raw_field | standard_field | transformation_or_formula | timezone | currency | evidence_path | risk_check | owner_decision_needed | notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 商品身份（`item_id`、`msku`、`store_id`） | Legacy `dim_product`，仅为负责人批准的阶段性只读来源，不是长期权威主数据 | `dp.item_id`, `dp.msku`, `dp.store_id` | 同名 API 候选；最终数据类型和 nullability 由接口 PRP/数据契约批准 | 原值只读，不互相推导，不生成内部 `product_id` | 不适用 | 不适用 | `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md:107`; `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md:109`; `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md:126`; `old-system/source/src/feishuRawSalesRoutes.ts:1008` | 来源新鲜度未知；身份必须保留外部语义 | No for narrowed scope | `store_name` 不由 `store_id` 自动补齐。 |
| `sku` | Legacy `dim_product`，仅为阶段性只读来源 | `dp.sku` | `sku` API 候选；契约必须允许 null | 原值只读；不得从 ItemID/MSKU 推导，不得用于丢弃产品 | 不适用 | 不适用 | `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md:108` | 缺失率 27.06%，存在重复和交叉映射风险 | No for narrowed scope | 不得声明唯一约束。 |
| `item_name` | Legacy `dim_product`，仅为阶段性只读来源 | `dp.item_name` | `item_name` API 候选；最终契约待接口 PRP | 优先原值只读；空值不 fallback `product_name` | 不适用 | 不适用 | `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md:58`; `old-system/source/src/syncLingxingDailyToDb.ts:308` | 空值率和来源新鲜度未由 OD-9 证明 | No for narrowed scope | `product_name` 不进入第一阶段契约。 |

### 6.2 Risk Checklist

| Check | Result | Owner decision / reason |
|---|---|---|
| 本次决策更新连接真实数据库 | No | 本轮只读引用已合并 OD-9 报告。 |
| OD-9 数据库盘点 | Completed | 已在独立 Approved PRP 下完成三表只读结构与脱敏聚合盘点。 |
| 调用真实外部 API | No | 未调用 Lingxing、Walmart 或其他外部 API。 |
| 读取 secrets 或 `.env` | No | 未读取或输出敏感配置。 |
| 修改 `old-system/**` | No | 旧系统只读。 |
| 临时只读来源是否已批准 | Yes | OD-1 已批准 `READ_LEGACY_TEMPORARILY`，仅限本决策五个字段和 Phase 2A 查询。 |
| 外部 API 是否未经验证 | Yes, deferred | OD-10 只批准验证顺序；未验证外部 API 不阻塞当前临时只读范围。 |
| 当前范围权威来源是否明确 | Yes | 五个字段只读 `dim_product`；被排除字段不得进入接口 PRP。 |
| 字段契约是否完成 | No | 后续接口 PRP 必须定义 response schema、类型、nullability、字段字典和数据质量警告；未批准前不得实现。 |
| 旧库性能边界 | Required in API PRP | 必须使用只读账号、受限服务端分页和有界查询；禁止全表加载、写入和未评估扫描。 |
| 时区 | 不适用 / 待确认 | 本次身份候选字段不含已确认时间字段；若后续纳入时间字段，需单独确认口径。 |
| 币种 | 不适用 | 本次排除所有金额、成本、费用和汇率字段。 |
| 当前缩小范围是否存在 `NEED_OWNER_DECISION` | No | OD-1 已批准；OD-3 通过排除 `store_name` 在本阶段解决；其他未决能力均已移出范围。 |
| Overall Decision State | `READY_FOR_PRP` | 只允许创建产品基础信息查询 API PRP，不授权实现。 |

## 7. Explicitly Excluded Findings

以下内容明确不在本次 `READY_FOR_PRP` 范围内：

- `store_name` 及旧系统多表名称 fallback；
- `product_name` fallback；
- `brand`、`category`；
- Walmart publish status、ERP status、人工运营状态；
- `product_type`、生命周期；
- 产品负责人或员工归属；
- manual correction、store alias、SKU mapping 写能力；
- 库存、销售、利润、广告、结算、退款、WFS 费用及其他成本/价格字段；
- mart/read model、新表、migration；
- Walmart/Lingxing 外部 API 同步；
- 后端或前端实现。

这些项目已从第一阶段接口契约中排除，因此不再构成当前缩小范围的 `NEED_OWNER_DECISION`。任何项目重新进入范围，都必须另行更新 Source Decision，并按风险取得负责人批准和独立 PRP。

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

## 8. Owner Decisions and Scoped Resolution

| ID | Final state | Approved Phase 2A boundary |
|---|---|---|
| OD-1 | Approved with restrictions | 第一阶段按 `READ_LEGACY_TEMPORARILY` 临时只读旧库，仅限本决策五个字段、只读账号、有界查询和明确退出里程碑；旧库不是长期主数据模型。 |
| OD-2 | Confirmed | 产品名称优先使用 `item_name`；为空时允许空值或待确认，不默认 fallback `product_name`。 |
| OD-3 | Resolved for Phase 2A | 第一阶段只使用 `store_id`；`store_name` 不进入 response 或前端展示，后续如需使用必须另做 Source Decision / PRP。 |
| OD-4 | Confirmed | SKU/MSKU/ItemID 可作为候选展示字段；SKU 可空、非全局唯一，不推导、不丢弃产品。 |
| OD-5 | Confirmed exclusion | `brand`、`category` 第一阶段排除。 |
| OD-6 | Confirmed exclusion | 基础状态第一阶段排除；后续如需状态，只单独评估 Walmart publish status。 |
| OD-7 | Confirmed deferral | `product_type` 和 CS 前缀推导后置到运营/生命周期模块。 |
| OD-8 | Confirmed deferral | store alias、SKU mapping 和 manual correction 写能力后置到独立 PRP。 |
| OD-9 | Completed | 证据来自 `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md`；三表结构、索引和批准聚合范围已完成盘点。 |
| OD-10 | Confirmed sequence only | 长期先验证 Walmart Listing，再按需评估 Lingxing local product；未授权任何真实外部 API 调用。 |

当前缩小范围不存在未解决的阻塞项。被排除或后置的能力不属于本期接口数据集，不得借 `READY_FOR_PRP` 重新带回。

## 9. Recommended Short-Term Strategy

1. 第一阶段只通过 Legacy Readonly Repository 读取 `dim_product.item_id`、`sku`、`msku`、`item_name`、`store_id`。
2. 不为第一阶段 response 连接 `dim_store` 或 `dim_store_config`；OD-9 对这两表的盘点只用于解决店铺证据，不构成运行时读取授权。
3. 旧库访问必须使用只读账号、服务端受限分页和有界查询；禁止全表加载、前端全量筛选、写入、DDL、临时表或未评估扫描。准确 page-size、timeout、过滤和排序边界由接口 PRP 明确并在实现前审批。
4. SKU 允许为空并必须保留；接口 PRP 必须定义缺失、重复和身份歧义的数据质量警告，不得自动补值或合并。
5. `item_name` 为空时返回空值或待确认状态；不得 fallback `product_name`。
6. 旧表更新时间只能标识行变更候选，接口不得将其宣称为外部来源新鲜度；具体 stale-data 提示由接口 PRP 定义。
7. 本策略不创建新表、mart/read model、同步任务或写路径，也不使旧库成为长期权威来源。

## 10. Recommended Long-Term Strategy

1. 先通过独立验证任务确认 Walmart Listing 的权限、字段、分页、限流、增量和错误行为；当前离线资料不等于验证或接入批准。
2. 只有 Walmart Listing 无法满足批准字段时，才按需评估 Lingxing local product；不得默认建立双来源或双写。
3. 如负责人批准重建，必须另行完成标准层/主数据层 Source Decision 与 PRP，再建设后台 integration、Celery 同步、RAW 留痕、标准化和数据质量检查。
4. 正式查询最终读取新系统已同步且获批的数据层；禁止 API route 实时批量调用外部平台。
5. 外部身份字段保持明确来源；人工运营状态、生命周期、负责人、成本等继续属于独立模块。

### 10.1 Legacy readonly exit criteria

旧库只读过渡以以下可验证里程碑为退出条件：

1. Walmart Listing 来源验证完成。
2. Lingxing local product 来源评估完成，如确有需要。
3. 新系统标准层或主数据层设计完成并通过独立 PRP。
4. 数据同步任务通过独立 PRP 和 Review。
5. 新后端接口切换到新系统批准的权威数据源。
6. 旧库产品基础信息查询下线。

## 11. Remaining Stop Conditions

- 本次缩小范围的数据源决策门禁已满足；这只允许创建接口 PRP，不允许直接实现。
- 在产品基础信息查询 API PRP 经负责人批准并获得单独执行 Prompt 前，禁止编写接口、repository、schema、测试实现或运行数据库查询。
- 如果接口 PRP 需要加入 `store_name`、`product_name` fallback、brand、category、status、product_type 或其他排除字段，必须停止并先更新 Source Decision。
- 如果方案需要查询 `dim_product` 之外的运行时业务表、写旧库、新表、migration、mart/read model、同步任务或真实外部 API，必须停止并另行取得对应 Source Decision、PRP 和负责人授权。
- 如果只读查询的分页、过滤、排序、扫描或超时风险无法在接口 PRP 中界定，接口 PRP 必须保持阻塞，不得以 `READY_FOR_PRP` 代替性能审查。
- 本轮未连接数据库、服务器或外部 API，未执行 SQL，也未读取或输出真实密钥。

## 12. Next Step

下一步只允许创建“产品基础信息查询 API PRP”。该 PRP 必须引用本决策和 OD-9 报告，并仅讨论：

- 只读查询接口；
- Legacy Readonly Repository；
- `item_id`、`sku`、`msku`、`item_name`、`store_id`；
- 权限和数据范围；
- request/response schema、`response_model`、`request_id` 和错误码；
- 服务端分页、过滤、排序、timeout 和查询性能边界；
- 测试；
- SKU 缺失/重复、身份歧义和来源新鲜度的数据质量警告。

该 PRP 不得授权写库、建表、migration、ORM model、mart/read model、外部 API、同步任务或任何被排除字段。只有接口 PRP 经架构师 Review、负责人批准并另行下发实现 Prompt 后，才可开始实现。

## 13. Appendix: Source Discovery Commands Run

最初 Source Discovery 只使用 `git branch`、`git status`、`find`、`rg`、`sed`、`git diff --check`、`bash scripts/check-rule-pack.sh` 和文件补丁写入；未执行旧系统脚本。当前 Source Decision 更新仅引用已合并文档，不重新执行调查或数据库访问。

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
