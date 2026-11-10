# 财务 · 回款对账（到账配对 + 审核）

回款对账 = 沃尔玛每店每期应付（`mart_walmart_bill_periods`，见 `finance-walmart-bills.md`）对上日记账到账（`std_finance_cashflow_lines`），再初审、终审。
口径：Rocky 2026-11-10 批准；PRP：`PRPs/finance-walmart-settlement-sync-v1.md` 第 16 节。只看 2026-10-01 起的账单。

## 1. 规则

- **自动配对**：到账日期在账单日之后 0–7 天；到账账户是这家店（账单日当天生效）的收款账户；收款账户识别（派安盈付款邮箱 / PingPong 公司名）填了就要出现在付款方、摘要或备注里；币种一致；金额差 ≤ 0.01。
- **合并打款**：一笔到账 = 同一收款账户下 2–4 期应付之和（差 ≤ 0.01），也自动配给这几期。
- 一笔到账能配出不止一种结果，或一期被几笔到账争抢 → 不自动配，留给财务手动配（`POST /matches`，金额可以不等，显示为金额不符；账单日早于 2026-10-01 的期次 422）。
- 日记账里已另有用途的流水不进自动配对：已剔除、已内部配对、已拆分、已人工分到 `T03` 以外的类别。`GET /lines` 给这些流水带 `journal_hint`（「已剔除」「已内部配对」「已拆分」「已分类 Xxx」），仍可手动配。
- 配上的到账流水后来在日记账里作废（整批作废）：配对记录不动，这一期按没到账算，`arrival_voided=true`、`anomaly=true`，不能再审核；任何阶段都可以撤销配对（撤销后回到待初审）。
- **配上之后改日记账**：这笔流水的人工备注为空 → 写「平台回款 · 店铺 · 账单日」；已有人工备注 → 追加成「原人工备注；平台回款 · 店铺 · 账单日」（已含同样内容不重复；拼完超过 500 字不改，配对照常，配对记录备注写「备注过长，未追加」）。分类是空的（没人工选、没挂审批单、没拆分、没剔除、规则分不出、且在待初审）才填 `T03 平台回款`。和日记账页面同一套事件留痕、版本号 +1。撤销配对时：备注没被人改过 → 恢复配对前的人工备注；被人改过但追加的那一段还在（恰好一处）→ 只删那一段；那一段找不到 → 不动。自动填的分类改回空。
- **回款状态**：`not_due` 未到账单日 / `waiting` 账单日后 7 天内 / `paid` 已打款 / `mismatch` 金额不符 / `unpaid` 过 7 天未到账 / `no_pay` 不需打款（不可付或应付 ≤ 0）/ `voided` 账单作废。`mismatch`、`unpaid`、`voided` = 打款异常（`anomaly=true`）。合并打款时每期按应付记到账，差额落在账单日最晚的一期。
- **审核**：`todo` 待初审 → `ok1` 待终审 → `ok2` 已终审；终审驳回 → `rej2`（必须写原因，回到待初审）。只有配上到账的期次能审。已初审 / 终审的期次不能改配对，要先终审驳回。
- **跟进**：每期可追加跟进记录（内容必填，Case 编号、下次跟进日期可空）。
- **收款账户映射**：店铺 → 入账账户（日记账账户）+ 收款账户识别 + 生效日期。换账户 = 新加一条、旧的自动截止到前一天（必须写原因）；`PUT` 只能改收款账户识别，入账账户不同 → 422「换账户请新增一条」；停用时这条映射生效期间（按账单日）里还有生效中的配对 → 409，先撤销配对。仓库里只有空表；真实映射上线后由部署 AI 录入生产库。

## 2. 接口

统一 envelope。前缀 `/api/finance/payout-recon`。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/periods` | `page:finance:settlement-reconciliation:view` | 每店每期：应付、到账、差额、回款状态、审核阶段、最新跟进；`auto_ready` = 现在点自动配对能配上的期数。参数 `store_id`、`report_date_from`、`report_date_to`；最多 2000 行（`truncated`） |
| GET | `/periods/{store_id}/{report_key}` | 同上 | 一期详情：按金额类型小计、配对历史（含撤销）、审核记录、跟进记录 |
| GET | `/accounts` | 同上 | 收款账户映射（含历史）+ 可选入账账户、店铺 |
| GET | `/lines` | `action:finance:settlement-reconciliation:review1` | 手动配对可选的到账（映射过的账户里、10 月起的收入流水），带 `journal_hint`；最多 2000 笔（`limit` / `truncated`） |
| POST | `/auto-match` | review1 | 按规则自动配对，只配能唯一确定的 |
| POST | `/matches` | review1 | 手动配对：`{line_uid, periods:[{store_id, report_key}] (1–4), note?}` |
| POST | `/matches/{match_id}/undo` | review1 | 撤销配对：`{reason}` 必填 |
| POST | `/reviews` | `review1_pass` 要 review1；`review2_pass` / `review2_reject` 要 review2 | 批量审核：`{kind, periods:[...] (≤500), reason?}`，不在这一步的期次跳过并返回原因 |
| POST | `/follow-ups` | `action:finance:settlement-reconciliation:follow` | 追加跟进：`{store_id, report_key, content, case_no?, next_follow_date?}` |
| POST | `/accounts` | `action:finance:settlement-reconciliation:review2` | 新增 / 更换收款账户 |
| PUT | `/accounts/{id}` | review2 | 改收款账户识别（入账账户不能改，要换请新增一条） |
| POST | `/accounts/{id}/deactivate` | review2 | 停用（写原因，留历史；期间内有生效中的配对 409） |

错误码：`PAYOUT_RECON_NOT_FOUND`（404）、`PAYOUT_RECON_CONFLICT`（409，已配对 / 作废 / 重复）、`PAYOUT_RECON_STAGE_NOT_ALLOWED`（409，已审核不能改配对）、`PAYOUT_RECON_INVALID`（422，缺原因、币种不符、账户无效）、`PAYOUT_RECON_RANGE_INVALID`（422）。

## 3. 数据表（迁移 `20261110_0086_finance_payout_recon`）

| 表 | 一行 | 说明 |
|---|---|---|
| `cfg_walmart_payout_accounts` | 一家店一段时间的收款账户 | 生效中同一店同一生效日唯一 |
| `manual_walmart_payout_matches` | 一笔到账配给一期 | 同 `match_id` = 一次配对；撤销只写 `undone_*`；生效中一期只配一次、一笔到账只在一组 |
| `evt_walmart_payout_reviews` | 一次审核动作 | 只追加；按 `seq_no` 重放得出阶段 |
| `evt_walmart_payout_follow_ups` | 一次跟进 | 只追加 |

所有写操作用同一把事务级咨询锁串行执行。迁移 down 在任一表有数据、或新动作权限已分给角色时拒绝。
