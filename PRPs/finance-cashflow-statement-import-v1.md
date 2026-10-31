# PRP: 财务 · 现金流账户报表导入 V1

- Status: Draft
- Owner Approval Required: Yes
- Implementation authorization state: Not authorized（本 PRP 获批后另发执行 Prompt 才能开实现分支）
- Main execution role: Backend Engineer（含数据中心 → 数据导入页最小前端接线）
- Source Decision: `docs/data-sources/decisions/finance-cashflow-statement-import-decision.md`（READY_FOR_PRP，负责人批准待确认）
- Business rules: `docs/business-rules/finance-cashflow-import-rules.md`
- Branch（实现时）: `feat/finance-cashflow-import`
- Production execution authorized: No
- 出票：Rocky 侧代码 AI，2026-10-31；Rocky 2026-10-31 18:06 确认立项，财务板块后续 PR 同样由 Rocky 侧代码 AI 提交、技术负责人审核合并。

## 1. Goal

财务在数据中心 → 数据导入 一次性上传全部现金流账户的原始导出文件（xls / xlsx / csv，多文件），系统按内容识别账户、解析为标准化流水、去重入库、留存原件与质量结果，并提供只读流水查询接口。完成态：财务周二上传后，`GET /api/finance/cashflow/lines` 能按账户 / 日期返回当周流水，`GET /imports` 能看到每批识别结果与覆盖区间；原件可回放；没有任何外部 API 调用。

## 2. Why

- 它是财务板块正式上线第一刀：「结算对账」（PR-C）的到账侧、「现金状况」的底座都只依赖这份流水。
- 不需要任何外部接口授权，可与领星结算账单同步（PR-B）并行推进。
- Rocky 2026-10-31 已否决 PingPong / 派安盈 / 万里汇 API 接入，文件导入即长期方案。
- 业务原型（Demo v5.3.0 ~ v5.5.0）已在财务手上跑了三轮，口径稳定；control totals 明细按 Demo 归档保存在 Rocky 侧工作区。

## 3. Scope

### In scope

- [ ] Alembic migration（接当前 head `20261029_0068_walmart_remote_jobs` 之后的最新 head）：`dim_finance_cash_accounts`（含种子 11 条：中行 ×4、银座、派安盈 ×2、万里汇、PingPong ×3）、`landing_finance_cashflow_imports`、`raw_finance_cashflow_files`、`std_finance_cashflow_lines`、`dq_run_finance_cashflow_import`。
- [ ] 新模块 `backend/app/modules/finance_cashflow/`：models / schemas / parsers（boc_xls、shenzhen_rural_bank_xlsx、payoneer_csv、worldfirst_xlsx、pingpong_xlsx）/ detector / service / repository / router。
- [ ] 接口：`POST /api/finance/cashflow/imports`（请求体 + `X-File-Name`，多文件 = 多次调用归入同一 `X-Import-Id`，与 operation_plans 一致）、`GET /api/finance/cashflow/imports`、`GET /api/finance/cashflow/imports/{import_id}`、`POST /api/finance/cashflow/imports/{import_id}/void`、`GET /api/finance/cashflow/lines`、`GET /api/finance/cashflow/accounts`。
- [ ] IAM：`rbac_schemas.ScopeType` 新增 `finance_cash_account`；角色数据范围界面（设置 → 角色管理 → 数据范围）增加「现金账户」资源的勾选；权限目录登记上述 action / field key。
- [ ] 依赖清单：xlsx 沿用 `operation_plans` 的标准库解析方式（zipfile + ElementTree，不新增依赖）；csv 标准库；**xls（中行导出）需新增 `xlrd`（纯 Python，BSD）**——若负责人不接受新依赖，则改为要求财务把中行导出另存为 xlsx 上传，二选一在 PRP 批准时定；上传沿用 `operation_plans` 的请求体 + `X-File-Name` 方案（多文件 = 多次调用归入同一 `X-Import-Id`），不引入 multipart 依赖。
- [ ] 权限：页面 `page:data-center:data-import:view`；功能 `action:data-center:data-import:finance-cashflow-upload`、`action:data-center:data-import:finance-cashflow-void`（high）；字段 `field:finance:settlement-reconciliation:counterparty`；data scope 资源 `finance_cash_account`（none → fail closed）；全部登记进 `permission_catalog_v2`。
- [ ] 前端：`frontend/src/pages/data-center/DataImportPage.tsx` 把「现金流账户报表」来源从 mock 接成真实 API（上传多文件、每文件识别结果、覆盖区间、去重数、作废需二次确认）；其余来源保持 mock 不动。
- [ ] 文档：`docs/api/finance-cashflow-import.md`、`docs/sop/data-center/finance-cashflow-import.md`、`DATA_INTERFACE_REGISTRY.md` 状态更新、`CODEX_HANDOFF.md`。
- [ ] 测试：合成样本文件（不含真实户名 / 账号 / 金额）覆盖 5 种格式 × 识别 / 解析 / 去重 / 拒绝 / 余额链 / 脱敏；权限 fail-closed；重复上传幂等；PostgreSQL 隔离测试库下 migration up / down。
- [ ] **门禁**：派安盈 CSV 的 UTC → Asia/Shanghai 业务日期折算、PingPong「专用账户入账」拆成回款全额 + 归集手续费两行的规则，须先用合成样本 + 一份脱敏真实样本在本地验证并记录，对应 parser 才允许进入实现；金额列 `numeric(18,4)`，解析按字符串转 Decimal。

### Out of scope

- [ ] 分类、挂审批单、拆分 / 剔除、初审 / 二审、折人民币（「现金状况」另立 PRP）。
- [ ] 领星结算账单 / 回款明细同步（PR-B）、结算对账页（PR-C）。
- [ ] 任何银行 / 派安盈 / PingPong / 万里汇 API；招商银行账户；PDF 回单解析。
- [ ] 账户主数据维护页（变更走 migration / 负责人授权脚本）。
- [ ] 原件下载接口。
- [ ] 旧 Excel 日记账（2026-05 ~ 09）迁入。
- [ ] 生产迁移、生产部署、数据回填（另行授权）。

## 4. Navigation / Page

```text
一级导航：数据中心
二级导航：数据导入（既有，frontend/src/config/navigation.ts key data_center.data_import）
页面路径：/data-center/data-import
页面状态：building（本 PRP 实现后由负责人改 ready）
```

不新增导航项。将来若负责人决定把上传入口放进「财务」一级菜单，另改导航规范。

## 5. Permissions

```text
page permissionKey: page:data-center:data-import:view
action permissionKeys: action:data-center:data-import:finance-cashflow-upload；action:data-center:data-import:finance-cashflow-void (high-risk)
data scope resource: finance_cash_account（按账户 / 法人主体；默认 none，fail closed；超管 *）
field permissions: field:finance:settlement-reconciliation:counterparty（对方户名、卡号尾号；未授权不返回该字段）
high-risk actions: void（二次确认 + 审计事件 + 幂等）
```

## 6. Data Source

```text
data source decision file: docs/data-sources/decisions/finance-cashflow-statement-import-decision.md
decision status: READY_FOR_PRP
dataset classifications: A 账户主数据 NEW_SYSTEM_OWNED(L7)；B 导入批次 NEW_SYSTEM_OWNED(L1)；C 原件 ARCHIVE_ONLY(L2)；D 标准化流水 NEW_SYSTEM_OWNED(L3)；E PingPong 非本主体行 ARCHIVE_ONLY；F 质量结果 NEW_SYSTEM_OWNED(L12)
contains NEED_OWNER_DECISION: no
owner approval status: 待确认
short-term strategy: 文件导入
long-term strategy: 文件导入（API 接入已被否决）
legacy exit criteria: 不适用（无旧库依赖）
old-system reference: no
legacy MySQL readonly tables: 无
new PostgreSQL tables: dim_finance_cash_accounts, landing_finance_cashflow_imports, raw_finance_cashflow_files, std_finance_cashflow_lines, dq_run_finance_cashflow_import
cache / mart tables: 无（本期）
sensitive or critical domains: 财务 / 敏感数据（个人户名、卡号尾号）
```

## 7. API Contract（要点，细节在 docs/api/finance-cashflow-import.md）

```text
POST /api/finance/cashflow/imports
  request: 文件字节（单文件 + X-File-Name；多文件 = 多次调用，用 X-Import-Id 归入同一 import_id）
  response: { import_id, files:[{file_id, file_name, sha256, size, account_key|null, account_display, detected_note, rows_parsed, rows_new, rows_duplicate, declared_range_from, declared_range_to, dq:{balance_chain_ok, warnings[]}, status: received|parsed|rejected, reject_reason}] }
  errors: 401/403（权限 / scope）、413（超过大小上限，上限写进配置）、415（不支持的类型）、422（整批参数错）
GET /api/finance/cashflow/imports?from&to&status&page
GET /api/finance/cashflow/imports/{import_id}
POST /api/finance/cashflow/imports/{import_id}/void  body:{reason}（high-risk）
GET /api/finance/cashflow/lines?account_key&from&to&page&sort=bank_order  → 字段见决策 §4；counterparty_* 受字段权限
GET /api/finance/cashflow/accounts
meta.source: finance_cashflow
meta.source_tables: std_finance_cashflow_lines / landing_finance_cashflow_imports / dim_finance_cash_accounts
request_id: 统一 envelope
```

## 8. UI Requirements

```text
layout: 数据导入页既有卡片列表中「现金流账户报表」一张卡 + 展开区
table columns（导入台账）: 上传时间 / 上传人 / 文件名 / 识别为 / 覆盖区间（表头声明 | 按首末笔）/ 行数 / 新增 / 重复 / 质量 / 状态 / 操作（作废）
filters: 日期范围、账户、状态
actions: 上传（多选）、作废（二次确认，填原因）
empty state: 「还没导入过；每周二 15:00 前上传全部账户导出」
loading state: 上传进度按文件
error state: 每文件拒绝原因中文原文（来自规则 §2）
helpUrl: /help/data-center/finance-cashflow-import
```

## 9. SOP / API Docs

- [x] Markdown API doc required
- [x] OpenAPI metadata required
- [x] SOP help page required
- [x] PageShell help entry required

## 10. Implementation Plan

```text
Task 1: migration + models + 种子（dim_finance_cash_accounts 11 条）；scaffold 测试更新
Task 2: detector + 5 个 parser + 脱敏 + line_uid + 余额链；合成样本测试
Task 3: service / repository / router + 权限 + 审计 + 幂等（同 sha256、同 line_uid）
Task 4: 前端 DataImportPage 现金流来源接线 + 作废二次确认 + 测试
Task 5: API 文档 / SOP / registry / CODEX_HANDOFF；完成报告八段
```

## 11. Validation Gates

```bash
# backend
uv run ruff check . && uv run ruff format --check .
uv run pytest backend/tests/modules/finance_cashflow -q
uv run alembic check
# frontend
npm run lint && npm run typecheck && npm run test -- data-center
npm run build
# CI
bash scripts/ci-preflight.sh
# control totals（本地，用 Rocky 侧 2026-10 真实导出，文件不进 Git）：按 Demo 归档的 control totals 核对，PR 只贴是否一致
```

## 12. Forbidden Actions

```text
不修改 old-system；不连接生产数据库；不修改 .env；不调用任何银行 / 平台 API；不部署；不重启服务
不把真实导出文件、真实户名 / 账号 / 金额写进测试、日志、文档或 PR
不改既有 operation_plans / integration_sync 行为；不改导航规范
```

## 13. Rollback Plan

- 代码：revert PR。
- 数据库：migration down（五张新表均为新建，无既有数据）。
- 配置 / feature flag：上传入口受 `action:...:finance-cashflow-upload` 控制，撤权限即关闭；无 Celery / schedule。

## 14. Acceptance Checklist

- [ ] 页面 / API 完成
- [ ] 权限生效（页面 / 功能 / 字段 / data scope，fail closed 测试）
- [ ] 数据权限生效
- [ ] API 文档完成
- [ ] SOP 完成
- [ ] 测试通过（含 PostgreSQL migration up/down）
- [ ] Playwright：上传两份合成文件 → 台账出现两行、识别正确、作废需确认
- [ ] control totals 与 Demo 基线一致（本地验证记录贴 PR）
- [ ] CODEX_HANDOFF 更新

## 15. Open items for owner

1. 原件存 bytea（默认）还是受控目录。
2. 上传入口留在数据中心（默认）还是财务一级菜单。
3. 上传文件大小上限（Demo 单文件 < 1 MB；建议 10 MB）。
