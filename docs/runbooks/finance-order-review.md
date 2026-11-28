# 订单审核 · 上线与录成本 SOP（结算利润 V3 PR-OR）

接口与规则：`docs/api/finance-order-review.md`。

## 1. 上线步骤（负责人授权后由部署 AI 按票据执行）

1. 迁移：`uv run alembic upgrade head`（到 `20261127_0101_finance_order_review_permissions`，只登记权限，不建表）。
2. 分配权限：`page:finance:order-review:view`（看）、`action:finance:order-review:cost-entry`（录成本）、`action:finance:order-review:review1`（初审）、`action:finance:order-review:review2`（终审）、`action:finance:order-review:recalc`（重算）。初审与终审分给不同的人。
3. 设置项（生产库写入，仓库里不出现数字）：`cfg_finance_settlement_settings` 里 `wfs_carrier_provider_ids`（`{"provider_ids": [...]}`，按生产库 `ods_lingxing_fin_shipping_detail_items.logistics_way` 以 `WFS` 开头的物流商 id 配置）；没配置前所有发货单来源的行都按 WFS 承运待审。`bill_month_cutoff_day` 不配默认 5 号。
4. 负责人标签规则：`cfg_finance_owner_tag_rules`（标签名 → 负责人），只在生产库。
5. 首次重算：有重算权限的人在页面点「重算」（或 `POST /api/finance/order-review/recalc`），从 2026-10-01 起的期；看期列表的待审 / 自动通过数量是否合理。
6. 前置数据：沃尔玛账单（已上线）、成本计价流水（#369）、发货单 / 明细 / 出库单（#370）三个同步都要先打开并回填，否则订单行全部 `cost_missing`。

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
