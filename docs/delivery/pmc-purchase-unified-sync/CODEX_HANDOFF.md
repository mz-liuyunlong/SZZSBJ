# PMC-PURCHASE-UNIFIED-SYNC 交接

## 本地初始化补充

负责人随后确认截图对应本地开发环境，并继续授权处理入口不可见问题。已通过严格环境检查，仅连接 `127.0.0.1:55432/<project>_dev`，登记统一任务，验证默认 cron 为 `0 */3 * * *`、任务和自动调度均关闭，原三个来源配置保留。写入前配置快照保存在本地 `.planning/current/pmc-purchase-local-config-before.json`，执行脚本为同目录 `register-local-purchase-sync.py`。未调用领星、未修改环境文件或生产数据。用户当前浏览器显示尚待刷新确认；下文“未执行bootstrap/未连接真实数据库”描述的是开发验证结束时状态，本次本地登记已补齐该步骤，生产仍未执行。

日期2026-10-27。主执行角色后端工程师。Worktree为当前项目目录，branch develop，base `99a25c93c211cbe5fd3b7be9bfde472791abde7a`。负责人明确要求当前分支开发、不新建分支，并明确要求保留其他会话的采购/国内仓改动。未暂存、提交、推送或创建PR。

## Implemented

- 保留三个来源采集器、数据及历史，新增业务级 `pmcPurchaseBoardSync` 父任务，单账号单配置。
- 手动、每三小时定时和失败重试共用计划/订单/收货/DWD/DWS流程；仅整链成功推进日期水位。
- 采购专用跨提交连接锁、内部子任务防重复派发、失败窗口重试、无新增数据仍重算；旧子任务配置/手动/重试在接管后受保护。
- 锁冲突退至恢复队列后部，避免阻塞其他任务。调度巡检在取得采购锁后恢复中断父/子运行，手动任务无需等待新自动运行。采购恢复失败仅记录安全警告，不阻断其他任务巡检。
- 页面按账号合并为一个入口；默认3h频率、阶段日志、来源历史可追溯、SOP帮助及数据中心API说明。
- 独立bootstrap只登记治理数据，默认不启用任务或定时；不新增表或迁移，不改原三接口bootstrap。

## Files changed / Scope

后端：`backend/app/modules/integration_sync/pmc_purchase_pipeline*.py`；existing `execution.py`、`service.py`、`scheduler.py`、`repository.py`及采购handler的采购专用分支；`backend/scripts/bootstrap_pmc_purchase_pipeline.py`；新pipeline测试。

前端：任务页面、配置/日志组件、API适配/类型、采购测试、E2E；新增采购API文档目录项；仅任务中心help metadata及静态SOP。国内仓既有同步API测试仅补齐mock响应信封，未改其断言或业务逻辑。

文档：PRP、本交接、采购同步API/SOP、任务与数据接口登记、API索引。`.planning/current/pmc-purchase-*`为本地计划、隔离浏览器配置/缓存/截图，不应提交。

其他会话的pmc_purchase业务计算/ItemID归属、pmc_domestic及采购页面改动均保留，本任务未修改这些实现。它们的DWD/DWS测试包含在兼容回归中。

## Validation

最终验证：后端160项通过；前端10文件28项通过；Playwright 1项完整流程通过；Ruff、Mypy、ESLint、TypeScript和构建通过。执行记录：

- 使用 `backend/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --tb=short`；目标integration_sync的pipeline、原采购handler/parser/bootstrap/runner、产品列表/详情重试、通用scheduler、国内仓schedule及采购publisher/refresher测试。来源使用synthetic/mock和内存SQLite。
- Ruff check/format --check：只针对本任务10个后端文件。
- Mypy：`--config-file backend/pyproject.toml --follow-imports=silent`，采购pipeline/repository及修改的执行、服务、调度、handler。
- 前端使用现有Node运行：`vitest run src/pages/data-center src/config --maxWorkers=1 --pool=threads`，10文件28测试通过；目标ESLint通过；`tsc -b --pretty false`及`vite build`通过。
- Playwright Edge：`e2e/pmc-purchase-sync.spec.ts`通过。覆盖单入口、其他任务仍在、三小时保存、手动运行、失败阶段日志、静态SOP。所有API被拦截，无数据库/外呼。已检查列表及失败日志截图。
- 初次浏览器验收受本机npm PATH和Vite缓存EPERM影响；改为本地独立端口/缓存、现有Node并经授权在沙箱外验收。曾修复测试拦截误匹配Vite源码路径，不删断言或扩大超时。环境有NO_COLOR与临时Vite配置加载提示，不影响通过。
- 初始TypeScript发现原国内仓同步测试mock缺少success/error/meta/request_id；已补齐信封，原测试继续通过。

## Explicitly not implemented / Risks

未部署、未开启真实同步、未执行bootstrap、未连接真实数据库或领星；未修改.env、密钥、权限模型、生产配置或旧系统。生产PostgreSQL真实锁竞争/断线场景未实测，当前锁语义有mock验证，治理持久化用内存SQLite验证，不能等同生产验收。

三个来源的外呼授权仍必须按现有机制配置。父配置尚未登记到真实数据库，因此现有页面在注册前仍显示原三个任务。生产数据需现有迁移和规则/主数据完备；缺少主数据不会由本任务自动跨模块同步。

DWD/DWS分别提交；来源成功不等于看板已更新。失败后可完整窗口重跑；不声称仅重试最后一步或新增自动间隔重试。现有列表100条分页限制保留，更早历史使用既有过滤接口。

## Rollback / Next recommended task

负责人审批真实目标环境后，按 `docs/api/pmc-purchase-unified-sync.md` 做治理配置备份、受控注册、一次手动整链验收，再开启三小时。生产部署、数据写入与服务操作另行授权。

回滚先关闭父调度并等待无活动任务，再回退本任务代码；保留历史，不恢复旧子任务定时。其他会话改动不可一起回退。没有新分支/worktree需要清理。
