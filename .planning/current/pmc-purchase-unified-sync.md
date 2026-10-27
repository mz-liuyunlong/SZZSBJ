# 采购看板统一同步执行计划

Worktree: C:/Users/treas/Desktop/work/SZZSBJ；branch: develop；base: 99a25c93c211cbe5fd3b7be9bfde472791abde7a。
起始状态只有本任务 PRP 未跟踪。用户明确要求当前分支开发，不建分支。
Scope: integration_sync 采购专用编排、现有任务页面采购入口、测试、相关文档。
禁止真实数据库/领星访问、生产配置修改和 Git 提交推送。

## 后端模块设计方案
- API Route / Pydantic Schema：复用既有 run/config/retry/work-items 接口和 schema。
- Service：采购专用父任务，串行来源采集和 DWD/DWS 发布。
- Repository：采购水位、子运行、注册及 PostgreSQL advisory lock 持久化边界。
- Model / Migration：复用既有治理模型，不增加表；独立受控 bootstrap 注册内部任务，默认关闭。不修改原 bootstrap 行为。
- Integration：复用三个原采集器，内部父运行校验；保留原环境及 outbound 门禁。
- Celery Task：现有 execute_sync_run 路由到采购 runner；仅采购分支变化。
- 权限与操作日志：复用 API 权限和 source_account scope、运行及 work item 日志。
- 测试：隔离 mock/synthetic，包含现有其他任务回归。

## 组件拆分方案
- 页面职责：继续组合现有组件，加入 3h 频率映射。
- 页面专属组件：复用 SyncTaskConfigDrawer / SyncTaskLogDrawer / SyncTaskTable。
- 可复用组件：PageShell、Ant Design Select/Table 均已有，不新增 Shared 业务组件。
- Hooks：沿用 integrationSyncTaskQueries。
- API 封装：integrationSyncTaskApi 仅按账号折叠采购内部行，保留历史日志。
- 类型文件：既有 syncTaskTypes；阶段信息放已有 requestSafeParams。
- 不建议封装的内容：三小时选项，无需另建配置框架。
- 风险点：旧独立调度重复执行；父任务成功必须在 DWS commit 后；锁跨阶段 commit。

## 计划 / 进展
- [x] 用户确认 PRP 与当前分支例外。
- [x] 官方文档核对 Celery 5.6 UTC cron、SQLAlchemy 2.0 connection/session、PostgreSQL session advisory lock。
- [ ] 后端统一编排、注册与保护。
- [ ] 前端入口、三小时配置和阶段日志。
- [ ] 隔离测试、文档及 handoff。

无子代理。官方 PostgreSQL 文档为当前 18 版；实际生产版本未探测。锁用法为稳定 API。未更改依赖。

## 验收进展

用户再次确认继续且保留其他会话的采购/国内仓改动。统一编排、3h入口、阶段日志、帮助/API说明已完成。前端28测试、TypeScript/ESLint/生产构建通过；Edge模拟E2E通过并已检查截图。最终后端回归与scope检查收尾；真实PG锁竞争/外呼/数据库注册未执行。
