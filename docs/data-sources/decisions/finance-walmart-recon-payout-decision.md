# 财务 · 沃尔玛对账报表打款额（回款对账应付口径）数据源决策

- 调查日期：2026-11-26
- 调查人：Rocky 侧代码 AI（财务板块）
- 目标接口（沃尔玛 Marketplace API，经 V4 通用通道 `call_walmart()` 只读 GET）：
  - `GET /v3/report/reconreport/availableReconFiles?reportVersion=v1` → 该店可用的对账日期（`MMDDYYYY`）
  - `GET /v3/report/reconreport/reconFileJson?reportDate=<MMDDYYYY>&offset=0&noOfRecords=100` → 对账报表第一页；`Transaction Type = PaymentSummary` 那一行的 `Total Payable` 即本期实际打款，`Period Start / End Date`、`Transaction Posted Timestamp` 为账期与打款日
- 业务用途：回款对账的「应付」底数。领星账单（`statement/list`）只含订单级交易，不含保证金扣留 / 释放等账户级交易；2026-11-26 探测一家店 11-17 期页面应付比沃尔玛实际打款少，差额正好等于对账报表里的 `Release Reserve` 一行；另两家店两者一致。
- 接口总体状态：**READY_FOR_PRP**（同日实现，PR #368）
- 是否包含 NEED_OWNER_DECISION：否（Rocky 2026-11-26 已定）

## Rocky 2026-11-26 决定

1. 应付以沃尔玛对账报表 `PaymentSummary` 行的 `Total Payable` 为准，领星值留作参考；不建业务新表，在 `mart_walmart_bill_periods` 上加列。
2. 原始数据要存：每店每期第一页原样落 RAW 表 `raw_walmart_recon_report_pages`（店铺 × 对账日期 × 页偏移），再解析写期表。
3. **只拉账单日 ≥ 2026-11-01 的期**：10 月及以前已人工对完，不拉、不改应付；10 月数据的清理另行安排。
4. 已配对或审核过的 11 月起的期，应付变化 > 0.01：照改应付，追加 `reset` 审核事件退回待初审，任务结果列出。

## RAW 存法与保留

- 不用 `ods_api_raw_blobs` + `ods_api_raw_request_refs`：那套绑定 Integration Sync 的 run / work item / 保留策略，这个任务是独立的 Celery 任务、不走 Integration Sync，硬套会多出一整层运行登记；改用专用表 `raw_walmart_recon_report_pages`（店铺 × 对账日期 × 页偏移），每页原样 JSONB + sha256 + 字节数 + 请求号。
- 拉到就先单独保存（独立保存点）再解析：解析失败、账期对不上、限流，原始页都留下，正好是要留证据的那些期。
- 重拉覆盖同一页时记上一版指纹 `previous_sha256`；生产任务不传 `refresh_existing`，不会主动重拉。
- 内容含订单号、收货城市 / 州 / 邮编等买家信息：没有任何接口返回这张表，只有数据库可读。**保留期限 12 个月**，到期由部署AI按 Rocky 票据清理（`delete … where received_at < now() - interval '12 months'`），不自动删；10 月及以前的期本就不拉。

## 实现要点

- 每期只拉第一页（`PaymentSummary` 在第一页；不在第一页报 `WALMART_RECON_SUMMARY_NOT_ON_FIRST_PAGE` 并跳过该期）；JSON 回包上限 1MB（云函数），一页 100 行远低于上限，不用翻页。
- 代码只允许上述两个路径（`recon_payout.ALLOWED_PATHS`），method 写死 GET。
- 对账日期与领星 `report_date` 一一对应（三家店核对）；账期起止差 > 3 天或币种不一致的期拒绝写入；同店账单日重复的期跳过。
- 开关 `ENABLED_ENV`（见 `recon_payout_sync.py`）默认关；生产 + 开关才排期（周三上海 04:30，领星账单同步之后）；页面按钮只投递任务。
- 调用量：首次每店 1 + ≤ 40 次，之后每周每店 1~2 次。

## 不做

- 不拉对账报表明细（后续结算利润另议）。
- 不拉 `/v3/report/payment/statement`：它只给当前未结算周期的账户汇总，没有历史每期打款。
- 不接领星 `payout/list`（Rocky 2026-11-08 已否）。

实现：`PRPs/finance-walmart-settlement-sync-v1.md`（回款对账）+ `docs/api/finance-payout-recon.md` §1、`docs/api/finance-walmart-bills.md`。
