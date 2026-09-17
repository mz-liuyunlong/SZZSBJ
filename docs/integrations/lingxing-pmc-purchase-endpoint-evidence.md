# Lingxing 采购三接口 Endpoint Evidence（PMC 采购看板）


Status: `Evidence Captured — Read-Only Probe via Legacy Client — No New-System Call Made`

Evidence capture date: `2026-09-15` (v2/v3) / `2026-09-17` (v4)

## 1. 证据定位

- 仓库 normalized 契约：`docs/integrations/lingxing-walmart-openapi/normalized/{interfaces,request_params,response_fields}.csv` 中 `LX-03B82747B50A`、`LX-D332F931885E`、`LX-4B9473A2D2E1`。
- 后端登记：`backend/app/integrations/lingxing/data/official_verified_interfaces.csv`（三者均 `OFFICIAL_VERIFIED`，`is_read=是 / is_write=否 / has_side_effect=否`，`offset/length`，页长 500，`token_bucket_capacity=1`）。
- 真实数据只读探测：由部署 AI 在 `company-ai:/opt/lingxing-auto` 用旧系统既有领星客户端执行（旧系统 src md5 前后一致，未改动），产物脱敏 CSV 与报告存 `features/pmc-purchase/data/probe_20260915/`（v2/v3，90 天）与 `probe_20260917/`（v4，12 个月）。**新系统未发起任何领星请求，未写任何数据库。**
- 凭据、真实单号、产品名不写入本文。

## 2. 当前仓库事实

- 三接口在 `docs/integrations/lingxing/API_CONTRACT_INVENTORY.csv` 中：采购计划、采购单 `READY_FOR_PRP`；收货单 `DO_NOT_USE`（`data_role=reference_only`，备注"excluded without separate Owner re-evaluation"）。与登记表只读属性矛盾，见 §7 风险 1。
- 三接口均无 `docs/integrations/lingxing/contracts/*.md` 快照；本包补齐 3 份。
- `phase-1-candidate-apis.csv` 已将采购单、收货单列为"采购管理页"候选（待负责人/架构师复核）。
- 后端 `LingxingOpenApiClient` 默认 deny：三接口不在 `enabled_interface_ids`，`dry_run=True`；只读接口不需要 `owner_authorized_interface_ids`，但治理侧仍需本决策批准。

## 3. 接口 contract 摘要（三接口共同）

| 项目 | 证据 | 结论 |
|---|---|---|
| Protocol / Method | HTTPS / POST（登记表） | 与 DATA-PAGES-1 领星客户端一致，可复用签名与 token 逻辑 |
| 分页 | `offset` + `length`（默认/上限 500） | 采购计划、收货单返回 `total`；**采购单不返回 `total`**（登记表 `returns_total=否`；探测确认） |
| 增量 | 采购计划/采购单 `search_field_time` ∈ {create_time, update_time} + `start_date/end_date`；收货单 `date_type` + 区间 | 用 `update_time` 90 天增量、按 30 天分段回填 12 个月 |
| 大整数 | `sid`、`wid`、`store_id` 为 18 位整数 | JSON 解析前正则保护为字符串；v2 曾出现假"尾数不一致"，v4 修正后店铺 ID 跨接口 100% 一致 |
| 成功码 | `code=0` | 同其他领星接口 |

## 4. 关键字段证据（探测 v4，12 个月）

| 数据集 | 行数 | 关键字段与观察 |
|---|---:|---|
| 采购计划 `getPurchasePlans` | 1455 | `status` 分布：-2=1180 / 124=118 / 2=107 / -3=46 / 122=4；`remark`/`plan_remark`/`item_purchase_remark` 三备注字段均存在，含 `ITEMID:` 规范格式者 **0**（规范尚未推行）；`sid` 为 0/空 **713（49%）**；`is_aux`/`is_combo` 全为 0；`msku` 无值；`expect_arrive_time` 为采购员统一填写值，不可作交期依据 |
| 采购单 `purchaseOrderList` | 1219（明细 1285） | `status`：9=1100 / 2=69 / 1=31 / -1=19；`status_shipped`：3=1100 / 1=116 / 2=3；`purchase_currency` 100% CNY、`purchase_rate`=1；`order_time` 为空 39（待下单/作废）；明细 `sid` 为 0/空 **725（56%）**，且这些行经 `plan_sn`/`relation_purchase_plan` 反查计划亦无 `sid`；明细无 `plan_sn` 125 行（未经计划直接下单）；金额字段 `amount_total/total_price/shipping_price/other_fee/price/amount/tax_rate` 全部存在 |
| 收货单 `PurchaseReceiptOrder/getOrderList` | 1138（明细 1193） | `status` 全部 40（已完成）；单头 `business_order_sn` 100% 非空且 **100% 命中采购单**；单头 `receive_time` 100% 非空；**明细 `purchase_order_sn`、`receive_time` 为空**，到仓日期必须取单头；明细 `product_receive_num` 用于累计 50% 规则 |
| Walmart 在线商品（DATA-PAGES-1 同接口） | 2620 | `store_id + item_id + msku + local_sku + gtin` 齐全；`fulfillment_type`：0 WFS Eligible=1190 / 1 Walmart Fulfilled=445 / 2 Seller Fulfilled=985；(`sid`≠0 的采购明细, `sku`) 命中 (store_id, local_sku) **499/560 = 89%** |
| 店铺（DATA-PAGES-1 同接口） | 10 | `sid` 与其他接口一致 |

派生指标证据（v3，90 天 780 单 + v4 复算）：整单采购交期（order_time → 50% 收货日）可算率 >95%；"计划创建 → 采购单创建"中位 4.9 天、73% 超 2 天。

## 5. 响应与错误证据

| 字段/情况 | 证据 | 风险说明 |
|---|---|---|
| `code≠0` | 未在探测中触发 | 错误码语义沿用 DATA-PAGES-1 客户端处理 |
| 分页尾页 | 采购单以"返回行数 < length"判定 | 不能用 total |
| 频控 | 探测串行 1 并发无 429 | 生产按 token_bucket_capacity=1 |

## 6. 最小受控验证可行性

Gate 2 实现后，可用 DATA-PAGES-1 同款 dry-run/契约测试 + 沙箱 fixture（探测 CSV 脱敏后作 fixture）覆盖解析与分层；真实调用需负责人单独授权，与 REAL-DATA-1 同流程。

## 7. 关键风险与待 Owner 决策

1. **收货单接口 `DO_NOT_USE` 标记**：只读、无副作用，疑为"收货质检"模块初筛规则误伤；无此接口则到仓日期不可得，看板核心指标缺失。需按 `do-not-use.md` 例外流程重评。
2. **店铺维度覆盖率**：56% 采购明细无 `sid`，店铺只能经 ItemID 归属（`dim_walmart_listings.store_id`）或人工得到；上线初期"店铺"筛选对这些行无效，需在页面明示"店铺待归属"。
3. **ItemID 备注规范未推行**：存量 0 条；上线初期 `unresolved` 高，依赖人工弹窗与后续 WFS 货件追溯。
4. **审批周期无官方时间戳**：以计划 `create_time` → 采购单 `create_time` 近似，≤1 天误差。
5. **财务口径**：金额原样入库、不换汇；成本核算放到发货后（PMC 后续板块），本期不算。

## 8. Gate 结论

- 三接口契约形状已由仓库 normalized CSV + 12 个月真实数据只读探测交叉确认，字段足以支撑业务规则 v3 全部指标。
- 本状态不等于 provider verification、implemented 或真实 API 已在新系统验证。

## 9. 明确未执行

- 未修改 `backend/`、`frontend/`、`old-system/`；未新增或改动 `official_verified_interfaces.csv`。
- 未在新系统请求领星 token、未调用接口、未写 RAW/DB/Redis、未读 `.env`。
- 探测由部署 AI 在旧系统只读执行，产物脱敏后存 `features/pmc-purchase/data/`，不入仓库。

## 10. Owner Review note

待负责人对 §7 第 1 项作出决定后，本证据文件与决策文件可合入 docs-only PR。
