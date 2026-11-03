# 财务 · 结算利润 V2 数据源决策

- 调查日期：2026-11-03
- 调查人：Rocky 侧代码 AI（财务板块·结算利润）
- 目标：`PRPs/finance-settlement-profit-v2.md` 及 `/api/finance/settlement-profit/*`
- 决策状态：**READY_FOR_PRP**
- `NEED_OWNER_DECISION = 否`
- 负责人决定：Rocky 2026-11-03，经刘云龙授权（含 2026-11-03 最新回答：汇率无兜底、入库运费只认领星、VDG 未归类、对不上店铺的库存异动进「待指定」）；审核 AI 复审 PRP Rev 4 通过后才可开发
- 旧系统：不读取、不依赖；正式系统按 RAW → ODS → FACT → MART，前端只读 MART / 读模型

## 1. 数据源与通道

| 数据集 | 层 / 表 | 权威来源 | 通道 | 状态 |
|---|---|---|---|---|
| 结算单行 | FACT `fact_walmart_settlement_lines` | Walmart 结算账单 | 既有同步 | 依赖 #290 实现 PR |
| 订单时间 | ODS `ods_lingxing_mp_profit_order_lines` | 领星多平台结算利润-订单 | Integration Sync | READY_FOR_PRP，需扩既有 WFS 同步字段 |
| FIFO 货本 / 库存异动 | ODS `ods_lingxing_wfs_cost_valuation_flow`（库存索赔 PRP 所有，只读 `is_current = true`） | 领星 `/basicOpen/multiplatform/wfs/cost/valuation/detail` | 库存索赔 PRP 的 Integration Sync | 依赖库存索赔 PR 1 |
| WFS 费用明细 | ODS `ods_walmart_wfs_fee_detail_lines` | Walmart WFS 费用明细报表 | `walmart_remote_jobs`，一店一服务器 | READY_FOR_PRP，默认关 |
| 仓储费报表 | ODS `ods_walmart_storage_fee_lines` | Walmart 仓储费报表 | `walmart_remote_jobs`，一店一服务器 | READY_FOR_PRP，默认关 |
| 评价加速器 | ODS `ods_walmart_review_accelerator_snapshots` | 报名商品账期快照 | `walmart_remote_jobs`，一店一服务器 | READY_FOR_PRP，默认关 |
| 广告 | FACT `fact_walmart_ad_item_sp_daily` | 广告日报 | 既有广告同步，补视频与 SEM | READY_FOR_PRP；补齐前标「只含 SP」 |
| 公司级费用 | 资金流水分类结果 | 财务资金流水导入 | 资金流水 PRP / 实现 | 前置依赖；上线前纯利为空 |
| 负责人 | DIM / 读模型 `mart_listing_management_current.owner_ref` | 产品管理 | 账单月最后一天快照 | READY_FOR_PRP |
| 汇率 | 既有 `ref_product_pricing_rule_versions.usd_cny_rate`（只读） | 定价规则版本 | 账单月内生效版本 | READY_FOR_PRP；无兜底，见 §2.3 |

不使用的来源：领星 WFS 货件列表（`queryWFSCargoPage`）不同步、不建表（入库运费只认领星头程，§2.1）；不新建任何汇率表；不读旧系统。

### 1.1 领星 WFS 成本计价（Rocky 2026-11-03 补充）

- 本决策不再拥有该接口：ODS 表 `ods_lingxing_wfs_cost_valuation_flow`、同步、契约快照与 SOURCE_MAP / INVENTORY / DATA_INTERFACE_REGISTRY 登记，全部由「库存索赔」PRP 的 PR 1 负责（接口键沿用手工键 `LX-8437AD0BCB9E`）。
- 该表按「同步批次 + 顺序号」入库、窗口内整段替换，唯一键 (raw_request_ref_id, source_item_ordinal)；流水号会重复、会变，不能作业务键。
- 结算利润只读 `is_current = true` 的行：货本按 订单号 + GTIN 匹配；库存异动以该行 id 为来源（`fact_inventory_movement_lines` 唯一键 (source_flow_id, calc_version)），不对该表建外键。
- 店铺：用该行的 store_id（sid 优先，否则 store_code 对照）。对不上店铺的异动按 §2.11 处理：财务指定前不写库存异动表，只写待指定，待指定的 store_id 存占位值 `__unmapped__`（不存 NULL）；指定后写入库存异动表，store_id = 指定店铺、`store_mapping_status = manual_assigned`。

## 2. 负责人已决定的业务口径

### 2.1 入库运费（Rocky 2026-11-03 最新）

只认领星 WFS 发货单物流费用（已含在 FIFO 头程里）。领星没填的，订单进订单审核「缺头程成本」（reason `missing_head`），由财务用 adjustment kind=cost 手工补；不自动补、不按货件分摊、不出补数清单，不同步领星货件列表。结算单里的 WPC / 入库运费扣款不计成本，在对平页列「入库运费：领星 vs 结算单」差异，不算对平失败（与广告同样处理）。国内发货单不涉及。

### 2.2 仓储费

金额以结算单仓储费行为准，按扣费账单月归月；商品比例取新同步 Walmart 仓储费报表该期 SKU 占比；该期没有报表时用该店最近一个账期占比并标注。不读旧系统，不设置迁移期旧表只读选项。

### 2.3 汇率与币种（Rocky 2026-11-03 最新）

只用 `ref_product_pricing_rule_versions.usd_cny_rate` 账单月内生效版本。货本 ¥→$ 与结算利润 $→¥ 使用同一汇率；纯利、C、固定额均按 CNY 计算与展示；结算利润同时给 USD 原值和 CNY 折算值。没有汇率就不换算，不做任何兜底（不用上月、不手录、不估算）：CNY 字段留空，`fx_status=missing`，纯利不算，不可结账（错误码 `FX_MISSING`）。不新建任何汇率表。

### 2.4 广告

广告金额取 `fact_walmart_ad_item_sp_daily` 广告日报（补视频与 SEM 后），按日报直接落商品。结算单广告扣款行（SEM Marketing Fee / Campaigns 等）不计成本，只在对平页单列「广告：日报 vs 结算单 / 信用卡」差异，不算对平失败；补齐视频 / SEM 前页面标「只含 SP」。

### 2.5 弃置费

货值与操作费都按弃置发生月计入；操作费从 WFS 服务费列移到「弃置损耗」列，只移一次，以结算单行为准；费用明细报表 `RC_InventoryDisposalFee` 不重复计入。对平页单列「跨月弃置操作费」一行。

### 2.6 负责人

负责人来源为 `mart_listing_management_current.owner_ref`，不是 `dim_walmart_listings`。按账单月最后一天的值取，月中换人不拆分。

### 2.7 纯利

- C = 当月管理费用 + 财务费用 + 税费（CNY）。
- `cfg_net_profit_allocation` 默认剔除林翔、刘云龙，财务主管可按生效月修改；剔除人不计入 N、不拿固定额、负责商品 C 分摊为 0。
- N = 剔除名单以外、当月有商品销售的负责人数；每人固定 ¥15,000，剩余 `C - 15,000 × N` 按当月结算销售额占比分配，为负照分；每人所得再按其负责商品销售额分到商品。
- N 内负责人销售额为 0 时报 `OWNER_SALES_ZERO` 并阻止结账。
- 资金流水分类上线前纯利为空，标「等资金流水上线」。
- 复核样例：C ¥235,292、N 10、固定 ¥150,000、剩余 ¥85,292；A/B/C 销售额占比 50%/30%/20% 时，剩余分配为 ¥42,646/¥25,587.60/¥17,058.40。

### 2.8 评价加速器

首个账期没有上期快照时按报名商品当期销售额分并标注；Δ 评论数 < 0 按 0 计；售价取 `std_walmart_monitor_listing_observations`：按 store_id + item_id 取快照日或之前最近一次成功采集的 `sale_price_amount`，空则 `strike_price_amount`（只作分摊权重，不产生差额）；Rocky 2026-11-03：只按「新增评论数 × 单价」分摊，不写任何兜底分支。通道只能走 `walmart_remote_jobs`（一店一服务器，不在 Mac 调）；按账期自动拉、不逐次审批。首次开启 outbound / schedule 仍需 Rocky 书面授权并记入本决策。

### 2.9 VDG（供应商短少 / 损坏，Rocky 2026-11-03）

标「未归类」（category `unclassified`），不参与计算，一出现就告警；目前没有这种情况，出现后由 Rocky 定归类再改字典。

### 2.10 审核、撤销与结账

撤销已终审订单上的调整回到待初审；终审后再修改重走初审；同一人不能对同单既初审又终审；已结账月禁止 adjust / review / revoke，返回 `MONTH_CLOSED`；退回回到上一步并必填原因。订单行使用稳定 `line_key`，结账后源数据变化只写 `fact_settlement_post_close_diffs`，不改已结账数。

### 2.11 对不上店铺的库存异动（Rocky 2026-11-03，按推荐）

领星流水对不上任何店铺的库存异动（例如弃置损耗）不进任何店铺，放进订单审核「待指定」行（待指定表和订单审核表的 store_id 存占位值 `__unmapped__`，不是 NULL；source_kind `inventory_unmapped_store`；领星 store_code 存在 detail 里；`__unmapped__` 不出现在店铺列表和筛选里，页面显示「未对上店铺」，只有全部店铺数据范围的财务用户可见），由财务用 adjustment kind `assign_store` 手工指定归属店铺，走初审 / 终审、可撤销；未指定前该月所有店铺不可结账。细则见 PRP §8.4。

## 3. 权限与依赖提示

`permission_catalog_v2` finance 模块新增 `settlement_profit` 页面；使用 `_slug` key：`page:finance:settlement-profit:view`、`action:finance:settlement-profit:adjust`、`review-first`、`review-final`、`close-month`、`config`，以及 `field:finance:settlement-profit:cost` / `net-profit` / `company-cost`。data scope 复用 `store + owner`。

#289、#290 是已合并的纯文档 PR；实现 PR 尚未落地。`fact_walmart_settlement_lines` 与资金流水表在 main 尚未建立；PR-1 / PR-3 依赖 #290 的实现 PR，纯利依赖资金流水导入实现与分类。依赖未落地前，PR-3 使用合成数据和测试内建表通过 CI。

## 4. 结论

本决策状态为 `READY_FOR_PRP`，`NEED_OWNER_DECISION = 否`。审核 AI 复审确认前不开发、不调用真实接口、不开启 outbound / schedule。
