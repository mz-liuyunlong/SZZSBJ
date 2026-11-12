# PRP: 财务 · WFS 费用明细 V1

- Status: Ready for review（Rocky 2026-11-12 22:24 ~ 22:40 口径；代码与本 PRP 同一 PR 审核）
- Owner Approval Required: Yes（财务板块 PRP / PR 负责人：Rocky；合并、上线：刘云龙）
- Main execution role: Backend Engineer + Frontend（新页面）
- Branch: `fin/wfs-fees`（PR 1）、`fin/wfs-fees-sync`（PR 2）
- Production execution authorized: No（上线、云函数发布、历史迁入各按票据执行）
- 口径来源：Rocky 2026-11-12 22:24（一个 tab、导入按钮、展示已匹配的全部费用）；22:28（接口直拉沃尔玛、定时 + 手动同步、一张表加费用类型列）；22:39 ~ 22:40（配送费不进、退货处理费进；账期 14 天、账单日后第三天打款；领星货件同步一起做；所有店都可导入；定时放任务中心；做快）
- 旧系统参照：`old-system/source/src/aiFinanceRoutes.ts`（仓储 / 入库 CSV 导入、防重、守恒、空报告留 0、未匹配重分摊）、`pmcFeeDetailRoutes.ts`
- 本次手工交付参照：`features/finance/deliverables/WFS服务费_202607-09/`、`WFS服务费_202610/`，脚本 `features/finance/drafts/{build_fee,wfs_fee_check,wfs_fee_oct}.py`

## 0. 决策记录

| 项 | 定稿 |
|---|---|
| 页面 | 财务 → **WFS 费用明细**，一个 tab，一张表 |
| 费用范围 | 结算报表（SETTLEMENT）里的服务费 11 类 + **退货处理费**；仓储费（WFS_STORAGE_FEE 报表）；入库运输费（卖家后台「入库运输」报告）。**配送费不进** |
| 数据来源 | 沃尔玛官方 API（每店自己的云函数线路）；所有店铺都可用「导入」上传卖家后台下载的文件；CN2502 只能导入 |
| 拉取时机 | 账期 14 天一期，账单日（周二）后第 3 天打款、报表可下载。定时 = **每个账单日后第 3 天（周五）凌晨**，在任务中心登记；页面有「同步」按钮 |
| 入库运费到商品 | 领星 WFS 货件同步（`QueryWFSCargoPage` + 货件商品），按实发数量分摊，没有实发按申报数量，尾差归最后一行 |
| 无 GTIN 行分摊 | 沿用 7~10 月手工表规则（§7） |
| 核对 | 和领星沃尔玛账单（`walmart_bill_lines`）按 店铺 × 账单期 × 费用类型 对；不一致列在表上方提示条 |
| 历史数据 | 旧系统仓储 / 入库 2026-05 起迁入；服务费 / 退货处理费 2026-07 起用已拉的报表导入 |
| 权限 | 有财务导入权限的能同步 / 导入 / 调整；查看跟财务板块 |
| 上线 | 两个 PR，做快：PR 1 表 + 页面 + 导入 + 解析 + 分摊 + 历史迁入；PR 2 接口拉取 + 任务中心定时 + 领星货件同步 + 云函数放行 |

## 1. Goal

财务在一个页面看到所有店铺、所有账期、按 ITEM ID 归属的 WFS 费用（服务费、退货处理费、仓储费、入库运费），能筛、能导出、能看和领星账单的核对结果，能对分摊和差异做调整并留痕；数据由定时任务从沃尔玛接口拉取，也可以手工上传。结算利润、订单审核从这一张表取 WFS 费用。

## 2. Why

- 这三类费用领星账单只到店铺一级，拆不到商品；旧系统的仓储 / 入库导入要下线，服务费靠 Mac 上的临时脚本拉、手工出表，不可持续。
- 结算利润、订单审核都依赖按商品的 WFS 费用，先把这张表做出来。

## 3. Scope

### PR 1（`fin/wfs-fees`）

- [ ] 迁移：`fact_walmart_wfs_fee_lines`（§6）、`manual_walmart_wfs_fee_adjustments`、`landing_walmart_wfs_fee_imports` / `raw_walmart_wfs_fee_files`（原文件存档，RAW-first）；权限 `page:finance:wfs-fees:view`、`action:finance:wfs-fees:import`、`action:finance:wfs-fees:adjust`、`action:finance:wfs-fees:sync`（PR 2 用，先登记）。
- [ ] 解析器：结算报表 CSV（接口下载的和卖家后台「服务费 → 下载」的两种列名）、仓储费报表 CSV（新旧两版表头）、入库运输报告 CSV；按内容认店铺（Partner ID / 报告头）和账期，不看文件名。
- [ ] 入库规则：按 §6 主键幂等；仓储费守恒（Σ明细 vs 头部 Total 差 > 0.5 拒收）、账期交叉拒收、空报告留 0 记录；同一文件再传只刷新，不重复。
- [ ] 商品匹配：店铺 + GTIN → `dim_walmart_listings`（item_id / msku / local_sku）；仓储报表自带 Item ID 优先。
- [ ] 分摊（§7）：无 GTIN 行、入库运费按货件；基数对不上标「待核」。
- [ ] 核对（§8）：和 `walmart_bill_lines` 按 店铺 × report_key × 费用类型 汇总比对，结果存表、页面提示条展示。
- [ ] 接口（§10）：列表 / 汇总 / 导入 / 调整 / 核对结果 / 导出。
- [ ] 页面：`/finance/wfs-fees`，ReportTableShell 表格 + 筛选 + 「导入」「导出」按钮 +（PR 2 启用的）「同步」按钮；行内「调整」。
- [ ] 历史迁入脚本（只读旧库导出 → 本模块导入接口）：旧系统 `fact_wfs_storage_fee`、`fact_inbound_freight_alloc`、`raw_walmart_inbound_csv`（2026-05 起）；`features/finance/data/wfs_fee_*` 已拉的结算报表（2026-06-24 起）。脚本在仓库，执行按票据。
- [ ] 测试、文档（`docs/api/finance-wfs-fees.md`、数据源决策、模块目录）。

### PR 2（`fin/wfs-fees-sync`）

- [ ] 沃尔玛接口：`report_request_create`（POST reportRequests，reportType=SETTLEMENT / WFS_STORAGE_FEE）、`report_request_status_get`、`report_download`（downloadReport + 文件 GET）加进只读目录（`operations_catalog.py`）并放行；云函数 ZIP 重新打包（CI 既有 walmart-scf-python310 任务），8 店 `stable` 切换按票据。
- [ ] Integration Sync handler `walmart.wfs_fee_reports.v1`：每店提交 → 轮询（每 2 分钟，最多 30 分钟）→ 下载 → 走 PR 1 的解析入库；每店每类报表一小时内只提交一次（沃尔玛限制），命中限制则排队到下一轮。
- [ ] 任务中心登记：interface_key `walmartWfsFeeReports`，默认关；定时 = 账单日后第 3 天上海 03:00（以 `walmart_bill_periods` 最新 report_date 推算，没有就按双周周五）；手动同步接口 `POST /api/finance/wfs-fees/sync`（按店 / 账期）。
- [ ] 领星 WFS 货件同步：`QueryWFSCargoPage` + 货件商品，写 `ods_lingxing_wfs_shipments` / `_items`；入库运费分摊改读这里；货件到了自动把「未分摊」补分。
- [ ] 测试：MockTransport 下的提交 / 轮询 / 限流 / 下载 / 解析幂等；任务中心开关、定时、手动、权限。

### Out of scope

- 配送费（FulfillmentFee）入表；结算利润、订单审核页面本身；CN2502 配服务器；云函数线上切换和历史迁入的执行（各按票据）。

## 4. Navigation / Page

`/finance/wfs-fees`，菜单「财务 → WFS 费用明细」。页面顶部筛选：店铺、账单期（下拉，来自 `walmart_bill_periods`）、费用类型、归属状态、ITEM ID / MSKU / SKU / GTIN 搜索。按钮：同步、导入、导出 Excel。表格上方提示条：本次筛选范围内核对不一致的 店铺 × 账期 × 类型 列表，可点开看两边金额。表格列见 §6 展示列；行内「调整」弹窗（改分摊 / 记公司 / 标已核实，必填原因）。

## 5. Permissions

```text
page: page:finance:wfs-fees:view
actions: action:finance:wfs-fees:import（导入）、action:finance:wfs-fees:sync（同步）、action:finance:wfs-fees:adjust（调整 / 标已核实）
data scope: store（沿用财务板块店铺范围）
field: 不展示订单买家信息；结算报表的 Customer Order ID 只存不展示
```

## 6. Data model

`fact_walmart_wfs_fee_lines`（一张表，费用类型一列）

| 列 | 说明 |
|---|---|
| id, store_id, source_account_ref | |
| fee_source | `settlement` / `storage` / `inbound` |
| fee_type | 服务费 11 类（Refund、PrepServiceFee、MultiChannelFulfillmentFee、LostInventory、InventoryTransferFee、InventoryRemovalOrder、InventoryDisposalOrder、FoundInventory、DiscountAdjustment、DamageInWarehouse、RC_InventoryDisposalFee、Charge、WFSWalmartFaultReturnRestockedFee…以报表为准）+ `ReturnProcessingFee` + `StorageFee` + `InboundTransportationFee` |
| reason_code, detail | 报表原文 |
| transaction_date, date_charged | 交易日、扣费周五（结算报表）；仓储 = 账期止日；入库 = 账期止日 |
| report_key, report_date | 归属的领星账单期（§8 归期规则） |
| po_number / shipment_id, partner_id, gtin, item_id, msku, local_sku, quantity | |
| amount_usd | 我方视角：正 = Walmart 付我们，负 = 扣费 |
| attribution | `matched` / `allocated` / `allocated_check` / `unallocated` / `company` |
| allocation_basis, parent_line_id | 分摊依据；分摊子行指向原行 |
| source_line_key | 幂等键：settlement = WFS Reference ID（空则 日期+GTIN+金额+类型 hash）；storage = GTIN×账期；inbound = 货件号×账期（分摊子行加 msku） |
| raw_file_id, import_id / sync_run_id | 回指原文件或同步运行 |

`manual_walmart_wfs_fee_adjustments`：line_id、kind（realloc / company / verified）、payload、reason、actor、created_at；调整不改原行，生效值由读取层叠加。

展示列：店铺、账单期、扣费日期、交易日期、费用类型（中 / 英）、Reason、PO / 货件号、GTIN、ITEM ID、MSKU、SKU、数量、金额、归属、依据、来源、调整。

## 7. 费用类型与归属规则（沿用 7~10 月手工表）

- 有 GTIN：店铺 + GTIN 匹配商品，`matched`；匹配不到 `unmatched`，提示条列出。
- 无 GTIN：
  - Refund · InboundTransportationShippingRefund：按该货件入库运费分摊比例分到商品（货件没数据 → `unallocated`）。
  - Refund · StorageFeeDispute：`company`。
  - DiscountAdjustment（新卖家补贴返还）：按明细里的期间；配送费返还 = 期间内无逐行折扣配送费原价 × 10%；仓储费返还 = 期间内各 SKU 仓储费原价 × 10%；基数 × 10% 与返还额差 > 1% 标 `allocated_check`。
  - 其他无 GTIN：`unallocated`，由财务调整。
- 入库运费：货件 → 领星货件商品，按实发数量分，没有实发按申报数量，尾差归最后一行；货件查无 → 整笔 `unallocated`，货件到了自动补分。
- 仓储费：报表到 GTIN，直接 `matched`。
- 金额口径：正 = Walmart 付我们，负 = 扣费；结算报表 Net Payable 取反。

## 8. 归期与核对

- 归期：结算报表按 `date_charged`（交易日所在周的周五）找领星同店同类同日的账单行 → 同店同日任一账单 → 账单期起止包含；退货处理费 / 退货中心弃置费按交易日（领星按天出账）。仓储、入库按报表账期止日。
- 核对：店铺 × report_key × fee_type：领星金额 vs 本表金额，差 ≥ 0.01 标不一致；本表有领星没有标「领星缺」，反之「报表缺」。结果存 `mart_walmart_wfs_fee_checks`，页面提示条读它；财务可标「已核实」+ 原因。
- 已知差异类型（写进提示文案）：期末一天时区差、报表漏行、领星没有的新类型。

## 9. 拉取与定时（PR 2）

- 定时：任务中心 `walmartWfsFeeReports`，账单日后第 3 天 03:00；每店提交 SETTLEMENT（交易日 = 刚结束账期起止）和 WFS_STORAGE_FEE（账期）。
- 限制：同店同类报表 1 小时 1 次；一次提交后最多轮询 30 分钟，超时记失败、下一轮重提。
- 手动同步：页面按钮，选店 / 账期；CN2502 没有线路，按钮禁用并提示用导入。
- 所有请求走既有每店云函数线路，只读 + 报表提交；原始文件进 `ods_api_raw_blobs`。

## 10. API

```text
GET  /api/finance/wfs-fees/lines?store_id&report_key&fee_type&attribution&q&page&page_size
GET  /api/finance/wfs-fees/summary?store_id&report_key          # 类型 × 店铺 × 账期汇总
GET  /api/finance/wfs-fees/checks?store_id&report_key          # 核对结果
POST /api/finance/wfs-fees/imports        multipart；返回每个文件：店铺、报表类型、账期、新增 / 重复 / 拒收原因
POST /api/finance/wfs-fees/lines/{id}/adjust   {kind, payload, reason}
POST /api/finance/wfs-fees/checks/{id}/verify  {reason}
GET  /api/finance/wfs-fees/export?...       xlsx，同筛选
POST /api/finance/wfs-fees/sync             {store_id?, report_key?}（PR 2）
```

统一 envelope、错误码前缀 `WFS_FEE_`。

## 11. Migration

- PR 1：`20261113_0087_finance_wfs_fees`（基于 0086；合并前按 main 最新 + 1 重编号）。只新增表和权限；downgrade 有数据拒绝。
- PR 2：如需新表（领星货件）另起一版。

## 12. Test plan

- 解析：三类报表、两种结算报表列名、仓储新旧表头、Excel 保护符、千分位、空报告、守恒不平、账期交叉、重复文件。
- 归属：GTIN 匹配 / 前导 0、各无 GTIN 规则、基数待核、入库按实发 / 申报、尾差、货件缺。
- 核对：一致 / 不一致 / 领星缺 / 报表缺、期末时区差。
- 调整：三种 kind、原因必填、留痕、不改原行。
- 接口 / 权限：三个 action 权限、店铺范围、导出。
- 历史迁入脚本：合成旧系统 CSV → 导入接口幂等。
- PR 2：Mock 下提交 / 轮询 / 限流 / 下载；任务中心开关、定时、手动。

## 13. Acceptance

- 线上导入 7~10 月结算报表和旧系统仓储 / 入库数据后，页面汇总与 `WFS服务费_202607-09.xlsx`、`WFS服务费_202610.xlsx` 的汇总页逐店逐类一致；核对结果与两份表的核对页一致。
- 财务能在页面完成：筛选、导出、调整分摊、标已核实。
- PR 2 上线后：账单日后第 3 天自动出现新账期数据；手动同步可用；CN2502 走导入。

## 14. Open items（不阻塞）

- 配送费以后是否也入表（订单审核可能要）。
- CN2502 是否配线路。
- 仓储费日摊（旧系统 `fact_storage_fee_daily`）结算利润要用时再做。