# PRP: 财务 · 领星 Walmart 结算账单 / 回款明细同步 V1

- Status: Draft
- Owner Approval Required: Yes
- Implementation authorization state: Not authorized（PRP 获批后另发执行 Prompt；生产 outbound / 回填 / schedule 三项另需书面授权）
- Main execution role: Backend Engineer（Integration Sync handler + migration；无前端）
- Source Decision: `docs/data-sources/decisions/finance-walmart-settlement-sync-decision.md`（READY_FOR_PRP，负责人批准待确认）
- Related: `PRPs/finance-cashflow-statement-import-v1.md`（PR-A，到账侧）；结算对账页另立 PRP（PR-C）
- Branch（实现时）: `feat/finance-walmart-settlement-sync`
- Production execution authorized: No
- 出票：Rocky 侧代码 AI，2026-10-31；Rocky 22:36 / 22:44 定：账单直拉领星不走 Walmart API、历史从 2026-03-01 起、回款明细一起登记、上线后自动拉。

## 1. Goal

在既有 Integration Sync 上新增两个领星只读接口 `walmartBillStatementList`、`walmartBillPayoutList`：每页先落 RAW，再解析进 ODS，规范化成结算事实表，并刷新「店铺 × 账单」期次读模型。完成态：负责人授权后，一次回填 9 店 2026-03-01 起全部账单，之后每周三 03:00 自动增量；任务中心能看到运行 / 异常；`mart_walmart_settlement_periods` 可供结算对账页读取。不含任何前端业务页面。

## 2. Why

- 结算账单是财务板块 ③④⑤ 的唯一底数；现在靠 Rocky 逐期批单、部署 AI 手跑，不可持续。
- 领星数据已与 Walmart 原始结算单逐期核平，直接拉领星省掉 Walmart 官方 API 那条仍被阻塞的路。
- 回款明细给结算对账提供「平台说打了多少」，与 PR-A 的流水对号。

## 3. Scope

### In scope

- [ ] catalog 登记两个接口（provider lingxing、request_kind offset_page、handler_key `lingxing.walmart_bill_statement.v1` / `lingxing.walmart_bill_payout.v1`、contract_version 引契约快照），默认 `outbound_enabled=false`；bootstrap 脚本把两条 sync_config 写成 `is_enabled=false` / `schedule_enabled=false`。
- [ ] handler：一店一 run、按月（回填）/ 35 天（增量）窗口、offset/length ≤ 200 翻页、totalCount 完整性、`totalSum.amount` control total、RAW blob + request ref、ODS **按店铺 × reportKey 整期快照替换**（行身份 = 复合键 + id + 同键序号的 `source_row_hash`；消失的行标 `missing_in_snapshot_at` 不删；见决策 §3.1）。金额 JSON 按字符串转 `Decimal`、落库 `numeric(18,4)`，不经 float。
- [ ] Alembic migration（接当时最新 head）：`ods_lingxing_walmart_bill_statement_items`、`ods_lingxing_walmart_bill_payouts`、`fact_walmart_settlement_lines`、`mart_walmart_settlement_periods`；金额列 `numeric(18,4)`；索引：store_id + report_key、report_date、source_row_hash 唯一。
- [ ] 规范化与 MART 刷新任务（run 成功后同事务内或独立 Celery 任务刷新受影响的 store × report_key）。
- [ ] 受控只读探测脚本：一店一月窗口，dry-run → 1 页，输出脱敏字段清单；默认禁用、需环境变量显式打开。**门禁**：`startDate` / `endDate` 的日期语义（账单日 vs 交易日）与 payout/list 的字段 / 分页，必须在该探测确认并记录后，对应 handler 才允许进入实现；探测前只能写契约驱动的 parser 骨架与合成测试。
- [ ] 回填 runner（manual、一店一次、按月窗口、幂等、可续跑）+ runbook `docs/runbooks/production-finance-settlement-backfill.md`（prepared，execution prohibited until Owner log）。
- [ ] 任务中心：复用既有同步任务页面与异常中心，无新页面。
- [ ] 文档：`docs/api/finance-settlement-sync.md`（handler / 表契约 / 字段映射）、`DATA_INTERFACE_REGISTRY.md` 更新、`CODEX_HANDOFF.md`。
- [ ] 测试：fixture 用合成 JSON（结构照契约，金额 / 订单号 / 店铺为假值）覆盖分页完整性、control total、行 hash、枚举未知值、deleteFlag、单店失败隔离、MART 刷新、禁用开关 fail-closed；PostgreSQL migration up/down。

### Out of scope

- [ ] 结算利润 / 分摊 / WFS 费用明细（③）；对账页与人工确认（PR-C）。
- [ ] Walmart 官方 Reconciliation / Reports API。
- [ ] Demo 已拉 JSONL 的导入（只用于 control totals）。
- [ ] 生产 outbound 开启、回填执行、schedule 开启、部署（各需单独授权与 runbook 执行记录）。
- [ ] 任何前端业务页面。

## 4. Navigation / Page

```text
一级导航：数据中心
二级导航：任务中心（既有；本 PRP 不新增页面）
页面路径：/data-center/task-center
页面状态：不变
```

## 5. Permissions

```text
page permissionKey: 既有 page:data-center:task-center:view
action permissionKeys: 既有 integrations:execute（手动触发 / 回填），integrations:update（配置）
data scope resource: source_account_ref + store（既有同步治理边界）
field permissions: 不适用（无新前端字段）；D/E 表的读取接口在 PR-C 定义字段权限（页面 key `page:finance:settlement-reconciliation:view`）
high-risk actions: 开启 outbound / schedule、回填 —— 仅负责人授权后由 runbook 执行
```

## 6. Data Source

```text
data source decision file: docs/data-sources/decisions/finance-walmart-settlement-sync-decision.md
decision status: READY_FOR_PRP
dataset classifications: A RAW REBUILD_SYNC（既有 ods_api_raw_blobs）；B/C ODS REBUILD_SYNC；D FACT REBUILD_SYNC；E MART REBUILD_SYNC
contains NEED_OWNER_DECISION: no
owner approval status: 待确认
short-term strategy: REBUILD_SYNC via Integration Sync，默认关闭
long-term strategy: 同上
legacy exit criteria: 不适用
old-system reference: no
legacy MySQL readonly tables: 无
new PostgreSQL tables: ods_lingxing_walmart_bill_statement_items, ods_lingxing_walmart_bill_payouts, fact_walmart_settlement_lines, mart_walmart_settlement_periods
cache / mart tables: mart_walmart_settlement_periods
sensitive or critical domains: 财务 / 结算（订单号、买家地址不进业务层）
```

## 7. API Contract

本 PRP 不新增前端业务 API。外部契约与字段映射见决策 §3；内部任务 / 配置接口复用 Integration Sync 既有路由（`/api/integrations/...`），仅新增两个 interface_key。读取接口（`GET /api/finance/settlements/periods|lines`）在 PR-C 定义。

```text
meta.source: integration_sync / lingxing
meta.source_tables: ods_lingxing_walmart_bill_statement_items, ods_lingxing_walmart_bill_payouts, fact_walmart_settlement_lines, mart_walmart_settlement_periods
request_id: 统一 envelope（既有）
```

## 8. UI Requirements

不适用（复用任务中心与异常中心展示 run / work item / anomaly）。

## 9. SOP / API Docs

- [x] Markdown API doc required（handler / 表契约）
- [ ] OpenAPI metadata required（无新路由）
- [x] SOP help page required（runbook：回填与定时开启）
- [ ] PageShell help entry required（无新页面）

## 10. Implementation Plan

```text
Task 1: migration 四张表 + model registry + scaffold 测试
Task 2: catalog / bootstrap 登记两个接口（默认关）；request planner（一店一窗口、offset 分页、totalCount 完整性）
Task 3: statement handler：RAW → ODS upsert（source_row_hash）→ FACT 规范化 → control total → MART 刷新
Task 4: payout 受控探测脚本 + payout handler（字段以探测结果为准）
Task 5: 回填 runner + runbook；单店隔离、续跑、幂等测试
Task 6: 文档 / registry / CODEX_HANDOFF；完成报告八段
```

## 11. Validation Gates

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest backend/tests/modules/integration_sync -k "walmart_bill" -q
uv run pytest tests/db -q
uv run alembic check
bash scripts/ci-preflight.sh
# control totals（授权回填后）：按 Demo 归档的 control totals 核对（每店行数 / 账单数，保存在 Rocky 侧工作区，不进仓库）；Σamount 与 totalSum.amount 对平
```

## 12. Forbidden Actions

```text
不修改 old-system；不连接生产数据库；不修改 .env；不调用真实领星接口（除显式授权的受控探测）；不部署；不重启服务
不改既有四个 DATA_PAGES 接口的 handler / 配置；不翻转任何 is_enabled / outbound_enabled / schedule_enabled 默认值
不把真实 JSON、订单号、金额明细写进测试 / 文档 / PR
```

## 13. Rollback Plan

- 代码：revert PR；两个接口在 catalog 中移除后，sync_config 行由 bootstrap 标记 disabled（不删 RAW）。
- 数据库：migration down（四张新表均新建）；RAW blobs 按既有保留策略处理。
- 运行：`is_enabled=false` 立即停；MART 可由 FACT 全量重刷。

## 14. Acceptance Checklist

- [ ] 两接口登记、默认关闭、bootstrap 幂等
- [ ] 分页完整性与 control total 失败时 run 标 failed、不发布
- [ ] 行身份（复合键 + id + 同键序号）在最大店 CN2601 真实 JSON 上零碰撞（授权探测记录只写是否零碰撞，贴 PR）
- [ ] startDate / endDate 日期语义与 payout 字段已由受控探测确认并记录，之后才实现对应 handler
- [ ] 单店失败隔离测试通过
- [ ] migration up/down 通过；`alembic check` 干净
- [ ] runbook 已写、状态 prepared
- [ ] registry / CODEX_HANDOFF 更新

## 15. Open items for owner

以下各项**待负责人批准**，本 PRP 不作最终决定；批准前不得开启任何生产同步、定时或回填。

1. 定时频率：每周三 03:00（建议）还是每日。
2. 回填时点：PR 合并后立即、还是等 PR-C 页面一起。
3. Demo 拉法停用时点（Rocky 定）。
