# 财务 · 订单审核（结算利润 V3 PR-OR）

按期（= 回款对账的期，一期一个账单日）× 店铺 × 订单行审产品成本三项（采购价、头程、尾程）。
PRP：`PRPs/finance-settlement-profit-v3.md` §7、§7A、§8.1～§8.4；表结构：`docs/api/finance-settlement-profit-tables.md`；录成本 SOP：`docs/runbooks/finance-order-review.md`。

## 1. 接口

统一 envelope（`success / data / error / meta / request_id`）；金额一律 `{ "amount": "123.4500", "currency_code": "USD" }`；外部 ID 一律字符串。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/finance/order-review/periods` | `page:finance:order-review:view` | 期列表（店铺 × 期）：账单日、账期、账单月、各审核状态行数、计算版本；只含 2026-10-01 起、有明细的期。参数 `store_ids[]` |
| GET | `/api/finance/order-review/lines` | 同上 | 订单行分页；参数 `period_keys[]`、`store_ids[]`、`status[]`、`reason[]`、`item_ids[]`、`skus[]`、`mskus[]`（精确多选）、`transaction_types[]`（代码，见下）、`line_kinds[]`（sale / refund / mcf）、`owner_ids[]`、`keyword`（订单号 / ItemID / MSKU / SKU / GTIN 模糊）、`sort_by`（白名单：posted_date、platform_order_no、item_id、msku、sales_usd、settlement_amount_usd、cost_total_cny、quantity、review_status、updated_at）、`sort_order`、`page`、`page_size`（≤ 200）；`meta.total` |
| GET | `/api/finance/order-review/lookup` | 同上 | 精确搜索弹层候选：`kind`（item_id / sku / msku / order_no）、`q`、`limit`（≤ 1000），返回 `items`、`truncated` |
| GET | `/api/finance/order-review/transaction-types` | 同上 | 当前订单行里实际出现的交易类型：`code`（`交易类型|描述|金额类型`）、`name_zh`、`name_en`、`category`、`translated`（没翻译的为 false，页面顶部黄条提醒） |
| GET | `/api/finance/order-review/cost-entries/{id}` | 同上 | 一条录入记录（撤销前取 `version`） |
| POST | `/api/finance/order-review/cost-entries` | `action:finance:order-review:cost-entry` | 录成本 / 确认；头 `Idempotency-Key`；body：`store_id`、`scope{msku, shipping_list_code \| outbound_order_no}`、`entry_kind`（confirm / override）、`purchase_cny`、`head_cny`、`last_leg_cny`（自发货才用）、`reason`（override 必填）。同一范围同时只能有一条未撤销的录入；录入后重算受影响的期（含跨期）。返回录入、影响行数、重算期数、`replayed` |
| POST | `/api/finance/order-review/cost-entries/{id}/revoke` | 同上 | 撤销：body `reason`、`expected_version`；受影响的行退回待审并重算 |
| POST | `/api/finance/order-review/review` | 初审 `action:finance:order-review:review1`；终审 `action:finance:order-review:review2` | body：`review_ids[]`（≤ 500，审核行 id = 订单行的 `review_id`）、`stage`（first / final）、`decision`（pass / reject / revert）、`comment`（reject 必填）。逐行返回 `ok` / `review_status` / `version` / `error_code` |
| POST | `/api/finance/order-review/recalc` | `action:finance:order-review:recalc` | 重算：body `store_ids[]`、`period_keys[]`、`report_date_from`；已结账的月返回 `skipped_closed` |

订单行字段：订单号 / 行号 / GTIN / ItemID / SKU / MSKU / 负责人、`line_kind`（sale / refund / mcf）、`fulfillment_type`（wfs / seller）、`quantity`、`transaction_types[]`、收入与费用列（USD：`sales`、`refund`、`promotion`、`commission`、`return_fee`、`tax_withheld`、`wfs_fulfillment_fee`、`mcf_fee`、`settlement_amount`）、货本三项（CNY：`purchase`、`head`、`last_leg`）、`cost_total`（CNY）、`cost_total_usd`、`profit_usd`、`fx_rate` / `fx_status`（missing 时 USD 货本与利润为空）、`cost_sources[]`（每段：`kind`、`quantity`、`msku`、`scope_ref`、三项单价、`reasons`、`entry_id`、发货单 / 出库单号、物流商、预填值）、`cost_entry_ids[]`、`reasons[]`、`auto_passed`、`review_status`（pending / auto / first_passed / final_passed / rejected）、初审 / 终审人与时间、`version`（审核行乐观锁）、`calc_version`。

## 2. 规则要点

- 订单行 = 账单明细按 订单号 × 订单行号 × GTIN 归组；只收订单级金额（WFS 退货处理费 / 弃置费、仓储费、广告、SEM 等店铺级不进订单行）。交易类型翻译表在 `backend/app/modules/settlement_profit/transaction_types.py`，测试断言本地归档出现过的每一种都有中文名；新类型出现时页面提醒、接口 `translated=false`。
- 货本：按订单号 + GTIN 查成本计价流水（is_current），每段 `costSource`：`shipment:SP…` → 发货单明细四项；`无源单配置-固定值` / `无源单配置-最近签收成本` / 空 → 待审（预填流水里的金额）；流水没覆盖全部件数 → `cost_missing`。
- 自动通过（§8.3 第 4 条）：全部段是发货单来源、物流商不在设置项 `wfs_carrier_provider_ids` 里且 `logisticsWay` 不以 WFS 开头（清单没配置算不满足）、四项齐全且之和 = 单位成本、币种 CNY、商品有负责人、没有任何其他原因。
- 自发货：`self_fulfilled` 待审，尾程预填销售出库单物流费用（USD 按账单月汇率折 ¥），录入范围 = MSKU × 出库单。
- 退款行：退货入库（Return Refund / Seller Initiated Returns）才按退回件数 × 原行货本单价冲回；免退货退款不冲；沿用原行结论。同期卖出又取消、净件数 0、未发货的自发货订单 → `cancelled_refund` 待审。
- 已录入 / 确认的范围：计算用录入值覆盖、清掉该段原因；撤销录入后退回待审。
- 写表：内容 hash 不变不写新版本；变了同一事务把旧版本 `is_current=false` 再插新版本；已初审 / 终审的行不自动改状态，计算值变了版本号 +1。
- 审核：终审前须初审；同一人不能既初审又终审（`SAME_REVIEWER`）；退回要原因；自动通过的行不接受审核（`ALREADY_PASSED`）；已结账的月拒绝一切写（`MONTH_CLOSED`）。

错误码：`VALIDATION_ERROR`（422）、`NOT_FOUND`（404）、`MONTH_CLOSED`、`STALE_VERSION`、`STAGE_ORDER`、`SAME_REVIEWER`、`COST_MISSING`（待审行没录成本不能初审）、`COST_ENTRY_EXISTS`、`ALREADY_REVOKED`、`ALREADY_PASSED`（均 409）。

## 3. 本 PR 不做

广告按日期分摊到订单行展示（放结算利润 PR）、店铺级项目审核、结账 / 解锁、评价加速器、SB / SV 广告。
