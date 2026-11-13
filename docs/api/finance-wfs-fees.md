# 财务 · WFS 费用明细（`/api/finance/wfs-fees`）

Rocky 2026-11-12 口径：一个 tab、一张表、一列费用类型；展示已归属到商品的全部 WFS 费用；导入按钮所有店铺可用；
定时拉取放任务中心（PR 2）。PRP：`PRPs/finance-wfs-fees-v1.md`。

## 费用范围与来源

| 来源 `fee_source` | 报表 | 费用类型 `fee_type` | 到商品 |
|---|---|---|---|
| `settlement` | 沃尔玛结算报表（SETTLEMENT；接口下载或卖家后台「服务费 → 下载」） | Refund、PrepServiceFee、MultiChannelFulfillmentFee、LostInventory、InventoryTransferFee、InventoryRemovalOrder、InventoryDisposalOrder、FoundInventory、DiscountAdjustment、DamageInWarehouse、RC_InventoryDisposalFee、Charge、WFSWalmartFaultReturnRestockedFee、ReturnProcessingFee（以报表为准，新类型照原名收） | 报表自带 GTIN；无 GTIN 按规则分摊 |
| `storage` | 仓储费报表（WFS_STORAGE_FEE） | StorageFee | 报表自带 GTIN / Item ID |
| `inbound` | 入库运输报告（卖家后台） | InboundTransportationFee | 按货件 → 货件商品件数分（沃尔玛远程采集的入库货件明细 `fact_walmart_wfs_inbound_items`：itemQty，没有时 receivedQty）；报告里的货件号都属于同一家店时自动认店 |

结算报表里的 **FulfillmentFee（配送费）不入表**；StorageFee / InboundTransportationFee 的店铺级周汇总行也不入表（另有专门报表），只用于核对。

金额 `amount_usd`：我方视角，正 = Walmart 付我们，负 = 扣费（结算报表 Net Payable 取反）。

## 表

- `raw_walmart_wfs_fee_files`：每个上传 / 同步 / 历史迁入的文件一条（原件按 sha256 存档在 `media_storage_root`）；`status` parsed / rejected / empty；仓储 / 入库记账期和头部总额。
- `fact_walmart_wfs_fee_lines`：一行 = 报表一笔；`(source_account_ref, store_id, line_key)` 唯一。`line_key`：结算 = WFS Reference ID（没有就 日期+类型+Reason+金额+GTIN+PO 的哈希，重复行按序号区分）；仓储 = GTIN × 账期；入库 = 货件 × 账期。分摊子行 `parent_line_id` 指向原行，子行 `attribution=allocated`。`missing_since`：仓储 / 入库同账期重传时上次有、这次没有的行。
- `manual_walmart_wfs_fee_adjustments`：人工调整留痕（realloc / company / verified），不改原行的报表字段。
- `mart_walmart_wfs_fee_checks`：店铺 × 账单期 × 费用类型，领星 vs 本表（ok / diff / lx_only / report_only），可标已核实。

## 归期与归属

- 归期：结算报表按扣费周五（`date_charged`）找领星同店同类同日账单行 → 同店同日任一账单 → 账单期起止包含 → 多期重叠取较晚（`bill_match` 记依据）；RC_InventoryDisposalFee、ReturnProcessingFee 领星按天出账，按交易日。仓储 / 入库按账期止日。
- 归属 `attribution`：matched（GTIN 对上商品表）、unmatched、allocated、allocated_check（新卖家补贴基数 × 10% 与返还额差 > 1%）、unallocated、company。规则见 `app/modules/wfs_fees/attribution.py`，和 7~10 月手工表一致。
- 分摊：按比例最大余数法分到分，每行与原行同号，Σ = 原行；人工分摊过的行重导后原金额变了 → 标「已分摊，基数待核」，依据写「原金额已变，人工分摊需重做」。
- 导入规则：同一文件再传只刷新；仓储报表同一 GTIN 多行：同 SKU 合并、不同 SKU 各一行；仓储 / 入库同账期重传 = 覆盖；账期交叉但起止不同 = 拒收；仓储头部 Total 与明细差 > 0.5 拒收；空报告留 0 行记录。人工调整过的行重新导入不重算。

## 接口

| 接口 | 权限 | 说明 |
|---|---|---|
| `GET /fee-types` | view | 费用类型中英文、来源 |
| `GET /periods` | view | 店铺 × 账单期（领星同步的沃尔玛账单；店铺代码 = 店铺名横杠前编号），页面筛选用；没有账单的沃尔玛店铺（领星店铺表）和只有费用行的店铺也各给一行 |
| `GET /lines?store_id&report_key&fee_type&fee_source&attribution&date_from&date_to&q&include_missing&page&page_size` | view | 原行分页（≤ 500），每行带 `children` 分摊子行；`store_id` / `report_key` / `fee_type` / `fee_source` / `attribution` 都可逗号分隔多选（summary / checks / files 同）；`split=yes|no` 筛有 / 无分摊子行的原行；`q` 搜 ITEM ID / MSKU / SKU / GTIN / 货件号 / Reference |
| `GET /summary`（参数同 `/lines`，不分页） | view | 店铺 × 账单期 × 类型 汇总 + 合计，筛选与明细同一口径 |
| `GET /checks?store_id&report_key&only_problem` | view | 核对结果（默认只给没核实的问题） |
| `GET /files?store_id&fee_source` | view | 文件记录 |
| `POST /imports`（body = 文件；头 `X-File-Name`、`X-Store-Id`、`X-Period-Start`、`X-Period-End`） | import | 上传一份报表（CSV，或卖家后台下载的 ZIP：只取里面的 .csv，≤50 个、每个解压后 ≤16MB、合计 ≤64MB），返回 `items`（每个 CSV 一条）；不用选店铺（Rocky 11-13）：结算报表按 Partner ID（`FINANCE_WFS_PARTNER_STORE_MAP` → 以前导入过的同一 Partner ID）认店，其余按文件里的 SKU / GTIN / Item ID 对商品表投票（只有一家店覆盖 ≥ 80% 的可匹配行、且可匹配行 ≥ 有商品信息行的 50% 才算；学到的 Partner 店铺与投票不一致 → 拒收待人选）；文件名里的 Partner ID 只给没有费用行的文件兜底；同一份文件（按内容）已导入到别的店 → 拒收；认不出才拒收并返回 `needs_store=true`，页面在那一行选店后带 `X-Store-Id` 重传——`X-Store-Id` 只补认不出的，不覆盖认出的；接口下载的仓储报表（没有汇总块）要账期头 |
| `POST /lines/{id}/adjust` `{kind: realloc|company, reason, payload:{shares:[{gtin,item_id,msku,amount}]}}` | adjust | 分摊合计必须等于原金额 |
| `POST /checks/verify` `{store_id, report_key, fee_type, reason}` | adjust | 标已核实；金额变了自动清掉 |

权限键：`page:finance:wfs-fees:view`、`action:finance:wfs-fees:import`、`action:finance:wfs-fees:adjust`、`action:finance:wfs-fees:sync`。错误码前缀 `WFS_FEE_`。

## 配置

- `FINANCE_WFS_PARTNER_STORE_MAP`：结算报表 Partner ID → 店铺 id 的 JSON，真实值只在线上 app.env。没配的店铺上传结算报表时要选店铺。
- `media_storage_root`：原件存档（同资金流水）。

## 历史数据

`backend/scripts/load_wfs_fee_history.py`（上线后按票据在服务器执行，数据不进仓库）：旧系统 `fact_wfs_storage_fee` / `fact_inbound_freight_alloc` 只读导出 → 合成报表导入；已拉的结算报表原始 CSV 直接导入。

## 同步（PR 2）

- 接口：`GET /sync/status`（view）：最近一次运行、失败的店、按钮锁到什么时候；`POST /sync`（sync 权限）：建一次任务中心运行。锁：点一次 90 分钟、最近一次手动同步失败 60 分钟（定时同步部分店失败不锁）、正在跑时都返回 409 `WFS_FEE_SYNC_LOCKED`；任务没开通 503 `WFS_FEE_SYNC_NOT_CONFIGURED`；队列不可用 503 `WFS_FEE_SYNC_UNAVAILABLE`。
- 任务中心：`walmart` / `walmartWfsFeeReports`，handler `walmart.wfs_fee_reports.v1`；登记脚本 `backend/scripts/bootstrap_wfs_report_governance.py`（要 `WFS_REPORT_BOOTSTRAP_AUTHORIZED=true`；定时默认关，在任务中心开，建议 UTC cron `0 * * * *`）。
- 期：2026-08-22 起每 14 天一期（周六到周五），止日 + 7 天上海 03:00 以后去要；历史只补 2026-10-01 以后结束的期。
- 任务表 `ops_walmart_wfs_report_jobs`：一店 × 一类（SETTLEMENT / WFS_STORAGE_FEE）× 一期；queued → submitted → imported / empty，failed / pii_blocked 终态。没生成好隔 1 小时再看，最多 48 次；下单失败最多 3 次（沃尔玛限流不算）；远端连不上 / 令牌被拒连续 48 次算失败；1 小时内真下过单的类型不再下（下单成功或失败都算，只复用已有请求不算，看 `last_post_at`）；定时不重试失败的，手动同步只重排失败的（疑似个人信息拦下的不重排）；一家店导入出错只回滚这家店、隔 1 小时再来，连续 48 次都出错算失败（`WFS_REPORT_IMPORT_FAILED`）。
- 远端：沿用沃尔玛远程采集的路由和店铺授权（`SZZSBJ_WALMART_REMOTE_ROUTES`、`SZZSBJ_WALMART_REMOTE_APPROVED_STORES`、`SZZSBJ_WALMART_SCF_STORE_ID_MAP`、云角色），另加开关 `SZZSBJ_WALMART_WFS_REPORTS_ENABLED=1`。每次把执行器 `wfs_report_engine.py` 上传到店铺服务器（核对 sha256）、令牌只走标准输入、跑完拉回结果按 SHA256SUMS 核对、删掉远端目录。执行器白名单写死：只有 SETTLEMENT / WFS_STORAGE_FEE、只有 GET / POST、POST 只发 `/v3/reports/reportRequests`；每店每类每次最多下单 1 次，下单前先复用近 30 天同范围的请求；下载后疑似个人信息不落盘；ZIP 解压上限：下载 ≤ 64MB、最多 20 个 CSV、ZIP 总条目 ≤ 1000、单个解压后 ≤ 64MB、全部解压后 ≤ 128MB（先按文件头查，解压时按实际大小再查），超了这份报表记 `WFS_REPORT_ZIP_TOO_LARGE` 直接失败，不影响别的任务和店铺。
- 仓储费以接口为准：同一期仓储费不要再手动导卖家后台的报表（账期起止不同会被当成交叉账期拒收）。
- 入库货件明细：每次运行先读远程采集落下的 `daily/<日期>/walmart/<店铺>/<run>/items.csv`（`SZZSBJ_WALMART_REMOTE_ARCHIVE_ROOT`），读过的 run 不再读；读到的货件里还没分摊、没人工调整过的入库运费自动补分摊；补分摊出错只记日志，不影响报表导入。
- 页面：「同步」按钮带确认弹窗、锁定时显示几点后可以再点；最近一次失败时表格上方列出失败的店和原因。
- 沃尔玛付款对账单（备用金、实付）不在这个 PR，留给回款对账。
