# 财务 · 沃尔玛账单同步（领星 statement/list）数据源决策

> **2026-11-08 变更（以本节为准，下文 10-31 原文保留作调查记录）**
>
> Rocky 2026-11-08 23:09 ~ 23:34 定：
> 1. 统一叫「沃尔玛账单」，不再叫「结算账单」。
> 2. **只用一个领星接口 `statement/list`**。`payout/list`（`walmartBillPayoutList`）不登记、不建表；下文 §2 C、§3.2、§6 里关于回款明细的内容作废。
> 3. 表做两层：明细表 `ods_lingxing_walmart_bill_lines` + 按店铺按期汇总表 `mart_walmart_bill_periods`（取代下文的 ODS 两张 + FACT + MART 四张）；原始响应仍进系统共用的原始层。回款对账、现金利润、结算利润三个板块共用这一层，只拉一次。
> 4. 领星「账单总额」（`totalPayable`）在 10-26 本地数据里全是空的 → **每期应付金额 = 有效明细合计**；以后领星给了一致的总额就用总额。应付 ≤ 0 标「本期不打款」；整期明细都被删除标「作废」。负数账单和几期合并打款时沃尔玛都不单独出账单，不另做处理。
> 5. 日期口径已确认：`startDate / endDate` 按**交易日期**（`transactionPostedTimestamp`）筛 —— 10-26 本地数据里每月请求返回的行数 = 按交易日期分月的行数。领星只在账单生成后才给出该期明细。
> 6. 店铺参数用 `sids`（数组，一次一个店）—— 10-26 拉取时自动探测确认（`sid` 不按店过滤，`sids` 按店过滤）。
> 7. 每周三上海 03:00 自动拉（重拉最近 35 天，长账单自动往前补），另加「手动同步」（回款对账页面按钮；动作权限 `action:finance:settlement-reconciliation:sync`，有权限的人都能点）。同步开关默认关闭，上线后由部署 AI 按票据打开。
> 8. 读取接口改为 `GET /api/finance/walmart-bills/periods`；手动同步 `GET` / `POST /api/finance/walmart-bills/sync`。
>
> 实现见 `PRPs/finance-walmart-settlement-sync-v1.md`（2026-11-08 改写）与 `docs/api/finance-walmart-bills.md`。

---

（以下为 2026-10-31 原文）


- 调查日期：2026-10-31
- 调查人：Rocky 侧代码 AI（财务板块）
- 目标 method/path：后端同步（无前端业务接口）：Integration Sync 新增两个领星只读接口 `walmartBillStatementList`（`POST /basicOpen/multiplatformFinance/walmart/bill/statement/list`，契约 `LX-727003CFF7B4`）与 `walmartBillPayoutList`（`POST /basicOpen/multiplatformFinance/walmart/bill/payout/list`，契约 `LX-63E99B54ED72`）；只读查询接口 `GET /api/finance/settlements/periods`、`GET /api/finance/settlements/lines` 留给结算对账 PRP（PR-C）。
- 业务用途：Walmart 每两周给每家店出一张结算账单（账单日 B 打款）。账单明细是 结算利润（③）、结算对账（④）、财务报表（⑤）的唯一底数；回款明细是 Walmart 侧「哪一期、打了多少」的汇总，用来与财务导入的银行 / 平台流水（PR-A）对号。正式上线后由系统按期自动拉取，不再逐期由 Rocky 批准、部署 AI 手跑。
- 接口总体状态：**READY_FOR_PRP**
- 是否包含 NEED_OWNER_DECISION：否
- 负责人批准状态：待确认（生产 outbound / schedule 的开启另需负责人书面授权，与 DATA_PAGES 四接口同一流程）
- 关联证据：
  - 契约快照：`docs/integrations/lingxing/contracts/finance-lx-727003cff7b4.md`（结算账单列表，77 个返回字段）、`docs/integrations/lingxing/contracts/finance-lx-63e99b54ed72.md`（回款明细列表，35 个返回字段），两者 Contract status `READY_FOR_PRP`。
  - 真实数据证据（Rocky 侧工作区，不在仓库）：财务 Demo 自 2026-10-11 起经 Rocky 逐次批准的只读拉取（最近一批归档为 `lx_pull_20261026`）：9 店、窗口 2026-03-01 起、按月切窗口、每页 200，全部 USD。Demo ③④⑤ 已用它跑了 7 个版本，CN2601 与 Walmart 原始结算单逐期对平（Rocky 侧 decisions D-FIN-2026-10-11）。各店行数 / 账单数 / 页数等 control totals 明细保存在 Rocky 侧工作区归档，不写入本仓库。
  - 业务决策：Rocky 2026-10-31 22:36「结算账单直接拉领星，不走 Walmart API；历史从 2026-03-01 起；上线后系统自动拉」；22:44「回款明细一起登记」。
  - 既有基础：`backend/app/modules/integration_sync/`（catalog / scheduler / execution / handlers / RAW blob + request ref）、`dim_lingxing_stores`（生产 9 家店）、DATA_PAGES 决策 `docs/data-sources/decisions/data-pages-daily-sales-listing-order-profit-decision.md` §6 数据库设计原则（外部 ID 字符串、金额 Decimal + 币种、时间三分）。

## 1. 旧系统与来源调查（强制前置）

| 前置调查项 | 证据位置与调查结论 |
|---|---|
| 旧页面 | 旧系统无结算账单页面；财务此前在领星后台 / Walmart 后台看账单、手工对账。Demo ③④⑤ 是唯一业务原型。不适用迁移。 |
| 旧 API | 无。不适用。 |
| 旧接口文件位置 | 不适用。 |
| 读取表 | 旧 MySQL 无结算表；新系统生产（NEWSYS-STATE-20261031）无结算 / 回款表；`gov_integration_interfaces` 18 个接口里没有这两个。 |
| 表写入方 | 本决策新建：唯一写入方 = Integration Sync handler；无人工写入。 |
| cron / 脚本 / 外部 API | Demo 侧 `features/tools/lx_pull`（Rocky 逐次批准、部署 AI 执行）为过渡方案；正式系统接管后 Demo 拉法停用（时点由 Rocky 定）。 |
| 人工写库入口 | 无。对账的人工确认记录属 PR-C，另立表。 |
| 外部平台重新获取可能性 | 可以：领星接口按日期窗口可随时重拉；Walmart 原始 Reconciliation 报告也可从卖家后台下载作为核对。 |
| 少量配置数据可行性 | 不涉及（店铺身份复用 `dim_lingxing_stores`）。 |
| 短期策略 | `REBUILD_SYNC`：经 Integration Sync 受治理采集，默认关闭，负责人授权后开。 |
| 长期策略 | 同上；不接 Walmart 官方 Reconciliation API（领星数据已核平且含店铺 / 佣金字段）。 |

## 2. 数据集分类

| 数据集 | 层 | 对象（建议名） | 分类 | 权威来源 | 必要约束 |
|---|---|---|---|---|---|
| A 账单明细原始页 | L2 RAW | 既有 `ods_api_raw_blobs` + `ods_api_raw_request_refs` | `REBUILD_SYNC` | 领星 statement/list | 每页先落 RAW 再解析；request ref 记 sids / 窗口 / offset；不记认证参数。 |
| B 账单明细（解析） | L3 ODS | `ods_lingxing_walmart_bill_statement_items` | `REBUILD_SYNC` | A | 一行一笔交易；字段见 §3.1；`source_row_hash`（复合键 + id + 同键序号）唯一；按店铺 × reportKey 整期快照替换，消失的行标记不删（见 §3.1）；保留 raw request ref、run id。 |
| C 回款明细（解析） | L3 ODS | `ods_lingxing_walmart_bill_payouts` | `REBUILD_SYNC` | 领星 payout/list | 一行一期打款（店铺 × reportKey）：periodStart/End、totalPayable、settlementCount、settlementDifference、transactionPostedTimestamp。 |
| D 结算事实 | L8 FACT | `fact_walmart_settlement_lines` | `REBUILD_SYNC` | B | 规范化：`source_account_ref` + `store_id`（字符串）+ `report_key` + `source_row_hash`；`numeric(18,4)` + `currency_code`（JSON 按字符串转 Decimal，不经 float）；`report_date`（账单日）、`transaction_posted_at`（Walmart 交易时间，来源时区待首批真实 JSON 确认，默认按 America/Los_Angeles 记 business date）、`amount_type` / `transaction_type` / `transaction_description` 原值保留 + 标准枚举映射版本。 |
| E 期次读模型 | L9 MART | `mart_walmart_settlement_periods` | `REBUILD_SYNC` | D + C | 店铺 × report_key 一行：账期起止、账单日、明细行数、按 amount_type 的合计、应付合计（Σamount）、回款侧 totalPayable / settlementDifference / 打款时间、`sum_matches_payout` 标志。④ 结算对账只读这张。 |

无 `READ_LEGACY_TEMPORARILY`、无 `MIGRATE_ONCE`。Demo 已拉的 2026-03 ~ 10 月 JSONL **不**作为正式数据导入（`ARCHIVE_ONLY`，只用作 control totals 核对），正式数据由授权后的回填运行重新采集。

## 3. 接口级决策

### 3.1 `walmartBillStatementList` — `/basicOpen/multiplatformFinance/walmart/bill/statement/list`

- 用途：账单明细全量。
- 请求（契约 16 参数，实际使用）：`sids`（领星 store_id 数组，**一次一店**，不混店）、`startDate` / `endDate`（Demo 证据：按自然月切窗口可用；日期语义以首批真实 JSON 与领星文档确认 — 候选为 reportDate）、`offset` / `length`（≤ 200）。不使用 search / sort / 过滤参数。
- 分页：offset/length，全量翻完为止；`data.totalCount` 作为完整性校验（页数 × 200 覆盖 totalCount，否则该窗口 run 失败，不发布）。大店单月窗口页数多，按 token bucket 串行。
- Token bucket：契约速率证据 `1`，与 saleStat / returnOrder 同档；单店单窗口串行。
- 返回字段取用（30 个）：`id`、`uniqueNo`、`reportKey`、`reportDate`、`periodStartDate`、`periodEndDate`、`storeId`、`storeName`（仅留痕，不作身份）、`transactionKey`、`transactionType`、`transactionDescription`、`transactionReasonDescription`、`transactionPostedTimestamp`、`amountType`、`amount`、`currency`、`customerOrderNo`、`customerOrderLineNo`、`purchaseOrderNo`、`purchaseOrderLineNo`、`partnerItemId`、`partnerGtin`、`shipQty`、`fulfillmentType`、`commissionRate`、`baseCommissionRate`、`originalCharge`、`originalCommission`、`totalPayable`、`deleteFlag`。其余（收货地址城市 / 州 / 邮编、商品名、税码等）留在 RAW，不进 ODS（邮编 / 城市属买家信息，不入业务层）。
- **行身份与写入方式（真实数据验证结论）**：`uniqueNo` 是账单级（取值数 = reportKey 数），`id` 是订单行级（一个 id 下多种 amountType），都不能单独当行键。在最大店 CN2601 的归档数据上验证：复合键 `store_id + reportKey + transactionKey + customerOrderNo + customerOrderLineNo + amountType + transactionDescription + amount` **即使加上 `id` 仍存在极少数同键重复**（同一订单行、同类型、同金额出现两笔，领星返回即如此）。因此：
  1. **行身份** = 上述复合键 + `id` + **同键序号 `dup_ordinal`**（同一窗口响应内按出现顺序 1、2、…），其 sha1 为 `source_row_hash`；
  2. **写入方式 = 按「店铺 × reportKey」整期快照替换**：每次 run 把该店该账单新拉到的行集合与库中有效集合比对——新增的行插入；`source_row_hash` 相同的行不动；库中有、新集合里没有的行**不删除**，标 `missing_in_snapshot_at`（领星删行但不返回 `deleteFlag=1` 的情况由此可见）；领星事后改了金额 / 描述的行，因 hash 变化表现为「旧行标 missing + 新行插入」，两者通过 `id + transactionKey` 可关联审计；`deleteFlag=1` 的行照常入库并标记，不参与合计。
  3. 一张账单只有在该窗口 run 完整（totalCount 覆盖、control total 对平）时才允许替换；否则保留上一次快照并标 run failed。
  4. 实现 PR 必须用 CN2601 的真实 JSON 重跑「复合键 + id + dup_ordinal」唯一性验证并把结果（只写是否零碰撞，不写行数）贴 PR；出现碰撞即停。
- 增量：按 `reportDate` 窗口；每次定时运行拉「最近 35 天」窗口 upsert（账单出来后仍可能有 Adjustment 补行），回填一次性按月窗口 2026-03-01 起。
- 枚举（真实数据）：`transactionType` ∈ Sale / Adjustment / Refund / Campaigns / Service Fee / Other / Dispute Settlement；`amountType` 18 种（Product Price、Commission on Product、Fee/Reimbursement、Product tax、Product tax withheld、Total Walmart Funded Savings、Promo Code、SEM Marketing Fee、WFS Inventory Fee/Reimbursement、WFS Inbound Fee、WFS Fee/Reimbursement、Other tax (Fees)、Extra Savings、ExcessRefundAdjustment、Review Accelerator Fee、Retroactive Discount、Item Fees、空）；未知值保留 raw、标 DQ，不猜。
- 币种：真实数据全部 USD；仍按字段存 `currency_code`，不推断。

### 3.2 `walmartBillPayoutList` — `/basicOpen/multiplatformFinance/walmart/bill/payout/list`

- 用途：Walmart 侧每期打款汇总（结算对账的「平台说打了多少」一侧）。
- 请求：`sids`（一次一店）、`startDate` / `endDate`、`offset` / `length`（≤ 200）；不用 fieldCompares / hasDifference 过滤（全量拉，差异在本地算）。
- 返回字段取用：`id`、`reportKey`、`periodStartDate`、`periodEndDate`、`periodRange`、`storeId`、`totalPayable`、`settlementCount`、`settlementDifference`、`transactionType`、`transactionDescription`、`transactionPostedTimestamp`、`currency`。
- 唯一键：`store_id + reportKey`（一期一行）；若真实数据出现同 reportKey 多行（分币种 / 分账户），实现 PR 改为 `store_id + reportKey + id` 并记录。
- **本接口 Demo 未拉过**，没有真实 JSON；实现 PR 先做一次受控只读探测（一店、一个月窗口、dry-run → 真实 1 页）确认字段与分页，再进 handler。
- 增量：同 3.1。

### 3.3 共同约束

- 店铺身份只认领星 `storeId`（字符串），映射 `dim_lingxing_stores`；`storeName` 只留痕。Rocky 2026-10-30 已把 CN2502 排除在 Walmart 远程采集之外，但**结算账单 9 店都拉**（CN2502 有历史账单）。
- 一店一 run、一窗口一 work item；单店失败隔离；部分窗口失败不发布 MART。
- 金额：JSON 数值一律按**字符串**读取后转 `Decimal`（解析器使用 `parse_float=Decimal` 或等价方式，全链路不经 float），落库 `numeric(18,4)` + `currency_code`，比较与合计用 `Decimal`、`ROUND_HALF_UP`；`totalSum` 用于窗口级 control total（Σamount 与 `data.totalSum.amount` 差 > 0.01 → run 标 DQ 失败）。
- 时间：`reportDate` = 账单日（date）；`transactionPostedTimestamp` 保留原文 + 来源时区字段；展示时区按仓库规范。
- 默认全关：`outbound_enabled=false`、`is_enabled=false`、`schedule_enabled=false`；回填与定时各需负责人授权一次。

## 4. 调度与回填

> 以下定时与回填均为**设计建议，待负责人书面授权**；本 PR 与后续实现 PR 都不得按本文档自动开启生产同步、定时或回填（负责人 2026-11-02 整改清单 §七 290-02）。

- 定时（建议，待授权）：每周三 03:00 Asia/Shanghai（账单日 B 为双周二，B+1 凌晨），每店拉最近 35 天窗口，upsert。
- 回填（建议，待授权）：授权后一次性手动运行，9 店 × 2026-03-01 起按月窗口，按 Demo 归档的 control totals（每店行数、账单数，保存在 Rocky 侧工作区）核对，比对口径为 reportDate ≤ 归档截止账单日。
- Demo 拉法停用时点：正式回填通过 control totals 且 ④ 页面上线后，由 Rocky 决定。

## 5. 权限与敏感性

- 同步运行：既有 `integrations:execute` / 任务中心页面权限；无新前端。
- 数据属「结算」敏感域：D / E 的读取接口（PR-C）需 `page:finance:settlement-reconciliation:view` + data scope（店铺）+ 字段权限（订单号、买家相关字段不出 API；RAW 中的收货地址永不进业务层）。
- 日志 / 错误不打印 RAW 行、金额明细、认证参数。

## 6. 质量门禁

- 窗口完整性：页数覆盖 totalCount；`totalSum.amount` 与 Σamount 对平。
- 行键无碰撞；`deleteFlag=1` 行保留但标记，不参与合计。
- 期次一致性：`mart_walmart_settlement_periods.sum_amount` 与 payout `totalPayable` 的差 = `settlementDifference`（容差 0.01），否则标「待核」。
- 新 amountType / transactionType 出现 → DQ 告警，不入标准枚举。

## 7. 退出条件 / 风险

- 无旧库依赖，无退出条件。
- 风险：领星接口 startDate / endDate 的日期语义（账单日 vs 交易日）与 payout/list 的字段 / 分页**必须在受控只读探测确认后才进入实现**；领星同步 Walmart 有滞后（Demo 观察 1–3 天），B+1 可能拉不到最新一期 → 35 天滚动窗口兜底；大店回填页数多（按月窗口拆分、串行），注意 token bucket。

## 负责人决定

（待技术负责人填写：批准 / 修改项 / 日期；生产 outbound / 回填 / schedule 三项授权分别记录）
