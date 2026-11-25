# PRP：财务 · 结算利润 V3 —— 订单审核（按期）+ 结算利润（店铺×月）+ 成本来源规则 + WFS 减免/调拨/MCF + 设置项

- Status: Rev 8（Rev 8：按 #358 复审 P2-2，§3 / §6.4 / §10 / §12 / §15 同步业务负责人 2026-11-24 13:46～14:00「探测通过的沃尔玛接口全部开放」；Rev 7 审核 AI 09:39 复核通过。Rev 7：按审核 AI 2026-11-24 第四轮意见改 §8.10 公式一处；Rev 6：按审核 AI 2026-11-24 第三轮意见 P2 ×1、P3 ×2 修订；Rev 5：按审核 AI 2026-11-24 复核意见 P1 ×1、P2 ×2、P3 ×4 修订；Rev 4：2026-11-24 09:08 业务负责人定评价加速器快照走云函数、授权放开 `POST /v3/growth/reviews-accelerator/items`（只此一路径、只读），§16 清空；Rev 3：按审核 AI 2026-11-24 意见 P1 ×5、P2 ×9、P3 ×1 修订，自成一体、不再依赖 v2；Rev 2：业务负责人 2026-11-24 02:07 答复 §16 五项；Rev 1：代码 AI 2026-11-24 按业务负责人 2026-11-09 ~ 11-24 拍板整理）。审核 AI 复核通过，随 PR-1 入库（2026-11-25）
- 取代：`PRPs/finance-settlement-profit-v2.md`（Rev 4.6）。本文自成一体：v2 仍有效的条款已原文并入（§5、§7、§8.1、§8.11 ~ §8.13、§11 ~ §14）。**v2 不入库，本文取代 v2**（v2 只留本地草稿）。
- Owner Approval Required: No（业务负责人 2026-11-24 已拍板，§16 无未决项）
- Implementation authorization state: Yes（审核 AI 2026-11-24 复核通过，按 §10 顺序开发）
- Production execution authorized: No（生产开关、回填、定时各需 业务负责人 书面授权一次，见 §6.5）
- 出票：业务负责人 侧代码 AI（财务板块·结算利润），2026-11-24
- 文件位置：`PRPs/finance-settlement-profit-v3.md`（随 PR-1 入库）；决策文件 `docs/data-sources/decisions/finance-settlement-profit-v3-decision.md`
- 依据：业务负责人 2026-11-09 ~ 11-24 的决策记录与 2026-11 的几次受控探测（决策记录与探测产物只在本地，不入库；结论已并入本文）
- 分支：沿用 `fin/settlement-profit*`；老 PR #307（PR-1 建表）、#308（库存索赔 PR-1）、#309（PR-3 计算）、#310（PR-4 接口）按 §10 重做；迁移号开工时取 main 最新 + 1（§10）

## 0. 业务口径（业务负责人 2026-11-09 ~ 11-24 拍板）

### 0.1 两块看板、两种周期
| 看板 | 周期 | 粒度 | 审核什么 |
|---|---|---|---|
| 订单审核 | 期（= 回款对账的期，一期一个账单日） | 订单行（订单号 × 订单行 × GTIN） | 产品成本三项：采购价、头程、尾程（§8.3、§8.4） |
| 结算利润 | 店铺 × 月（账单月，§8.2） | 店铺 × ItemID（三个视图：店铺汇总 / 店铺×ItemID / 负责人汇总） | 评价加速器、WFS 减免（费用返还）、调拨费、多渠道配送费（§8.6、§8.7） |

- 订单审核是核心，结算利润是汇总展示 + 店铺级项目审核。订单审核的成本结论自动带到结算利润的「货本」列。
- 结账在「店铺 × 月」上做（§8.11）。
- 只显示已出账单的期（未进沃尔玛账单的交易不出现）；从 2026-10-01 起显示。

### 0.2 收入
销售收入、退款（Product Price 部分）、促销折扣 / 冲回按结算单订单行落到订单 × 商品。退款行单独标「退款」；促销折扣 / 冲回从「收入抵减」里拆出来单列。广告补贴（赠送额度）、杂项发票（Misc Invoices）= 公司层收入（其他业务收入），不进结算利润。

### 0.3 费用分类：在哪审、从哪来（唯一来源表 + 取数条件）、怎么展示
| 费用 | 唯一来源表 / 取数条件 | 订单审核 | 结算利润 | 备注 |
|---|---|---|---|---|
| 佣金、退货处理费（**非 WFS** 的退货处理费）、税费代收代缴 | `ods_lingxing_walmart_bill_lines` 订单行，按 transaction_description 分类（不以 WFS 开头） | 展示 | 按订单行汇总 | 不审；WFS 的退货处理费只进「其他 WFS 服务费」 |
| WFS 配送费（WFS 订单尾程） | `ods_lingxing_walmart_bill_lines` 订单行 `WFS Fulfillment fee` | 「尾程」列**只展示**，**不计入货本合计** | 独立列「WFS 配送费」，只扣一次 | 费用本身在 WFS 板块审核 |
| 尾程（非 WFS 自发货订单） | `ods_lingxing_fin_wms_outbound_orders`（销售出库单）物流费用，按平台订单号 | **审**（§8.4） | 计入货本 | 领星没有 → 待审、财务录 |
| 采购价、头程 | `ods_lingxing_fin_shipping_detail_items`（SP 发货单明细），经 `ods_lingxing_wfs_cost_valuation_flow.costSource` 定位发货单 | **审**（§8.3、§8.4） | 计入货本 | WFS 承运货件头程口径见 §8.4 |
| WFS 仓储费 | 金额：`ods_lingxing_walmart_bill_lines` 店铺级行 `WFS StorageFee`；商品占比：`fact_walmart_wfs_fee_lines` fee_source = storage（仓储费报表 CSV 人工导入）同店同期 | 不出现 | 按报表商品占比分到 ItemID | 报表缺当期用最近一期并标注 |
| WFS 入库运输费 | `ods_lingxing_walmart_bill_lines` 行 `WFS InboundTransportationFee`；报告：`fact_walmart_wfs_fee_lines` fee_source = inbound | 不出现 | **不进产品成本、不出现在结算利润** | 只做 WFS 板块现金核对；WFS 承运货件的费用已由财务录在发货单头程里 |
| 调拨费 `WFS InventoryTransferFee` | `ods_lingxing_walmart_bill_lines` 店铺级行；件数来源：`fact_walmart_wfs_fee_lines` fee_source = settlement、fee_type = InventoryTransferFee 的 GTIN + quantity（同店同期）；报表缺则按该店当期各 ItemID 销售件数并标注 | 不出现 | **审**，按件数分到 ItemID | |
| 多渠道配送费 `WFS MultiChannelFulfillmentFee` | `ods_lingxing_walmart_bill_lines` 行（带订单号 / PO / GTIN） | MCF 行作为订单行进入订单审核，货本按 §8.3 同一规则（经 costSource 定位发货单），**审**成本 | 费用在结算利润**审**；费用与货本都记到发货的那家店 | 不跨店关联 |
| WFS 费用返还 `WFS DiscountAdjustment` | `ods_lingxing_walmart_bill_lines` 店铺级行 | 不出现 | **审**；店铺合计单独一行，**不分摊到产品、不预估** | 结算利润**不读** #342 WFS 板块对返还的分摊结果；WFS 板块现有「按配送费 / 仓储费占比分摊返还」只用于 WFS 板块自己的核对展示，保留不删，两边口径互不影响 |
| 评价加速器 | `ods_lingxing_walmart_bill_lines` 店铺级行（评价加速器费）+ `ods_walmart_review_accelerator_snapshots` 权重 | 不出现 | **审**；按 §8.6 权重分到 ItemID | |
| 其他 WFS 服务费（预处理、移除、WFS 退货处理等） | `fact_walmart_wfs_fee_lines` fee_source = settlement 原始行，**排除** DiscountAdjustment、StorageFee、InboundTransportationFee、InventoryTransferFee、MultiChannelFulfillmentFee 及弃置类（InventoryDisposalOrder、RC_InventoryDisposalFee）；有 GTIN 直接落 ItemID；无 GTIN 的行（不论 attribution 是 company / unallocated / unmatched）**不排除**：都进店铺合计单独一行「其他 WFS 服务费（未分到商品）」，财务都可在店铺级审核区把它转成待指定、指定 ItemID 后进商品 | 不出现 | 展示；未分到商品的单列 | WFS 板块审；PR-0 补入的结算单汇总行（仓储费 / 入库运输费周汇总，attribution = company）只用于 WFS 板块现金核对，不进结算利润（仓储费金额从结算单店铺级行取，入库运输费不计） |
| 弃置损耗 | 仓库板块「库存损耗与索赔」结果表（货值）+ `fact_walmart_wfs_fee_lines` 弃置类费用（操作费） | 不出现 | 列「弃置损耗」= 货值 + 操作费 | 弃置订单费、退货中心弃置费**只**进本列，不再进「其他 WFS 服务费」 |
| 包装费 | PMC 发货单金额 | 不出现 | 读发货单；没有则留空「等发货单」 | 不在这里分摊 |
| 广告 SP / SB / SV | `fact_walmart_ad_item_sp_daily`（来源领星广告接口；PR-2 补 SB / SV 同表或同构表），按 store_id + item_id + 日期 | 按日期分摊到订单行展示、**不审** | 按日报按 ItemID | 按实际日期归期 |
| SEM | 旧系统广告板块导出值（旧系统下线前，人工导入表 `manual_settlement_sem_month`） | 不出现 | 展示 | 广告审核板块等旧系统下线后再做 |
| 公司级费用（管理 + 财务 + 税费） | 日记账分类结果（`finance_cashflow` 模块），按日期 | 不出现 | 按日期分到期，再分到产品（§8.8） | 只在结算利润 |

通用规则（结算单明细 vs WFS 费用表）：`ods_lingxing_walmart_bill_lines` 里 transaction_description 以 `WFS` 开头的交易，**只有**上表明确写「从结算单取」的六类（配送费 `WFS Fulfillment fee`、仓储费 `WFS StorageFee`、调拨费 `WFS InventoryTransferFee`、MCF `WFS MultiChannelFulfillmentFee`、返还 `WFS DiscountAdjustment`、入库运输费 `WFS InboundTransportationFee`）从结算单明细计入；其余 WFS 服务费类交易一律**不从结算单明细计入**，只用 `fact_walmart_wfs_fee_lines`。同一笔 WFS 服务费在结算利润里有且只出现一列（§14 验收）。

### 0.4 库存损耗
归仓库板块「库存损耗与索赔」（原「库存异动」改名；仓库板块已预留「移除 / 弃置」「入库差异」）：产品负责人初审、财务核对。结算利润只读其结果，列「弃置损耗」。枚举字典见 §8.13。

### 0.5 纯利与设置项
纯利 = 结算利润 − 公司级费用分摊。以下 6 项做成财务设置（财务主管可改，改动留日志，生效月粒度）：
1. 评价加速器单价公式参数：现 `5 + 0.25 × 售价`，下限 10、上限 30（美元）。
2. 公司级费用分摊参数：每个负责人固定额、剔除名单（两者默认值只在生产库配置，仓库里不出现数字和人名）；口径固定为「负责人固定额 + 剩余按负责人销售额占比，再按负责商品销售额分到产品」（§8.8）。
3. 固定成本来源优先级：SP 发货单取不到时，先取定价表固定成本 / 先取最近签收成本 / 直接待审（默认：直接待审，§8.4）。
4. 评价加速器快照频率：默认每周一次。
5. 无订单提示月数：默认 1 个月（§8.9）。
6. 账单月归属分界日：默认 5 号（§8.2）。
另有（11-09 第 13 条）「按 Listing 标签指定负责人」规则表：标签名 → 负责人，只存数据库，仓库里不出现标签名和人名。

## 1. Goal
按「期 × 店铺 × 订单行」审核产品成本，按「账单月 × 店铺 × ItemID」计算并展示全口径结算利润与纯利；店铺级项目（评价加速器、WFS 返还、调拨费、MCF）在结算利润里审核；店铺 × 月结账冻结，解锁后可改、留日志。

## 2. Why
财务要逐单核成本、按店铺按月看利润并结账；5174 Demo 只到商品 × 月、手工跑、没有审核和锁定；成本来源混乱（领星固定值 / 最近签收 / 空）导致利润不可信。

## 3. Scope
### In scope
- [ ] 领星新系统客户端登记 3 个端点：`/basicOpen/multiplatform/query/shippingList`（v2，platformCodes ["10008"]）、shippingDetail（`shippingListCode`）、wmsOrderList（销售出库单）；同步只拉本公司 Walmart 店铺；落财务自己的「当前状态」表（§6.2），不与 PMC #282 的快照表同名。
- [ ] 广告同步补 SB / SV：广告数据来源是**领星广告接口**（现由旧系统拉取；沃尔玛侧没有可用广告 API，与云函数无关），在既有广告同步模块内补领星 SB / SV 端点的登记与同步；领星拿不到的保持「只含 SP」标注，等广告审核板块（旧系统下线后）再议。
- [ ] 评价加速器报名清单快照：接口是 `POST /v3/growth/reviews-accelerator/items?scrollId=*`（2026-10-11 已实际调通），云函数通道现只放 GET → 云函数白名单**只加这一个 POST 路径**（仍只读、无其他域名），重建 SCF 包、每店切 stable（业务负责人 2026-11-24 09:19 书面授权，见 §15 第 15 条）；每周拉一次（设置项）。
- [ ] 计算任务、FACT / MART / MANUAL / CFG 表、读接口与操作接口、权限、审计。
- [ ] 结算单里仓储费 / 入库运输费汇总行导入 WFS 表（记公司，核对排除配送费）；16 个历史结算 CSV 重新导入。
- [ ] 页面：订单审核、结算利润（含列配置、升降序、多选精确搜索、交易类型全列）。
- [ ] 无订单提示与财务分析报告（§8.9）。
### Out of scope
- [ ] 仓库板块「库存损耗与索赔」页（另立 PRP，#308 的表归它）。
- [ ] 广告审核板块（旧系统下线后）。
- [ ] 回款对账 PR 3（结算 JSON 自动拉取）与回款对账修正：另议。SSH runner 不在另议范围，在本 PRP 的 PR-0 删除。
- [ ] 日记账小修、飞书审批单自动匹配（记下不做）。
- [ ] 沃尔玛报表（WFS 结算、仓储费）自动拉取：云函数已在 #358 放开按需报表下单与 ZIP 回传（§6.4），但同步任务与导入接线不在本 PRP；本 PRP 期间这几类继续人工导入 CSV，自动拉取另起。入库运输报告沃尔玛没有按需报表类型，继续人工导入。
- [ ] 历史月份补数：首个计算月 2026-10。

## 4. Navigation / Page
```text
一级导航：财务
二级导航：订单审核（新菜单项）、结算利润（既有菜单项）
页面路径：/finance/order-review?period=…   /finance/settlement-profit?month=…&view=store|item|owner
页面状态：building（5174 预览，wt-preview）→ testing → ready
```

## 5. Permissions

| 角色 | permissionKey | 数据范围 | 可见字段 |
|---|---|---|---|
| 财务专员 | `page:finance:order-review:view`、`action:finance:order-review:cost-entry`、`action:finance:order-review:review-first`；`page:finance:settlement-profit:view`、`action:finance:settlement-profit:adjust`、`action:finance:settlement-profit:review-first` | 全部店铺 | 全部 |
| 财务主管 | 以上 + `action:finance:order-review:review-final`、`action:finance:settlement-profit:review-final`、`action:finance:settlement-profit:close-month`（含解锁）、`action:finance:settlement-profit:config` | 全部店铺 | 全部 |
| 管理层 | 两个 page view | 全部店铺 | 全部，只读 |
| 运营负责人 | 两个 page view（data scope = owner） | 只看自己负责的商品 | 结算利润与纯利；公司级费用总额、他人数据、货本单价不可见 |

- 数据范围资源：`store` + `owner`；财务角色与管理层不受 owner 限制。
- 全部 key 按 #347 RBAC 的 `permission_catalog_v2` 规则登记（finance 模块新增页面 `order_review`，`settlement_profit` 沿用）；字段级 key：`field:finance:settlement-profit:cost` / `net-profit` / `company-cost`。#310 的权限部分按 #347 重做。
- 高风险动作（批量调整 / 审核 ≥ 20 行、解锁、修改设置）：前端二次确认 + 后端要求 `confirm_token`；全部写操作记 `actor_id、actor_role、acted_at、request_id、reason、before、after`。
- 写接口一律要求 `Idempotency-Key` 请求头（同 key 24 小时内重复请求返回首次结果）。

## 6. Data Source
### 6.1 决策
```text
data source decision file: docs/data-sources/decisions/finance-settlement-profit-v3-decision.md（随 PR-1 入库，内容 = 本文 §0、§8、§15）
decision status: READY_FOR_PRP（§16 答复后）
old-system reference: SEM 值暂读旧系统广告板块导出（旧系统 2026-12 底下线后删）
sensitive or critical domains: 财务 / 利润 / 成本 / 结算 / 库存 / 广告
```

### 6.2 新表（RAW → ODS → FACT → MART；manual_ 只覆盖计算结果）
| 层 | 表 | 写入方 | 键 |
|---|---|---|---|
| ODS | `ods_lingxing_fin_shipping_lists` | shippingList 同步（当前状态表，按 shipping_list_code upsert） | (source_account_ref, store_id, shipping_list_code)。**不与 PMC #282 的 `ods_lingxing_wfs_shipping_lists` 同名**：PMC 表是每次运行一份快照（唯一键 run_id + source_account_ref + shipping_code），财务需要的是当前状态；两表各自同步、互不依赖。#282 先合并时 PR-2 可读其最新快照作为初始化来源，但仍写自己的表 |
| ODS | `ods_lingxing_fin_shipping_detail_items` | shippingDetail 同步 | (source_account_ref, shipping_list_code, msku)；字段：purchase_price、head_stock_price（出库头程）、per_firstlet_cost（头程费用，= actual）、per_firstlet_expected、per_tax、wfs_stock_price、other_cost、transportation_cost、logistics_way、logistics_provider_id、head_fee_type、value_source、delivery_num、currency_code、synced_at |
| ODS | `ods_lingxing_fin_wms_outbound_orders` | wmsOrderList 同步 | (source_account_ref, store_id, outbound_order_no)；物流费用、币种、平台订单号、出库时间 |
| ODS | `ods_walmart_review_accelerator_snapshots` | 评价加速器快照（云函数 POST items，翻 scrollId） | (source_account_ref, store_id, snapshot_date, item_id)；字段：sku、status（ENROLLED / COMPLETE / ELIGIBLE / ENROLLED_FAV）、reviews_collected、enrolled_at、category、原始 JSON 进 RAW |
| FACT | `fact_settlement_order_lines` | 计算任务 | (store_id, period_key, calc_version, line_key)；一期一行一订单行；含收入、各费用、货本三项（采购 / 头程 / 尾程，其中 WFS 订单尾程只展示不入合计）、成本来源（可多段，§8.3）、reasons[]、审核状态 |
| FACT | `fact_settlement_store_month_items` | 计算任务 | (store_id, bill_month, source_kind, source_ref)：店铺级项目（评价加速器、返还、调拨、MCF、公司级费用）及其审核状态 |
| FACT | `fact_settlement_post_close_diffs` | 结账后差异 | (store_id, bill_month, line_key, detected_at)；旧值、新值、发现时间，不改冻结数 |
| MART | `mart_settlement_profit_item_month` | 计算任务 | (store_id, item_id, bill_month) |
| MART | `mart_settlement_order_review` | 计算任务 | (store_id, period_key, line_key)；row_kind = order / store_item / reconcile_diff |
| MART | `mart_settlement_reconcile_store_period` | 计算任务 | (store_id, period_key) |
| MART | `mart_settlement_no_order_flags` | 计算任务 | (store_id, item_id, bill_month)：§8.9 |
| MANUAL | `manual_settlement_cost_entries` | 订单审核录成本 / 确认 | id；范围 = MSKU × 发货单（或 MSKU × 出库单）；purchase_cny、head_cny、last_leg_cny、entry_kind = confirm / override、reason、status、version |
| MANUAL | `manual_settlement_sem_month` | 财务导入 | (store_id, item_id, bill_month)：SEM 月值（旧系统下线前） |
| MANUAL | `manual_settlement_order_adjustments` | 财务操作 | id；含 version（乐观锁）、status active / revoked、kind = amount / assign_item / note |
| MANUAL | `manual_settlement_review_actions` | 财务操作 | id；stage、decision、comment、line_key |
| MANUAL | `manual_settlement_month_close` | 财务主管 | (store_id, bill_month, seq)：close / unlock 记录，含 reason、frozen calc_version |
| CFG | `cfg_finance_settlement_settings` | 财务主管 | (setting_key, effective_month)：§0.5 六项 |
| CFG | `cfg_finance_owner_tag_rules` | 财务主管 | (tag_name)：标签 → 负责人（值只在生产库） |

金额一律 `numeric(18,4)` + `currency_code`；有折算的字段同时存 `*_amount_orig`、`*_currency_orig`、`*_amount_usd`、`*_amount_cny`、`fx_rate`、`fx_month`、`fx_status`（final / missing；missing 时 `*_amount_cny` 与 `fx_rate` 为空）。外部 ID（订单号、GTIN、item_id、店铺 ID、流水号、report_id）一律字符串。v2 里的 `fact_inventory_movement_lines`、`fact_settlement_unassigned_amounts`、`mart_inventory_movement_month`、`cfg_net_profit_allocation` 不再建（库存归仓库板块；待指定收窄为 §8.12，存 `fact_settlement_store_month_items` status = pending；纯利设置并入 `cfg_finance_settlement_settings`）。

### 6.3 复用的既有表（2026-11-23 生产核对）
| 表 | 用法 |
|---|---|
| `ods_lingxing_walmart_bill_lines`、`mart_walmart_bill_periods` | 结算单明细与期；收入、订单费用、店铺级行的唯一底数（覆盖 2026-03-01 起，9 店） |
| `fact_walmart_order_items`、`fact_walmart_refund_items` | 订单 / 退款行身份与时间 |
| `raw_walmart_wfs_fee_files`、`fact_walmart_wfs_fee_lines`（#342 / #346，main 已有） | WFS 费用明细：fee_source = settlement（结算单 CSV）、storage（仓储费报表 CSV）、inbound（入库运输报告 CSV）三种来源同一张表，既有列 fee_type / reason_code / detail / period_start / period_end / gtin / item_id / msku / quantity / amount_usd / attribution / extra 够用：仓储费报表行用 quantity 存平均在库件数、日费率等放 extra；入库报告行 source_ref 存 Shipment ID、reason_code / detail 照抄。**不新加列**。结算单汇总行（仓储费 / 入库运输费店铺周汇总）按 PR-0 补入，attribution = company |
| `fact_walmart_ad_item_sp_daily` | 广告 SP；SB / SV 在 PR-2 补 |
| `fact_lingxing_fx_rate` | **唯一汇率来源**（取代 v2 的 `ref_product_pricing_rule_versions`） |
| `ods_lingxing_wfs_cost_valuation_flow`（#308，未合） | 订单 → `costSource`（`shipment:SPxxx` / 固定值 / 最近签收 / 空）与 GTIN、MSKU、数量；一个订单行可能对应多段（不同发货单）；本 PRP 只读 |
| `products` / `dws_product_management_pricing_current` | 定价表固定成本（设置项 3 用） |
| `ods_lingxing_purchase_orders` | 采购价兜底展示（不自动用） |
| `mart_listing_management_current` | 负责人（账单月最后一天）、Listing 标签、归档状态 |

### 6.4 Walmart 调用通道（2026-11-14 定）
唯一通道：公司 AI 服务器 → STS → 每店腾讯云函数（alias stable）→ 云函数从 SSM 取 token → 调 marketplace.walmartapis.com `/v3/…` → JSON / PDF / ZIP（base64）回传。#358（业务负责人 2026-11-24 09:19、13:46～14:00 书面授权）后：GET 照旧「服务端登记即可、不改云函数」；只读 POST 11 个（评价加速器清单 / 分类、选品推荐 ×2、报表下单、Listing 质量明细、SEM 查询 ×5），云函数用包内契约钉死方法 / 路径 / 请求体键；按需报表 ZIP 只在同一主机取、≤3.5MB；写（WFS 6 个、SEM 广告活动 4 个）走读写模式 + MAX_RISK=write + 写 key + 审批号 + 共享防重放；未探测通过的能力不登记。本 PRP 用到：评价加速器清单（§8.6）、recon（回款对账）。

### 6.5 生产开关
所有新同步 `is_enabled=false`、`schedule_enabled=false`；开启、回填、定时各需 业务负责人 书面授权一次（落 runbook）。领星探测类调用每次需 业务负责人 批准；正式定时任务开启后不再逐次批准。

## 7. API Contract
统一 envelope 沿用仓库现有格式（`backend/app/core/api.py` 的 `SuccessEnvelope` / `ErrorEnvelope`）：成功 `{ "success": true, "data": ..., "error": null, "meta": { "source": "finance_settlement_profit_v3", "source_tables": [...], "calc_version", "data_as_of", "total" }, "request_id": "..." }`；错误 `{ "success": false, "data": null, "error": { "code", "message", "details" }, "meta": null, "request_id": "..." }`。业务错误码通过 `ApiError` 抛出，沿用既有 `X-Request-ID`。权限不足 403 `FORBIDDEN`；数据范围外 404 `NOT_FOUND`。分页：`page`（从 1）、`page_size`（≤ 200，默认 50），响应 `meta.total`。排序：`sort_by`（白名单字段）、`sort_order` asc / desc。金额字段一律成对：`{ "amount": "123.4500", "currency_code": "USD" }`（字符串小数）。外部 ID 一律字符串。所有 POST / PUT 有 response_model；写操作错误码：`MONTH_CLOSED`、`STALE_VERSION`、`VALIDATION_ERROR`、`STAGE_ORDER`（终审前须初审）、`ALREADY_REVOKED`、`RECONCILE_FAILED`、`OWNER_MISSING`、`OWNER_SALES_ZERO`、`UNASSIGNED_PENDING`、`FX_MISSING`、`PAYOUT_NOT_FINAL`（回款对账未终审）、`NOT_CLOSED`。

| 方法 / 路径 | 请求 | 响应 data |
|---|---|---|
| GET `/api/finance/order-review/periods` | store_ids[] | 期列表（period_key、账单日、窗口、待审数、状态） |
| GET `/api/finance/order-review/lines` | period_keys[]、store_ids[]、status、reason[]、item_ids[]、skus[]、mskus[]（精确多选）、keyword、transaction_types[]、sort_by、sort_order、page、page_size | rows[]：订单行 + 收入 / 费用列 + 货本三项 + cost_source + reasons[] + version |
| GET `/api/finance/order-review/lookup` | kind=item_id / sku / msku、q、limit≤1000 | 精确搜索弹层候选 |
| GET `/api/finance/order-review/transaction-types` | — | 生产账单实际出现的交易类型清单（code、中文名、英文原名） |
| POST `/api/finance/order-review/cost-entries` | Idempotency-Key；body：scope（msku + shipping_list_code 或 outbound_order_no）、purchase_cny、head_cny、last_leg_cny、reason、expected_version | 录入记录；影响的订单行数 |
| POST `/api/finance/order-review/review` | line_ids[]≤500、stage、decision、comment | 每行结果 |
| GET `/api/finance/settlement-profit/summary` | months[]、store_ids[]、owner_ids[]、view、currency、item_ids[]、skus[]、mskus[]、sort_by、sort_order、page、page_size | rows[] + totals（店铺合计含「WFS 费用返还」单独一行） |
| GET `/api/finance/settlement-profit/store-items` | months[]、store_ids[]、kind=review_accelerator / discount_back / transfer_fee / mcf / company_cost | 店铺级项目与审核状态 |
| POST `/api/finance/settlement-profit/store-items/review` | ids[]、stage、decision、comment | 每条结果 |
| GET `/api/finance/settlement-profit/no-order-flags` | months[]、store_ids[] | §8.9 |
| GET `/api/finance/settlement-profit/no-order-flags/export` | months[]、columns[] | 标记清单导出（CSV，列按用户列配置） |
| POST `/api/finance/settlement-profit/months/{month}/close` / `unlock` | confirm_token；store_ids[]、reason（unlock 必填） | 结账 / 解锁记录 |
| GET / PUT `/api/finance/settlement-profit/settings` | setting_key、effective_month | §0.5 六项 + 标签规则 |
| GET `/api/finance/settlement-profit/columns` / PUT | 用户列配置（复用 Listing 管理抽屉的存储） | |

## 7A. UI Requirements
```text
订单审核：/finance/order-review
  顶部：期选择（多选）、店铺、状态（待审 / 自动通过 / 已录成本 / 初审通过 / 终审通过 / 退回）、原因、
        交易类型（列出生产账单里实际出现的全部类型，不省略；每项显示「中文名（英文原名）」，可输入搜索；中文名全部翻译，
        翻译表在代码里维护，测试断言探测清单里的每个类型都有中文名；新类型出现时同步任务告警，翻译补上前不上线）、
        ItemID / SKU / MSKU 多选 + 精确搜索弹层（最多 1000 行）、关键词
  表格：列配置（复用 Listing 管理的列配置抽屉）、每列可升降序；列：订单号、订单行、店铺、ItemID、SKU、MSKU、下单 / 发货 / 结算时间、
        收入（销售 / 退款 / 促销折扣单列）、佣金、WFS 配送费、广告（展示）、采购价、头程、尾程、成本来源、货本合计、利润、状态、原因、版本
  动作：录成本（按 MSKU × 发货单批量）、批量初审 / 终审、退回（原因必填）
结算利润：/finance/settlement-profit
  顶部：账单月（多选，显示该月包含的期范围，如「9.19–10.31」）、店铺、负责人、视图（店铺汇总 / 店铺×ItemID / 负责人汇总，切换不省略列）、
        币种、ItemID / SKU / MSKU 多选 + 精确搜索弹层
  表格：列配置 + 升降序；列：销售、退款、促销折扣、佣金、WFS 配送费、仓储费、调拨费、MCF、其他 WFS 服务费、包装费、广告 SP/SB/SV、SEM、
        评价加速器、弃置损耗、货本、结算利润（USD / CNY）、公司级费用分摊、纯利（CNY）、利润率、无订单标记
  店铺合计区：「WFS 费用返还」单独一行（不分摊）
  店铺级审核区：评价加速器、返还、调拨费、MCF 待审列表，批量初审 / 终审
  结账：按店铺 × 月；已结账灰显并显示结账人 / 时间；解锁按钮（财务主管，confirm_token + 原因）
empty state: 「该期 / 该月没有结算数据」，提示账单同步状态与最近同步时间（#357 的失败红条同样显示）
loading state: 表格骨架屏；写操作按钮转圈并禁用，防重复提交
error state: 显示错误码对应中文说明与 request_id，可重试；STALE_VERSION 提示「数据已被他人修改，请刷新」；MONTH_CLOSED 提示「该月已结账，先解锁」
no-permission state: 无 page 权限显示「没有访问权限」；运营负责人只显示自己负责的商品，公司级费用总额、货本单价列隐藏；无 action 权限的按钮不显示
fx-missing state: 该账单月无汇率 → CNY 列与纯利列显示「汇率缺失」，顶部黄条提示，结账按钮禁用并提示 FX_MISSING
```

## 8. 计算规则
### 8.1 触发与幂等
沃尔玛账单同步、发货单 / 出库单同步、广告同步、快照、人工录入 → 重算受影响的 (store_id, period_key) 与其所属 (store_id, bill_month)；已结账月不重算，只写差异。同一输入重算结果逐字段相同（calc_version 递增，内容 hash 不变则不写新版本）。
内容 hash 口径：不计入 `source_flow_id`、`source_run_ids` 以及 id、calc_version、created_at 等每次重算或重新同步都会变的技术字段。来源为领星成本计价 flow 行的，用该 flow 行的 `row_hash` 加本表业务字段（店铺、期、line_key、SKU / MSKU、数量、金额、币种、fx_status、成本来源、分摊结果等）计算；其他来源只用业务字段。字段顺序固定，数值按列精度规范化后再算。

### 8.2 期、账单月、汇率
- 期 = 回款对账的期（账单日）。账单月 = 账单日归月，分界日为设置项（默认 5 号：账单日 ≤ 次月 5 号算上月）。一个账单月 = 该月包含的所有期，页面显示期范围（如 9.19–10.31）。
- 广告按实际日期落到期；弃置按发生日期落到期；公司级费用按日期落到期（§8.8）。
- 汇率只用 `fact_lingxing_fx_rate`，取账单日所在月；货本 ¥→$ 与结算利润 $→¥ 同汇率；没有则 `fx_status=missing`、CNY 留空、不可结账，不做兜底。
- 舍入：计算全程 `Decimal`，不经 float；分摊用最大余数法，保证分配后合计与被分配总额逐分相等；展示层两位小数，四舍五入（ROUND_HALF_UP）。

### 8.3 货本：成本来源规则
1. 订单行按订单号 + GTIN 查 `ods_lingxing_wfs_cost_valuation_flow`（is_current）取 `costSource`、MSKU、数量。一个订单行可能对应多段（例如 2 件来自两张发货单）：每段各自取数，货本按段数量加权合计。
2. 段 `costSource = shipment:SP…` → 查该发货单 `ods_lingxing_fin_shipping_detail_items` 的 MSKU 行：采购价 = `purchasePrice`、出库头程 = `headStockPrice`、头程费用 = `perFirstletCost`（= `perFirstletActual`，已含 `otherCost`，不再加）、税 = `perTax`；单位成本 = `wfsStockPrice`（¥）。
3. 尾程：WFS 订单的尾程 = 结算单 `WFS Fulfillment fee`，在订单审核「尾程」列只展示、**不计入货本合计**（它已在费用列扣过）；非 WFS 自发货订单的尾程 = 销售出库单物流费用，计入货本。
4. **自动通过**（三条同时满足，且每一段都满足，且该行没有任何其他 reason）：
   - 该段 `costSource` 是 shipment；
   - 该发货单明确是非 WFS 物流商：按 `logistics_provider_id` 对照「WFS 承运商清单」（设置项 `wfs_carrier_provider_ids`，初值由部署 AI 按生产库里 logisticsWay 以 `WFS-` 开头的物流商 id 配置；`logisticsWay` 同时存档作展示）。以下任一条成立即算**不满足**：
     - 物流商 id 为空；
     - id 在 WFS 承运商清单里，或 `logisticsWay` 以 `WFS` 开头；
     - 清单还没配置；
   - shippingDetail 里能找到该 MSKU 行，`purchasePrice`、`headStockPrice`、`perFirstletCost`、`perTax` 都存在且 ≥ 0 且前三项 > 0，四项之和 = `wfsStockPrice`（按列精度比较），币种 CNY。
   任一不满足 → 待审（§8.4）。
5. 退款行的货本：同一订单行在后续期出现退款（Product Price 冲回且退货入库）时，按退回件数 × 该订单行原货本单价冲回货本（负数），记在退款所在期；只退款不退货（件数不回仓）不冲货本。退款行不重新走成本来源判定，沿用原行的来源与审核结论。

### 8.4 待审规则与成本录入
待审原因（reason，一行可多个）：
| reason | 情形 | 财务要做 |
|---|---|---|
| `wfs_carrier_shipment` | 发货单物流商 = WFS（WFS-FedEx 等） | 确认头程（见下「WFS 承运货件头程口径」） |
| `self_fulfilled` | 非 WFS 自发货订单 | 采购价、头程、尾程（尾程预填销售出库单物流费用） |
| `fixed_value` | `costSource` = 固定值 | 采购价、头程 |
| `last_received` | `costSource` = 最近签收成本 | 采购价、头程 |
| `cost_missing` | `costSource` 空 / 匹配不到 flow 行 | 采购价、头程 |
| `shipment_detail_invalid` | `costSource` 是 shipment 但 shippingDetail 找不到该 MSKU、四项有缺 / 为 0 / 之和 ≠ `wfsStockPrice`、币种非 CNY、`logisticsWay` 为空 | 采购价、头程（预填能取到的值） |
| `owner_missing` | 商品无负责人（先按标签规则补，仍无则待审） | 指定负责人 |
| `cancelled_refund` | 同期卖出又取消退款、净件数 0、未发货的自发货订单 | 确认无成本，通过 |
| `price_missing` | 评价加速器分摊时查不到售价（§8.6，店铺级项目的 reason，不在订单行） | 指定 ItemID 或确认按销售额分 |
共 9 个 reason（订单行 8 个 + 店铺级 1 个）。
- **WFS 承运货件头程口径（统一 §0.3、§15 第 8 条）**：以领星发货单上的头程为准（财务在领星维护）。系统把 shippingDetail 的四项预填到待审行，财务点「确认」即生成 `entry_kind = confirm` 的录入记录，订单通过；领星值不对时财务可「修正」（`entry_kind = override`，原因必填），系统提示同时去领星改；领星补完 / 改完后重新同步会自动带出新值，但已确认 / 修正的行不自动改（写差异提示，财务可撤销后重确认）。
- 录入范围 = MSKU × 发货单（或 MSKU × 出库单），一次录入覆盖该范围内所有订单行（含跨期）；录入写 `manual_settlement_cost_entries`（修正表），**不回写领星**。
- 录入后进初审 / 终审；撤销回到待审。同一人不可对同单既初审又终审。
- 同一期内卖出又被取消退款、净件数 0、未发货的自发货订单：**待审**（`cancelled_refund`），财务审核后通过，不自动通过（业务负责人 11-24）。

### 8.5 费用归集
按 §0.3 表：订单行费用直接落行；店铺级行（仓储费按报表占比、调拨费按件数、其他 WFS 服务费按 GTIN / 件数）分到 ItemID；对不上商品的金额进「待指定」待办（财务指定 ItemID），pending 期间该店该月不可结账。WFS 返还不分摊（§8.7）。MCF 行按 GTIN 直接记到发货店铺的 ItemID，同时该订单的货本也记到该店。

### 8.6 评价加速器
- 快照每周一次（设置项），通过 §6.4 通道 POST items（scrollId 翻页到空）拉报名清单；快照键 (store_id, snapshot_date, item_id)。接口只给每个 SKU 的状态和累计评论数 `reviewsCollected`，没有费用金额、扣费日期、费用与评论的对应关系——所以只能当分摊权重，不能把每笔费用精确挂到某条评论（2026-10-11 分析结论）。
- Δ(item) = 账单月最后一次快照 reviewsCollected − 上一账单月最后一次快照；负数记 0；无上期视为 0。
- 权重 = Δ × clamp(a + b × 售价, lo, hi)，a / b / lo / hi 为设置项（默认 5 / 0.25 / 10 / 30）；售价取 `std_walmart_monitor_listing_observations` 快照日前最近一次 `sale_price_amount`，空则 `strike_price_amount`。
- 本月结算单评价加速器费按权重分到 ItemID（最大余数法，总额逐分相等）；有 Δ 但查不到售价 → 该店铺级项目标 `price_missing`、整笔待指定，财务指定 ItemID 或确认改按销售额分（保留 v2 口径：不估价、不写兜底）；Δ 全 0 → 按报名商品当月销售额分；仍分不出 → 待指定。在结算利润里审核（店铺级项目）。

### 8.7 WFS 费用返还、调拨费、多渠道配送费
- 返还（`WFS DiscountAdjustment / Retroactive Discount`）：按实际入账记店铺级「WFS 费用返还」，归入账日所在期 / 账单月；不分摊到产品、不预估。探测结论（probe_nss_20261124）：每店每月最多 1 笔整笔入账（入账日在 25 号后 3～11 天，对应 26 日～25 日窗口），没有明细与原因；口头规则「尾程 + 仓储 9 折、有封顶额」只能解释部分店铺头两个月（≈9～10%），封顶后仍有零星返还、另有店铺比例逐月上升，无法作为计算规则。页面上可显示参考值「9 折 × 上一窗口配送费 + 仓储费」供财务对照（不入账）。
- 调拨费（`WFS InventoryTransferFee`）：店铺级行，按件数分到 ItemID，财务在结算利润里审核。
- MCF（`WFS MultiChannelFulfillmentFee`，带订单号 / PO / GTIN）：费用和货本都记到发货的那家店；在结算利润里审核。

### 8.8 公司级费用与纯利
- 公司级费用（管理 + 财务 + 税费，CNY，来自日记账）按日期落到期：某自然月费用 × 该期账期落在该自然月的天数 / 该自然月天数；只在结算利润出现。C（账单月）= 该账单月内各期分到的费用之和；销售额按账单月（该月各期结算销售额之和）计算。
- 分到产品（不分到店铺），口径（业务负责人 11-24 确认沿用 11-03）：C 如上；N = 剔除名单以外、当账单月有商品销售的负责人数；每人固定额 F（设置项，默认值只在生产库配置）；剩余 C − F × N 按各负责人当月销售额占比分（为负照分）；每人所得再按其负责商品当月销售额分到产品（全部店铺一起算）。剔除名单内的人不计 N、不拿固定额、负责商品分摊为 0。N 内负责人销售额为 0 → `OWNER_SALES_ZERO` 阻止结账。
- 标签为「无用链接」等的商品按标签规则记到指定负责人，不进「没有负责人」报警；该负责人在剔除名单内则不分摊公司级费用（规则值只在生产库）。
- 纯利 = 结算利润（CNY）− 公司级费用分摊；汇率缺失不算。

### 8.9 无订单提示
店铺 × ItemID 连续 N 个账单月（设置项，默认 1）无销售订单，且 WFS 有库存（取最近库存快照 > 0）→ 标记并在财务板块提示。这只是给财务做分析用的数据（财务带着 AI 分析），系统不做固定格式的报告：提供标记清单导出（店铺、ItemID、SKU、负责人、最后订单日、WFS 库存、累计仓储费、弃置损耗，同结算利润表的列配置，财务自选列）。

### 8.10 对平
每店每期：结算单总额 = Σ 订单行结算金额 + Σ 按 ItemID 分摊的店铺级费用 + Σ 店铺级审核项目 + Σ 店铺合计单列项（含「WFS 费用返还」「WFS 服务费（结算单口径）」）+ Σ pending 待指定。其他 WFS 服务费（未分到商品）来自 WFS 费用表，只在结算利润里展示和计入利润，不参与对平；与结算单的差异在「WFS 明细 vs 结算单」列体现。|差额| ≤ $0.01 为 ok；否则 RECONCILE_FAILED，可审核、不可结账、生成待办。
结算单每一行落在公式右边**有且只有一项**：
| 结算单行（`ods_lingxing_walmart_bill_lines`） | 落在 |
|---|---|
| 订单行：销售、退款、促销折扣 / 冲回、佣金、非 WFS 退货处理费、税费代收代缴、`WFS Fulfillment fee`、`WFS MultiChannelFulfillmentFee` | 订单行（MCF 记发货店） |
| 店铺级：`WFS StorageFee`、`WFS InventoryTransferFee`、评价加速器费 | 按 ItemID 分摊的店铺级费用（分不出的部分 → 待指定） |
| 店铺级：`WFS DiscountAdjustment` | 店铺合计单列「WFS 费用返还」 |
| 店铺级：其他以 WFS 开头的服务费交易 | 店铺合计单列项「WFS 服务费（结算单口径）」：不进商品、不进利润计算，只为对平按原金额计入；并与 `fact_walmart_wfs_fee_lines` 同店同期合计列差异（差异不算对平失败，列「WFS 明细 vs 结算单」） |
| `WFS InboundTransportationFee`、广告扣款行 | 只列差异（领星头程 vs 结算单；广告日报 vs 结算单），不计入总额 |
| 广告补贴、Misc Invoices | 公司收入，不计入总额，另列 |
| 对不上商品、无法归类的店铺级行 | 待指定（pending） |
广告日报、领星货本、弃置货值、公司级费用不来自结算单，不参与此对平，另有覆盖率检查（§14）。

### 8.11 结账、解锁、日志
- 结账条件（店铺 × 月，业务负责人 11-24 确认）：该月包含的每一期都满足 (a) 订单审核无待审；(b) 回款对账该期终审通过（钱没回来、没对账就不能结）；另：店铺级项目全部终审通过；无 pending 待指定；对平 ok；汇率齐。
- 结账后冻结 FACT / MART（frozen_at / by / calc_version）；源数据变化只写 `fact_settlement_post_close_diffs`，页面提示，**不允许改**。
- 解锁：财务主管 + confirm_token + 原因；解锁后直接改当月、重算、所有改动留日志（before / after）；改完再结账。
- 订单行 `line_key` = 店铺 + reportKey + 订单号 + 订单行号 + GTIN 的稳定业务键；店铺级项目 `line_key` = 店铺 + 账单月 + source_kind + source_ref；对平差额行 `line_key` = 店铺 + 期 + "reconcile_diff"；manual_ 表引用 `line_key`，不引用会重算变化的 UUID。
- 乐观锁：每行 version；请求带 expected_version，不一致返回 STALE_VERSION。撤销已终审的录入 / 调整回到待初审；终审后修改重走初审；同一人不可对同单既初审又终审；已结账月 adjust / review / revoke 返回 `MONTH_CLOSED`；退回回到上一步且原因必填。
- 调整 / 撤销 / 指定商品 → 同步重算该行所属 (store_id, period_key) 的订单 → 商品月 → 纯利（全店当月，因销售额占比变化）→ 对平；返回新 version。
- 解锁后按最新数据全量重算该店该月，审计记录 before / after 合计。

### 8.12 待指定
对不上商品的店铺级金额写待指定（status pending，store_id 必有；本 PRP 不再有「对不上店铺」的情形，库存异动归仓库板块）。每笔在结算利润店铺级审核区显示为待办；财务指定 ItemID（adjustment kind assign_item）后进入该商品。pending 期间该店该月对平状态 UNASSIGNED_PENDING：可审核、不可结账。
待指定分两种来源（`source_kind`）：来自结算单行的参与 §8.10 对平（计入 Σ pending 待指定）；来自 WFS 费用表的（财务把「其他 WFS 服务费（未分到商品）」转成的待指定）**不参与对平**，否则会与「WFS 服务费（结算单口径）」重复，但同样挡住结账（审核 AI 2026-11-24 P3，PR-3 实现并加测试）。

### 8.13 库存损耗枚举字典（仓库板块维护，本 PRP 只读结果）
| 枚举 | 类别 | 结算利润处理 |
|---|---|---|
| LIQ 弃置、ODB 过期弃置 | 真实损耗 | 扣：货值（采购 + 头程）+ 操作费（弃置订单费、退货中心弃置费），按弃置发生期，列「弃置损耗」 |
| RFS 退回卖家、MTR 调拨 | 非损耗 | 不扣 |
| ADJ、CCA 丢失 / 找回，D16 仓内损坏，ADX 收货差错，VTM 仓内找回 | 找沃尔玛索赔 | 不扣（赔付已在 WFS 服务费里） |
| VDG 供应商短少 / 损坏 | 未归类 | 不参与计算；出现即告警 |
| NEGATIVE_INVENTORY 领星负库存调整 | 领星调账 | 不扣，单列告警 |
| 未知枚举 | 未知异动 | 不参与计算，告警 |

## 9. SOP / API Docs（实现时交付）
- PR-1：表结构文档 `docs/api/finance-settlement-profit-tables.md`
- PR-2：同步 handler 文档 + runbook `docs/runbooks/finance-settlement-profit-sync.md`
- PR-3：计算口径文档 `docs/api/finance-settlement-profit-calc.md`（即本 PRP §8）
- PR-4：API 文档 + OpenAPI metadata + SOP（审核 / 撤销 / 结账 / 解锁）
- PR-5：PageShell help entry + Playwright E2E
另加：`docs/runbooks/finance-order-review.md`（录成本 SOP）、`docs/runbooks/walmart-review-accelerator-snapshot.md`（通道登记与开关）。

## 10. Implementation Plan
合并顺序：**PR-0 → PR-1 → #308（库存索赔 PR-1）→ PR-2 → PR-3 → PR-4 → PR-5**；**PR-SCF** 独立，与 PR-0 / PR-1 并行，PR-2 之前上线。每个 PR 等上一个合并后基于最新 main 开分支，不叠分支；开工时迁移号取 main 最新 + 1，同轮改 `.github/workflows/ci.yml` 两处版本号断言和 `tests/db/test_alembic_scaffold.py`；每个 PR 独立 CI 全绿后再提下一个。

| PR | 内容 | 老 PR 处理 |
|---|---|---|
| PR-0 WFS 汇总行与清理 | ① 结算单仓储费 / 入库运输费店铺周汇总行入 `fact_walmart_wfs_fee_lines`：来自**结算单 CSV 原文件**（解析器不再跳过 StorageFee / InboundTransportationFee 汇总行，`raw_file_id` 非空），attribution = company，来源标结算单汇总；**不从**领星账单明细 `ods_lingxing_walmart_bill_lines` 写进 WFS 费用表；② 同店同期按商品仓储费报表导入后顶掉汇总行；③ 核对表剔除配送费；④ 16 个历史结算 CSV 重导补行；⑤ #346 部件处理：**删除** SSH 执行器（`walmart_remote_pull` 执行脚本）、runner、远端取文件同步任务及其任务中心登记、页面「同步」按钮；**保留** 0091 的表、ZIP 解析器与导入服务层（人工导入继续用）、按店隔离的导入失败计数；`fact_walmart_wfs_inbound_items` 与按货件分摊代码标「不启用」（不删表） | 新 PR |
| PR-1 建表 | §6.2 新表、model registry、scaffold 测试、表结构文档；§6.1 决策文件；本 PRP 入库为 `PRPs/finance-settlement-profit-v3.md`，v2 不入库、本文取代 | #307 关闭重开 |
| #308 库存索赔 PR-1 | `ods_lingxing_wfs_cost_valuation_flow` + 同步（另一 PRP） | 基于 PR-1 后的 main 重开 |
| PR-SCF 云函数开放（#358） | 评价加速器 POST、recon、按需报表下单 + ZIP、payment / insights / sem / misc、SEM 写契约；云端钉死非 GET 契约；独立，可与 PR-0 / PR-1 并行，不依赖财务表 | #358（已授权） |
| PR-2 同步 | shippingList / shippingDetail / wmsOrderList 登记与同步（写 `ods_lingxing_fin_*`）；SB / SV 广告；评价加速器快照同步（依赖 PR-SCF 上线） | 新 PR |
| PR-3 计算 | §8 全部；重算入口；无订单标记 | #309 关闭重开 |
| PR-4 接口 + 权限 | §7；权限按 #347 RBAC 登记；审计 | #310 关闭重开 |
| PR-5 页面 | 订单审核页、结算利润页（列配置、升降序、多选精确搜索、交易类型全列）、设置页；Playwright | 新 PR |

与 PMC #282 不再有同名表（§6.2）；如 #282 先合并，PR-2 只多一个可选的初始化来源，不改本计划。

## 11. Validation Gates
```bash
cd backend
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/modules/finance -q
uv run pytest tests/modules/integration_sync -k "settlement_profit or order_review or shipping or wms_outbound or review_accelerator" -q
uv run pytest tests/db -q && uv run alembic check
cd ../frontend && npm run lint && npx tsc --noEmit -p tsconfig.json && npx vitest run && npx playwright test e2e/finance-settlement-profit e2e/finance-order-review
cd .. && bash scripts/ci-preflight.sh && bash scripts/check-rule-pack.sh
```

## 12. Forbidden Actions（安全红线）
```text
Walmart：只走 §6.4 云函数通道；禁止 SSH 到店铺服务器；禁止在 Mac 本地直连 Walmart 任何接口；云函数可用范围以 #358 登记的契约为准，未探测通过的能力不登记、不调用。
代码 AI：不碰任何服务器（不 SSH / scp / 部署 / 重启）；不读凭证（.secrets/、token、.env、店铺凭证）；不改 .env；不直接连 GitHub，不推 main、不合并、不自己提交 / 提 PR（由部署 AI 提）。
不调用真实领星 / Walmart 接口（业务负责人书面授权的受控探测除外，每次一票）；测试只用合成 fixture。
生产同步开启、回填、定时开启（is_enabled / outbound_enabled / schedule_enabled）：各要业务负责人另行书面授权一次；代码默认全关，不翻转默认值。
不读旧系统数据库（SEM 值由财务从旧系统导出后人工导入）；不连接生产数据库；不部署；不重启服务。
不把真实订单号、金额明细、人名、店铺名、标签名、公司名、带项目前缀的环境变量名写进测试 / 文档 / PR；manual_ 表不得写 RAW / ODS / FACT。
```

## 13. Rollback Plan
每个 PR 独立 revert；manual_ 表回滚前先导出备份；已结账月份以冻结快照为准，不随回滚改变。
迁移回滚不删业务数据：PR-3 迁移的 downgrade 只在 FACT / MANUAL 表都没有记录时才回退结构；只要有一条记录就报错拒绝（`rollback blocked`），不执行任何 DELETE / TRUNCATE。生产环境禁止对已有数据的结算利润迁移做 downgrade；要修正结构一律写新的前向迁移；如确需恢复数据，先导出备份，经业务负责人书面同意后按备份恢复。

## 14. Acceptance Checklist
| 项 | 阈值 | 失败行为 | 测试数据 |
|---|---|---|---|
| 成本来源判定 | 三条件同时满足（shipment、非 WFS 物流商、明细四项有效且之和 = wfsStockPrice、CNY）且无其他 reason → 自动通过；8 个订单行 reason 各一单全部待审；跨两段的订单行一段不满足即待审 | 测试失败 | 合成：每类一单 + 一单跨两张发货单 |
| 成本字段映射 | 单位成本 = purchasePrice + headStockPrice + perFirstletCost + perTax = wfsStockPrice | 测试失败 | 合成（数值取自探测样本结构，不用真实值） |
| 录成本传播 | MSKU × 发货单一次录入覆盖全部订单行并带到结算利润货本 | 测试失败 | 合成 |
| 返还不分摊 | 店铺合计单独一行；ItemID 行合计不含返还；不读 WFS 板块分摊结果 | 测试失败 | 合成 |
| 配送费只扣一次 | WFS 订单利润 = 收入 − 费用（含配送费）− 货本（不含尾程）；尾程列值 = 配送费但不入货本合计 | 测试失败 | 合成：一单 WFS、一单自发货 |
| 弃置操作费只在一列 | 弃置订单费 / 退货中心弃置费只出现在「弃置损耗」，不出现在「其他 WFS 服务费」 | 测试失败 | 合成：同一笔费用 |
| WFS 服务费只在一列 | 结算单里以 WFS 开头、不属六类的交易不从结算单计入商品 / 利润；同一笔 WFS 服务费（结算单行 + WFS 明细行）在结算利润里只出现一列；无 GTIN 行不论 attribution（company / unallocated / unmatched）都出现在店铺合计单列「其他 WFS 服务费（未分到商品）」，其中 unallocated 的无 GTIN 行单独一条用例 | 测试失败 | 合成：同一笔费用两来源 + 一条 unallocated 无 GTIN 行 |
| 退款冲回货本 | 退货入库按件数冲回原单价；只退款不退货不冲 | 测试失败 | 合成 |
| 调拨费件数来源 | 有同期 WFS 明细按其 GTIN 件数分；无则按销售件数分并标注 | 测试失败 | 合成 |
| MCF 归店 | 费用与货本记到发货店 | 测试失败 | 合成 |
| 账单月归属 | 分界日设置生效；月范围 = 期拼接 | 测试失败 | 合成：跨月期 |
| 结账 / 解锁 | 结账后改动被拒 MONTH_CLOSED；解锁后可改、留日志 | 测试失败 | 合成 |
| 无订单标记 | 有库存 + N 月无单才标 | 测试失败 | 合成 |
| 交易类型翻译 | 探测清单里每个类型都有中文名；未翻译类型 0 个 | 测试失败 | 探测清单（只含类型名，无金额） |
| 取消退款订单 | 净件数 0、未发货 → 待审 cancelled_refund | 测试失败 | 合成 |
| 待指定 / 评价加速器缺价 | price_missing → 整笔待指定、不估价；pending 不可结账 | 测试失败 | 合成 |
| WFS 费用表来源的待指定 | 不计入对平公式的 Σ pending 待指定；仍阻止结账 | 测试失败 | 合成：一条转待指定的无 GTIN 行 |
| 负责人缺失 / 销售额 0 | OWNER_MISSING / OWNER_SALES_ZERO 阻止结账 | 测试失败 | 合成 |
| 回款未终审 | 该月任一期回款对账未终审 → 结账拒绝 PAYOUT_NOT_FINAL | 测试失败 | 合成 |
| 设置项生效月 | 六项按生效月取值 | 测试失败 | 合成 |
| 店铺期对平 | 结算单每一行按 §8.10 表落在且只落在一项；总额差 ≤ $0.01（入库运输费行、广告扣款行、公司收入行不计入，只列差异） | RECONCILE_FAILED，不可结账，生成待办 | 合成：一店一期，每类行各一条 |
| 汇率缺失 | 账单月无汇率 → CNY 为空、fx_status=missing、纯利不算；不得出现兜底汇率 | FX_MISSING，不可结账 | 合成 |
| 重算幂等 | 同输入两次结果逐字段相同 | 测试失败 | 合成 |
| 人工操作审计 | 每次写操作有 actor / role / before / after / request_id | 测试失败 | 合成 |
| 公司级费用公式 | 3 人、已知占比、固定额 F → 手算期望值一致 | 测试失败 | 合成（固定额用测试值，不用生产值） |
| 业务对数 | 2026-10 每店对平；与 5174 预览差异表贴 PR（只贴差异，不贴金额明细） | 不合并 | 真实数据 |

## 15. 已拍板事项（业务负责人，日期）
1. 11-09：周期 = 回款对账的期；只放已出账单的期；2026-10-01 起显示；三个视图；订单审核是核心。**11-09 第 4 条（按期结账）、第 5 条（不要月度）自 11-24 起被取代**：结账改为店铺 × 账单月，账单月 = 该月包含的期（§8.2、§8.11）；决策文件 `settlement-profit-period-decisions-20261109.md` 同步加注。
2. 11-09：包装费写进发货单、随订单进成本，结算利润只读。
3. 11-09：公司级费用按账期天数分到期。
4. 11-09 / 11-10：归档无负责人 / 「无用链接」标签商品按标签规则归指定负责人，规则只在数据库。
5. 11-10：仓储费、入库运输费无 API，人工导入 CSV；表字段照旧系统；历史从 2026-05 迁；旧系统 2026-12 底下线。
6. 11-14：Walmart 唯一通道 = 云函数 GET JSON；SSH 通道废除；暂不改云函数。（「暂不改云函数」已被第 15 条取代：只加评价加速器一个 POST。）
7. 11-18：审核对象保持订单维度；退款、促销折扣拆开单列；广告分摊到订单但不在订单审核里审；结算利润按店铺 + ItemID 审核。
8. 11-19 ~ 11-21：成本只取 SP 发货单；自动通过仅限 shipment + 非 WFS 物流商（Rev 3 按审核意见细化为 §8.3 三条件）；WFS 物流商货件的头程以领星发货单为准、财务在领星维护、系统预填财务确认（§8.4 口径）；自发货、固定值、最近签收、空值一律财务录入；固定值也要重录；最近签收按待审；入库运输费不进成本、只现金核对；WFS 物流商零物流费的若干票由财务在领星手工补，系统不管。
9. 11-21：两块看板分工（§0.1、§0.3）；库存板块改名「库存损耗与索赔」归仓库；广告审核板块等旧系统下线；SEM 读旧系统值。
10. 11-22：MCF 费用和货本记到发货店，不跨店；返还需查清；11 月账单不管、只管 10 月（回填已完成，3 月起齐）。
11. 11-23：先做账单同步失败记录小 PR（#357）；PR 3 与回款对账修正另议；审批单自动匹配不做。
12. 11-24：返还无固定规律，按实际入账、店铺合计单独一行、不分摊、不预估；公司级费用分到产品、不分到店；结账后不允许改、解锁后直接改当月留日志；评价加速器快照每周一次可改；无订单提示前提 WFS 有库存、财务板块提示、出分析报告；设置项按 §0.5 六项做。
13. 11-24：成本字段映射确认（§8.3 第 2 条）。
14. 11-24 02:07：公司级费用沿用「负责人固定额 + 剩余按销售额」再分到产品；取消退款净 0 的自发货订单待审（财务审核）；无订单标记只是给财务分析用的数据，不做固定报告；结账必须回款对账该期终审通过；交易类型全部翻译成中文（显示中文 + 英文原名）。

15. 11-24 09:08 ~ 09:19：评价加速器清单接口是 POST，现通道拉不到；**业务负责人书面授权**改云函数放开该 POST（只读）。09:24：广告日报数据来源是领星广告接口（旧系统在拉）。**13:46 ~ 14:00 取代本条「只加一个 POST」口径**：业务负责人书面授权探测通过的沃尔玛接口全部开放（只读 GET / 只读 POST / 按需报表 ZIP / WFS 与 SEM 写），清单 `walmart-api-open-plan-20261124.md`，实施为 #358；未探测通过的 90 个能力不开。第 6 条「暂不改云函数」同被取代。

## 16. 待业务负责人确认
无（2026-11-24 09:19 全部答复：措辞「业务负责人」确认；评价加速器走云函数 POST，已授权）。
