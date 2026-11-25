# 财务 · 回款对账（到账配对 + 审核）

回款对账 = 沃尔玛每店每期应付（`mart_walmart_bill_periods`，见 `finance-walmart-bills.md`）对上日记账到账（`std_finance_cashflow_lines`），再初审、终审。
口径：Rocky 2026-11-10 批准；PRP：`PRPs/finance-walmart-settlement-sync-v1.md` 第 16 节。只看 2026-10-01 起的账单。

## 1. 规则

- **应付口径（0097，Rocky 2026-11-26）**：应付以**沃尔玛对账报表**（`GET /v3/report/reconreport/reconFileJson` 第一页里 `Transaction Type = PaymentSummary` 那一行的 `Total Payable`）为准；领星账单合计只作参考。原因：领星账单只含订单级交易，不含保证金扣留 / 释放（`Release Reserve` 等）这类账户级交易，碰上就对不上实际打款。沃尔玛的对账日期和领星的账单日一一对应（按 店铺 × `report_date` 对上）。`mart_walmart_bill_periods` 加列：`walmart_total_payable`、`walmart_diff`（沃尔玛 − 领星）、`payable_source`（`walmart` / `lingxing`）、`walmart_period_start_date` / `walmart_period_end_date` / `walmart_posted_date`、`walmart_account_rows`（第一页里没有订单号 / PO / GTIN 的账户级交易，只留类型、描述、金额、日期）、`walmart_account_rows_complete`（报表不止一页时为假，页面提示「只看了第一页」）、`walmart_synced_at`。每页原样先落 RAW 表 `raw_walmart_recon_report_pages`（店铺 × 对账日期 × 页偏移，重拉覆盖）再解析。有沃尔玛数据的期 `payable_amount` = 沃尔玛打款额，领星重算期汇总时保留这几列、只更新参考值与差额；没有的期照旧用领星。自动配对、状态、合计都读 `payable_amount`，不改。
- **拉取**：Celery 任务 `walmart_bills.recon_payout_sync`，走 V4 通用通道 `call_walmart()`，只读 GET，代码里只允许 `availableReconFiles` 与 `reconFileJson` 两个路径；每店 1 次可用日期 + 每个缺的期 1 次第一页（100 行，不翻页）；**只拉账单日 ≥ 2026-11-01 的期**（Rocky 2026-11-26：10 月及以前已人工对完，不拉、不改应付），每店最多 40 期；沃尔玛有、领星还没有这期的先跳过下次再补。每期一个保存点：这一期拉不到 / 没有 `PaymentSummary`（不在第一页给 `WALMART_RECON_SUMMARY_NOT_ON_FIRST_PAGE`）/ 账期起止或币种和领星对不上 / 同店账单日重复 → 记错误码跳过，其余照写；每店成功后单独提交；可用日期拉不到或 429 限流 → 该店停止、整店回滚、其他店照常。**已配对或审核过的期**应付变化 > 0.01：照改应付，追加一条 `reset` 审核事件（原因写明来自沃尔玛打款额）退回待初审，已配对的到账差额会显示为金额不符，任务结果列出这些期。开关环境变量 `<项目前缀>_WALMART_RECON_PAYOUT_ENABLED=1`（名字见 `backend/app/modules/walmart_bills/recon_payout_sync.py` 的 `ENABLED_ENV`；默认关，打开要业务负责人授权）：打开后生产 Beat 每周三上海 04:30 跑一次（领星账单同步之后），页面「拉沃尔玛打款额」按钮（`POST /api/finance/walmart-bills/recon-payout-sync`，手动同步权限）也只投递这个任务；没打开返回 409 `WALMART_RECON_PAYOUT_DISABLED`。
- **自动配对**：到账日期在账单日之后 0–7 天；到账账户是这家店（账单日当天生效）的收款账户；收款账户识别（派安盈付款邮箱 / PingPong 公司名）填了就要出现在付款方、摘要或备注里；币种一致；金额差 ≤ 0.01。
- **合并打款**：一笔到账 = 同一收款账户下 2–4 期应付之和（差 ≤ 0.01），也自动配给这几期。
- 一笔到账能配出不止一种结果，或一期被几笔到账争抢 → 不自动配，留给财务手动配（`POST /matches`，金额可以不等，显示为金额不符；账单日早于 2026-10-01 的期次 422）。
- 日记账里已另有用途的流水不进自动配对：已剔除、已内部配对、已拆分、已挂审批单、已人工分到 `T03` 以外的类别；没人工分类但日记账规则分出 `T03` 以外类别的（提示带「（规则）」）也不自动配。`GET /lines` 给这些流水带 `journal_hint`（「已剔除」「已内部配对」「已拆分」「已挂审批单」「已分类 Xxx」），仍可手动配。
- 配上的到账流水后来在日记账里作废（整批作废）：配对记录不动，这一期按没到账算，`arrival_voided=true`、`anomaly=true`，不能再审核；任何阶段都可以撤销配对（撤销后回到待初审）。
- **配上之后改日记账**：这笔流水的人工备注为空 → 写「平台回款 · 店铺 · 账单日」；已有人工备注 → 追加成「原人工备注；平台回款 · 店铺 · 账单日」（备注按「；」切开后已有一段和它完全相同就不重复；拼完超过 500 字不改，配对照常，配对记录备注写「备注过长，未追加」）。分类是空的（没人工选、没挂审批单、没拆分、没剔除、规则分不出、且在待初审）才填 `T03 平台回款`。和日记账页面同一套事件留痕、版本号 +1。撤销配对时：备注没被人改过 → 恢复配对前的人工备注；被人改过 → 按「；」切段、去空格，和当初追加的 tag 完全相同的段恰好一处才删这一段（其余各段用「；」拼回，删完为空则清空）；0 处或多处 → 不动。自动填的分类改回空。
- **回款状态**：`not_due` 未到账单日 / `waiting` 账单日后 7 天内 / `paid` 已打款 / `mismatch` 金额不符 / `unpaid` 过 7 天未到账 / `no_pay` 不需打款（不可付或应付 ≤ 0）/ `voided` 账单作废。`mismatch`、`unpaid`、`voided` = 打款异常（`anomaly=true`）。合并打款时每期按应付记到账，差额落在账单日最晚的一期。
- **审核**：`todo` 待初审 → `ok1` 待终审 → `ok2` 已终审；终审驳回 → `rej2`（必须写原因，回到待初审）。只有配上到账的期次能审。已初审 / 终审的期次不能改配对，要先终审驳回。
- **跟进**：每期可追加跟进记录（内容必填，Case 编号、下次跟进日期可空）。
- **收款账户映射**：店铺 → 入账账户（日记账账户）+ 收款账户识别 + 生效日期。换账户 = 新加一条、旧的自动截止到前一天（必须写原因）；`PUT` 只能改收款账户识别，入账账户不同 → 422「换账户请新增一条」；停用时这条映射生效期间（按账单日）里还有生效中的配对 → 409，先撤销配对。仓库里只有空表；真实映射上线后由部署 AI 录入生产库。

## 2. 接口

统一 envelope。前缀 `/api/finance/payout-recon`。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/periods` | `page:finance:settlement-reconciliation:view` | 每店每期：应付（`payable_source`、`lingxing_payable`、`walmart_total_payable`、`walmart_diff`、`walmart_note`）、到账、差额、回款状态、审核阶段、最新跟进；`auto_ready` = 现在点自动配对能配上的期数。参数 `store_id`、`report_date_from`、`report_date_to`；最多 2000 行（`truncated`） |
| GET | `/periods/{store_id}/{report_key}` | 同上 | 一期详情：按金额类型小计、配对历史（含撤销）、审核记录、跟进记录 |
| GET | `/accounts` | 同上 | 收款账户映射（含历史）+ 可选入账账户、店铺 |
| GET | `/lines` | `action:finance:settlement-reconciliation:review1` | 手动配对可选的到账（映射过的账户里、10 月起的收入流水），带 `journal_hint`；最多 2000 笔（`limit` / `truncated`） |
| POST | `/auto-match` | review1 | 按规则自动配对，只配能唯一确定的 |
| POST | `/matches` | review1 | 手动配对：`{line_uid, periods:[{store_id, report_key}] (1–4), note?}` |
| POST | `/matches/{match_id}/undo` | review1 | 撤销配对：`{reason}` 必填 |
| POST | `/reviews` | `review1_pass` 要 review1；`review2_pass` / `review2_reject` 要 review2 | 批量审核：`{kind, periods:[...] (≤500), reason?}`，不在这一步的期次跳过并返回原因 |
| POST | `/follow-ups` | `action:finance:settlement-reconciliation:follow` | 追加跟进：`{store_id, report_key, content, case_no?, next_follow_date?}` |
| POST | `/accounts` | `action:finance:settlement-reconciliation:review2` | 新增 / 更换收款账户 |
| PUT | `/accounts/{id}` | review2 | 改收款账户识别（原因必填；入账账户不能改，要换请新增一条） |
| POST | `/accounts/{id}/deactivate` | review2 | 停用（写原因，留历史；期间内有生效中的配对 409） |

错误码：`PAYOUT_RECON_NOT_FOUND`（404）、`PAYOUT_RECON_CONFLICT`（409，已配对 / 作废 / 重复）、`PAYOUT_RECON_STAGE_NOT_ALLOWED`（409，已审核不能改配对）、`PAYOUT_RECON_INVALID`（422，缺原因、币种不符、账户无效）、`PAYOUT_RECON_RANGE_INVALID`（422）。

## 3. 数据表（迁移 `20261110_0085_finance_payout_recon`）

| 表 | 一行 | 说明 |
|---|---|---|
| `cfg_walmart_payout_accounts` | 一家店一段时间的收款账户 | 生效中同一店同一生效日唯一 |
| `manual_walmart_payout_matches` | 一笔到账配给一期 | 同 `match_id` = 一次配对；撤销只写 `undone_*`；生效中一期只配一次、一笔到账只在一组 |
| `evt_walmart_payout_reviews` | 一次审核动作 | 只追加；按 `seq_no` 重放得出阶段 |
| `evt_walmart_payout_follow_ups` | 一次跟进 | 只追加 |

所有写操作用同一把事务级咨询锁串行执行。迁移 down 在任一表有数据、或新动作权限已分给角色时拒绝。
