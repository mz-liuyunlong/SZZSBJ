# PRP：仓库 · 库存索赔（WFS 库存流水入库 + 索赔案件）

- 状态：**已批准，开发 PR 1**（审核 AI 复审通过、rocky 2026-11-03 批准）。PR 2、PR 3 暂缓。
- 起草日期：2026-11-03
- 依据规则：AGENTS.md §11（复杂功能 PRP）、§11.1（数据源决策门禁，docs/delivery/backend-data-source-decision-gate.md）、§11.2（docs/data-sources/database-layering-standard.md、field-standardization-standard.md）
- 数据源决策文件：docs/data-sources/decisions/warehouse-wfs-inventory-claim-decision.md
- 负责人已定事项（rocky，2026-11-03）：
  1. WFS 库存流水新建一张专用表 `ods_lingxing_wfs_cost_valuation_flow`（复用国内仓流水表、原始数据存接口记录表两种放法均否决）。
  2. 该表和领星 WFS 成本计价同步、接口契约登记，**全仓库只此一份，归本 PRP 的 PR 1**；结算利润 V2 不再建 `ods_lingxing_wfs_cost_valuation_lines`，改读本表 `is_current = true` 的行。
  3. 索赔案件新建独立案件表 `ops_wfs_inventory_claim_cases`。
  4. 赔付数据未接入；页面「已赔」「差额」显示「未接入」。当前只做 PR 1 数据底座。
- 本地预览：5174 `/#/warehouse/inventory-claim` 已有前端页（读本地 JSON，仅 DEV），本 PRP 定义它接入正式后端的方案。

---

## 1. Goal

在「仓库」板块新增「库存索赔」页：把领星「查询WFS成本计价明细」接口同步进新系统一张 ODS 表（同时供结算利润 V2 读取），按商品算出 Walmart 仓内丢失、损坏、收货差错、供应商短少、找回的件数，财务据此开索赔案件、跟进，并走「财务专员初审 → 财务主管终审」两步审核后结案。

## 2. Why

- Walmart 仓内丢失、损坏的货，Walmart 应赔而未赔的部分目前没有系统跟踪，只能人工翻库存日志。
- 现有正式系统没有任何 WFS 库存流水（已核实，见 §6.2），每日销售里的「WFS 可售库存」是当前快照，不是流水，算不出丢失和损坏。
- 结算利润 V2 的货本和库存异动也需要同一份流水，只建一份可避免两套口径。

## 3. Scope

### In scope

- [ ] PR 1：接口契约四处登记（§6.1）、数据源决策文件、`ods_lingxing_wfs_cost_valuation_flow` 迁移、同步任务（默认关闭）、店铺对照、测试（合成 fixture）。
- [ ] PR 2（暂缓）：索赔读接口、`ops_wfs_inventory_claim_cases`、两步审核、权限点、写接口。
- [ ] PR 3（暂缓）：前端页面从本地 JSON 切到正式接口、导航、帮助入口。

### Out of scope

- [ ] Walmart 赔付（Reimbursement）数据：正式系统没有来源（`gov_wfs_settlement_collections` 为空；`settlement_parser.py` L128–131 丢弃非订单类交易）。依赖结算通道，本 PRP 不接。
- [ ] 财务「利润结算 → 库存异动」汇总（结算利润 V2 负责，只读本表）。
- [ ] 自动向 Walmart 提交 Case（只记录 Case 号，人工在 Seller Center 提交）。
- [ ] 8088 Demo 不改。
- [ ] 国内仓流水（wareHouseCenterStatement / getBatchStatementList）不改。

## 4. Navigation / Page

```text
一级导航：仓库
二级导航：库存索赔（排在「WFS费用异常」之后）
页面路径：/warehouse/inventory-claim
page key：warehouse_inventory_claim
页面状态：building（本地 5174 有预览；正式环境 PR 3 合入前为 hidden）
```

## 5. Permissions

```text
page permissionKey:
  page:warehouse:inventory-claim:view
action permissionKeys:
  action:warehouse:inventory-claim:open-case        开索赔案件            medium
  action:warehouse:inventory-claim:follow           记录跟进 / 填 Case 号  medium
  action:warehouse:inventory-claim:submit-review    提交审核              medium
  action:warehouse:inventory-claim:review-first     财务专员初审          high
  action:warehouse:inventory-claim:review-final     财务主管终审          high
  action:warehouse:inventory-claim:mark-recovered   确认已追回            high
field permissions:
  field:warehouse:inventory-claim:cost              成本金额列（采购 / 头程 / 其他成本）
data scope resource:
  店铺。按现有店铺数据权限过滤；store_mapping_status = 'unmapped'（店铺未对照）的行只对拥有全店铺权限者可见，页面标「店铺未对照」。
high-risk actions:
  review-first、review-final、mark-recovered 写审计日志。
审批步骤校验:
  第 1 步决定须持有 review-first；第 2 步决定须持有 review-final；同一人不能决定两步，也不能审批自己提交的申请。
  已核实：approvals/generic.py 的 decide() 只校验申请人≠审批人、同一人不重复审批，不按步骤校验权限；
  approvals/router.py L203–L226 对 wfs_case_abandon 以外的类型只允许超级权限（"*"）审批。
  → 按步骤校验权限不被现有模块支持，列入 PR 2：在通用审批规则上增加「每步所需权限键」并在 decide() 校验。
界面只显示角色名「财务专员初审」「财务主管终审」，不显示个人姓名。
```

## 6. Data Source

```text
data source decision file: docs/data-sources/decisions/warehouse-wfs-inventory-claim-decision.md
decision status: READY_FOR_PRP
dataset classifications:
  WFS 成本计价流水 = REBUILD_SYNC（领星是权威来源）
  店铺对照 = 读已有 dim_lingxing_stores（不新建）
  索赔案件 = NEW_SYSTEM_OWNED
contains NEED_OWNER_DECISION: 否（待探测项见 §15.2，不阻塞分类）
owner approval status: 新建流水表、独立案件表已批准（rocky，2026-11-03）；首次开启同步与补历史数据需另行书面同意
old-system reference: 否
new PostgreSQL tables: ods_lingxing_wfs_cost_valuation_flow（PR 1）；ops_wfs_inventory_claim_cases（PR 2）
cache / mart tables: 无
sensitive or critical domains: 库存、成本、敏感数据（店铺名含员工姓名）
downstream readers: 库存索赔（本 PRP）；结算利润 V2（PRPs/finance-settlement-profit-v2.md，只读 is_current = true）
```

### 6.1 接口：领星「查询WFS成本计价明细」

依据：`features/pmc-wfs-shipment/context/lingxing-wfs-cost-valuation-api.md`（rocky 2026-09-23 提供的官方文档摘录，2026-09-10 新增接口，对应领星【多平台管理】>【WFS成本计价】）。文档没有写明的标「待探测」。

| 项 | 内容 |
|---|---|
| 接口键 | `LX-8437AD0BCB9E`（手工键：本接口无官方 document_path，取 SHA1(api_path) 前 12 位；沿用结算利润 V2 已起草的键，全仓库只此一个） |
| path / 方法 | POST `/basicOpen/multiplatform/wfs/cost/valuation/detail`，HTTPS，参数在 body JSON |
| 鉴权 | 与其他 basicOpen 接口相同的公共鉴权（access_token / timestamp / sign / app_key）；契约和日志不记录任何凭证或签名 |
| 令牌桶 | 容量 1 |
| 分页 | offset / length，默认 20，最大 200；本同步取 200 |
| 返回 | `data.page.records[]`；`data.page.total / size / current / pages`；`data.detail.calculationStartTime / calculationEndTime`（重算时间） |

请求参数（本同步的取值）：

| 参数 | 文档说明 | 本同步取值 |
|---|---|---|
| startDate / endDate | yyyy-MM-dd，必填 | 同步窗口；是否含 endDate 当天：待探测 |
| dateType | 0 出入库日期（默认）/ 1 结算日期 | 0（窗口按出入库日期划） |
| sidList | 店铺 ID 列表，不传查全部 | 不传 |
| businessType | 出入库类型编码多选（600 / 20 / 30 / 40 / 610 / 400） | **不传，全量拉**。核实编码覆盖范围前不过滤（PMC run.py L846 传了 6 个编码，是否漏类型待探测） |
| costSource / costZeroType / searchField 等 | 筛选项 | 不传 |
| sortField / sortType | dateLocal 等；asc / desc | dateLocal / asc |

返回字段（`data.page.records[]`）：dateLocal（出入库日期，时区待探测）、imageUrl、gtin、msku、title、localName、localSku、sellerName、businessType、businessName、businessDesc、quantity、businessNumber（货件号）、costSource、orderBasePurchaseAmount、purchaseTotalAmount、orderBaseLogisticsAmount、logisticsTotalAmount、orderBaseOtherAmount、otherTotalAmount、orderNumber、date1（结算日期）、serialNumber（流水编号）。PMC 实测还返回 `sid`（文档未列，多数为空）。金额币种：待探测。

PR 1 交付的契约登记（四处，结算利润 V2 的 PR-1 删除其同名登记）：

| 位置 | 内容 |
|---|---|
| `docs/integrations/lingxing/contracts/inventory-lx-8437ad0bcb9e.md` | 脱敏契约快照：参数、返回字段、分页、限流、边界；不含示例值、店铺、订单号、金额、凭证 |
| `docs/integrations/lingxing/API_CONTRACT_SOURCE_MAP.md` | 新增 `LX-8437AD0BCB9E` 一行，指向上面快照 |
| `docs/integrations/lingxing/API_CONTRACT_INVENTORY.md` | 新增一行，状态 `READY_FOR_PRP`、risk `AUTH_UNKNOWN`、consumer 写本表 |
| `docs/data-registry/DATA_INTERFACE_REGISTRY.md` | 新增 `ext-lingxing-wfs-cost-valuation-detail`，目标 ODS 本表，默认关闭，迁移号写 PR 1 的 revision |

### 6.2 来源取舍（证据）

| 来源 | 结论 | 出处 |
|---|---|---|
| 领星 wareHouseCenterStatement（国内仓流水） | 不传 wids 时能返回「WFS虚拟仓」（wid 28030），但只有领星类型「WFS出库」「库存调整- WFS库存调整」，无 Walmart 原因代码，分不出丢失 / 损坏 / 找回 | 21_lingxing_read.md §2.1.19；`daily/20261102/domestic/inventory_statement.csv`；正式同步只拉 wid 16168（`handlers/lingxing_pmc_domestic_sync.py` L245、L349） |
| 领星 getBatchStatementList（批次流水） | 正式表 0 行；PMC 从未拉过；交接文档无字段说明 | `ods_lingxing_domestic_inventory_events`；`handover.html` L133 |
| 每日销售「WFS 可售库存」 | 当前快照，不是流水 | `mart_listing_management_current.wfs_available_quantity` |
| Walmart inventory_log | 只是归档文件，不在库；CN2502 不拉 | walmart_remote schedule |
| 结算利润 V2 原计划的 `ods_lingxing_wfs_cost_valuation_lines` | **取消**（rocky 2026-11-03）。同一接口只留本表；结算利润的货本和库存异动读本表 `is_current = true` 的行；其 `fact_inventory_movement_lines` 不得用 serial_number 做唯一键，店铺从 store_code / store_id 对照取 | rocky 2026-11-03 补充决定 |

### 6.3 流水号唯一性验证（已完成，只读本地 PMC 文件）

**结论：流水号（serialNumber）不能做唯一键，也不能做跨批次的稳定标识。**

| 检查 | 结果 | 数据 |
|---|---|---|
| 单次文件内是否唯一 | 否。185,527 行、185,394 个不同流水号，133 个流水号重复（262 行 SLO、2 行 RFS、2 行 SIP），同号行的件数、成本、costSource 不同；另有 17 行完全相同 | `daily/20261102/lingxing/lx_wfs_flow.csv` |
| 两次拉取间同号是否同一条 | 否。两份文件里都只出现一次的 154,538 个流水号中，75,145 个日期不同、10,756 个 MSKU 不同 | 对比 `20261025` 与 `20261102` |
| 旧批次的号是否会消失 | 是。19,971 个，分布在 5–10 月 | 同上 |
| 业务字段组合能否做唯一键 | 否。(店铺, 类型, MSKU, 时间, 件数, 业务单号, 订单号) 在单文件内仍有 2,833 组重复 | 同上 |
| 领星是否回改历史数据 | 是，但很少。10-20 前的流水两次拉取相差约 400 行（共约 17 万行）；索赔相关 6 类按 店铺×类型×MSKU×日 汇总，2,761 组中 4 组不同 | 同上 |
| 流水号格式 | 全部 15 位，无空值 | 同上 |
| sid 字段 | 95.7% 为空，店铺主要靠 sellerName 前 6 位的店铺编码对照 | 同上 |

注：PMC 文件是按 6 个 businessType 编码过滤后拉的，全量拉取后的唯一性须在首次授权探测时复核。

### 6.4 索赔相关类型（20261102 实测）

| businessType | businessName | businessDesc | 方向 | 归类 |
|---|---|---|---|---|
| CCA / ADJ | 库存调整出库 / 入库 | Lost/Found Item | − / + | 丢失 / 找回 |
| D16 | 库存调整出库 | Damaged at FC | − | 损坏 |
| ADX | 库存调整出库 | Receiving Correction: Receipt Error | − | 收货差错 |
| VDG | 库存调整出库 | Receiving Correction: Vendor-Caused Shortage | − | 供应商短少 |
| VTM | 库存调整入库 | Found Inventory in FC | + | 找回 |

其他类型（SIP、SLO、RFS、NEGATIVE_INVENTORY、LIQ、MTR、WOC、ODB 等）全部入库，索赔计算不用，结算利润按需读取。

## 7. 设计

### 7.1 表：`ods_lingxing_wfs_cost_valuation_flow`（PR 1）

沿用 `app/modules/pmc_domestic/models.py` 的 `DomesticOdsMixin` 写法（run_id → `gov_integration_sync_runs`，raw_request_ref_id → `ods_api_raw_request_refs`）。

| 列 | 类型 | 说明 |
|---|---|---|
| id | uuid PK | 行 id（下游只存它，不建外键） |
| run_id | uuid FK not null | 同步批次 |
| raw_request_ref_id | uuid FK not null | 哪一页请求 |
| source_account_ref | varchar(128) not null | 领星账号引用（不存密钥） |
| source_item_ordinal | int not null | 该页内顺序号 |
| window_start / window_end | date not null | 本批次请求窗口（dateType = 0） |
| is_current | bool not null default false | 是否当前有效 |
| superseded_by_run_id | uuid null | 被哪个批次替换 |
| serial_number | varchar(32) | 仅追溯，**不唯一** |
| date_local | timestamp（无时区） | dateLocal 原值，时区待探测 |
| business_date | date not null | date_local 的日期部分 |
| settlement_date | date null | date1 的日期部分 |
| store_code | varchar(16) not null | sellerName 前 6 位，如 CN2501 |
| store_id | varchar(128) null | 对照得到的系统店铺 ID，见 §7.2 |
| store_mapping_status | varchar(16) not null | mapped / unmapped |
| msku / gtin / local_sku | text | |
| business_type | varchar(32) not null | 原始字符串 |
| business_name / business_desc | text | |
| quantity | int not null | 带符号 |
| business_number / order_number / cost_source | text | |
| order_base_purchase_amount、purchase_total_amount、order_base_logistics_amount、logistics_total_amount、order_base_other_amount、other_total_amount | numeric(18,4) | 金额，接口返回按字符串转 Decimal |
| currency_code | char(3) null | 币种待探测；确认前为 null，读方须视 null 为「未确认」 |
| row_hash | char(64) not null | 业务字段 sha256，用于比对批次差异 |
| payload_json | jsonb not null | 原始一行 |
| observed_at / created_at | timestamptz | |

- 唯一约束：`(raw_request_ref_id, source_item_ordinal)`。不使用任何业务字段（含 serial_number）做唯一键。
- 索引：`(source_account_ref, is_current, business_type, business_date)`；`(source_account_ref, store_code, msku) where is_current`；`(source_account_ref, settlement_date) where is_current`。
- 敏感字段：sellerName 原值含员工姓名，只存在 payload_json；API 和页面只出 store_code / 系统店铺名。
- **整段替换**：一次同步覆盖一个日期窗口、全部店铺。全部页成功且行数等于 `data.page.total` 后，在一个事务里：旧行中 is_current = true 且 business_date 在窗口内的改为 false 并写 superseded_by_run_id，新行置 true。任一页失败或行数不符，整批标记 failed，旧数据不动，新行保持 is_current = false。
- **同账号单批次**：同一 source_account_ref 同时只允许一个本同步批次运行。实现：批次开始时检查 `gov_integration_sync_runs` 中该同步项、该账号无其他 running 记录，并取 PostgreSQL session 级 advisory lock（键 = 同步项键 + source_account_ref，批次结束释放）；任一不满足则本次标记 failed、错误码 `SYNC_WFS_FLOW_CONCURRENT_RUN`，不发任何请求（运行状态枚举没有 skipped，不新增枚举）。另外，现有执行器的接口级锁（`gov_integration_sync_locks`）和 `uq_gov_integration_sync_runs_running` 仍然生效。
- 保留：被替换的旧行保留 30 天供核对；清理任务本期不做，只在文档写明。
- 下游约定：每次同步行 id 都会换新，旧 id 的 is_current 变为 false；结算利润须过滤 is_current = true 后再按 settlement_date 取数。

### 7.2 店铺对照

- 对照来源：已有表 `dim_lingxing_stores`（`app/modules/data_pages/models.py` L39，字段 store_id、store_name、sid、platform_code）。
- 规则（按顺序）：① 记录 `sid` 非空且在 dim 中唯一命中 sid → 取其 store_id；② 否则按 Walmart 平台、`store_name` 前 6 位 = store_code 唯一命中 → 取其 store_id；③ 都不唯一命中 → store_id 为空、store_mapping_status = 'unmapped'。
- 对不上的照样入库，不丢行；只对拥有全店铺权限者可见，页面标「店铺未对照」。
- 对照在入库时做；dim 更新后，下一次同步自然重算（窗口内整段替换）。

### 7.3 同步任务（PR 1）

- 在 `app/modules/integration_sync/` 登记同步项（参照 `pmc_domestic_catalog.py`），handler 参照 `handlers/lingxing_pmc_domestic_sync.py`。
- 请求参数见 §6.1：dateType = 0、不传 businessType、不传 sidList、length = 200、按 dateLocal 升序。每页前等 1.25 s，超时 60 s，重试 3 次，最多 1000 页兜底；每页记 `ods_api_raw_request_refs`。
- **默认关闭**：is_enabled = false、schedule_enabled = false。迁移和代码上线不会自动调领星。
- 开启后建议：每天一次，滚动窗口 = 最近 60 天（覆盖领星回改）；首次补历史 = 2026-05-01 起，按月分窗口跑。
- 首次开启、补历史数据，须 rocky 书面同意。PR 1 测试只用合成 fixture。
- 不在 API 路由里实时拉领星。

### 7.4 索赔计算（PR 2，读时计算，不建汇总表）

只用 is_current = true 的行。按 (store_code, msku) 汇总：

```text
丢失 lost      = Σ(−quantity)  where business_type in (CCA, ADJ) and quantity < 0
损坏 damaged   = Σ(−quantity)  where business_type = D16
收货差错 recv  = Σ(−quantity)  where business_type = ADX
供应商短少     = Σ(−quantity)  where business_type = VDG
找回 found     = Σ(quantity)   where business_type in (CCA, ADJ, VTM) and quantity > 0
应赔 should    = lost + damaged + recv + vendor − found
```

- 「已赔」「差额」「预估金额」返回 null，页面显示「未接入」。
- 商品名、ItemID：按 (store_id, msku) 关联现有 Listing 数据，PR 2 开工前确认具体表。
- 成本列只给持有 field:warehouse:inventory-claim:cost 的人。

### 7.5 索赔案件与两步审核（PR 2）

- 案件表：新建 `ops_wfs_inventory_claim_cases`（rocky 已定）。状态值与 `ops_wfs_fee_anomaly_cases` 一致：pending_confirm / following / archive_pending / archived / recovered；另有 claim_kind、应赔件数快照、Walmart Case 号、跟进记录、version（乐观锁）。
- 状态流转：待确认 → 跟进中 → 待初审 → 待终审 → 已追回 / 已归档；驳回回到跟进中。
- 两步审核：在 `approvals/generic.py` 新增 kind `wfs_inventory_claim`，`app_approval_rules` 插入 required_steps = 2、不允许批量；按 §5 增加每步权限校验。审批只记录决定，不自动执行业务动作。

### 7.6 API Contract（PR 2）

```text
读接口
GET  /api/warehouse/inventory-claims/summary
GET  /api/warehouse/inventory-claims                          筛选 store_code、claim_kind、status、keyword；分页
GET  /api/warehouse/inventory-claims/{store_code}/{msku}/movements

写接口（均须 Header Idempotency-Key；请求体带 expected_version，新建除外）
POST /api/warehouse/inventory-claims/cases                     开案
POST /api/warehouse/inventory-claims/cases/{id}/follow-ups      跟进
POST /api/warehouse/inventory-claims/cases/{id}/submit-review   提交审核
POST /api/warehouse/inventory-claims/cases/{id}/mark-recovered  确认追回
审核走 /api/approvals/{id}/decision（kind = wfs_inventory_claim，带 expected_version）

envelope：{ success, data, error, meta, request_id }
  error = { code, message, details } 或 null
  meta  = { source: "lingxing_wfs_cost_valuation",
            source_tables: ["ods_lingxing_wfs_cost_valuation_flow", "ops_wfs_inventory_claim_cases"],
            data_as_of: 最近一次成功同步结束时间（从未同步为 null） }

错误码
  401 UNAUTHENTICATED
  403 FORBIDDEN
  404 NOT_FOUND                       商品或案件不存在
  409 STALE_VERSION                   expected_version 与当前版本不一致
  409 IDEMPOTENCY_KEY_REUSED          同一 Idempotency-Key 请求体不同
  409 CLAIM_CASE_ALREADY_OPEN         该商品已有未结案件
  409 INVALID_STATUS_TRANSITION       当前状态不允许该操作
  409 REVIEWER_CONFLICT               审批人与申请人或上一步审批人相同
  422 VALIDATION_ERROR
  422 STORE_UNMAPPED                  店铺未对照的商品不能开案
```

## 8. UI Requirements（PR 3）

```text
layout: 沿用 5174 已有页面（PageShell + FinanceBoardFrame + 7 张统计卡 + ProTable + 详情抽屉）
table columns: 店铺编码、ItemID / MSKU、商品、类型、丢失、损坏、收货差错、找回、应赔、已赔（未接入）、差额（未接入）、最近异动日、状态
filters: 店铺、类型、状态、关键词
actions: 按权限显示开案、跟进、提交审核、初审、终审、确认追回；导入 / 导出 / 批量开 Case 保持禁用
抽屉: 领星 WFS 库存流水明细；审核步骤条只显示角色名
店铺未对照: 行内标「店铺未对照」
empty state: 「没有需要索赔的商品」
数据新鲜度: 页头显示「流水更新至 YYYY-MM-DD」；未同步时提示「流水尚未同步」
helpUrl: 新增 SOP 帮助页
```

## 9. SOP / API Docs

- [ ] PR 1：契约快照与三处登记（§6.1）；ODS 表说明（列、身份键、is_current 规则、下游约定）
- [ ] PR 2：Markdown API doc、OpenAPI metadata
- [ ] PR 3：SOP 帮助页、PageShell 帮助入口

## 10. Implementation Plan 与 PR 拆分

代码 AI 只在本地写代码，不做 git 写操作、不连服务器、不调真实接口；提 PR 由部署 AI 做，合并上线由刘云龙做；不推 main、不合并。

```text
PR 1 数据底座（本期）
  - 契约四处登记：contracts/inventory-lx-8437ad0bcb9e.md、API_CONTRACT_SOURCE_MAP、API_CONTRACT_INVENTORY、DATA_INTERFACE_REGISTRY
  - 数据源决策文件
  - Alembic 迁移：ods_lingxing_wfs_cost_valuation_flow（暂定 20261103_0073_wfs_cost_valuation_flow；
    与结算利润 V2 的 20261103_0072 谁后合并谁改 down_revision；结算利润的表不对本表建外键）
  - 同步 handler + 登记（默认关闭）+ 店铺对照 + 整段替换 + 同账号单批次锁
  - 测试（合成 fixture，不含真实订单号、金额）：
      分页拉全；行数与 total 不符时整批失败、旧数据不动；
      重复流水号可入库；整段替换后窗口内只有新批次 is_current；
      同账号第二个批次被拒（failed / SYNC_WFS_FLOW_CONCURRENT_RUN）且不发请求；
      店铺对照三种情况（sid 命中 / 店铺编码命中 / 未对照）；
      默认关闭时调度不触发
  - 下游：结算利润 V2 读本表 is_current = true，由其 PRP 负责
PR 2 索赔接口 + 案件 + 两步审核（暂缓，PR 1 合入后再排）
  - ops_wfs_inventory_claim_cases 迁移；approvals kind 与每步权限校验；权限点；读写接口；审计
PR 3 前端（暂缓，随 PR 2）
  - 依赖 FinanceBoardFrame 已合入 main
```

上线后同步仍是关闭状态；rocky 书面同意后由部署 AI 开启并补历史数据。

## 11. Validation Gates

```bash
# backend
cd backend
uv run ruff check .
uv run pytest
uv run alembic check

# frontend（PR 3）
cd frontend
npm run lint
npx tsc --noEmit -p tsconfig.app.json
npm run test
npm run build
npm run test:e2e
```

## 12. Forbidden Actions

```text
不调用真实领星 / Walmart / 飞书接口，只用合成 fixture（开启同步须 rocky 书面同意）
不碰服务器，不连接生产数据库，不读 .env / .secrets / 凭证，不打印 env / token / 签名链接
不推 main，不合并；代码 AI 不做 git 写操作
测试和文档里不写真实订单号和金额
不修改 old-system；不改 8088 Demo
local-fin-data、凭证图片、飞书数据不进 Git
```

## 13. Rollback Plan

- 同步：同步项 is_enabled 置 false 即停。
- 数据：先停同步；本表被库存索赔和结算利润读，回滚前须确认结算利润读侧已停用或可接受空数据；Alembic downgrade 删除本表。
- 案件与审批（PR 2）：停用 `wfs_inventory_claim` 审批规则；downgrade 删除案件表。
- 前端：导航项改 hidden。

## 14. Acceptance Checklist（PR 1）

- [ ] 契约四处登记完成，全仓库只有一个 `LX-8437AD0BCB9E`
- [ ] 迁移通过 `alembic check`
- [ ] 同步默认关闭，测试证明不会自动调领星
- [ ] 重复流水号能入库，整段替换正确，失败不破坏旧数据
- [ ] 同账号单批次锁有测试
- [ ] 店铺对照三种情况有测试，未对照行照样入库
- [ ] 测试 fixture 不含真实订单号、金额
- [ ] CODEX_HANDOFF 更新

## 15. 负责人决定与待探测事项

### 15.1 已定（rocky，2026-11-03）

1. 新建 `ods_lingxing_wfs_cost_valuation_flow`，归本 PRP 的 PR 1；同一接口全仓库只此一表、一份契约登记；结算利润读 is_current = true。
2. 案件表：新建独立的 `ops_wfs_inventory_claim_cases`。
3. 「已赔」「差额」显示「未接入」；当前只做 PR 1。

### 15.2 待探测（不阻塞 PR 1 写代码，首次开启同步前须用一次授权探测确认）

1. endDate 是否含当天；dateLocal、date1 的时区。
2. 金额币种（决定 currency_code 取值）。
3. 不传 businessType 时返回的类型全集，与 PMC 传 6 个编码时相比是否多出类型；全量下流水号唯一性复核。
4. 记录里 `sid` 何时有值。
5. 同步频率和窗口：建议每天一次、滚动 60 天。

建议首次开启时先用 1 天窗口探测，需 rocky 书面同意。
