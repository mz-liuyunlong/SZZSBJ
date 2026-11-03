# PRP：财务 · 结算利润 V2 —— 订单级分摊 / 订单审核 / 库存异动与弃置 / 纯利 / 评价加速器

- Status: Rev 4.5（Rev 4.5 按已定规则写明 §8.6 查不到价格的处理：与快照缺失相同，整笔转待指定，不估价；Rev 4.4：Rev 4.4 按 Rocky 2026-11-03 拍板：对不上店铺的库存异动进订单审核「待指定」行，由财务手工指定店铺，见 §8.4、§15 第 13 条；Rev 4.3：Rev 4.3 按审核 M2 补 §8.1、§8.9：内容 hash 与结账后差异比对排除 source_flow_id、source_run_ids，改用领星成本计价 flow 行 row_hash 加业务字段；Rev 4.2：Rev 4 已由审核 AI 2026-11-03 审核通过；Rev 4.1 按审核 M1、M2 修订；Rev 4.2 按 Rocky 2026-11-03 补充：领星 WFS 成本计价表与同步归库存索赔 PRP，本 PRP 改为只读；待审核 AI 确认后提 PR-1）
- Owner Approval Required: No（Rocky 已拍板，2026-11-03，经刘云龙授权）
- Implementation authorization state: Authorized（审核 AI 2026-11-03 审核 Rev 4 通过，按 §10 顺序开发；生产开关仍另需授权）
- Production execution authorized: No（生产同步开关、回填、定时开启各需 Rocky 书面授权一次，见 §6.4）
- 出票：Rocky 侧代码 AI（财务板块·结算利润），2026-11-03
- 文件位置：本地草稿 `features/finance/context/prp-settlement-profit-v2-draft-20261103.md`；入库正式路径 `PRPs/finance-settlement-profit-v2.md`（随 PR-1 由部署 AI 提交，内容与本草稿一致）
- 数据源决策：本地草稿 `features/finance/context/decision-settlement-profit-v2-draft-20261103.md`；正式路径 `docs/data-sources/decisions/finance-settlement-profit-v2-decision.md`；状态 **READY_FOR_PRP**，无未决 NEED_OWNER_DECISION（2026-11-03 由 Rocky 拍板，记录见决策 §4）
- 依赖：#289、#290 是已合并的纯文档 PR；`fact_walmart_settlement_lines` 与资金流水表在 main 尚未建立。PR-1 / PR-3 依赖 #290 的实现 PR；纯利依赖资金流水导入实现与资金流水分类（当前无 PRP，列为本 PRP 前置 / out of scope）；依赖未落地前 PR-3 用合成数据和测试内建表通过 CI。
- 分支：`fin/settlement-profit`，按 §10 分 5 个 PR；分支名已获 Rocky 认可

## 0. 业务口径（Rocky 2026-11-03 拍板，按七个独立小节）

### 0.1 收入
销售收入、平台补贴促销、退款（Product Price 部分）按结算单订单行，落到 订单 × 商品。广告补贴（赠送额度）、其他杂项发票**不进结算利润**，进经营利润表「其他业务收入」（财务报表 PRP），本 PRP 只提供其月合计读接口。

### 0.2 订单费用（结算单本身带订单号）
佣金、WFS 履约费、退货处理费、税费代收代缴，直接按订单行。

### 0.3 商品费用（能对到商品、不带订单号）
| 费用 | 来源 | 落商品方式 | 商品 → 订单 |
|---|---|---|---|
| WFS 服务费（预处理、调拨、移除、费用返还等） | Walmart WFS 费用明细报表，按 GTIN | 直接按 GTIN | 按件数 |
| 仓储费 | 结算单 StorageFee 行决定金额，按扣费账单月归月；新 Walmart 仓储费报表给商品占比 | 按报表商品占比；缺当期报表用最近账期并标注 | 按件数 |
| 入库运费 | 只认领星 WFS 发货单物流费用（已含在 FIFO 头程里），不另列、不按货件分摊、不自动补 | 随 FIFO 货本落到订单 | 随货本；领星没填 → 订单进订单审核「缺头程成本」（reason `missing_head`），财务用 adjustment kind=cost 手工补 |
| 广告（SP / 视频 / SEM） | 广告日报，按结算账期窗口 | 按 item | 按日报；补齐前标「只含 SP」 |
| 测评加速（评价加速器） | 结算单店铺级行 + 报名清单快照 | 见 §8.6 | 按销售额 |

结算单里的 WPC / 入库运费扣款行不计成本，只在对平页列「入库运费：领星 vs 结算单」差异，不算对平失败（与广告同样处理，§8.8）。

推广费（领星推广订单，接口拿不到）、包装费（等 PMC）本期不做，表结构预留列，值为空，不参与计算。

### 0.4 库存损耗
领星 WFS 成本计价明细 businessType 枚举字典（未知枚举 → 进「未知异动」并告警，不参与计算）：
| 枚举 | 类别 | 是否扣利润 |
|---|---|---|
| LIQ 弃置、ODB 过期弃置 | 真实损耗 | 扣：货值（采购 + 头程）+ 操作费（WFS 弃置订单费、退货中心弃置费，从 WFS 服务费挪到「弃置损耗」列，不重复扣），按弃置发生月；结算利润与现金利润都扣 |
| RFS 退回卖家、MTR 调拨 | 非损耗 | 不扣，只记件数、货值、去向 |
| ADJ、CCA 丢失 / 找回，D16 仓内损坏，ADX 收货差错，VTM 仓内找回 | 找沃尔玛索赔 | 不扣（赔付已在 WFS 服务费里）；索赔处理在仓库板块「库存索赔」（另立 PRP） |
| VDG 供应商短少 / 损坏 | 未归类（Rocky 2026-11-03：目前没有这种情况） | 不参与计算；一出现就告警（category `unclassified`），由 Rocky 定归类后改字典 |
| NEGATIVE_INVENTORY 领星负库存调整 | 领星调账 | 不扣，单列告警 |

### 0.5 公司级费用
管理费用 + 财务费用 + 税费（CNY），取资金流水分类结果；资金流水正式上线前纯利列为空并标「等资金流水上线」。

### 0.6 纯利
见 §8.7。剔除名单默认林翔、刘云龙（设置项）；剔除人不计入 N、不拿固定额、负责商品 C 分摊为 0。

### 0.7 对平
见 §8.8。不再有「店铺层未分摊」「零星」；对不上商品的金额进「待指定」（§8.4），不是隐含的店铺层。

## 1. Goal

正式系统后端按「账单月 × 店铺 × 订单 × 商品」计算全口径结算利润与纯利；产出订单审核清单、库存异动汇总、人工调整台账、对平结果；提供页面读接口与审核 / 调整 / 结账接口。结算账单同步成功后自动重算受影响的 店铺 × 账单月；已结账月份冻结。

## 2. Why

财务要按订单逐笔审核结算利润（Rocky 2026-11-03）；现有 Demo 只到 商品 × 月且手工跑；「店铺层未分摊」「零星」导致利润对不平、责任不清；纯利要按负责人分摊公司费用用于考核。

## 3. Scope

### In scope
- [ ] 三个新同步（全部默认关闭）：Walmart WFS 费用明细报表、Walmart 仓储费报表、Walmart 评价加速器报名清单快照；另扩展领星多平台结算利润-订单全字段。领星 WFS 成本计价明细的同步归「库存索赔」PRP，本 PRP 只读其表。不做领星 WFS 货件列表同步（入库运费只认领星头程，§0.3）。
- [ ] 广告同步补视频广告与 SEM（在既有广告同步模块内扩展）。
- [ ] 计算任务（§8 流水），FACT / MART 表，manual_ 覆盖表，cfg 设置表。
- [ ] 读接口与操作接口（§7）、权限（§5）。
- [ ] 文档、Playwright E2E、runbook（§9）。

### Out of scope
- [ ] 仓库板块「库存索赔」页（另立 PRP）。
- [ ] 推广费、包装费（预留列）。
- [ ] 经营利润表「其他业务收入」展示（财务报表 PRP）。
- [ ] 生产同步开启、回填、定时开启的执行（各需书面授权）。
- [ ] 历史月份补数（不为历史缺数据定规则；首个计算月 2026-10）。

## 4. Navigation / Page

```text
一级导航：财务
二级导航：结算利润（既有菜单项）
页面路径：/finance/settlement-profit?tab=summary|orders|inventory|adjustments
页面状态：building（5174 本地预览）→ testing → ready
```

## 5. Permissions

| 角色 | permissionKey | 数据范围 | 可见字段 |
|---|---|---|---|
| 财务专员 | `page:finance:settlement-profit:view`、`action:finance:settlement-profit:adjust`、`action:finance:settlement-profit:review-first` | 全部店铺 | 全部 |
| 财务主管 | 以上 + `action:finance:settlement-profit:review-final`、`action:finance:settlement-profit:close-month`、`action:finance:settlement-profit:config` | 全部店铺 | 全部 |
| 管理层 | `page:finance:settlement-profit:view` | 全部店铺 | 全部，只读 |
| 运营负责人 | `page:finance:settlement-profit:view`（data scope = owner） | 只看自己负责的商品 | 结算利润与纯利；公司级费用总额、他人数据、货本单价不可见 |

- 数据范围资源：`store` + `owner`；财务角色与管理层不受 owner 限制。
- 高风险动作（批量调整 ≥ 20 行、反结账、修改纯利设置）：前端二次确认 + 后端要求 `confirm_token`；全部写操作记 `actor_id、actor_role、acted_at、request_id、reason、before、after`。
- 写接口一律要求 `Idempotency-Key` 请求头（同 key 24 小时内重复请求返回首次结果）。
- `permission_catalog_v2` finance 模块新增页面 `settlement_profit`；key 按 `_slug` 规则使用：`page:finance:settlement-profit:view`；`action:finance:settlement-profit:adjust` / `review-first` / `review-final` / `close-month` / `config`；`field:finance:settlement-profit:cost` / `net-profit` / `company-cost`。data scope 复用 `store + owner`。

## 6. Data Source

### 6.1 决策
```text
data source decision file: docs/data-sources/decisions/finance-settlement-profit-v2-decision.md
decision status: READY_FOR_PRP
contains NEED_OWNER_DECISION: no（2026-11-03 Rocky 拍板，见决策 §4）
owner approval status: Rocky 已确认业务决定；待审核 AI 复审
old-system reference: no（不读旧系统）
sensitive or critical domains: 财务 / 利润 / 成本 / 结算 / 库存 / 广告
```

### 6.2 分层（RAW → ODS → FACT → MART；前端与 API 只读 MART / 读模型；manual_ 只覆盖计算结果，不改 RAW / ODS / FACT）

| 层 | 表 | 写入方 | 主键 / 唯一键 |
|---|---|---|---|
| RAW | 既有 `ods_api_raw_blobs` + `ods_api_raw_request_refs` | 各同步 handler | 每页一条；request ref 记 来源、店铺、窗口、offset、run_id、采集时间；不记认证参数；保留策略沿用既有（RAW 90 天后归档压缩，不删） |
| ODS | `ods_lingxing_mp_profit_order_lines` | 领星多平台结算利润-订单 handler | (source_account_ref, store_id, platform_order_no, order_item_no, transaction_type, settlement_date, source_row_seq) |
| ODS | `ods_walmart_wfs_fee_detail_lines` | Walmart WFS 费用明细 handler（一店一服务器） | (source_account_ref, store_id, report_id, line_no) |
| ODS | `ods_walmart_storage_fee_lines` | Walmart 仓储费报表 handler（`walmart_remote_jobs`） | (source_account_ref, store_id, report_period_start, report_period_end, gtin) |
| ODS | `ods_walmart_review_accelerator_snapshots` | 评价加速器 handler（每账期一次） | (source_account_ref, store_id, snapshot_report_key, item_id) |
| FACT | `fact_settlement_order_lines` | 计算任务 | 唯一键只有 (store_id, bill_month, calc_version, line_key)，即 `line_key` 每个 calc_version 内唯一；(store_id, bill_month, platform_order_no, order_item_no) 只建普通索引（同一订单行第 1 期销售、第 2 期退款分属两期，不能按订单号做唯一键）。同一期结算单里同一订单行的各交易类型汇总成一行 |
| FACT | `fact_inventory_movement_lines` | 计算任务 | (source_flow_id, calc_version)：`source_flow_id` = 库存索赔 PRP 表 `ods_lingxing_wfs_cost_valuation_flow` 中 `is_current = true` 行的 id（不建外键）。**不用流水号做键**（领星流水号会重复、会变），流水号只作展示列。店铺：store_id 取该行的 store_id（sid 优先，否则 store_code 对照）；对不上则 store_id 为空、`store_mapping_status = unmapped`，原样保留 store_code |
| FACT | `fact_settlement_unassigned_amounts` | 计算任务 | (store_id, bill_month, source_kind, source_ref) —— 「待指定」金额，§8.4。对不上店铺的库存异动也写这里：store_id 用固定占位值 `__unmapped__`（不用 NULL，保证唯一键生效），source_kind = `inventory_unmapped_store`，source_ref = flow 行 row_hash |
| MART | `mart_settlement_profit_item_month` | 计算任务 | (store_id, item_id, bill_month) |
| MART | `mart_settlement_order_review` | 计算任务 | (store_id, bill_month, line_key)；`row_kind` = order / unassigned / reconcile_diff；order 行另按 (store_id, bill_month, platform_order_no, order_item_no) 建索引；待指定和对平差额待办没有订单号，用 `line_key` 识别 |
| MART | `mart_settlement_reconcile_store_month` | 计算任务 | (store_id, bill_month) |
| FACT | `fact_settlement_post_close_diffs` | 结账后差异记录 | (store_id, bill_month, line_key, detected_at)；旧值、新值、发现时间，不改冻结数 |
| MART | `mart_inventory_movement_month` | 计算任务 | (store_id, item_id, month, category) |
| MANUAL | `manual_settlement_order_adjustments` | 财务操作 | id；含 version（乐观锁）、status active / revoked |
| MANUAL | `manual_settlement_review_actions` | 财务操作 | id |
| MANUAL | `manual_settlement_month_close` | 财务主管 | (store_id 或 ALL, bill_month) |
| CFG | `cfg_net_profit_allocation` | 财务主管 | (effective_month)；fixed_cny、excluded_owner_ids |
| REF（既有，只读） | `ref_product_pricing_rule_versions` | 既有汇率版本表 | 只读账单月内生效版本的 `usd_cny_rate`；没有就不换算，不做任何兜底，不新建任何汇率表（§8.2） |

金额一律 `numeric(18,4)` + `currency_code`；有折算的字段同时存 `*_amount_orig`、`*_currency_orig`、`*_amount_usd`、`*_amount_cny`、`fx_rate`、`fx_month`、`fx_status`（final / missing；missing 时 `*_amount_cny` 与 `fx_rate` 为空）。外部 ID（订单号、GTIN、item_id、店铺 ID、流水号、report_id）一律字符串。

领星 WFS 成本计价明细（Rocky 2026-11-03 补充）：本 PRP **不建**该接口的 ODS 表、**不写**该接口同步、**不做**契约登记。三件事统一由「库存索赔」PRP（`PRPs/wfs-inventory-claim.md`）的 PR 1 负责：表 `ods_lingxing_wfs_cost_valuation_flow`，按「同步批次 + 顺序号」入库、窗口内整段替换，流水号不唯一；接口键沿用 `LX-8437AD0BCB9E`（手工键），契约快照 `docs/integrations/lingxing/contracts/inventory-lx-8437ad0bcb9e.md`。本 PRP 只读该表 `is_current = true` 的行（见 §6.3），不对它建外键。

### 6.3 复用的既有表（2026-11-03 读仓库模型核对）

| 表 | 真实结构要点 | 本 PRP 用法 | 结论 |
|---|---|---|---|
| `fact_walmart_settlement_lines`（#290） | 店铺 + report_key + source_row_hash 唯一；`numeric(18,4)`；report_date 账单日、transaction_posted_at | 收入、订单费用、店铺级行（仓储费、测评加速、广告补贴、杂项发票）的唯一底数 | 复用；依赖 #290 合并 |
| `fact_walmart_wfs_fee_actual` | 唯一键 (source_account_ref, source_line_ref)；字段 business_date_la、store_id、item_id、msku、platform_order_no、sales_num、settlement_date、actual_fee_amount（≥ 0）、currency_code；**只有履约费，没有下单 / 发货时间** | 不作为订单时间来源 | 不复用；改为新建 `ods_lingxing_mp_profit_order_lines`（同一领星接口，全字段落 ODS） |
| `gov_wfs_settlement_collections` | 一店一窗口一次采集的治理记录（expected / captured / accepted / duplicate 计数） | 新 ODS 的采集治理沿用同一模式 | 参照，不复用数据 |
| `fact_walmart_ad_item_sp_daily` | 唯一键含 source_line_hash；business_date_la（LA 时区）、store_id、item_id、msku、ad_spend_amount + 币种；**只有 SP** | 广告 SP 部分 | 复用；视频、SEM 在同一模块补（PR-2） |
| `ods_lingxing_wfs_cost_valuation_flow`（库存索赔 PRP 所有，未合并前不存在） | 行 id、source_account_ref、store_id（可空）、store_code、store_mapping_status、serial_number、business_type（原始字符串）、gtin、msku、order_number、quantity（带符号）、purchase_total_amount / logistics_total_amount / other_total_amount（numeric(18,4)）、currency_code（待探测前为空）、date_local、business_date、settlement_date、is_current；唯一键 (raw_request_ref_id, source_item_ordinal)，每次同步行 id 换新 | 货本（§8.3）与库存异动（§0.4）只读 `is_current = true` 的行 | 只读复用；PR-3 依赖库存索赔 PR 1 合并，未合并前用合成数据和测试内建表 |
| `mart_listing_management_current` | 商品管理当前负责人 | 负责人、商品匹配 | 按账单月最后一天的 `owner_ref` 取值；负责人缺失 → OWNER_MISSING |

### 6.4 生产开关
所有新同步代码合并后 `is_enabled=false`、`schedule_enabled=false`。上线时由 Rocky 书面授权一次开启（落 runbook 执行记录）；开启后按账期自动运行，不再逐期审批（Rocky 2026-11-03）。Walmart 调用只经一店一服务器 `walmart_remote_jobs`。

## 7. API Contract

统一 envelope 沿用仓库现有格式（`backend/app/core/api.py` 的 `SuccessEnvelope` / `ErrorEnvelope`）：成功 `{ "success": true, "data": ..., "error": null, "meta": { "source": "finance_settlement_profit_v2", "source_tables": [...], "calc_version", "data_as_of", "total" }, "request_id": "..." }`；错误 `{ "success": false, "data": null, "error": { "code", "message", "details" }, "meta": null, "request_id": "..." }`。业务错误码通过 `ApiError` 抛出，沿用既有 `X-Request-ID`。权限不足 403 `FORBIDDEN`；数据范围外 404 `NOT_FOUND`。分页：`page`（从 1）、`page_size`（≤ 200，默认 50），响应 `meta.total`。排序：`sort_by`（白名单字段）、`sort_order` asc / desc。金额字段一律成对：`{ "amount": "123.4500", "currency_code": "USD" }`（字符串小数）。外部 ID 一律字符串。

| 方法 / 路径 | 请求 | 响应 data | 错误码 |
|---|---|---|---|
| GET `/api/finance/settlement-profit/summary` | months[]（YYYY-MM）、store_ids[]、owner_ids[]、view=item / store / owner、currency=USD / CNY、page、page_size、sort_by | rows[]：key、sales、各费用组、gross_profit、net_profit（可空）、margin；totals | — |
| GET `/api/finance/settlement-profit/items/{store_id}/{item_id}` | store_id、item_id 均为字符串路径参数；months[] | 按月瀑布：费用组 → 列 | NOT_FOUND |
| GET `/api/finance/settlement-profit/orders` | months[]、store_ids[]、owner_ids[]、status=pending / auto / adjusted / first_passed / final_passed / rejected、reason=missing_purchase / missing_head / unassigned / unmapped_store / reconcile_diff、keyword、page、page_size、sort_by | rows[]：line_id、platform_order_no、store_id、item_id、sku、serial_number、ordered_at、shipped_at、settled_at、金额列、profit、status、reasons[]、version | — |
| GET `/api/finance/settlement-profit/inventory` | months[]、store_ids[]、category=loss / non_loss / claim / unclassified / lx_adjust / unknown | 汇总 + 明细 | — |
| GET `/api/finance/settlement-profit/adjustments` | months[]、status=active / revoked、page | 台账 | — |
| GET `/api/finance/settlement-profit/reconcile` | months[]、store_ids[] | 每店每月：结算单总额、订单级合计、待指定、差额、status | — |
| POST `/api/finance/settlement-profit/orders/{line_id}/adjustments` | Idempotency-Key；body：kind=cost / amount / assign_item / assign_store / note、payload（cost：purchase_cny、head_cny；amount：column、delta、currency；assign_item：item_id）、reason（必填）、expected_version | adjustment 记录 + 新 version | MONTH_CLOSED、STALE_VERSION、VALIDATION_ERROR |
| POST `/api/finance/settlement-profit/orders/review` | Idempotency-Key；body：line_ids[]（≤ 500）、stage=first / final、decision=pass / reject、comment、expected_versions{} | 每行结果 | MONTH_CLOSED、STALE_VERSION、STAGE_ORDER（终审前须初审） |
| POST `/api/finance/settlement-profit/adjustments/{id}/revoke` | Idempotency-Key；body：reason、expected_version | 撤销后的记录 | MONTH_CLOSED、STALE_VERSION、ALREADY_REVOKED |
| POST `/api/finance/settlement-profit/months/{month}/close` | Idempotency-Key、confirm_token；body：store_ids[] 或 ALL | 结账记录 | RECONCILE_FAILED、OWNER_MISSING、OWNER_SALES_ZERO、UNASSIGNED_PENDING、FX_MISSING |
| POST `/api/finance/settlement-profit/months/{month}/reopen` | Idempotency-Key、confirm_token；body：store_ids[]、reason | 反结账记录 | NOT_CLOSED |
| GET `/api/finance/settlement-profit/config/net-profit` | month | fixed_cny、excluded_owner_ids[]、effective_month、version | — |
| PUT `/api/finance/settlement-profit/config/net-profit` | Idempotency-Key、confirm_token；body：fixed_cny、excluded_owner_ids[]、effective_month、expected_version | 新设置 | STALE_VERSION、MONTH_CLOSED（生效月已结账） |

所有 POST / PUT 有 response_model；所有写操作写审计字段（§5）。

## 7A. UI Requirements（对应 `PRPs/templates/prp_base.md` 第 8 节）

```text
layout: PageShell；页面 /finance/settlement-profit，4 个标签页（URL ?tab=）：汇总 summary / 订单审核 orders / 库存异动 inventory / 调整台账 adjustments；
        顶部公共筛选条 + 对平状态条（每店每月 ok / RECONCILE_FAILED / UNASSIGNED_PENDING / FX_MISSING，红标可点进订单审核对应待办）
table columns:
  汇总：店铺 / 商品(item_id、MSKU) / 负责人、销售额、各费用组（订单费用、WFS 服务费、仓储费、广告、测评加速、弃置损耗）、货本、结算利润(USD / CNY)、纯利(CNY)、利润率；
        视图切换 item / store / owner，币种切换 USD / CNY；广告列在视频 / SEM 补齐前带「只含 SP」角标
  订单审核：订单号、店铺、商品、SKU、库存流水号、下单时间、发货时间、结算时间、收入与费用列、货本、利润、状态、原因、版本
  库存异动：类别（真实损耗 / 非损耗 / 找沃尔玛索赔 / 未归类 / 领星调账 / 未知异动）、商品、件数、货值、操作费、去向、发生月
  调整台账：调整时间、操作人、角色、订单行、类型、调整前后、原因、状态（生效 / 已撤销）
filters: 账单月（多选）、店铺、负责人；订单审核另有 状态（待审 / 自动通过 / 已调整 / 初审通过 / 终审通过 / 退回）、
         原因（缺采购成本 / 缺头程成本 / 待指定 / 对平差额）、关键词（订单号 / SKU / item_id）；库存异动另有 类别
actions: 订单审核：调整（成本 / 金额 / 指定商品 / 备注）、批量初审、批量终审、退回（原因必填）；调整台账：撤销；
         汇总：导出、结账、反结账（财务主管，二次确认 + confirm_token）；设置：纯利设置（财务主管）
empty state: 「该月没有结算数据」，提示结算账单同步状态与最近同步时间
loading state: 表格骨架屏；写操作按钮转圈并禁用，防重复提交
error state: 显示错误码对应中文说明与 request_id，可重试；STALE_VERSION 提示「数据已被他人修改，请刷新」；MONTH_CLOSED 提示「该月已结账」
no-permission state: 无 page 权限显示「没有访问权限」；运营负责人只显示自己负责的商品，公司级费用总额、货本单价列隐藏；无 action 权限的按钮不显示
fx-missing state: 该账单月无生效汇率 → CNY 列与纯利列显示「汇率缺失」，顶部黄条提示「请在定价规则里维护该月汇率」，结账按钮禁用并提示 FX_MISSING
helpUrl: docs/sop/finance-settlement-profit.md（PR-4 交付），PageShell help 入口（PR-5）
```

## 8. 计算规则（流水：结算单行 → 商品归集 → 订单分摊 → 人工覆盖 → 商品月汇总 → 纯利 → 店铺月对平 → 结账冻结）

### 8.1 触发与幂等
结算账单 / 任一来源 ODS 同步成功 → 重算受影响的 (store_id, bill_month)；已结账月份不重算（§8.9）。同一输入重算结果逐字段相同（calc_version 递增，内容 hash 不变则不写新版本）。

内容 hash 口径：不计入 `source_flow_id`、`source_run_ids` 以及 id、calc_version、created_at 等每次重算或重新同步都会变的技术字段（库存索赔同步重拉后 flow 行 id 会换，同步批次也会变，计入会让内容未变也写新版本）。来源为领星成本计价 flow 行的，改用该 flow 行的 `row_hash` 加本表业务字段（店铺、账单月、line_key、SKU / MSKU、数量、金额、币种、fx_status、分摊结果等）计算；其他来源只用业务字段。字段顺序固定，数值按列精度规范化后再算。

### 8.2 账单月与汇率
- 账单月 = 账单日归月（账单日 ≤ 次月 5 号算上月），与现有财务页一致。
- 汇率只用 `ref_product_pricing_rule_versions.usd_cny_rate` 账单月内生效版本；货本 ¥→$ 与结算利润 $→¥ 使用同一汇率。纯利、C、固定额均按 CNY 计算与展示，同时提供 USD 原值和 CNY 折算值。
- 没有生效汇率就不换算，不做任何兜底（不用上月、不手录、不估算）：CNY 字段留空，`fx_status=missing`，货本 ¥→$ 不折算（订单利润显示「汇率缺失」，不按缺成本处理），纯利不算，不可结账（`FX_MISSING`）。汇率补上后自动重算该月。
- 舍入：计算全程 `Decimal`，不经 float；分摊用最大余数法，保证分配后合计与被分配总额逐分相等；展示层两位小数，四舍五入（ROUND_HALF_UP）。

### 8.3 货本
订单行按 订单号 + GTIN 匹配 `ods_lingxing_wfs_cost_valuation_flow` 中 `is_current = true` 的行（FIFO：采购 + 头程 + 其他，¥；按结算日期取数时先过滤 is_current 再按 settlement_date 取，因为该表按出入库日期窗口同步），按 §8.2 汇率折算。入库运费只认领星 WFS 发货单物流费用（已含在 FIFO 头程里），不另列、不按货件分摊、不自动补。领星头程为 0 或没填 → 订单进订单审核「缺头程成本」（reason `missing_head`），由财务用 adjustment kind=cost 手工补；采购成本为 0 或没填 → reason `missing_purchase`；匹配不到 FIFO → 两个 reason 都标。

### 8.4 待指定金额（取代店铺层 / 零星）
对不上商品的费用（2026-10 起）写入 `fact_settlement_unassigned_amounts`，状态 pending；每笔在订单审核里显示为一条待办（reason unassigned）。财务指定商品（adjustment kind assign_item）后进入该商品，再按 §0.3 规则分到订单。pending 期间：店铺月对平 status = UNASSIGNED_PENDING；可发布、可审核，不可结账。2026-10 以前的月份不计算，不产生待办。

对不上店铺的库存异动（`store_mapping_status = unmapped`，例如弃置损耗；Rocky 2026-11-03 拍板）：
- 不进任何店铺的库存异动汇总和利润，写一条「待指定」：store_id = `__unmapped__`，bill_month = 异动月份，source_kind = `inventory_unmapped_store`，source_ref = 该 flow 行 `row_hash`，金额按 ¥ 原值记 `amount_cny`，并按 §8.2 汇率折 `amount_usd`（没有汇率则 `amount_usd` 为空、fx_status = missing），原样展示领星 store_code、流水号、SKU、类别。
- 订单审核里显示为待办（row_kind unassigned，reason `unmapped_store`），只有数据范围为全部店铺的财务用户能看到和处理。
- 财务用 adjustment kind = `assign_store`（payload：store_id）指定店铺，原因必填，走初审 / 终审，可撤销。指定后该异动按该店重算：`fact_inventory_movement_lines.store_id` = 指定店铺、`store_mapping_status = manual_assigned`，再按 SKU 落商品；该店对不上商品的，转成该店的普通「待指定」（assign_item）。撤销则回到 `__unmapped__` 待办。
- 某月还有 pending 的 `inventory_unmapped_store` 待办时，该月所有店铺对平状态为 UNASSIGNED_PENDING，不可结账（不知道属于哪家店，先结哪家都可能事后产生差异）。
- 同一 flow 行重同步后 row_hash 不变，待办和指定结果保留；row_hash 变了，旧指定作废（status void）并生成新待办。
- PR-3 需带一个小迁移：`ADJUSTMENT_KINDS` 加 `assign_store`；`STORE_MAPPING_STATUSES` 加 `manual_assigned`，CHECK 改为 store_id 非空 ⇔ 状态为 mapped / manual_assigned；`fact_settlement_unassigned_amounts` 加 `assigned_store_id`、`amount_cny`，`amount_usd` 允许为空（与 amount_cny 至少一个非空），「已指定」CHECK 改为 assigned_item_id 或 assigned_store_id 至少一个非空。

### 8.5 商品 → 订单
按 §0.3 表：件数或销售额加权，最大余数法。商品当月没有销售订单（只有费用）→ 该金额转为 §8.4 待指定，不隐含留在店铺层。

### 8.6 评价加速器
- 快照唯一键 (store_id, snapshot_report_key, item_id)；snapshot_report_key = 该结算账期的 report_key；每账期账单日后拉一次。
- 新增评论数 Δ(item) = 本期快照 reviewsCollected − 上一期快照（无上一期视为 0；商品退出报名 Δ 记 0；Δ 为负记 0）。
- 单价 = clamp(5 + 0.25 × 售价, 10, 30) 美元；售价取 `std_walmart_monitor_listing_observations`：按 store_id + item_id 取快照日或之前最近一次成功采集的 `sale_price_amount`，为空则取 `strike_price_amount`。Rocky 2026-11-03：费用只按「新增评论数 × 单价」分摊，不写任何兜底分支（不用平均成交价、不改按销售额分、不设最低单价）；有新增评论但查不到价格、算不出权重时，按已定规则不写兜底：与快照缺失相同，整笔转 §8.4 待指定（reason `price_missing`），由财务手工指定。
- 首个账期无上期快照时按报名商品当期销售额分并标注；Δ 评论数小于 0 按 0 计；通道只走 `walmart_remote_jobs`，自动按账期拉取，首次开启 outbound / schedule 仍需 Rocky 书面授权并记入决策文件。
- 权重 = Δ × 单价；本期结算单测评加速费按权重分到商品（最大余数法），总额与结算单逐分相等 —— 估算单价只当权重，不产生差额。
- Δ 全为 0 → 按报名商品当期销售额分；报名商品当期销售额也全为 0 或快照缺失 → 整笔转 §8.4 待指定。

### 8.7 纯利
- 纯利、C、固定额均按 CNY；结算利润同时提供 USD 原值和 CNY 折算值。C = 当月管理费用 + 财务费用 + 税费（CNY）。账单月 `fx_status=missing` 时纯利不算（列为空，标「汇率缺失」），不可结账（`FX_MISSING`）。
- `cfg_net_profit_allocation` 生效月内的剔除名单默认林翔、刘云龙，财务主管可改；剔除人不计入 N、不拿固定额、负责商品 C 分摊为 0。
- N = 剔除名单以外、当月有商品销售的负责人数；每人固定 ¥15,000，剩余 `C - 15,000 × N` 按各人当月销售额占比分配（为负照分）；每人所得再按其负责商品销售额分到商品。
- 当月销售额 = 账单月结算销售额；若 N 内负责人销售额为 0，报 `OWNER_SALES_ZERO` 并阻止结账。无负责人商品报 `OWNER_MISSING` 并阻止结账。
- 示例：C=¥235,292，N=10，固定 ¥150,000，剩余 ¥85,292。若 A/B/C 当月销售额占比为 50%/30%/20%，三人的剩余分配分别为 ¥42,646/¥25,587.60/¥17,058.40；每人所得分别为 ¥57,646/¥40,587.60/¥32,058.40，再按各自负责商品销售额分到商品。
- 资金流水正式上线前纯利列为空，标「等资金流水上线」。

### 8.8 对平
- 结算单总额 = 该店该账单月 `fact_walmart_settlement_lines` 全部金额（含店铺级行，但不含已转「其他业务收入」的广告补贴、杂项发票，也不含只做差异展示的广告扣款行、WPC / 入库运费扣款行）。广告日报为广告成本权威来源；结算单广告扣款行不计成本，只在对平页列「广告：日报 vs 结算单 / 信用卡」差异，不算对平失败。
- 订单级合计 = Σ `fact_settlement_order_lines` 中来源于结算单的金额（收入、订单费用、仓储费、测评加速）+ Σ pending 待指定。
- 结算单 WPC / 入库运费扣款行同广告处理：不计成本，只在对平页列「入库运费：领星 vs 结算单」差异，不算对平失败。
- 广告日报、领星货本、弃置货值不来自结算单，不参与此对平，另有覆盖率检查（§14）。弃置货值与操作费按发生月计入；操作费从 WFS 服务费移到「弃置损耗」列只移一次，RC_InventoryDisposalFee 不再重复计入。跨月弃置操作费单列一行。
- |差额| ≤ 0.01 美元为 ok；否则 RECONCILE_FAILED：可发布、可审核，页面红标，不可结账，差额生成一条订单审核待办（reason reconcile_diff）。

### 8.9 人工覆盖、撤销与结账
- 调整 / 撤销 / 指定商品 → 重算该行所属 (store_id, bill_month) 的订单 → 商品月 → 纯利（全店当月，因销售额占比变化）→ 对平；同步执行，返回新 version。
- 乐观锁：每行 version；请求带 expected_version，不一致返回 STALE_VERSION。
- 结账：冻结该店该月 FACT / MART 快照（写 `frozen_at`、`frozen_by`、`calc_version`）。结账后源数据变化只写 `fact_settlement_post_close_diffs`（差异记录，不改冻结数），页面提示。判断「源数据是否变化」与 §8.1 用同一内容 hash 口径：排除 `source_flow_id`、`source_run_ids`，用 flow 行 `row_hash` 加业务字段比对；只是重新同步导致 id 或批次变化、row_hash 与业务字段都不变的，不写差异。
- 反结账：财务主管 + confirm_token + reason；解冻后按最新数据全量重算该店该月，审计记录 before / after 合计。
- 订单行 `line_key` = 店铺 + reportKey + 订单号 + 订单行号 + GTIN 的稳定业务键；待指定行 `line_key` = 店铺 + 账单月 + source_kind + source_ref；对平差额行 `line_key` = 店铺 + 账单月 + "reconcile_diff"；manual_ 表引用 `line_key`，不引用会重算变化的 UUID。撤销已终审订单调整回到待初审；终审后修改重走初审；同一人不可对同单既初审又终审；已结账月 adjust / review / revoke 返回 `MONTH_CLOSED`；退回回到上一步且原因必填。

## 9. SOP / API Docs（实现时交付，现均为待完成）

- [ ] PR-1：表结构文档 `docs/api/finance-settlement-profit-tables.md`
- [ ] PR-2：同步 handler 文档 + runbook `docs/runbooks/finance-settlement-profit-sync.md`（开关、回填，状态 prepared）
- [ ] PR-3：计算口径文档 `docs/api/finance-settlement-profit-calc.md`（即本 PRP §8）
- [ ] PR-4：API 文档 + OpenAPI metadata + SOP（审核 / 撤销 / 结账）
- [ ] PR-5：PageShell help entry + Playwright E2E

## 10. Implementation Plan（每个 PR 独立 CI 全绿后再提下一个）

| PR | 输入 | 输出 | 迁移依赖 | 独立验收 | 回滚 |
|---|---|---|---|---|---|
| PR-1 建表 | 本 PRP §6.2 | 新建 `backend/app/modules/finance/`（models）与 `backend/tests/modules/finance/`；本 PRP 新表（16 张，不含领星 WFS 成本计价表）迁移 + model registry + scaffold 测试；表结构文档。领星 WFS 成本计价表、同步与契约登记不在本 PRP（归库存索赔 PR 1） | 接当时最新 head；#290 已合并 | migration up / down、`alembic check` 干净 | migration down（全部新表） |
| PR-2 同步 | PR-1 的 ODS 表；Walmart 契约快照 | 多平台结算利润-订单走 Integration Sync（领星成本计价同步归库存索赔 PRP）；Walmart WFS 费用、仓储费报表、评价加速器快照走 `walmart_remote_jobs` | PR-1 | 合成 fixture 覆盖分页完整性、RAW 先落、行身份、未知枚举、单店失败隔离、开关 fail-closed；不调真实接口 | 关开关 + revert |
| PR-3 计算 | PR-1 表；合成 fixture | §8 全部计算 + 重算任务；§8.4 所列小迁移（assign_store、manual_assigned、unassigned 表加列）；订单时间扩字段属于跨板块改动，测既有 WFS 同步不回归 | PR-1（不依赖 PR-2 真实数据） | 合成 fixture 覆盖 §14 每一项；重算幂等 | revert；MART 可全量重算 |
| PR-4 接口 | PR-3 计算 contract | §7 全部接口 + 权限 + 审计 | PR-1、PR-3 | API 测试：权限、数据范围、幂等、乐观锁、错误码 | revert |
| PR-5 页面切换 | 5174 已验收前端；PR-4 接口 | 前端数据读取从本地文件切到接口（只切接口，不含后端逻辑） | PR-4 | Playwright E2E：4 个标签加载、筛选、调整、审核、撤销、结账拦截 | revert（回到本地数据） |

## 11. Validation Gates

```bash
cd backend
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/modules/finance -q            # 即 backend/tests/modules/finance
uv run pytest tests/modules/integration_sync -k "settlement_profit or wfs_cost or wfs_fee_detail or review_accelerator" -q
uv run pytest tests/db -q && uv run alembic check  # 即 backend/tests/db
cd ..
cd frontend && npm run lint && npx tsc --noEmit -p tsconfig.app.json && npx vitest run && npx playwright test e2e/finance-settlement-profit
bash scripts/ci-preflight.sh
```

## 12. Forbidden Actions（安全红线）

```text
Walmart：只走一店一服务器 walmart_remote_jobs；禁止在 Mac 本地直连 Walmart 任何接口。
代码 AI：不碰任何服务器（不 SSH / scp / 部署 / 重启）；不读凭证（.secrets/、token、.env、店铺凭证）；不改 .env；不推 main、不合并、不自己提交 / 提 PR（由部署 AI 提）。
不调用真实领星 / Walmart 接口（Rocky 书面授权的受控探测除外）；测试只用合成 fixture。
生产同步开启、回填、定时开启（is_enabled / outbound_enabled / schedule_enabled）：各要 Rocky 另行书面授权一次；代码默认全关，不翻转默认值。
不读旧系统（old-system 与旧 MySQL 都不读、不改）；不连接生产数据库；不部署；不重启服务。
不把真实订单号、金额明细写进测试 / 文档 / PR；manual_ 表不得写 RAW / ODS / FACT。
```

## 13. Rollback Plan

见 §10 每个 PR 的回滚列；manual_ 表回滚前先导出备份；已结账月份以冻结快照为准，不随回滚改变。

## 14. Acceptance Checklist（阈值 / 失败行为 / 测试数据）

| 项 | 阈值 | 失败行为 | 测试数据 |
|---|---|---|---|
| 店铺月对平 | 差额 ≤ $0.01（不含广告扣款行、WPC / 入库运费扣款行，二者只列差异） | RECONCILE_FAILED，不可结账，生成待办 | 合成：一店一月含店铺级行、WPC 行 |
| 缺头程成本 | 领星头程为 0 / 没填 → 订单进待审 missing_head，不自动补 | 待审 | 合成：头程为 0 的订单 |
| VDG / 未知枚举 | 不参与计算，告警 | 测试失败 | 合成：一行 VDG、一行未知枚举 |
| 重复扣费检测（弃置操作费只在一列；广告补贴 / 杂项不进结算利润） | 0 条 | 测试失败 | 合成：同一费用同时出现在两处 |
| 订单 ↔ 货本匹配覆盖率 | 显示比例；缺采购 / 头程进待审 | 待审 | 合成：部分订单无 FIFO |
| WFS 费用明细 GTIN 缺失 | 缺失行按 §0.3 规则或转待指定 | 不丢金额 | 合成：无 GTIN 行 |
| 仓储费商品归集覆盖率 | 报表缺失账期 → 转待指定 | 不隐含留店铺 | 合成：缺一期报表 |
| 评价加速器快照缺失 | 转待指定 | 不可结账 | 合成：无快照 |
| 负责人缺失 | 0 个有销售的无负责人商品 | OWNER_MISSING，纯利不发布 | 合成 |
| 汇率缺失 | 账单月无生效 `usd_cny_rate` → CNY 字段为空、`fx_status=missing`、纯利不算；不得出现任何兜底汇率 | FX_MISSING，不可结账 | 合成：一月无汇率版本 |
| 重算幂等 | 同输入两次结果逐字段相同 | 测试失败 | 合成 |
| 结账冻结 | 结账后源数据变 → 冻结数不变、写差异 | 测试失败 | 合成 |
| 人工调整审计 | 每次写操作有 actor / role / before / after / request_id | 测试失败 | 合成 |
| 纯利公式 | 样例：C ¥235,292、N 10、F ¥15,000 → 固定 ¥150,000、剩余 ¥85,292，按销售额占比分（10 月真实占比在 Rocky 侧对数表，不进仓库） | 测试失败 | 合成：3 人、已知占比，手算期望值 |
| 业务对数（授权回填后） | 2026-10 每店对平；与 5174 预览同月数差异表贴 PR | 不合并 | 真实数据，只贴差异表 |

## 15. 已拍板事项（Rocky 2026-11-03，经刘云龙授权）

1. 仓储费：以结算单仓储费行为准，按扣费账单月归月；商品比例取新同步 Walmart 仓储费报表当期 SKU 占比，无当期报表用最近账期并标注；不读旧系统。
2. 广告：广告日报为成本权威来源；结算单广告扣款仅用于差异展示，不计成本、不算对平失败；视频 / SEM 补齐前标「只含 SP」。
3. WFS 费用明细通道：Walmart WFS 费用明细、仓储费报表、评价加速器快照走 `walmart_remote_jobs` 一店一服务器；默认关闭。
4. 评价加速器：首账期无上期快照按当期销售额分并标注；Δ 评论数 < 0 按 0；售价取 `std_walmart_monitor_listing_observations` 快照日或之前最近一次成功采集的 `sale_price_amount`，空则 `strike_price_amount`（不写任何兜底分支，Rocky 2026-11-03）；自动按账期拉，首次开启 outbound / schedule 仍需书面授权。
5. 入库运费（Rocky 2026-11-03 最新）：只认领星 WFS 发货单物流费用（已含在 FIFO 头程里）。领星没填的，订单进订单审核「缺头程成本」（missing_head），由财务用 adjustment kind=cost 手工补；不自动补、不按货件分摊、不出补数清单、不同步领星货件列表。结算单 WPC / 入库运费扣款不计成本，对平页列「入库运费：领星 vs 结算单」差异，不算对平失败。国内发货单不涉及。
6. 汇率与纯利币种（Rocky 2026-11-03 最新）：只用 `ref_product_pricing_rule_versions.usd_cny_rate` 账单月内生效版本；货本 ¥→$ 与结算利润 $→¥ 同汇率；纯利、C、固定额按 CNY，结算利润同时给 USD 原值和 CNY 折算值。没有汇率就不换算，不做任何兜底（不用上月、不手录、不估算）：CNY 字段留空，`fx_status=missing`，纯利不算，不可结账（`FX_MISSING`）；不新建任何汇率表。
7. 弃置费归月：货值与操作费按弃置发生月；操作费从 WFS 服务费移到「弃置损耗」只移一次，RC_InventoryDisposalFee 不重复计；跨月操作费在对平页单列。
8. 纯利剔除名单：`cfg_net_profit_allocation` 默认林翔、刘云龙，财务主管可按生效月修改；剔除人不计 N、不拿固定额、负责商品 C 分摊为 0；`OWNER_SALES_ZERO` 阻止结账。
9. 负责人：取 `mart_listing_management_current.owner_ref`，按账单月最后一天值，不用 `dim_walmart_listings`。
10. 订单身份与结账：使用稳定 `line_key`；结账后源数据只写 `fact_settlement_post_close_diffs`，页面展示，财务决定是否反结账。
11. 复核：本 PRP 与决策文件无 NEED_OWNER_DECISION；审核 AI 复审确认后才开发。
12. VDG（供应商短少 / 损坏，Rocky 2026-11-03）：标「未归类」，不参与计算，一出现就告警；目前没有这种情况。
13. 对不上店铺的库存异动（Rocky 2026-11-03，按推荐）：进订单审核「待指定」行，由财务手工指定归属店铺（adjustment kind `assign_store`）；未指定前该月所有店铺不可结账。细则见 §8.4。
