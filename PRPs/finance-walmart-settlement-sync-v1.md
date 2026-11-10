# PRP: 财务 · 沃尔玛账单同步（领星 statement/list）V1

- Status: Ready for review（2026-11-08 按 Rocky 新口径改写；代码与本 PRP 同一 PR 审核，Rocky 2026-11-08 23:34 同意）
- Owner Approval Required: Yes（财务板块 PRP / PR 负责人：Rocky；合并、上线：刘云龙）
- Implementation authorization state: 本 PR 内实现；生产开启同步开关、定时、历史回填三项另需书面授权
- Main execution role: Backend Engineer（Integration Sync handler + migration + 读取 / 手动同步接口；本 PR 无前端页面）
- Source Decision: `docs/data-sources/decisions/finance-walmart-settlement-sync-decision.md`
- Related: `PRPs/finance-cashflow-statement-import-v1.md`（日记账，到账侧）；回款对账页面另提 PR-2
- Branch: `fin/walmart-bill-sync`
- Production execution authorized: No
- 口径来源：Rocky 2026-10-31 22:36 / 22:44（账单直拉领星、历史从 2026-03-01）；2026-11-08 23:09 ~ 23:34（统一叫「沃尔玛账单」、只用一个接口、两层表、每周拉 + 手动同步、有权限的人都能点）

## 0. 和 10-31 版的区别（2026-11-08）

| 项 | 10-31 版 | 本版 |
|---|---|---|
| 接口 | 领星 statement/list + payout/list 两个 | **只用 statement/list**；payout/list 不登记、不建表 |
| 叫法 | 结算账单 / 结算单 | 统一叫「沃尔玛账单」 |
| 表 | ODS 明细、ODS 回款、FACT、MART 四张 | **明细表 + 每期汇总表两张**（原始响应仍进系统共用的原始层） |
| 应付金额 | payout 的 totalPayable | 领星「账单总额」目前全是空的 → **每期应付 = 有效明细合计**；以后领星给了一致的总额就用总额 |
| 频率 | 每周三 03:00 | 同（每周三上海 03:00），**另加「手动同步」接口**（回款对账页面的按钮，PR-2 接上） |
| 页面 | 无 | 本 PR 仍无页面；新增只读接口和手动同步接口给 PR-2 用 |

## 1. Goal

把领星「沃尔玛账单」（Walmart 结算报告明细）按店同步进新系统，供回款对账、现金利润、结算利润三个板块共用，只拉一次。完成态：负责人授权后，一次回填 2026-03-01 起全部账单，之后每周三自动重拉最近 35 天，财务也可以在回款对账页面点「手动同步」；任务中心能看到每次运行；`mart_walmart_bill_periods` 给出每个店每一期的应付金额。

## 2. Why

- 沃尔玛账单是回款对账、结算利润、现金利润的底数；现在靠 Rocky 逐次批单、部署 AI 手跑，不可持续。
- 领星数据已与 Walmart 原始结算单逐期核平，直接拉领星，不走 Walmart 官方 API。

## 3. Scope

### In scope

- [x] 领星客户端登记 `POST /basicOpen/multiplatformFinance/walmart/bill/statement/list`（契约 `LX-727003CFF7B4`）：请求体只允许 `offset / length / sids / startDate / endDate`，每页最多 200，一次只查一个店。
- [x] catalog：interface_key `walmartBillStatementList`，handler `lingxing.walmart_bill_statement.v1`，默认 `outbound_enabled=false`、`is_enabled=false`、`schedule_enabled=false`；bootstrap / enable 两个脚本（都要显式授权环境变量）。
- [x] handler（见 §10 规则）：按店、按交易日期时间段、offset 翻页；原始响应先落 `ods_api_raw_blobs` / `ods_api_raw_request_refs`；解析写明细表；每店拉完重算该店涉及的各期汇总。
- [x] 迁移 `20261108_0085_finance_walmart_bills`：`ods_lingxing_walmart_bill_lines`、`mart_walmart_bill_periods`；登记动作权限 `action:finance:settlement-reconciliation:sync`（页面权限 `page:finance:settlement-reconciliation:view` 已有则不动）。
- [x] 接口：`GET /api/finance/walmart-bills/periods`、`GET /api/finance/walmart-bills/sync`、`POST /api/finance/walmart-bills/sync`。
- [x] 测试：合成数据；解析、翻页、条数变化、时间段外的行、对半切、往前补拉、重拉后消失标记、回填时间段、开关、定时、手动同步、权限；迁移头。
- [x] 文档：本 PRP、数据源决策、`docs/api/finance-walmart-bills.md`、`DATA_INTERFACE_REGISTRY.md`、`BACKEND_MODULE_CATALOG.md`。

### Out of scope

- [ ] 回款对账页面、店铺 ↔ 收款账户匹配表、和日记账自动配对、初审终审（PR-2）。
- [ ] 结算利润 / 现金利润的计算（之后改读本层）。
- [ ] 领星 payout/list、Walmart 官方 API。
- [ ] 10-26 本地已拉的 JSONL 导入（只用来核对字段和总数，不进仓库）。
- [ ] 生产开启 outbound / schedule、回填执行、部署（各需单独授权）。

## 4. Navigation / Page

本 PR 无新页面。任务中心沿用既有页面（`/data-center/task-center`）。回款对账页面（`/finance/settlement-reconciliation`）在 PR-2。

## 5. Permissions

```text
page permissionKey: page:finance:settlement-reconciliation:view（看每期汇总、看同步状态）
action permissionKeys: action:finance:settlement-reconciliation:sync（手动同步；Rocky：有权限的人都能点，由角色分配）
task centre: 既有 page:data-center:task-center:view / action:data-center:task-center:execute（回填走任务中心）
data scope resource: source_account_ref（同步治理既有边界）
field permissions: 读取接口不返回订单号、买家信息；收货地址字段不进业务层
high-risk actions: 开启 outbound / schedule、回填 —— 负责人授权后由部署 AI 按票据执行
```

## 6. Data Source

```text
data source decision file: docs/data-sources/decisions/finance-walmart-settlement-sync-decision.md
dataset classifications: RAW REBUILD_SYNC（既有原始层）；ODS 明细 REBUILD_SYNC；MART 每期汇总 REBUILD_SYNC
contains NEED_OWNER_DECISION: no
owner approval status: Rocky 2026-11-08 已定口径；生产开启另批
new PostgreSQL tables: ods_lingxing_walmart_bill_lines, mart_walmart_bill_periods
sensitive or critical domains: 财务 / 结算（订单号只在明细表；收货地址不进业务层）
```

## 7. API Contract

见 `docs/api/finance-walmart-bills.md`。

```text
GET  /api/finance/walmart-bills/periods?store_id&report_date_from&report_date_to   每期汇总，新到旧，最多 2000 行
GET  /api/finance/walmart-bills/sync                                               最近一次同步状态
POST /api/finance/walmart-bills/sync                                               手动同步（202；已在跑就返回那一次）
errors: 401 / 403；409 WALMART_BILL_SYNC_NOT_CONFIGURED；503 WALMART_BILL_SYNC_UNAVAILABLE；422 WALMART_BILL_RANGE_INVALID
```

## 8. UI Requirements

本 PR 无。PR-2 回款对账页面：顶部显示「最后同步时间」+「手动同步」按钮（无动作权限的人看不到按钮）。

## 9. SOP / API Docs

- [x] Markdown API doc：`docs/api/finance-walmart-bills.md`（含同步规则和上线步骤）
- [ ] PageShell help：PR-2

## 10. 同步规则（实现要点）

1. 店铺：系统里的领星沃尔玛店铺（`dim_lingxing_stores`，与 WFS 结算同一个发现函数），一店一次请求，`sids` 只放这一个店。
2. 时间段：手动 / 定时 = 最近 35 天（上海日期，含当天）；回填 = 任务里给的时间段，最早到 2026-03-01。按自然月切开；某段总条数超过翻页上限（默认 500 页 × 200 条）就对半切再拉。
3. 筛选口径：领星 `startDate / endDate` 按**交易日期**（`transactionPostedTimestamp`）筛 —— 用 10-26 本地数据核对过（每月请求的行数 = 按交易日期分月的行数）。程序再校验：返回的任何一行交易日期不在请求的时间段里，或店铺对不上，整店失败、已有数据不动（说明领星口径变了）。
4. 完整性：翻页过程中总条数变了 → 整店失败；拉完行数对不上总条数 → 整店失败。同一时间段里同一个领星行号出现两次且内容不同 → 整店失败。
5. 写入：按（店铺, 领星行号）去重更新；金额按字符串转 Decimal，`numeric(18,4)`；收货城市 / 州 / 邮编 / 国家不落业务层；其余字段原样放 `extra_fields` 给结算利润用。
6. 重拉后消失：某个时间段完整拉完后，这段时间里以前有、这次没再出现的明细标 `missing_since`（不删），汇总时不算；以后又出现就清掉。
7. 往前补拉：领星只在账单生成后才给出明细，一期账单可能横跨 35 天以上（几期合并打款）。某期账单最早一笔明细落在窗口开头 7 天内，就往前补拉 31 天；补到这期不再靠前为止，最多 12 次，最早到 2026-03-01。
8. 每期汇总（一期 = 一个 reportKey = 一次打款）：有效明细 = 没删除（deleteFlag=0）且没消失；应付金额 = 领星账单总额（全期一致地给了一个值时）否则 = 有效明细合计；状态：没有有效明细 = `voided`（作废），应付 ≤ 0 = `not_payable`（本期不打款），其余 `normal`；同时给出按金额类型的小计、账期起止（领星没给就用最早 / 最晚交易日期）。
9. 失败隔离：一个店失败不影响其他店；有店失败整次任务记为失败（`SYNC_WALMART_BILL_STORE_PARTIAL` / `SYNC_WALMART_BILL_ALL_STORES_FAILED`），任务中心能看到。

## 11. Implementation Plan

```text
Task 1: 客户端登记接口 + catalog / bootstrap / enable（默认关）
Task 2: 迁移两张表 + 动作权限；model registry；迁移头测试
Task 3: handler（翻页、校验、写入、消失标记、对半切、往前补拉、每期汇总）
Task 4: 读取 / 手动同步接口 + 权限
Task 5: 测试、文档、registry
```

## 12. Validation Gates

```bash
cd backend
uv run ruff format --check . && uv run ruff check .
APP_ENV=test TEST_DATABASE_URL=... uv run alembic upgrade head
APP_ENV=test TEST_DATABASE_URL=... uv run pytest tests/modules/walmart_bills tests/db/test_alembic_scaffold.py tests/modules/fx_rates tests/modules/finance_cashflow tests/core -q
uv run alembic check
uv run python -c "import app.main"
```

授权回填后（不进仓库）：用 10-26 本地数据按店、按期核对行数和每期合计。

## 13. Forbidden Actions

```text
不连接生产数据库；不修改 .env；不调用真实领星接口；不部署；不重启服务
不改其他同步接口的 handler / 配置；不翻转任何 is_enabled / outbound_enabled / schedule_enabled 默认值
不把真实 JSON、订单号、金额明细、店铺名写进测试 / 文档 / PR
```

## 14. Rollback Plan

- 运行：`is_enabled=false` 立即停。
- 代码：revert PR。
- 数据库：迁移 down —— 明细表有数据时拒绝；动作权限已分配给角色时拒绝（先收回权限）。
- 每期汇总可以随时由明细表重算。

## 15. 上线步骤（负责人授权后由部署 AI 按票据执行）

1. 合并上线后跑 `scripts/bootstrap_walmart_bill_governance.py`（登记，全关）。
2. 首次手动同步 = 受控探测：确认生产环境对这个接口的鉴权、`sids` 用店铺编号可用、条数与 10-26 本地数据一致。
3. 跑 `scripts/enable_walmart_bill_sync.py`（打开同步 + 每周三定时）。
4. 任务中心发起回填：2026-10-01 至今（Rocky 2026-11-10 改；更早的以后要用再补），按月分批。
5. 用 10-26 本地数据按店按期核对（只回报是否一致）。

## 16. 回款对账：到账配对 + 审核（PR-2，Rocky 2026-11-10 批准，和本 PR 一起交审）

口径来源：Rocky 2026-11-10 17:22 / 17:26（自动配对、合并打款、日记账联动、状态、审核、跟进、收款账户映射、页面全部同意；今天整体上线）。接口与数据表见 `docs/api/finance-payout-recon.md`。

- **范围**：只看账单日 2026-10-01 起的期次；到账只读日记账流水（`std_finance_cashflow_lines`），不导新流水。
- **自动配对**：到账在账单日后 0–7 天、到账账户 = 这家店账单日当天生效的收款账户、收款账户识别（填了才比）出现在付款方 / 摘要 / 备注、币种一致、金额差 ≤ 0.01。
- **合并打款**：一笔到账 = 同一收款账户下 2–4 期应付相加，也自动配。能配出多种结果、或一期被几笔到账争抢，不自动配，留给财务手动配（手动配允许金额不符，显示打款异常）。
- **日记账联动**：配上后这笔流水备注写「平台回款 · 店铺 · 账单日」，分类为空才填 `T03 平台回款`；走日记账同一套事件和版本号。撤销配对时恢复（备注被人改过不动）。
- **状态**：未到账单日 / 等到账（7 天内）/ 已打款 / 金额不符 / 未到账（过 7 天）/ 不需打款 / 账单作废；后三种中的金额不符、未到账、作废 = 打款异常。
- **审核**：待初审 → 待终审 → 已终审；终审驳回必须写原因，回到待初审。只能审已配上到账的期次；已初审 / 终审的不能改配对。支持批量。
- **权限**：看 = 回款对账页面权限；初审 + 自动 / 手动配对 + 撤销 = `action:finance:settlement-reconciliation:review1`；终审 + 收款账户映射 = `…:review2`；跟进 = `…:follow`。
- **跟进**：打款异常每期可追加跟进（内容必填，Case 编号、下次跟进日期），保留全部历史。
- **收款账户映射**：店铺 → 入账账户 + 收款账户识别 + 生效日期；换账户写原因、旧记录自动截止。真实数据不进仓库，上线后由部署 AI 录入生产库。
- **页面**：照 5174 预览：店铺列固定左侧、账单日多选（含全选）、列配置、导出 Excel、勾选、合计行、批量初审 / 终审、映射抽屉、期次详情（配对、审核、跟进记录）。
- **数据表**：迁移 `20261110_0086_finance_payout_recon` 新建 4 张表（映射、配对、审核记录、跟进记录）+ 3 个动作权限；down 在有数据或权限已分配时拒绝。
- **验证**：纯规则单测（窗口、账户、识别、容差、合并、争抢、状态、阶段）；接口权限测试；隔离库测试（自动 / 合并 / 手动配对、日记账联动与撤销恢复、审核流、换账户、跟进）。
- **上线追加步骤**（接在第 15 节后）：6. 部署 AI 按 Rocky 给的对照把各店收款账户录入 `cfg_walmart_payout_accounts`（只在生产库）；7. 给财务角色分配 review1 / review2 / follow；8. 页面点「自动配对」，回报配上的期数和打款异常期数（只报数量）。
