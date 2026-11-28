# 订单审核 · 上线与录成本 SOP（结算利润 V3 PR-OR）

接口与规则：`docs/api/finance-order-review.md`。

## 1. 上线步骤（负责人授权后由部署 AI 按票据执行）

1. 迁移：`uv run alembic upgrade head`（到 `20261128_0105_settlement_recalc_queue`。0105 只新建重算队列表 `settlement_recalc_queue`。回滚前检查：还有 queued / running 的期就拒绝回滚，先等 sweep 扫空队列或在页面「重算」这些期；只剩 done / failed 才删表。0101 `20261127_0101_finance_order_review_permissions`：登记订单审核权限；加 3 列：审核动作表 `idempotency_key`，录入表 `revoke_idempotency_key`、`platform_order_no`（并改范围约束）；新建 `manual_settlement_review_requests` 表存批量审核的请求编号和结果。回滚前先检查，权限已分配、新列有值、或请求表有数据，就拒绝回滚）。
2. 分配权限：`page:finance:order-review:view`（看）、`action:finance:order-review:cost-entry`（录成本）、`action:finance:order-review:review1`（初审）、`action:finance:order-review:review2`（终审）、`action:finance:order-review:recalc`（重算）。初审与终审分给不同的人。
3. 设置项（生产库写入，仓库里不出现数字）：`cfg_finance_settlement_settings` 里 `wfs_carrier_provider_ids`（`{"provider_ids": [...]}`，按生产库 `ods_lingxing_fin_shipping_detail_items.logistics_way` 以 `WFS` 开头的物流商 id 配置）；没配置前所有发货单来源的行都按 WFS 承运待审。`bill_month_cutoff_day` 不配默认 5 号。
4. 负责人标签规则：`cfg_finance_owner_tag_rules`（标签名 → 负责人），只在生产库。
5. 首次重算：有重算权限的人在页面点「重算」（或 `POST /api/finance/order-review/recalc`），从 2026-10-01 起的期；看期列表的待审 / 自动通过数量是否合理。
6. 前置数据：沃尔玛账单（已上线）、成本计价流水（#369）、发货单 / 明细 / 出库单（#370）三个同步都要先打开并回填，否则订单行全部 `cost_missing`。
7. 日常自动重算只算受影响的期（见接口文档「自动重算」）。同步运行事件里出现 `ORDER_REVIEW_RECALC_MANUAL_NEEDED`（有行拿不到 MSKU 和订单号），或队列里有 `failed` 的期：在页面「重算」按店铺 / 账期补算。查队列：`settlement_recalc_queue` 按 `status` 看（queued / running / done / failed）。queued 的行正常最迟 10 分钟内被 Beat 的 sweep 扫掉；长时间 queued 不动，先查 Celery Beat 和 worker 是否在跑。

## 2. 录成本 SOP（财务）

1. 期列表选期，筛「待审」，看「待审原因」列。
2. WFS 承运货件（`wfs_carrier_shipment`）：头程以领星发货单为准。点「录成本」→ 选范围（MSKU × 发货单）→ 看领星四项预填 → 「确认」保存；领星值不对就选「修正」改值、填原因，并同时去领星把发货单改掉（系统不回写领星）。
3. 自发货（`self_fulfilled`）：录采购价、头程、尾程，范围 = MSKU × 平台订单号。尾程预填 = 该订单已出库 / 已发货的出库单里本 MSKU 的分摊运费合计（按件折单价）；已截单 / 已作废的出库单不计。出库单状态确认不了（页面黄标「出库单状态待核实」）、缺件数、缺分摊运费、找不到本 MSKU 时尾程留空，核实出库单后在「录成本」里手填。
4. 固定值 / 最近签收 / 没有来源 / 发货单明细不完整：按预填或自己查到的值录采购价、头程。
5. 商品无负责人：负责人取领星「产品管理 → 产品负责人」（按 Listing 的本地 SKU）。先在领星补产品负责人、等产品资料同步，或确认 Listing 的店铺 SKU 和本地 SKU 已配对；再点「重算」。
6. 同期卖出又取消（`cancelled_refund`）：确认无成本，直接初审通过。
7. 录入后进初审；初审通过 → 终审（另一人）。退回写原因；终审通过后要先撤销终审才能改。
8. 领星补完 / 改完后重新同步会自动带出新值，已确认 / 修正的行不自动改（版本号 +1 提醒），要改就撤销录入重录。

## 3. 回滚

迁移 0100 的 downgrade 在权限已分给角色时拒绝；页面入口由导航的权限点控制，去掉权限即不可见。
