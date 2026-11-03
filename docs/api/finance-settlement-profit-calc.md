# 财务 · 结算利润 V2 计算口径（PR-3）

依据：`PRPs/finance-settlement-profit-v2.md` Rev 4.6 §0、§8。代码：`backend/app/modules/finance/settlement_profit/`。

## 结构

| 文件 | 作用 |
|---|---|
| `inputs.py` | 一店一月的内存输入；结算单行按 `SettlementKind` 归类 |
| `money.py` | 账单月（账单日 ≤ 次月 5 号算上月）、¥/$ 换算（无汇率不换算）、最大余数法分摊 |
| `keys.py` | `line_key`、内容 hash（排除 id、calc_version、`source_flow_id`、`source_run_ids` 等技术字段） |
| `rules.py` | businessType 字典、评价加速器权重、纯利分配 |
| `engine.py` | 一店一月纯计算：订单行 → 商品 → 订单分摊 → 人工调整 → 毛利 → 对平；对不上店铺的库存异动 |
| `persistence.py` | 写 PR-1 表：calc_version、整月结果 hash、结账冻结与结账后差异 |
| `service.py` | 整月重算入口 `recalculate_month`：各店计算 → 跨店纯利 → 落库；数据经 `SettlementProfitLoader` 读取 |

## 计算顺序

1. 结算单行按类型分三类。订单级（销售、补贴、退款、佣金、履约费、退货费、代扣税）带订单号，直接落订单行。商品级（WFS 服务费、弃置操作费、仓储费、评价加速器）先落商品，再分到订单。广告补贴和杂项发票进「其他业务收入」，不进结算利润。广告扣款和 WPC / 入库运费扣款只列差异。
2. 商品级费用落商品：
   - WFS 服务费的金额以结算单为准，按费用明细报表各 GTIN 的金额占比分到商品。
   - 弃置操作费（`RC_InventoryDisposalFee`、`WFS_DisposalOrderFee`）也按费用明细的 GTIN 分，但只进「弃置损耗」列，不进 WFS 服务费。
   - 仓储费按仓储费报表的商品占比分；用的是最近账期的报表时，加告警标注。
   - 评价加速器按 §8.6 的权重分。
   - 对不上商品的部分进「待指定」。
3. 商品 → 订单：一般按件数分，评价加速器按销售额分，都用最大余数法。商品当月没有订单时，这笔钱转「待指定」。
4. 货本：按订单号 + GTIN 匹配 FIFO，¥ 按当月汇率换算成 $。头程为 0 或为空记 `missing_head`；采购为 0 或为空记 `missing_purchase`；匹配不到两个都标。
5. 人工调整（只认有效状态的调整）：
   - `cost` 覆盖采购 / 头程。
   - `amount` 覆盖订单级列，覆盖后的差额会体现在对平里。
   - `assign_item` 把待指定指到商品。
   - `assign_store` 把对不上店铺的异动指到店铺。
6. 库存异动：按 businessType 字典分类。只有真实损耗（LIQ、ODB）的货值计入「弃置损耗」。VDG、未知类型、领星负库存调整只告警，不参与计算。
7. 毛利：结算单各列按原符号相加，再减去货本、广告、弃置货值。没有汇率时，毛利和人民币列都为空，不做兜底。
8. 纯利（跨店）：N 是剔除名单以外、当月有销量的负责人数。剩余额 `C − 固定额 × N` 按各人销售额占比分，每人所得再按其负责商品的销售额分到商品，最后按订单销售额分到订单。资金流水上线前 C 为空，纯利也为空。
9. 对平：结算单总额（不含其他业务收入、广告扣款、WPC）减去「商品月里来自结算单的各列合计 + 未指定的待指定」，差额绝对值 ≤ $0.01 为 ok。

## 状态与结账拦截

- 对平状态：差额超标为 `reconcile_failed`，会生成一条「对平差额」待办。否则，本店有未指定的待指定，或当月有未指定店铺的库存异动，状态为 `unassigned_pending`。其余为 `ok`。
- 拦截码：`FX_MISSING`、`RECONCILE_FAILED`、`UNASSIGNED_PENDING`、`OWNER_MISSING`、`OWNER_SALES_ZERO`。
- 当月只要有一笔对不上店铺的损耗异动还没指定店铺，所有店铺都不能结账（Rocky 2026-11-03 确认）。
- 订单审核状态：最新一次审核晚于最新一次调整时，取审核结果（初审通过 / 终审通过 / 退回）。有调整时为 `adjusted`，有原因待处理时为 `pending`，其余为 `auto`。

## 版本与结账

- 一店一月整体结果的 hash 不变时，不写新 calc_version（`mart_settlement_reconcile_store_month.result_hash`）。
- 领星流水重同步后，flow 行 id 变了但 row_hash 不变，结果仍视为未变。row_hash 变了，原来的待指定和指定结果作废，同时生成新的待办。
- 已结账的月份不改冻结数，只按行比对内容 hash，有差异就写 `fact_settlement_post_close_diffs`。同一行同一新 hash 只记一次。

## 对不上店铺的存储口径

- 还没指定店铺的异动不写 `fact_inventory_movement_lines`，只写待指定。待指定表和订单审核表的 store_id 存占位值 `__unmapped__`，不存 NULL；领星 store_code 放在 detail 里。
- 指定店铺后，才写入库存异动表：store_id 为指定的店铺，`store_mapping_status = manual_assigned`。撤销指定后，回到 `__unmapped__` 待办，该店重算时不再包含这笔异动。
- `__unmapped__` 不是店铺：不出现在店铺列表和店铺筛选里，没有对平行，只有数据范围为全部店铺的财务用户能看到（PR-4 接口负责过滤）。

## 行身份与重同步

- 库存异动的业务身份是 flow 行的 `row_hash`。`source_flow_id` 只用来追溯，不参与比对。
- 重同步后 flow id 变了、row_hash 没变：结果 hash 不变，不写新版本，待指定和指定结果保留。
- row_hash 变了：旧的待指定作废，生成新的待办；如果月份已结账，记一条结账后差异。

## 本 PR 的边界

- 本 PR 的落库代码只接受 `SettlementProfitLoader` 给的输入。测试里的 FakeLoader 和合成 fixture 只用于测试，不能接到生产环境。
- 生产用的读取实现（读结算单行表、领星流水表、汇率、负责人、广告日报）和「同步成功后触发重算」不在本 PR，要等两张源表上 main 后另提 PR，并经审核通过。在那之前没有任何代码会调用 `recalculate_month`。

## 迁移与回滚

- 0074 只在本 PRP 的表上加列、改 CHECK。回滚时，只要待指定、库存异动、人工调整、对平四张表中有任何一条记录，就直接拒绝，不执行 DELETE 或 TRUNCATE。生产环境禁止回滚这个迁移（PRP §13）。
- 与库存索赔 0073 的先后顺序：先合并的一方不动，后合并的一方把迁移改接到已合并的迁移上，最后 main 上只能有一个 head（PRP §10）。

## 依赖与本 PR 未覆盖的部分

- `fact_walmart_settlement_lines`（#290 的实现 PR）和 `ods_lingxing_wfs_cost_valuation_flow`（库存索赔 PR 1）还没上 main。本 PR 只定义读取接口 `SettlementProfitLoader`，测试用合成数据。这两张表合并后，再补数据库读取实现和「同步成功触发重算」的挂接。
- 汇率版本的选取由读取实现负责：只取 `usd_cny_rate`，没有就返回空，不兜底。
- 评价加速器有新增评论但查不到价格时，按已定规则不兜底：与快照缺失相同，整笔转待指定（reason `price_missing`）。
