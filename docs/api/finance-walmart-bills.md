# 财务 · 沃尔玛账单（领星 statement/list）

沃尔玛账单是回款对账、现金利润、结算利润三个板块共用的底数，只由同步任务写入，只拉一次。
PRP：`PRPs/finance-walmart-settlement-sync-v1.md`；数据源决策：`docs/data-sources/decisions/finance-walmart-settlement-sync-decision.md`。

## 1. 接口

统一 envelope（`success / data / error / meta / request_id`）。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/finance/walmart-bills/periods` | `page:finance:settlement-reconciliation:view` | 每期汇总（店铺 × 一期），新到旧，最多 2000 行 |
| GET | `/api/finance/walmart-bills/sync` | `page:finance:settlement-reconciliation:view` | 最近一次同步状态 |
| POST | `/api/finance/walmart-bills/sync` | `action:finance:settlement-reconciliation:sync` | 手动同步：在任务中心建一条运行记录交给队列；已经有一次在跑（手动、定时或回填）就直接返回那一次 |

`GET /periods` 查询参数：`store_id`（数字）、`report_date_from`、`report_date_to`（账单日，`YYYY-MM-DD`）。

每期字段：`store_id`、`store_name`、`report_key`、`report_date`（账单日）、`period_start_date` / `period_end_date`（账期；领星没给就用最早 / 最晚交易日期）、`currency_code`、`line_count`（有效明细数）、`excluded_line_count`（被删除或重拉后消失的明细数）、`amount_sum`（有效明细合计）、`total_payable`（领星账单总额，目前都是空）、`payable_amount`（应付金额 = 账单总额，没有就用明细合计）、`amounts_by_type`（按金额类型小计，字符串金额）、`status`（`normal` / `not_payable` 本期不打款 / `voided` 作废）、`refreshed_at`。不返回订单号、买家信息。

同步状态字段：`run_id`、`status`（`never` / `queued` / `running` / `succeeded` / `failed`）、`trigger_type`（`manual` / `schedule` / `backfill` / `retry`）、`started_at`、`finished_at`、`error_code`、`records_seen`、`records_written`、`last_success_at`。

错误码：

| HTTP | code | 含义 |
|---|---|---|
| 401 / 403 | 通用 | 未登录 / 没有权限 |
| 409 | `WALMART_BILL_SYNC_NOT_CONFIGURED` | 同步任务还没打开（上线后由部署 AI 按票据打开） |
| 503 | `WALMART_BILL_SYNC_UNAVAILABLE` | 任务队列暂时不可用 |
| 422 | `WALMART_BILL_RANGE_INVALID` | 开始日期晚于结束日期 |

## 2. 数据表

| 表 | 一行 | 写入 |
|---|---|---|
| `ods_api_raw_blobs` / `ods_api_raw_request_refs` | 领星每页原始响应 / 每次请求 | 同步任务，先于解析 |
| `ods_lingxing_walmart_bill_lines` | 领星一条账单明细 | 同步任务；行身份 `line_key` = 组合键 + 同组合键出现序号；收货地址不入 |
| `mart_walmart_bill_periods` | 一个店的一期账单（reportKey） | 每店拉完后重算涉及的各期 |

## 3. 同步规则

- 接口：领星 `POST /basicOpen/multiplatformFinance/walmart/bill/statement/list`；请求体只用 `offset / length（≤200）/ sids（一次一个店）/ startDate / endDate`。
- interface_key `walmartBillStatementList`，handler `lingxing.walmart_bill_statement.v1`；默认关闭。
- 时间段：手动、定时 = 最近 35 天（上海日期）；回填 = 任务给定时间段，最早 2026-03-01；按自然月切，超过翻页上限对半切。`startDate / endDate` 按交易日期筛。
- 完整性：总条数中途变化、拉完行数不足、返回的行交易日期不在请求时间段或店铺对不上 → 整店失败。
- 整店回滚：一个店这次的明细写入、missing 标记、期汇总重算、分页记录和原始响应都在一个保存点里，店拉完才一起提交；店失败时全部回滚，明细表和期汇总保持这次同步前的样子，只补一条失败的分页记录（带错误码，有响应的话连同出错那一页的原始响应）。心跳用独立 session 续锁，不提交业务事务；店内若有人提交业务 session 会被拒绝（`SYNC_WALMART_BILL_COMMIT_INSIDE_STORE`），按单店失败整店回滚；续锁失败（锁丢失）整个任务中止，不再拉下一个店。
- 某段领星返回 0 条、而库里这段日期原来有有效明细 → 不当成「全被删」，整店失败（`SYNC_WALMART_BILL_EMPTY_UNEXPECTED`），什么都不标。
- 重拉后消失的明细标 `missing_since`，不删；再出现就清掉。领星改了金额 = 旧行消失 + 新行插入。被标 missing 的明细所在的期一并重算：一期的明细全没了 → `voided`，金额归 0；同一批明细换了 reportKey 重新出现 → 旧期 `voided`、新期按新明细算，不重复。
- `totalSum`（领星每段的合计，对象，含 amount / totalPayable / totalCount 等）已确认是整段合计，但 amount 与明细金额之和是否一致还没用有明细的样本核实，暂不做金额对平校验；核实后再加 `SYNC_WALMART_BILL_SUM_MISMATCH`。
- 长账单往前补：某期最早一笔落在窗口开头 7 天内就往前补 31 天，最多 12 次。
- 一个店失败不影响其他店；有店失败整次记失败（`SYNC_WALMART_BILL_STORE_PARTIAL` / `SYNC_WALMART_BILL_ALL_STORES_FAILED`）。
- 定时：每周三上海 03:00（cron `0 19 * * 2`，UTC）。

同步错误码（任务中心可见）：`SYNC_WALMART_BILL_RUNTIME_NOT_AUTHORIZED`、`SYNC_WALMART_BILL_EXECUTION_NOT_AUTHORIZED`、`SYNC_WALMART_BILL_GOVERNANCE_DISABLED`、`SYNC_WALMART_BILL_NO_STORES`、`SYNC_WALMART_BILL_PAGINATION_INVALID`、`SYNC_WALMART_BILL_WINDOW_INVALID`、`SYNC_WALMART_BILL_REQUEST_FAILED`、`SYNC_WALMART_BILL_RESPONSE_FAILED`、`SYNC_WALMART_BILL_TOTAL_CHANGED`、`SYNC_WALMART_BILL_INCOMPLETE`、`SYNC_WALMART_BILL_DAY_PAGE_LIMIT`、`SYNC_WALMART_BILL_EMPTY_UNEXPECTED`（某段返回 0 条但库里原来有）、`SYNC_WALMART_BILL_STORE_FAILED`（店失败但不是上面任何一种，如数据库出错）、`SYNC_WALMART_BILL_COMMIT_INSIDE_STORE`（店内提交业务事务，被拒绝）、`SYNC_WALMART_BILL_STORE_MISMATCH`、`SYNC_WALMART_BILL_DATE_OUT_OF_WINDOW`、`SYNC_WALMART_BILL_INVALID_ROW`、`SYNC_WALMART_BILL_INVALID_DATE`、`SYNC_WALMART_BILL_INVALID_AMOUNT`。

## 4. 上线步骤（负责人授权后由部署 AI 按票据执行）

1. 登记：`WALMART_BILL_GOVERNANCE_BOOTSTRAP_AUTHORIZED=true WALMART_BILL_SOURCE_ACCOUNT_REF=<账号引用> uv run python scripts/bootstrap_walmart_bill_governance.py`（全部关闭）。
2. 只开手动：`WALMART_BILL_SYNC_ENABLE_AUTHORIZED=true WALMART_BILL_SOURCE_ACCOUNT_REF=<账号引用> uv run python scripts/enable_walmart_bill_sync.py`（手动同步可用，定时不开）。
3. 首次手动同步当作受控探测：确认鉴权、按店筛选、条数与本地归档一致（只回报是否一致）。
4. 开定时：探测通过后，同上命令再加 `WALMART_BILL_SYNC_SCHEDULE_AUTHORIZED=true` 重跑一次（打开每周三定时）。
5. 回填：任务中心对该接口发起回填，2026-03-01 至今。
6. 分配权限：给有关角色分配 `action:finance:settlement-reconciliation:sync`。

回滚：任务中心关掉 `is_enabled` 立即停；迁移 down 在明细表有数据、或动作权限已分给角色时拒绝。
