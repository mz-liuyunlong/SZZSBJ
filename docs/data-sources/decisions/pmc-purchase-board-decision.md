# PMC-PURCHASE-1 数据源决策：采购看板（采购计划 / 采购单 / 收货单）

> 依据 `docs/delivery/backend-data-source-decision-gate.md`，参照 `docs/data-sources/decisions/data-pages-daily-sales-listing-order-profit-decision.md` 的形态。

状态：`BLOCKED_BY_OWNER_DECISION`（仅 1 项：收货单接口 `LX-4B9473A2D2E1` 在契约清单中为 `DO_NOT_USE`，需负责人按例外流程重评；其余数据集均可 `READY_FOR_PRP`）

日期：2026-09-17

- 调查日期：2026-09-15 ~ 2026-09-17
- 调查人：Rocky（业务）+ 代码 AI；真实数据探测由部署 AI 在旧系统只读执行
- 目标 method/path：`GET /api/v1/pmc/purchase/board`（列表）、`GET /api/v1/pmc/purchase/board/summary`（卡片）、`GET /api/v1/pmc/purchase/orders/{order_sn}`（详情）、`GET /api/v1/pmc/purchase/sku-cycles`（SKU 实际交期）
- 业务用途：每张采购单的阶段/状态、进度率、采购交期、审批周期、金额，按店铺 + ItemID 可追溯；产出"待下单逾期""下单未到货逾期""ItemID 待处理""WFS 待转换""交期不稳定 SKU"清单（本期只做状态，不推送）
- 接口总体状态：`BLOCKED_BY_OWNER_DECISION`（见 §12 唯一阻塞项）
- 是否包含 NEED_OWNER_DECISION：是（1 项）
- 负责人批准状态：待确认
- 关联证据：`docs/integrations/lingxing-pmc-purchase-endpoint-evidence.md`；契约快照 ×3（`docs/integrations/lingxing/contracts/purchase-lx-*.md`、`warehouse-receipt-lx-4b9473a2d2e1.md`）；业务规则 `docs/business-rules/pmc-purchase-rules.md` v3
- 决策文件路径：`docs/data-sources/decisions/pmc-purchase-board-decision.md`
- 后续接口 PRP：`PRPs/pmc-purchase-board.md`

适用范围：

- 页面：PMC → 采购看板（`/pmc/purchase-board`）
- 三个领星只读接口的同步、ODS/DWD/DWS 分层、人工覆盖表、查询 API 与前端渲染
- 不含：采购计划/采购单/备货单/WFS 货件的任何写接口；通知推送；成本核算

## 1. 决策摘要

```text
策略：REBUILD_SYNC（三个领星只读接口，走 integration_sync 框架 + Celery + RAW → ODS → DWD → DWS）
复用（引用，不自带接口）：
  dim_lingxing_stores            ← DATA-PAGES-1 getSellerList
  dim_walmart_listings           ← DATA-PAGES-1 walmartListingList（store_id + item_id + msku + local_sku + gtin；本期申请新增 fulfillment_type 列）
  产品管理：产品负责人 / 标签 / 分类 ← product_management（已有）
新增 ODS：
  ods_lingxing_purchase_plan
  ods_lingxing_purchase_order / ods_lingxing_purchase_order_item
  ods_lingxing_receipt_order / ods_lingxing_receipt_order_item
新增 DWD：
  dwd_purchase_order（整单：状态、阶段、金额、order_time、到仓日期、进度率）
  dwd_purchase_order_line_item（明细 × ItemID 归属，含合并单按计划比例拆分）
  dwd_purchase_plan（S1/S2 起点、审批周期观察）
新增 DWS：
  dws_purchase_board（看板行）
  dws_purchase_sku_cycle（SKU 实际交期：近 5 有效样本、剔除、不稳定标记）
  dws_purchase_pending（ItemID 待处理 / WFS 待转换 / 逾期清单）
人工覆盖（manual-override-policy）：
  manual_purchase_item_itemid_override（ItemID 指定）
  manual_purchase_cycle_override（单次到仓修正 / 样本剔除 / 整体基准值）
```

## 2. 文档来源

```text
docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv        #LX-03B82747B50A / #LX-D332F931885E / #LX-4B9473A2D2E1
docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv    同上
docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv   同上
backend/app/integrations/lingxing/data/official_verified_interfaces.csv      同上（OFFICIAL_VERIFIED）
docs/integrations/lingxing-walmart-openapi/phase-1-candidate-apis.csv       采购管理页候选（LX-D332F931885E、LX-4B9473A2D2E1）
features/pmc-purchase/data/probe_20260915/  probe_20260917/                真实数据只读探测（脱敏 CSV + 报告）
```

## 3. 前置调查表（gate §3.1）

| 前置调查项 | 证据位置与调查结论 |
|---|---|
| 旧页面 | 旧系统 PMC 采购提醒（飞书群通知 R001–R004）；无独立采购看板页面。`old-system/` 只读参考，不复用代码 |
| 旧 API | 旧系统直接调用领星 getPurchasePlans / purchaseOrderList / PurchaseReceiptOrder/getOrderList（同三接口），写 MySQL `walmart_ai_data` |
| 旧接口文件位置 | `old-system/source/src/...`（部署 AI 探测时使用旧系统领星客户端，md5 校验前后一致，未改动） |
| 读取表 | 旧 MySQL 采购相关表**不读取**（规则：新系统业务 API 不得运行时读旧库）；本决策不含 `READ_LEGACY_TEMPORARILY` |
| 表写入方 | 新系统：integration_sync handler（RAW/ODS）、DWD/DWS 刷新任务、`manual_*` 由 API 经权限写入 |
| cron / 脚本 / 外部 API | 三个领星只读接口；增量 90 天（`search_field_time=update_time`），一次性回填 12 个月；调度经 Celery beat，生产开启需另行授权 |
| 人工写库入口 | 仅两张 `manual_*` 覆盖表（ItemID 指定、交期修正），带 before/after/operator/reason/审计；不允许改 ODS/DWD 原始值 |
| 外部平台重新获取可能性 | 可：三接口均支持按更新时间增量与日期分段全量重拉；`purchaseOrderList` 不返回 total |
| 少量配置数据可行性 | 默认阈值（S2 7 天、审批 2 天、<2 天剔除、不稳定 ≥5 样本极差 ≥3）作为版本化规则表 `rule_purchase_thresholds`（NEW_SYSTEM_OWNED） |
| 短期策略 | REBUILD_SYNC 三接口 + 复用 DATA-PAGES-1 DIM；WFS 货件追溯字段预留、值为 `unresolved` |
| 长期策略 | PMC 后续板块（国内仓入库、打包/备货单、WFS 货件）上线后补齐 `from_shipment` 归属与整体前置期；写接口（createPurchasePlan 等）另立 PRP |

## 4. 接口总览

| 数据集 | 接口 ID | API path | token_bucket_capacity | 分页 | 最大页长 | 增量字段 / 时间范围 | 目标表 |
|---|---|---|---:|---|---:|---|---|
| 采购计划 | LX-03B82747B50A | `/erp/sc/routing/data/local_inventory/getPurchasePlans` | 1 | offset/length（返回 total） | 500 | `search_field_time` + `start_date/end_date` | ods_lingxing_purchase_plan |
| 采购单（含明细 `item_list`） | LX-D332F931885E | `/erp/sc/routing/data/local_inventory/purchaseOrderList` | 1 | offset/length（**不返回 total**） | 500 | `search_field_time` + `start_date/end_date` | ods_lingxing_purchase_order / _item |
| 收货单（含明细 `item_list`） | LX-4B9473A2D2E1 | `/erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/getOrderList` | 1 | offset/length（返回 total） | 500 | `date_type` + `start_date/end_date` | ods_lingxing_receipt_order / _item |
| 店铺 | （复用 DATA-PAGES-1 getSellerList） | — | — | — | — | — | dim_lingxing_stores |
| Walmart 在线商品 | （复用 DATA-PAGES-1 walmartListingList） | — | — | — | — | — | dim_walmart_listings（+ `fulfillment_type`） |

## 5. 数据集分类表（gate §7）

| 数据集或字段组 | 业务用途 | 当前权威来源 | 分类 | 短期策略 | 长期策略 | 退出条件或切换点 | 需负责人确认 |
|---|---|---|---|---|---|---|---|
| 采购计划 | S1/S2 起点、审批周期、ItemID 备注来源、合并单拆分比例 | 领星 getPurchasePlans | REBUILD_SYNC | 90 天增量 + 12 月回填 | 系统自动建计划后仍以领星为权威 | 不适用 | 是（真实外部 API） |
| 采购单 + 明细 | 看板主单：状态、金额、数量、order_time、计划关联 | 领星 purchaseOrderList | REBUILD_SYNC | 同上 | 同上 | 不适用 | 是 |
| 收货单 + 明细 | 到仓日期（50% 累计规则）、进度率 | 领星 PurchaseReceiptOrder/getOrderList | REBUILD_SYNC | 同上 | 同上 | 不适用 | **是（清单 DO_NOT_USE 重评）** |
| 店铺 | 店铺名/ID 权威 | dim_lingxing_stores（DATA-PAGES-1） | EXISTING_NEW_SYSTEM_DATA | 引用 | 引用 | 不适用 | 否 |
| Walmart 在线商品（ItemID/MSKU/GTIN/发货方式） | ItemID 归属、GTIN 列、WFS 校验 | dim_walmart_listings（DATA-PAGES-1） | EXISTING_NEW_SYSTEM_DATA（申请新增 `fulfillment_type` 列） | 引用 + 新增一列 | 引用 | 不适用 | 是（跨模块加列） |
| 产品负责人 / 标签 / 分类 | 筛选、负责人列（唯一来源） | product_management | EXISTING_NEW_SYSTEM_DATA | 引用 | 引用 | 不适用 | 否 |
| 阈值与算法参数 | S2/审批/剔除/不稳定阈值 | 新系统 | NEW_SYSTEM_OWNED_VERSIONED_RULE | 版本化规则表 | 同 | 不适用 | 否 |
| ItemID 指定 / 交期修正 | 人工覆盖 | 新系统 `manual_*` | NEW_SYSTEM_OWNED | 覆盖表 + 审计 | 同 | 不适用 | 否 |
| ItemID 发货追溯 | 存量单归属 | WFS 货件（PMC 后续板块） | NEED_OWNER_DECISION → 本期不接入，字段预留为 `unresolved` | 预留 | 后续板块接入 | WFS 货件同步上线 | 否（本期明确不做） |

## 6. 数据血缘表（核心字段，gate §8）

| 接口字段 | 数据集 | 源系统/表/接口 | 原始字段 | 标准字段 | 转换或公式 | 时区 | 币种 | 更新频率/新鲜度 | 写入方 | 风险与证据 |
|---|---|---|---|---|---|---|---|---|---|---|
| 采购单号 | 采购单 | purchaseOrderList | `order_sn` | `purchase_order_sn` | 原样 | — | — | 每日增量 | sync | 主键 |
| 下单日期 | 采购单 | purchaseOrderList | `order_time` | `order_date` | 取日期（Asia/Shanghai） | CST | — | 同上 | sync | 探测 12 月 1219 单中 39 单为空（待下单/作废单） |
| 到仓日期 | 收货单 | PurchaseReceiptOrder/getOrderList | header `receive_time`, item `product_receive_num` | `arrival_date` | 按 `business_order_sn` 归到采购单，累计收货量 ≥ 整单 `quantity_total`×50% 的首个收货日期 | CST | — | 同上 | dwd 刷新 | 明细 CSV `purchase_order_sn/receive_time` 为空，必须用单头字段（探测 v4） |
| 采购交期 | 派生 | — | — | `purchase_cycle_days` | `arrival_date − order_date` 整数天；<2 天自动剔除样本 | — | — | 同上 | dwd | 业务规则 §4 |
| 审批周期 | 派生 | getPurchasePlans + purchaseOrderList | plan `create_time`, po `create_time` | `approval_cycle_days` | 日期差；领星无审批时间戳，≤1 天误差 | CST | — | 同上 | dwd | 探测中位 4.9 天、73% > 2 天 |
| 金额 | 采购单 | purchaseOrderList | `amount_total`,`total_price`,`shipping_price`,`other_fee`,`purchase_currency`,`purchase_rate`; item `price`,`amount` | 同名 | numeric(18,4) 原样 + `currency_code` | — | CNY（探测 100%）| 同上 | sync | 财务口径，需负责人确认 |
| 店铺 | 采购单明细 / 计划 / Listing | item `sid` → dim_lingxing_stores；为 0 时经 ItemID 归属 → dim_walmart_listings.store_id | `sid` | `store_id` | 字符串处理 18 位 ID | — | — | 同上 | dwd | **探测：明细 56% `sid=0`、计划 49% `sid=0`，这些行店铺只能经 ItemID 归属或人工得到** |
| ItemID | 计划备注 / 人工 | plan `remark` 正则 `ITEMID:\s*(\d{11})`；manual 覆盖 | `remark` | `item_id`,`item_id_source` | 优先级 manual > from_plan_remark > from_shipment > unresolved | — | — | 同上 | dwd + manual | 探测：存量 1455 计划 **0 条**含 ITEMID 备注（规范未推行），上线初期大量 `unresolved` |
| 发货方式 | Listing | walmartListingList | `fulfillment_type` (0/1/2) | `fulfillment_type` | 原样；`≠1` 且已归属 → `wfs_not_ready` | — | — | DATA-PAGES-1 同步 | DATA-PAGES-1 sync | 探测 2620 条：0=1190 / 1=445 / 2=985 |

## 7. 数据库设计原则

- 外部 ID（`sid`/`wid`/`store_id`/`item_id`）一律 `varchar`，禁止 bigint（探测 v2 曾因 JSON 精度丢失产生假"尾数不一致"）。
- 金额 numeric(18,4) + 币种列；不做汇率换算。
- 时间：ODS 保留原始 `datetime`（CST）；DWD 派生日期列 `date`；天数为整数。
- 阈值走版本化规则表，不写死在代码。
- 前端只读 DWS；`manual_*` 按 `docs/data-governance/manual-override-policy.md`。

## 8. 同步顺序

1. dim_lingxing_stores / dim_walmart_listings（DATA-PAGES-1 已有）
2. 采购计划 → 采购单（含明细）→ 收货单（含明细）
3. DWD 刷新（归属、拆分、到仓、交期）→ DWS 刷新（看板、SKU 交期、待处理）

## 9. 调度决策

- 每日一次增量（`update_time` 近 90 天，按 30 天分段）；首启一次性 12 个月回填（约 1.5k 计划 / 1.2k 采购单 / 1.1k 收货单，各 ≤3 页/段）。
- token_bucket_capacity=1，串行调用；`purchaseOrderList` 以"返回行数 < length"终止分页。
- 生产调度默认 `schedule_enabled=false`，需单独书面授权。

## 10. 数据质量门禁

- 采购单明细 `quantity_plan` 合计 = 单头 `quantity_total`；收货明细归属采购单率 = 100%（探测 1138/1138）。
- 店铺 ID 跨接口一致率（探测 v4：100%）。
- ItemID 归属率、`unresolved` 数、`wfs_not_ready` 数每日记录到 sync 质量表。

## 11. PRP 进入条件

除 §12 阻塞项外，本决策已满足 `READY_FOR_PRP` 条件。实现时仍需：Alembic migration；Route→Schema→Service→Repository→Model；前端不查 RAW；不连生产库；不调真实外部 API（含探测）；不改 `old-system/**`；不输出密钥或真实明细。

## 12. 最终建议

- 接口总体状态：`BLOCKED_BY_OWNER_DECISION`（单项）
- 推荐短期策略：REBUILD_SYNC 三接口 + 复用 DATA-PAGES-1 DIM + 两张 manual 覆盖表
- 推荐长期策略：PMC 后续板块补齐发货追溯与写接口
- 旧库退出条件：不适用（不读旧库）
- 迁移或同步边界：只读；12 个月回填 + 90 天增量
- 主要风险：(1) 56% 明细无 `sid`，店铺维度依赖 ItemID 归属；(2) 存量计划无 ITEMID 备注，上线初期 `unresolved` 高；(3) 审批周期无官方时间戳；(4) `purchaseOrderList` 无 total
- 待负责人决定：
  1. **收货单接口 `LX-4B9473A2D2E1` 由 `DO_NOT_USE` 重评为 `READY_FOR_PRP`**（只读、无副作用，登记表 `is_read=是`；`DO_NOT_USE` 疑为"收货质检"模块规则初筛误伤）。方案 A：按 do-not-use.md 例外流程在本 docs PR 内更新 `API_CONTRACT_INVENTORY.csv/.md`、`API_CONTRACT_SOURCE_MAP.md`、`api-verification-status.csv`；方案 B：先只批采购计划 + 采购单两接口，到仓时间暂缺（看板不可用，不建议）。
  2. `dim_walmart_listings` 新增 `fulfillment_type`（0/1/2）列并在 Listing 管理展示（跨模块最小改动）。
  3. 系统级 UI 规则：ItemID 统一渲染为 `https://www.walmart.com/ip/<ItemID>` 链接（`WalmartItemLink` 组件）。
  4. 产品详情页"采购交期"改读 `dws_purchase_sku_cycle`（跨模块，可放 Gate 4）。
- PRP 必须引用的结论：§5 分类表、§6 血缘表、业务规则 v3 §2–§5.6、§10 数据质量门禁

## 负责人决定

- 决定：批准进入 PRP / 要求补充证据 / 选择方案 [A/B]
- 批准的数据集分类：
- 批准的短期策略：
- 批准的长期策略：
- 约束与退出条件：
- 批准人：
- 批准日期：
- 备注：
