# 采购看板统一同步契约

2026-10-27；PRP：`PRPs/pmc-purchase-unified-sync.md`。实现复用原同步 API，不增加路由、权限或数据库结构。

## 任务与数据来源

业务任务标识 `pmcPurchaseBoardSync`，handler `pmc.purchase_board.pipeline.v1`。登记中的 `/internal/pmc-purchase-board-sync` 是内部编排标识，不是领星 URL，也不接受 HTTP 请求。

数据源决策：`docs/data-sources/decisions/pmc-purchase-board-decision.md`，READY_FOR_PRP / REBUILD_SYNC。采购计划、采购单、收货单 → RAW/ODS → DWD → DWS；店铺、Listing、产品资料及采购规则继续复用已有来源。各采集器、原表、历史记录均保留。

## 现有接口的采购用途

| Method / Path | Body / Query | Permission | 结果 |
|---|---|---|---|
| GET `/api/integrations/sync-configs` | `interface_key=pmcPurchaseBoardSync`；page/page_size | `integrations:read` | 当前账号可见配置 |
| PATCH `/api/integrations/sync-configs/{id}` | `is_enabled`、`schedule_enabled`、`schedule_cron`；三小时为 `0 */3 * * *` | `integrations:update` | 配置及下一次 UTC 运行时间 |
| POST `/api/integrations/sync-configs/{id}/run` | `reason` 必填，`idempotency_key` 可选 | `integrations:execute` | 202；`run_id`、`status=queued`、`trigger_type=manual` |
| POST `/api/integrations/sync-runs/{id}/retry` | 同上 | `integrations:execute` | 202；新父运行，保留失败窗口及 retry_of_run_id |
| GET `/api/integrations/sync-runs/{id}/work-items` | page/page_size | `integrations:read` | 阶段状态、错误与安全参数 |

统一响应 `{ success, data, error, meta, request_id }`；Config、Run、WorkItem 继续使用原 Pydantic response_model。身份认证失败401，权限不足403，资源不在可信 source-account 范围404，配置/状态冲突409，参数错误422，队列不可用503。前端确认弹窗不替代后端权限。

页面保存和触发使用原审计/入队机制，Celery 的 execute_sync_run 分派到采购专用编排。每个账号一套配置；按账号折叠三个子入口，其他账号未注册时保留原入口。子运行日志归入对应账号的父任务，但明确显示“完整流程”或来源阶段，子步骤成功不能代表整体成功。

## 执行语义

默认每三小时整点（UTC），Asia/Taipei 显示为02/05/08/11/14/17/20/23点。保存关闭自动同步后仍可手动运行。首次注册配置禁用，不自动授权真实采集。

手动/定时/重试均执行计划 → 采购单 → 收货单 → DWD 发布 → DWS 刷新。无来源变化仍重算。第一次从2026-08-01开始分段，每段包含首尾且不超过90天；以后从上次整链成功结束日回叠一天。来源窗口按上海日期，字段仍遵循原契约；看板计算日按Asia/Taipei。重试重新执行原窗口，依靠原来源和DWD自然键去重；不承诺只重跑最后失败步骤或自动间隔重试。

仅成功父运行的 window_end 是增量水位。原采集器仍要求生产环境、已授权的外呼/RAW设置及各来源 outbound 开关；内部子配置的启用/定时/page_size/max_pages 由父配置控制。保留各来源 retention policy，且预检三项元数据与保留策略后才采集。

同一数据库上的采购任务使用 PostgreSQL session advisory lock，写入固定在持锁连接，覆盖每个阶段提交。采购内部子运行不能由队列恢复器另行派发。锁冲突保留 queued 并更新排队时间，避免占据通用队列恢复首位；下次 tick 重试。新执行取得锁后将旧 running 父/子标记为 interrupted，可从失败父任务重试。

阶段安全参数：`stage`（purchasePlanList / purchaseOrderList / purchaseReceiptOrderList / publish_dwd / refresh_dws）、`start_date`、`end_date`、采集阶段 `child_run_id`。日期空值用于清洗/刷新阶段；offset_page/ordinal仅复用现有工作项容器，并不表示清洗阶段进行了HTTP分页。

采购专用错误：`SYNC_PURCHASE_USE_UNIFIED_TASK`、`SYNC_PURCHASE_PIPELINE_DISABLED`、`SYNC_PURCHASE_SOURCE_DISABLED`、`SYNC_PURCHASE_SOURCE_CONTRACT_INVALID`、`SYNC_PURCHASE_WINDOW_INVALID`、`SYNC_PURCHASE_SOURCE_FAILED`、`SYNC_PURCHASE_STAGE_FAILED`、`SYNC_PURCHASE_PIPELINE_FAILED`、`SYNC_PURCHASE_INTERRUPTED`。不向页面输出底层异常、密钥或原始响应。

## 事务、审计与限制

调度巡检取得采购专用锁后恢复中断父子运行，即使自动同步关闭，手动任务也能恢复为可重试的失败状态。采购恢复异常只记录安全警告，不阻断其他业务巡检。

每个采集分页保留原RAW、质量与血缘。父子运行和阶段状态存入原治理表。DWD与DWS分别提交，并非整个链路一笔事务；DWS失败由原刷新器回滚、保留已发布看板。DWS成功后若最终状态持久化失败，下一轮仍会重算，不能把阶段成功时间当采集时间。

本次不自动刷新店铺、Listing或产品资料；这些维表时效仍受各自任务控制。前端治理列表沿用100条分页上限，更早历史需使用带过滤的既有运行查询接口。上线验收需检查来源时间和维表时效，不能只看任务结束时间。

## 注册、上线与回滚

受控注册脚本：`backend/scripts/bootstrap_pmc_purchase_pipeline.py`。使用明确的 `PMC_PURCHASE_PIPELINE_BOOTSTRAP_AUTHORIZED=true` 和 `PMC_PURCHASE_SOURCE_ACCOUNT_REF` 环境注入，禁止修改真实.env。它要求三项来源治理记录已存在、无采购 queued/running，幂等增加父接口/配置并关闭该账号三项独立调度；不改来源外呼授权，不调用领星。父接口内部派发标记为true，但新配置 is_enabled/schedule_enabled=false。无Alembic结构变更。

生产执行需另行授权：备份采购治理配置；检查既有Alembic版本（含采购 draft_no 字段）、业务规则及主数据、Redis/worker/beat和领星外呼配置；注册后先手动跑通及核验，再开启三小时调度。当前开发未执行该脚本、未操作真实数据库。

回滚先停父调度、确认无活动采购任务，再回退本次代码；保留父/子历史，父配置保持禁用，不能误恢复旧子任务自动调度（旧执行器仅手动）。需要手动采集或重算时走原受控操作流程。任何真实数据恢复另行审批。

## 文档核对

查阅 Celery 5.6 官方 periodic tasks（UTC cron、调度重叠）、SQLAlchemy 2.0 connections（显式连接绑定及提交）、PostgreSQL advisory locks（session锁跨事务并需显式释放）。项目依赖范围见backend/pyproject.toml；生产数据库版本和配置未探测。无依赖新增或升级。
