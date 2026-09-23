# PRP：DATA-PAGES-1 每日销售 / 订单利润 / Listing 管理真实数据闭环


> **2026-09-24 refund truth override:** Refund Management is the only refund source of truth.
> Refund Management keeps the raw refund event date from `return_order_at::date`
> (`returnOrderDate`). Daily Sales consumes `after_sales_refund_items` directly but attributes
> refund quantity/loss to `purchase_time_at::date`. `purchase_time_at` is already the US order
> time shown by Refund Management, so Daily Sales must not apply any timezone conversion.
> A purchase date is included only when authoritative direct SaleStat exists for that date;
> refund-only historical dates are deferred until sales facts are backfilled. The legacy
> `fact_walmart_refund_items` / `dws_walmart_refund_business_amounts` chain remains retired.
> This rule supersedes older conflicting refund statements later in this historical PRP.

状态：`APPROVED_FOR_IMPLEMENTATION`

关联数据源决策：`docs/data-sources/decisions/data-pages-daily-sales-listing-order-profit-decision.md`

## 0. 2026-09-18 Implementation Amendment

负责人已批准本轮实现，并确认本节覆盖旧 PRP 中与以下口径冲突的内容：

- Daily Sales 商品身份：严格 `store_id + item_id + msku`。
- 页面销售额：净销售额 = SaleStat 原始销售额 - 送样金额 - 已完成退款金额。
- 页面销量/订单量：分别从 SaleStat 原始值剔除有效送样；退款数量不再次扣销量。
- sample-only 商品必须保留 0 付费销售行。
- refund 只认 `REFUND_COMPLETED`，金额直接用 `lineTotalAmount`，按 `purchaseTimeLocale China UTC+8 -> fixed UTC-7` 回归原销售日。
- Ads campaignType = manual + auto + sba + video，日事实按完整快照替换。
- `cost_qty = sales_qty + sample_qty`；当前采购/WFS/头程/仓储成本和负责人取 Product Management。
- 当前汇率 fallback = 6.6；汇率按业务日期快照。
- 店铺佣金按有效版本，缺省 15%。
- 订单利润基于净销售额，不二次扣退款；ROI 分母为采购成本 + 头程成本。
- 30 天退货率 = 近 30 天归属退款量 / 近 30 天实际销量。
- MART 保留 gross / sample / net / cost source / warning 血缘以及 expected-vs-actual 成本扩展字段。
- WFS异常预计值来自 Product Management；未来实际账单独立保存并与预计值做差，支持 Case/追回闭环。未批准的实际账单 source 不得伪造。

实现允许修改仓库代码、测试、模型和新增 Alembic revision；本批准 **不授权** 生产数据库 migration、生产回填、部署、重启或旧 MySQL 访问。

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