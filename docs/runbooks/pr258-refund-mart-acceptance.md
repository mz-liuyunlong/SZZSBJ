# PR #258 — 退款事实、财务 MART 与同步任务验收

状态：**Draft / 只读证据与隔离环境验收**。此文档不授权生产迁移、同步、历史回填、费用手动归集或部署。

## 已实现的代码边界

- `walmartReturnOrderList` 退款事实首先提交；后续历史 Daily Sales / Order Profit 不变量失败时 Run 保持 `failed`，但已正确写入的退款事实不会因此回滚。
- 业务日会产生 `SYNC_REFUND_MART_PENDING` 与 `SYNC_REFUND_MART_VALIDATED` 审计事件。仅后续 MART 事务成功，才可从当前退款同步流程关闭对应待重算状态。
- 新退款 Run 记录洛杉矶业务日窗口，重试沿用原窗口；旧 Run 仅从已提交的原始 Run 采集事件恢复业务日，无可靠证据则拒绝重试。非连续日期不能被扩大成连续回填窗口。
- 同步总览按账号权限统计今日 Run、最近 Run；ProductList / ProductInfo 仅按账号折叠；日志通过后端服务端筛选和分页；批量启停/触发/重试调用原有授权 API，真正操作需用户在 UI 中二次确认。

## 历史已知问题：没有数据证据不得自动修正

| 日期 | 已发现的异常 | 处置准则 |
| --- | --- | --- |
| 2026-08-04 | SEM CSV 12 条 Campaign，无可靠 Item ID 映射；$8.35 | 保留未归集，核对来源账号、店铺、Campaign ID 与平台广告报表 |
| 2026-09-13 | SEM CSV 1 条 Campaign，无可靠 Item ID 映射；$7.94 | 保留未归集，不用名称猜测 SKU |
| 2026-08-11 | `DATA_PAGES_CONFIRMED_SAMPLE_EXCEEDS_SALESTAT` | 对照平台 SaleStat、订单明细与已核验送样事实，严格核对业务日期和有效版本 |

**警告：** 上述 13 条、$16.29 是指定只读分析结果，不可直接作为生产账本修正金额；重算前应重新对账和核实来源范围。SEM 来源 CSV 不包含可信商品身份时，不得按任意商品、销售比例或广告 SP 费用“摊平”以通过校验。

## 只读与本地验收步骤

1. 在隔离 PostgreSQL 中以至少两个数据源账号构造合成数据；验证 `/api/integrations/sync-tasks/dashboard`、`/api/integrations/sync-runs?source_account_ref=...` 及 ProductInfo 合并日志均不能跨账号。
2. 构造退款事实成功、历史 SEM 校验失败、再次重试的案例；确认退款事实保持、MART 无半提交、审计事件记录精确日期。
3. 分别测试连续、不连续、跨夏令时和无可信事件的历史退款重试，要求未授权日期不进入计划。
4. 只读查看 `/api/integrations/sync-tasks/refund-mart-pending`；对每个待处理日期审计 `SYNC_REFUND_MART_PENDING`、`SYNC_REFUND_MART_VALIDATED`，禁止把 UI 警告消失等同于已经完成销售/利润总账对账。
5. 使用现有 `scripts.audit_walmart_sample_coverage` 在**经批准的只读快照及只读账号**上查看送样覆盖，不以候选折扣或无明细的汇总数自动确认为已核验送样。
6. 获取平台方原始订单行证据，并按 `source_account_ref + store_id + source_order_id + source_order_line_id` 检查唯一身份、取消/退款、正确 LA 购买日及金额口径。
7. 只有取得财务负责人对 SEM 商品映射或保留未分配账本方案的书面确认、送样核对通过、完整回归测试通过，才提交定向修正/回填变更申请。执行前必须备份、演练回滚并限定账号/日期/数量。

## 仍需单独授权的动作

- 生产数据库变更、历史订单身份修复、已核验送样标记变动；
- SEM 手动映射或费用再分配，及历史利润 MART 定向重算；
- 合并 PR、部署 API / Worker / Scheduler 和启动同步任务。

这些是数据核对与发布的**授权边界**，不是一个代码提交可以自动证明完成的操作。若仍存在待归集 SEM 或送样证据矛盾，相关 SKU 利润不能宣布已经最终准确。
