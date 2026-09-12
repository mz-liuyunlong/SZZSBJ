# Source Decision: 服务器正式 Lingxing ProductList 同步

```text
Decision Date: 2026-09-13
Decision Owner: Project Owner
Status: APPROVED_FOR_IMPLEMENTATION_AND_CONTROLLED_EXECUTION
Source Decision Status: APPROVED_BY_OWNER_DECISION
Implementation Branch: feat/production-lingxing-productlist-sync
Authorized PRP: PRPs/integration-sync-governance-backend-v1.md
ProductList Real Call Permission: Yes, within this decision only
Lingxing Token Request Permission: Yes, only for the authorized ProductList run
batchGetProductInfo Real Call Permission: No
Initial Trigger: Manual only
Initial schedule_enabled: false
Formal Application Database: szzsbj_app
```

## 1. 正式决定

项目负责人正式批准下一阶段实现并执行服务器 Lingxing ProductList 同步。该授权只适用于 `/erp/sc/routing/data/local_inventory/productList`，只允许从已合并 `main` 部署的代码执行，并只允许将获批记录写入 PostgreSQL 正式应用数据库 `szzsbj_app`。

`szzsbj_app` 是固定的正式应用数据库名，不以 `test`、`staging`、`dev` 或 `prod` 命名，也不得被描述为这些临时库之一。本决定不授权在当前 docs-only 分支连接服务器、数据库、请求 Token 或调用 Lingxing。

本决定是对 `docs/decisions/2026-09-12-integration-sync-governance-backend-v1-source-decision.md` 的限定后续授权：PR #61 的历史实现边界不变；仅下一阶段 ProductList 正式链路解除真实 Token、真实 ProductList 和指定新系统表写入禁令。其他 Lingxing 接口继续 fail closed。

## 2. 数据源与分层决定

| 数据对象 | 来源与分层 | 正式决定 |
|---|---|---|
| ProductList response | Lingxing L0 来源；L2 RAW evidence | 凭据脱敏后写入 `szzsbj_app` 数据库中的 `ods_api_raw_blobs`，不是业务权威表 |
| ProductList request metadata | 新系统 L1/L12 请求证据 | 安全元数据写入 `szzsbj_app` 数据库中的 `ods_api_raw_request_refs`；不得包含认证 query、完整 URL 或 payload |
| Sync run | `NEW_SYSTEM_OWNED` governance | 写入 `szzsbj_app` 数据库中的 `gov_integration_sync_runs` |
| Sync work item | `NEW_SYSTEM_OWNED` governance | 每个分页工作项写入 `szzsbj_app` 数据库中的 `gov_integration_sync_run_work_items` |
| ProductList SKU reference | Lingxing-derived L3 evidence | 从 `productList.data.id` 或 response `data.id` 提取 `lingxing_sku_id`，写入 `szzsbj_app` 数据库中的 `ods_lingxing_productlist_sku_refs` |
| Lingxing SKU identity index | Lingxing-derived L6 identity | 幂等 upsert `szzsbj_app` 数据库中的 `dwd_lingxing_sku_identity_index`；不得用 SKU code、MSKU、ItemID 或名称推导身份 |

RAW 是可回放证据，不是前端或业务 API 的直接真源。服务器保存 RAW 到数据库不等于允许把 RAW JSON、归档包或商品字段值提交到 Git、日志、错误信息或任务输出。

## 3. 明确授权范围

下一阶段在独立 backend worktree 中允许：

1. 在服务器正式环境请求 Lingxing ProductList。
2. 为 ProductList 请求受控获取或刷新 Token。
3. 在执行前对 `szzsbj_app` 执行 `alembic upgrade head`。
4. 将凭据脱敏后的 ProductList RAW response 写入 `ods_api_raw_blobs`。
5. 将 ProductList request metadata 写入 `ods_api_raw_request_refs`。
6. 写入 `gov_integration_sync_runs`。
7. 写入 `gov_integration_sync_run_work_items`。
8. 将 `productList.data.id` / response `data.id` 解析为 `lingxing_sku_id`。
9. 写入 `ods_lingxing_productlist_sku_refs`。
10. 幂等 upsert `dwd_lingxing_sku_identity_index`。
11. 将 RAW 保存在数据库，但不得把 RAW JSON 或 `.tar.gz` 提交到 Git。
12. 第一次正式执行使用 manual trigger only。
13. 第一次正式执行保持 `schedule_enabled=false`。

授权写入对象仅为本节列出的 6 张表。PR #61 migration 中的其他表可以由 `alembic upgrade head` 创建，但本 ProductList 执行不得借此写入未列出的业务、详情、DWS 或 Product Core 表。

## 4. 数据库与 migration 前置条件

执行前必须逐项确认：

1. 服务器已存在 PostgreSQL 数据库 `szzsbj_app`。
2. `DATABASE_URL` 明确指向 `szzsbj_app`。
3. `DATABASE_URL` 不指向旧系统 MySQL。
4. `DATABASE_URL` 不指向承载旧 `raw_lingxing_api` 的数据库。
5. `szzsbj_app` 是新建正式应用数据库，或执行前已具备可验证的备份/snapshot。
6. 环境变量只通过受控 env 文件、部署平台或 secret manager 注入，不进入 Git、文档、命令输出或聊天。
7. 数据库账号遵循最小权限；本授权不包含数据库超级用户或跨库写权限。
8. ProductList interface、retention policy 与 sync config 等执行前置记录必须已由合并代码和已批准流程建立；如缺失或需要写入本决策未批准的其他表，必须停止并申请单独授权，禁止临时手工补写。
9. migration revision、当前 head、备份/恢复路径和预期 schema 必须在执行前复核。
10. migration 与正式 ProductList 执行分步进行；任何 migration 失败必须停止，禁止继续请求 Lingxing。

`alembic upgrade head` 只允许从已合并 `main` 的部署产物执行。禁止在服务器直接编辑代码、临时修补 migration 或绕过 PR。

## 5. 首次正式执行规则

- 必须由 manual trigger 创建唯一 `run_id`，不得先开启 scheduler、beat 或周期任务。
- 必须从 offset 起点按 ProductList contract 串行分页；分页大小、重试、限流、超时、总页数和停止条件由下一阶段代码 PR 明确并测试。
- 每个请求先创建/更新受控 work item；成功响应先写脱敏 RAW 与 request ref，再解析和发布 identity。
- API transport 成功不等于 RAW、解析或 identity 发布成功；每一阶段必须分别记录安全状态与计数。
- 日志只允许安全代码、run/work-item ID、阶段状态、耗时和聚合计数，不得打印认证材料、RAW 或商品字段值。
- 首次执行完成后必须核对 `total_captured`、`raw_blobs_count`、`request_refs_count`、`sku_identity_active_count`。
- 如 ProductList `total` 与 `sku_identity_active_count` 不一致，必须停止后续真实接口扩展，保留证据并进入人工复核；不得自动调用其他接口补齐。
- 执行结果必须形成脱敏报告；不得包含 RAW payload、SKU code、product name、价格、负责人、图片 URL 或任何可复用凭据。

## 6. 明确禁止

- 禁止真实调用 `batchGetProductInfo`。
- 禁止真实调用任何非 ProductList 的 Lingxing 业务接口。
- 禁止输出或持久化 app secret、access token、refresh token、signature 或 Authorization。
- 禁止打印 RAW payload、完整请求 URL 或商品字段值，包括 SKU code、product name、price、developer、owner、图片 URL。
- 禁止提交 RAW JSON 或 RAW `.tar.gz`。
- 禁止连接或写入旧系统 MySQL。
- 禁止写入旧 `raw_lingxing_api`。
- 禁止修改 frontend、admin-frontend 或 old-system。
- 禁止把 `test`、`staging`、`dev` 或 `prod` 用作本次正式应用数据库名。
- 禁止默认或自动开启定时任务；后续 schedule activation 必须另行获得 Owner 批准。
- 禁止在服务器直接开发、修改或运行未合并代码。
- 禁止扩展到 Product Core、详情同步、DWS 计算、其他 provider、前端页面或旧数据迁移。

## 7. 停止条件

出现以下任一情况必须停止 migration 或同步，且不得通过放宽校验继续：

- 数据库不存在、目标库不是 `szzsbj_app`、数据库归属无法确认或缺少备份/snapshot。
- `DATABASE_URL` 目标不明确、可能指向 MySQL、旧 RAW 库或其他数据库。
- 部署代码不是已合并 `main`，或服务器工作区存在临时修改。
- ProductList interface、retention policy 或 sync config 等前置记录缺失，或需要调用 ProductList 之外的接口，或需要写入授权清单之外的表。
- 需要打印、导出或检查 RAW/商品明细才能继续。
- 发现 credential、Token、signature、Authorization 或完整 URL 进入日志、异常、任务参数或数据库元数据。
- migration 锁、DDL、容量、事务、分页或查询可能影响正式服务且风险无法评估。
- ProductList provider total、捕获计数、RAW/request-ref 数量或 active identity 计数无法解释。
- 重试、分页、限流或幂等行为与批准契约不一致。

## 8. 下一阶段实现任务

建议分支：`feat/production-lingxing-productlist-sync`

只允许实现：

1. 服务器正式 ProductList Token 请求。
2. 服务器正式 ProductList 分页请求。
3. ProductList RAW 入库。
4. ProductList request metadata 入库。
5. ProductList SKU ID 解析入库。
6. governance sync run / work item 记录。
7. 脱敏日志。
8. 手动触发入口。
9. 后端测试。
10. 正式服务器执行说明。

实现 PR 不得自行执行服务器代码。PR Review 并合并后，才可从合并后的 `main` 部署，并依据本决定进行第一次 manual trigger。真实执行后的脱敏结果由后续 docs-only reconciliation 记录；无需借结果记录扩大本决定范围。

## 9. 回滚与事故边界

- 首选回滚是保持 `schedule_enabled=false`、关闭 ProductList outbound、停止新 run，并保留已有 run、work item、RAW 和 lineage 证据。
- 不得通过删除 RAW、run 或审计记录掩盖失败。
- 数据库 downgrade、删除表、清空数据或重新执行 migration 均不由本决定自动授权。
- secret 暴露时停止调用，不回显值，由 Owner 轮换 credential 并评估日志、数据库和 Git 历史。
- 恢复执行前必须说明根因、修复 PR、受影响 run、计数核对和 Owner 决定。

## 10. Owner approval record

Project Owner 于 2026-09-13 批准本文件所列 ProductList-only 实现、`szzsbj_app` migration 和第一次 manual server execution。该批准不包括 `batchGetProductInfo`、其他 Lingxing 接口、自动调度、前端、旧系统、旧 MySQL、旧 `raw_lingxing_api` 或 RAW 文件入 Git。
