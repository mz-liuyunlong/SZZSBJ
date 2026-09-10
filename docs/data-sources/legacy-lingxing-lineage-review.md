# 旧系统领星链路证据复核

```text
Status: draft_candidate
Review type: repository-only static evidence review
Database access: No
External API call: No
Secret access: No
```

## 1. 文档定位

`old-system/reports/database/LEGACY_LINGXING_API_LINEAGE_MATRIX.md` 是旧系统迁移证据基线，不是新系统实现方案，也不批准接口调用、RAW 表、同步任务、DIM/FACT、读模型或前端接入。

本复核只确认仓库中能否找到矩阵所列证据路径，并记录矩阵中已列出的旧表和 GET 入口。它没有重新运行旧脚本、连接旧库或验证生产运行状态；源码存在不等于任务仍在生产运行，表名出现不等于表在生产环境存在。

## 2. 覆盖范围

本次覆盖矩阵中的 36 条链路：

- 商品与库存、商品价格、销售；
- 广告 SP、SB、SV、关键词和配置快照；
- 店铺与广告主、商品成本与商品名；
- 采购、批次、本地库存、汇率、头程和 WFS 货件；
- 月度结算、订单结算 WFS 费率、退款、账期和渠道订单；
- 利润派生链；
- CSV、XLSX、PDF 导入链；
- 探针、旧脚本和内存型 PMC 链。

## 3. 证据状态定义

| 状态 | 含义 |
|---|---|
| `LOCATED_STATICALLY` | 矩阵引用的主要文件在当前旧系统副本中可定位；未验证运行状态或生产数据。 |
| `PARTIAL_EVIDENCE` | 部分文件可定位，但关键写入器、解析器、运行状态或完整链路缺失。 |
| `NEEDS_EVIDENCE` | 矩阵引用的关键文件在当前副本中不可定位，或矩阵自身明确说明实现缺失。 |
| `NOT_APPLICABLE` | 该链没有稳定业务 GET，或本身是派生/探针而非独立接口链。 |

## 4. 逐链路静态复核

表中“表”和“GET”均表示矩阵文本可定位，不代表数据库或服务已实测。

| ID | 数据分类 | 证据文件 / 源码路径 | 旧 RAW / DIM / FACT 可定位 | GET 可定位 | 复核结果 |
|---|---|---|---|---|---|
| LX-LINEAGE-001 | 通用基础链路 | `reports/database/LEGACY_DATABASE_SCHEMA_ONLY.sql`、`src/internalReadonlyApi.ts` 可定位 | `raw_lingxing_api`、`sync_task_log` | internal-readonly RAW / sync-task GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-002 | 商品与库存 | `src/syncLingxingDailyToDb.ts`、`src/lingxingSalesRoutes.ts`、`src/internalReadonlyApi.ts` 可定位 | `raw_lingxing_api`、`dim_store`、`dim_product`、`fact_inventory_daily` | inventory / products GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-003 | 商品价格 | `src/syncWalmartListingPrice.ts`、`src/aiBusinessRoutes.ts` 可定位 | `raw_lingxing_walmart_listing`、`dim_product` | 无专用价格 GET；间接入口已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-004 | 销售 | `src/syncLingxingDailyToDb.ts`、销售和 internal-readonly route 可定位 | `raw_lingxing_api`、`fact_sales_daily` | sales / summary / overview GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-005 | 广告商品绩效 SP | 日同步、销售 route、internal-readonly 文件可定位 | `raw_lingxing_api`、`fact_ads_product_daily` | 销售、内部只读和费用 GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-006 | 广告关键词 SP | `src/syncManualAdKeywordDaily.ts`、`src/internalReadonlyApi.ts` 可定位 | `raw_lingxing_api`、`fact_ads_keyword_daily` | keyword-daily GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-007 | 广告商品绩效 SB/SV | `src/syncSbSvAdsDaily.ts`、`src/adsFeeReportRoutes.ts` 可定位 | `raw_lingxing_api`、`fact_ads_product_daily` | 与 SP 共用 GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-008 | 广告配置快照 | `src/syncAdsConfigSnapshotDaily.ts` 可定位 | 三类 snapshot FACT 与状态表已列出 | 无稳定前端专用 GET | `LOCATED_STATICALLY` |
| LX-LINEAGE-009 | 店铺与广告主 | `src/syncWalmartStores.ts`、`src/lingxingSalesRoutes.ts` 可定位 | 未见 RAW；`dim_store_config`、`dim_store` 已列出 | stores GET 已列出 | `LOCATED_STATICALLY`，但缺 RAW |
| LX-LINEAGE-010 | 商品成本与商品名 | 成本和商品名同步文件可定位 | `raw_lingxing_api`、`dim_product_cost_config`、`dim_product` | 多个间接 GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-011 | 采购进度 | `src/syncPurchaseOrders.ts`、`src/pmcInventoryRoutes.ts` 可定位 | `raw_lingxing_api`、采购头/明细 FACT | PMC inventory GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-012 | 采购现金支出 | `src/syncPurchaseCash.ts`、`src/aiFinanceIcpV2Routes.ts` 可定位 | `raw_lingxing_api`、采购现金头/明细 FACT | item-cash-profit GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-013 | 库存批次与成本 | `src/syncLingxingBatch.ts`、`src/aiFinanceRoutes.ts` 可定位 | `raw_lingxing_api`、`fact_lingxing_batch` | 无专用 GET；间接 GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-014 | 本地仓库存 | `src/syncLocalInventory.ts`、`src/pmcInventoryRoutes.ts` 可定位 | inventory RAW、`fact_local_inventory_daily`；仓库列表缺独立 RAW | PMC inventory GET 已列出 | `LOCATED_STATICALLY`，部分来源缺 RAW |
| LX-LINEAGE-015 | 汇率 | `src/syncLingxingFxRate.ts`、`src/aiFinanceRoutes.ts` 可定位 | `raw_lingxing_api`、`fact_lingxing_fx_rate` | finance FX GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-016 | 头程发货与分摊 | `src/syncShippingOrders.ts`、`src/aiFinanceRoutes.ts` 可定位 | `raw_lingxing_api`、shipping 头/明细 FACT | item-cash-profit GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-017 | WFS 货件 | `src/syncWfsShipments.ts`、`src/pmcInventoryRoutes.ts` 可定位 | `raw_lingxing_api`、shipment 头/明细 FACT、事件 | PMC inventory GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-018 | 月度结算利润 | `src/syncSettlementMonthly.ts`、`src/aiFinanceIcpV2Routes.ts` 可定位 | `raw_lingxing_api`、`fact_settlement_msku_monthly` | 无专用 GET；间接 GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-019 | 订单结算 WFS 费率 | `src/syncWfsFeeFromSettlement.ts`、`src/pmcWfsFeeRoutes.ts` 可定位 | `raw_lingxing_settlement_order`、`dim_product_wfs_fee_auto` | WFS fee GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-020 | 售后退款 | `src/syncWalmartReturnOrders.ts`、`src/orderProfitV2Routes.ts` 可定位 | `raw_walmart_return_order`、`fact_refund_daily` | profit / sales-detail GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-021 | 账期与对账单 | `src/syncWalmartBillDaily.ts`、`src/aiFinanceRoutes.ts` 可定位 | `raw_lingxing_api`、reconciliation / credit / commission FACT 与事件 | finance GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-022 | 渠道订单销量 | 同步、清货和业务 route 文件可定位 | `raw_lingxing_api`、渠道销售 FACT | clearance / monthly-plan GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-023 | 促销折扣与快速销量 | `src/syncMpOrderDiscount.ts`、`src/salesDetailV2Routes.ts` 可定位 | 两类 RAW、折扣和快速销售 FACT | profit / sales-detail GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-024 | TEMU 清货刊登 | `src/syncTemuClearanceListing.ts`、`src/clearanceCenterRoutes.ts` 可定位 | `raw_lingxing_api`、`biz_clearance_other_channel` | clearance GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-025 | AI PMC 直连补货 | 三个 `src/ai_pmc/` 文件可定位 | 矩阵明确为内存处理，缺统一 RAW/MySQL 追溯 | 无浏览器 GET | `PARTIAL_EVIDENCE`：运行状态待确认 |
| LX-LINEAGE-026 | 利润派生链 | 三个查询/服务文件可定位 | 上游表与 `fact_profit_daily` 已列出 | 多个利润/销售 GET 已列出 | `NEEDS_EVIDENCE`：矩阵段落标签错位且构建器缺失 |
| LX-LINEAGE-027 | WFS 仓储 CSV | finance route、展开脚本、管理前端文件可定位 | CSV RAW、仓储 FACT 与日摊 FACT | finance / PMC GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-028 | WFS 入库运输 CSV | finance route、管理前端文件可定位 | inbound RAW、运费分摊 FACT | finance / PMC GET 已列出 | `LOCATED_STATICALLY` |
| LX-LINEAGE-029 | 清货目标 XLSX/CSV | 清货 route、管理前端文件可定位 | 矩阵明确不保留原文件/原始行；目标业务表已列出 | clearance GET 已列出 | `LOCATED_STATICALLY`，但缺原文件审计 |
| LX-LINEAGE-030 | 其他渠道清货 XLSX/CSV | 清货 route、管理前端文件可定位 | 矩阵明确不保留原文件/原始行；清货业务表已列出 | clearance GET 已列出 | `LOCATED_STATICALLY`，但缺原文件审计 |
| LX-LINEAGE-031 | 月度规划 XLSX/CSV | 业务 route、月度规划前端文件可定位 | 矩阵明确不保留文件；`biz_monthly_plan` 已列出 | monthly-plan GET 已列出 | `LOCATED_STATICALLY`，但缺原文件审计 |
| LX-LINEAGE-032 | 自动广告搜索词 CSV | rebuild 脚本、internal-readonly、AppShell 可定位 | ads CSV RAW、keyword FACT 已列出 | internal-readonly GET 已列出 | `NEEDS_EVIDENCE`：生产主导入器/API 缺失 |
| LX-LINEAGE-033 | SEM 每日报表 CSV | 矩阵所列 `交付件/walmart_sem_delivery/**` 在当前 clean source 中不可定位 | SEM CSV RAW、ads FACT 仅在矩阵列出 | SEM data GET 仅在矩阵列出 | `NEEDS_EVIDENCE` |
| LX-LINEAGE-034 | SEM 账单 CSV | 矩阵所列 `交付件/walmart_sem_delivery/**` 在当前 clean source 中不可定位 | SEM CSV RAW、billing FACT 仅在矩阵列出 | SEM billing GET 仅在矩阵列出 | `NEEDS_EVIDENCE` |
| LX-LINEAGE-035 | Connect 广告发票 PDF | schema、费用/财务 route、AppShell 可定位 | invoice RAW、head/line/account 表已列出 | ads-fee / credits GET 已列出 | `NEEDS_EVIDENCE`：解析写入器缺失 |
| LX-LINEAGE-036 | 探针与旧脚本 | 三个探针/测试文件可定位 | 无稳定生产 RAW/DIM/FACT | 无正式业务 GET | `LOCATED_STATICALLY`，结论为不直接迁移 |

## 5. 关键迁移风险

1. **订单数口径**：旧销售链把销量写入 `order_count`，不能作为去重订单数迁移。
2. **广告重复计算**：SP/SB/SV、自动搜索词 CSV、SEM 和账单是并行来源，禁止无条件相加。
3. **成本覆盖优先级**：领星采购/头程成本与人工配送费并存，必须在后续 Source Decision 中明确 authority、有效期和覆盖顺序。
4. **利润派生**：日界、汇率、送样阈值、成本快照和缺失成本策略均未满足新系统权威口径要求；本任务不实现利润。
5. **店铺授权缺 RAW**：旧店铺/广告主同步没有完整 RAW 审计，授权状态和历史变更不可仅凭 DIM 反推。
6. **导入审计**：部分 XLSX/CSV 不保存原文件、原表头和拒绝行；Connect PDF 解析器证据缺失。
7. **生产状态未知**：静态文件存在不证明 cron、接口或页面仍在生产运行。

## 6. 结论

- 旧系统溯源矩阵可作为迁移证据基线，但必须连同本复核的缺口状态使用。
- 新系统不得复制旧系统 DIM/FACT 设计、计算口径或运行时依赖。
- 第一阶段应先建设受控的 L2 RAW 留痕，再通过独立 Source Decision / PRP 建设 L3 标准化、L4/L7/L8 结构化与 L9 读模型。
- `NEEDS_EVIDENCE` 链路不得进入实现；真实 JSON、文件样本、数据库或外部接口验证均需另行批准。

## 7. 复核边界

- 未连接数据库、服务器或外部 API。
- 未读取 `.env`、凭据、Token 或 Secret。
- 未运行旧系统脚本，也未修改 `old-system/**`。
- 仅检查仓库路径存在性；未声明任何生产事实。
